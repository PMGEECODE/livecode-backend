import httpx
from fastapi import HTTPException, status
from app.core.config import settings

async def upload_product_image_blob(
    *,
    pathname: str,
    data: bytes,
    content_type: str,
) -> str:
    """
    Uploads a product image directly to Vercel Blob using HTTP REST API.
    Returns the public URL of the uploaded image.
    """
    token = settings.BLOB_READ_WRITE_TOKEN
    if not token or token.startswith("vercel_blob_rw_d4kZqhoIRR4VC17E_***") or "*" in token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vercel Blob storage is not configured. Please supply a valid BLOB_READ_WRITE_TOKEN in .env.",
        )

    # Vercel Blob REST API PUT URL
    # format: https://blob.vercel-storage.com/{pathname}
    url = f"https://blob.vercel-storage.com/{pathname.lstrip('/')}"

    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-version": "7",
        "x-content-type": content_type,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                url,
                headers=headers,
                content=data,
                timeout=30.0,
            )
            
            if response.status_code not in (200, 201):
                error_detail = response.text
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        error_detail = error_json["error"].get("message", error_detail)
                except ValueError:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to upload to Vercel Blob: {error_detail}",
                )

            res_json = response.json()
            if "url" not in res_json:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid response schema from Vercel Blob API.",
                )
            return res_json["url"]
            
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vercel Blob storage communication error: {str(exc)}",
        )
