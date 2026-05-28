"""create_trainer_applications_table

Revision ID: d0fd51fdf5ad
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 16:15:26.306983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd0fd51fdf5ad'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the trainer_applications table
    op.create_table('trainer_applications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('alternate_phone', sa.String(), nullable=True),
    sa.Column('dob', sa.String(), nullable=False),
    sa.Column('gender', sa.String(), nullable=False),
    sa.Column('country', sa.String(), nullable=False),
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('specialization', sa.Text(), nullable=False),
    sa.Column('other_specialization', sa.Text(), nullable=True),
    sa.Column('cv_url', sa.String(), nullable=False),
    sa.Column('cover_letter_url', sa.String(), nullable=True),
    sa.Column('referee1_name', sa.String(), nullable=True),
    sa.Column('referee1_speciality', sa.String(), nullable=True),
    sa.Column('referee1_phone', sa.String(), nullable=True),
    sa.Column('referee1_email', sa.String(), nullable=True),
    sa.Column('referee2_name', sa.String(), nullable=True),
    sa.Column('referee2_speciality', sa.String(), nullable=True),
    sa.Column('referee2_phone', sa.String(), nullable=True),
    sa.Column('referee2_email', sa.String(), nullable=True),
    sa.Column('referee3_name', sa.String(), nullable=True),
    sa.Column('referee3_speciality', sa.String(), nullable=True),
    sa.Column('referee3_phone', sa.String(), nullable=True),
    sa.Column('referee3_email', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trainer_applications_email'), 'trainer_applications', ['email'], unique=False)
    op.create_index(op.f('ix_trainer_applications_full_name'), 'trainer_applications', ['full_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_trainer_applications_full_name'), table_name='trainer_applications')
    op.drop_index(op.f('ix_trainer_applications_email'), table_name='trainer_applications')
    op.drop_table('trainer_applications')
