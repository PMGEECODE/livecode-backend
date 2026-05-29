"""add enabled to schedule

Revision ID: f3a9b2c1d8e7
Revises: eb603d5337d9
Create Date: 2026-05-29 14:43:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9b2c1d8e7'
down_revision: Union[str, Sequence[str], None] = 'd0fd51fdf5ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enabled boolean column to schedule table, defaulting all existing rows to True."""
    op.add_column(
        'schedule',
        sa.Column(
            'enabled',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
    )


def downgrade() -> None:
    """Remove enabled column from schedule table."""
    op.drop_column('schedule', 'enabled')
