"""add payment option settings

Revision ID: d5f1c2a3b4e5
Revises: c9e1a4b7d902
Create Date: 2026-06-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5f1c2a3b4e5"
down_revision: Union[str, Sequence[str], None] = "c9e1a4b7d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_option_setting",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("disabled_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.create_index("ix_payment_option_setting_is_enabled", "payment_option_setting", ["is_enabled"])

    payment_options = [
        {
            "provider": "mpesa",
            "label": "M-Pesa STK Push",
            "disabled_message": "M-Pesa payments are temporarily unavailable. Please choose another payment option or contact support.",
        },
        {
            "provider": "paystack",
            "label": "Paystack Cards",
            "disabled_message": "Card payments are temporarily unavailable. Please choose another payment option or contact support.",
        },
        {
            "provider": "paypal",
            "label": "PayPal",
            "disabled_message": "PayPal payments are temporarily unavailable. Please choose another payment option or contact support.",
        },
        {
            "provider": "stripe",
            "label": "Stripe Cards",
            "disabled_message": "Stripe card payments are temporarily unavailable. Please choose another payment option or contact support.",
        },
        {
            "provider": "offline",
            "label": "Offline / Bank Transfer",
            "disabled_message": "Offline payment registration is temporarily unavailable. Please contact support for assistance.",
        },
    ]

    op.bulk_insert(sa.table(
        "payment_option_setting",
        sa.column("provider", sa.String),
        sa.column("label", sa.String),
        sa.column("is_enabled", sa.Boolean),
        sa.column("disabled_message", sa.Text),
    ), [{**option, "is_enabled": True} for option in payment_options])


def downgrade() -> None:
    op.drop_index("ix_payment_option_setting_is_enabled", table_name="payment_option_setting")
    op.drop_table("payment_option_setting")
