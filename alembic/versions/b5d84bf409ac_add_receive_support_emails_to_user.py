"""add receive_support_emails to user

Revision ID: b5d84bf409ac
Revises: a7e6b83f9821
Create Date: 2026-06-21 19:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d84bf409ac'
down_revision: Union[str, Sequence[str], None] = 'a7e6b83f9821'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('receive_support_emails', sa.Boolean(), nullable=True, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('user', 'receive_support_emails')
