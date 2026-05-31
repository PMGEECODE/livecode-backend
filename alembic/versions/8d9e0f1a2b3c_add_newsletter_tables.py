"""add newsletter tables

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-05-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "8d9e0f1a2b3c"
down_revision = "7c8d9e0f1a2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    uuid_type = postgresql.UUID(as_uuid=True) if bind.dialect.name == "postgresql" else sa.String(length=36)

    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("occupation", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("unsubscribe_token", sa.String(length=80), nullable=False),
        sa.Column("welcome_email_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("unsubscribe_token"),
    )
    op.create_index("ix_newsletter_subscribers_email", "newsletter_subscribers", ["email"])
    op.create_index("ix_newsletter_subscribers_is_active", "newsletter_subscribers", ["is_active"])
    op.create_index("ix_newsletter_subscribers_unsubscribe_token", "newsletter_subscribers", ["unsubscribe_token"])
    op.create_index("ix_newsletter_subscribers_created_at", "newsletter_subscribers", ["created_at"])

    op.create_table(
        "newsletter_deliveries",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("subscriber_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_newsletter_deliveries_subscriber_email", "newsletter_deliveries", ["subscriber_email"])
    op.create_index("ix_newsletter_deliveries_status", "newsletter_deliveries", ["status"])
    op.create_index("ix_newsletter_deliveries_scheduled_at", "newsletter_deliveries", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_newsletter_deliveries_scheduled_at", table_name="newsletter_deliveries")
    op.drop_index("ix_newsletter_deliveries_status", table_name="newsletter_deliveries")
    op.drop_index("ix_newsletter_deliveries_subscriber_email", table_name="newsletter_deliveries")
    op.drop_table("newsletter_deliveries")
    op.drop_index("ix_newsletter_subscribers_created_at", table_name="newsletter_subscribers")
    op.drop_index("ix_newsletter_subscribers_unsubscribe_token", table_name="newsletter_subscribers")
    op.drop_index("ix_newsletter_subscribers_is_active", table_name="newsletter_subscribers")
    op.drop_index("ix_newsletter_subscribers_email", table_name="newsletter_subscribers")
    op.drop_table("newsletter_subscribers")
