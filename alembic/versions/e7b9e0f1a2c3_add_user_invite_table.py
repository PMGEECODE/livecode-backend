"""add userinvite table

Revision ID: e7b9e0f1a2c3
Revises: b5d84bf409ac
Create Date: 2026-06-23 03:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7b9e0f1a2c3'
down_revision: Union[str, Sequence[str], None] = 'b5d84bf409ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'userinvite',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_userinvite_email'), 'userinvite', ['email'], unique=True)
    op.create_index(op.f('ix_userinvite_token'), 'userinvite', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_userinvite_token'), table_name='userinvite')
    op.drop_index(op.f('ix_userinvite_email'), table_name='userinvite')
    op.drop_table('userinvite')
