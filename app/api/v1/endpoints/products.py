import logging
import uuid
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, Product as ProductSchema
from app.services.s3_storage import _clean_key_part
from app.services.vercel_blob import upload_product_image_blob
from app.core.upload_security import read_upload_file_limited, validate_image_upload
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[ProductSchema])
async def read_products(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Retrieve products."""
    result = await db.execute(select(Product).offset(skip).limit(limit))
    products = result.scalars().all()
    return products

@router.get("/{id}", response_model=ProductSchema)
async def read_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """Get product by ID."""
    result = await db.execute(select(Product).where(Product.id == id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@router.post("/", response_model=ProductSchema)
async def create_product(
    *,
    db: AsyncSession = Depends(deps.get_db),
    product_in: ProductCreate,
    current_user = Depends(deps.check_permission("manage_products")),
) -> Any:
    """Create new product."""
    # Check if slug exists
    result = await db.execute(select(Product).where(Product.slug == product_in.slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Product with this slug already exists.")
    
    product = Product(**product_in.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@router.put("/{id}", response_model=ProductSchema)
async def update_product(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: uuid.UUID,
    product_in: ProductUpdate,
    current_user = Depends(deps.check_permission("manage_products")),
) -> Any:
    """Update a product."""
    result = await db.execute(select(Product).where(Product.id == id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    update_data = product_in.model_dump(exclude_unset=True)
    
    # Check slug conflict if updating slug
    if "slug" in update_data and update_data["slug"] != product.slug:
        slug_check = await db.execute(select(Product).where(Product.slug == update_data["slug"]))
        if slug_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Product with this slug already exists.")
            
    for field, value in update_data.items():
        setattr(product, field, value)
        
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@router.delete("/{id}", response_model=dict)
async def delete_product(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: uuid.UUID,
    current_user = Depends(deps.check_permission("manage_products")),
) -> Any:
    """Delete a product."""
    result = await db.execute(select(Product).where(Product.id == id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    await db.delete(product)
    await db.commit()
    return {"detail": "Product deleted successfully"}

@router.post("/upload-image", response_model=dict)
async def upload_product_image(
    file: UploadFile = File(...),
    current_user = Depends(deps.check_permission("manage_products")),
) -> Any:
    """
    Upload a product image to Vercel Blob.
    Returns the public URL of the uploaded image.
    """
    logger.info(
        "Product image upload request received: filename=%s, content_type=%s",
        file.filename,
        file.content_type,
    )
    try:
        data = await read_upload_file_limited(file, settings.IMAGE_UPLOAD_MAX_BYTES)
        ext = validate_image_upload(file, data)
    except HTTPException as e:
        logger.error(
            "Product image validation failed: status_code=%d, detail=%s",
            e.status_code,
            e.detail,
        )
        raise e
    except Exception as e:
        logger.exception("Unexpected error during product image validation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during image validation.",
        )
    
    import os
    import time
    
    safe_name = _clean_key_part(os.path.splitext(file.filename or "image")[0][:50])
    filename = f"{safe_name}_{int(time.time())}.{ext}"
    
    blob_key = f"products/{filename}"
    
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    actual_content_type = mime_types.get(ext, file.content_type or "application/octet-stream")
    
    try:
        public_url = await upload_product_image_blob(
            pathname=blob_key,
            data=data,
            content_type=actual_content_type,
        )
    except HTTPException as e:
        logger.error(
            "Vercel Blob upload failed: status_code=%d, detail=%s",
            e.status_code,
            e.detail,
        )
        raise e
    except Exception as e:
        logger.exception("Unexpected error during Vercel Blob upload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while saving the image.",
        )
    
    logger.info("Product image uploaded successfully: url=%s", public_url)
    return {"url": public_url}
