"""Add trusted_partner table

Revision ID: a1b2c3d4e5f6
Revises: 18a635724e54
Create Date: 2026-05-28 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '18a635724e54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the trusted_partner table."""
    op.create_table(
        'trustedpartner',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('logo_url', sa.String(), nullable=False),
        sa.Column('website_url', sa.String(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trustedpartner_name'), 'trustedpartner', ['name'], unique=False)
    op.create_index(op.f('ix_trustedpartner_is_active'), 'trustedpartner', ['is_active'], unique=False)
    op.create_index(op.f('ix_trustedpartner_display_order'), 'trustedpartner', ['display_order'], unique=False)


def downgrade() -> None:
    """Drop the trusted_partner table."""
    op.drop_index(op.f('ix_trustedpartner_display_order'), table_name='trustedpartner')
    op.drop_index(op.f('ix_trustedpartner_is_active'), table_name='trustedpartner')
    op.drop_index(op.f('ix_trustedpartner_name'), table_name='trustedpartner')
    op.drop_table('trustedpartner')
