"""add paystack payment metadata

Revision ID: b4a2f6c8d901
Revises: 8d9e0f1a2b3c
Create Date: 2026-05-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4a2f6c8d901"
down_revision: Union[str, Sequence[str], None] = "8d9e0f1a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_transaction", sa.Column("provider", sa.String(), nullable=False, server_default="mpesa"))
    op.add_column("payment_transaction", sa.Column("provider_reference", sa.String(), nullable=True))
    op.add_column("payment_transaction", sa.Column("currency", sa.String(), nullable=True))
    op.add_column("payment_transaction", sa.Column("authorization_url", sa.Text(), nullable=True))
    op.add_column("payment_transaction", sa.Column("access_code", sa.String(), nullable=True))
    op.add_column("payment_transaction", sa.Column("gateway_response", sa.Text(), nullable=True))
    op.add_column("payment_transaction", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("payment_transaction", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_payment_transaction_provider", "payment_transaction", ["provider"])
    op.create_index("ix_payment_transaction_provider_reference", "payment_transaction", ["provider_reference"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payment_transaction_provider_reference", table_name="payment_transaction")
    op.drop_index("ix_payment_transaction_provider", table_name="payment_transaction")
    op.drop_column("payment_transaction", "paid_at")
    op.drop_column("payment_transaction", "metadata_json")
    op.drop_column("payment_transaction", "gateway_response")
    op.drop_column("payment_transaction", "access_code")
    op.drop_column("payment_transaction", "authorization_url")
    op.drop_column("payment_transaction", "currency")
    op.drop_column("payment_transaction", "provider_reference")
    op.drop_column("payment_transaction", "provider")
