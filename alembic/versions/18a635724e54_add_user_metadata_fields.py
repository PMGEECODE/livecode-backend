"""add_user_metadata_fields

Revision ID: 18a635724e54
Revises: eb603d5337d9
Create Date: 2026-05-27 23:45:08.712105

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18a635724e54'
down_revision: Union[str, Sequence[str], None] = 'eb603d5337d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "username" VARCHAR(255)')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "first_name" VARCHAR(255)')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "last_name" VARCHAR(255)')
    op.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS \"role\" VARCHAR(50) DEFAULT 'user'")
    op.execute("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS \"status\" VARCHAR(50) DEFAULT 'active'")
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "phone" VARCHAR(50)')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "bio" TEXT')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "avatar_url" VARCHAR(1024)')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "is_verified" BOOLEAN DEFAULT FALSE')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    op.execute('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS "last_login" TIMESTAMP')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "username"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "first_name"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "last_name"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "role"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "status"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "phone"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "bio"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "avatar_url"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "is_verified"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "created_at"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "updated_at"')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS "last_login"')

