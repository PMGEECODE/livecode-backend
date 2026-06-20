"""add template layout to newsletter themes

Revision ID: a7e6b83f9821
Revises: f83b2a5c1e9d
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e6b83f9821'
down_revision: Union[str, None] = 'f83b2a5c1e9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'newsletter_themes',
        sa.Column('template_layout', sa.String(length=50), nullable=False, server_default='classic_card')
    )


def downgrade() -> None:
    op.drop_column('newsletter_themes', 'template_layout')
