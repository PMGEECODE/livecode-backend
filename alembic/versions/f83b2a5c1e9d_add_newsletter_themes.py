"""add newsletter themes table

Revision ID: f83b2a5c1e9d
Revises: f5647bd57321
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f83b2a5c1e9d'
down_revision: Union[str, None] = 'f5647bd57321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = postgresql.UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(length=36)

    op.create_table(
        'newsletter_themes',
        sa.Column('id', uuid_type, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('primary_color', sa.String(length=7), nullable=False),
        sa.Column('secondary_color', sa.String(length=7), nullable=False),
        sa.Column('bg_color', sa.String(length=7), nullable=False),
        sa.Column('card_bg', sa.String(length=7), nullable=False),
        sa.Column('text_color', sa.String(length=7), nullable=False),
        sa.Column('heading_color', sa.String(length=7), nullable=False),
        sa.Column('font_family', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_newsletter_themes_is_active', 'newsletter_themes', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_newsletter_themes_is_active', table_name='newsletter_themes')
    op.drop_table('newsletter_themes')
