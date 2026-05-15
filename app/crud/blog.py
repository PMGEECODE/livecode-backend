from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.db.models.blog import BlogPost
from app.schemas.blog import BlogPostCreate, BlogPostUpdate

class CRUDBlogPost(CRUDBase[BlogPost, BlogPostCreate, BlogPostUpdate]):
    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[BlogPost]:
        result = await db.execute(select(BlogPost).filter(BlogPost.slug == slug))
        return result.scalars().first()

blog_post = CRUDBlogPost(BlogPost)
