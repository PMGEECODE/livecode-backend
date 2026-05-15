from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas
from app.api import deps

router = APIRouter()

@router.get("/", response_model=List[schemas.BlogPost])
async def read_blog_posts(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve blog posts.
    """
    posts = await crud.blog_post.get_multi(db, skip=skip, limit=limit)
    return posts

@router.post("/", response_model=schemas.BlogPost)
async def create_blog_post(
    *,
    db: AsyncSession = Depends(deps.get_db),
    post_in: schemas.BlogPostCreate,
) -> Any:
    """
    Create new blog post.
    """
    post = await crud.blog_post.get_by_slug(db, slug=post_in.slug)
    if post:
        raise HTTPException(
            status_code=400,
            detail="The blog post with this slug already exists in the system.",
        )
    return await crud.blog_post.create(db, obj_in=post_in)

@router.get("/{slug}", response_model=schemas.BlogPost)
async def read_blog_post_by_slug(
    slug: str,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Get a specific blog post by slug.
    """
    post = await crud.blog_post.get_by_slug(db, slug=slug)
    if not post:
        raise HTTPException(
            status_code=404,
            detail="Blog post not found",
        )
    return post
