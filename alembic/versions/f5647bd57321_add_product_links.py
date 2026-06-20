"""add product links

Revision ID: f5647bd57321
Revises: a1e5282209f2
Create Date: 2026-06-20 02:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f5647bd57321'
down_revision: Union[str, Sequence[str], None] = 'a1e5282209f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('preview_url', sa.String(length=1024), nullable=True))
    op.add_column('products', sa.Column('view_url', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'view_url')
    op.drop_column('products', 'preview_url')
