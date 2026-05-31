"""add product analytics events

Revision ID: 7c8d9e0f1a2b
Revises: f3a9b2c1d8e7
Create Date: 2026-05-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7c8d9e0f1a2b"
down_revision = "f3a9b2c1d8e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()
    uuid_type = postgresql.UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(length=36)

    op.create_table(
        "product_analytics_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_name", sa.String(length=80), nullable=False),
        sa.Column("page_path", sa.String(length=500), nullable=True),
        sa.Column("page_title", sa.String(length=300), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=160), nullable=True),
        sa.Column("entity_title", sa.String(length=300), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column("session_id", sa.String(length=80), nullable=True),
        sa.Column("metadata_json", json_type, nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_analytics_events_event_name", "product_analytics_events", ["event_name"])
    op.create_index("ix_product_analytics_events_page_path", "product_analytics_events", ["page_path"])
    op.create_index("ix_product_analytics_events_entity_type", "product_analytics_events", ["entity_type"])
    op.create_index("ix_product_analytics_events_entity_id", "product_analytics_events", ["entity_id"])
    op.create_index("ix_product_analytics_events_session_id", "product_analytics_events", ["session_id"])
    op.create_index("ix_product_analytics_events_ip_hash", "product_analytics_events", ["ip_hash"])
    op.create_index("ix_product_analytics_events_created_at", "product_analytics_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_product_analytics_events_created_at", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_ip_hash", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_session_id", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_entity_id", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_entity_type", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_page_path", table_name="product_analytics_events")
    op.drop_index("ix_product_analytics_events_event_name", table_name="product_analytics_events")
    op.drop_table("product_analytics_events")
