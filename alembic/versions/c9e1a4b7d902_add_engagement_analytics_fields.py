"""add engagement analytics fields

Revision ID: c9e1a4b7d902
Revises: b4a2f6c8d901
Create Date: 2026-06-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1a4b7d902"
down_revision: Union[str, Sequence[str], None] = "b4a2f6c8d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product_analytics_events", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("product_analytics_events", sa.Column("scroll_depth_percent", sa.Integer(), nullable=True))
    op.add_column("product_analytics_events", sa.Column("interaction_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_analytics_events", "interaction_count")
    op.drop_column("product_analytics_events", "scroll_depth_percent")
    op.drop_column("product_analytics_events", "duration_ms")
