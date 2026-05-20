from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas, models
from app.api import deps
from app.core.limiter import limiter
from app.core.redis import redis_manager

router = APIRouter()

@router.get("/", response_model=List[schemas.BlogPost])
@limiter.limit("60/minute")
async def read_blog_posts(
    request: Request,
    response: Response,
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    new_post = await crud.blog_post.create(db, obj_in=post_in)
    await redis_manager.delete_pattern("dashboard:*")
    return new_post

@router.get("/{slug}", response_model=schemas.BlogPost)
@limiter.limit("60/minute")
async def read_blog_post_by_slug(
    request: Request,
    response: Response,
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
