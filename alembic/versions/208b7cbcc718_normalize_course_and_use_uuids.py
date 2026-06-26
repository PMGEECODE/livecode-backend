"""Normalize course and use UUIDs

Revision ID: 208b7cbcc718
Revises: 41de5c1dd901
Create Date: 2026-05-16 20:15:34.238103

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '208b7cbcc718'
down_revision: Union[str, Sequence[str], None] = '41de5c1dd901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # pgcrypto extension intentionally omitted: all UUID generation is handled
    # in Python via uuid.uuid4 (see model definitions). No server-side
    # gen_random_uuid() is required, and pgcrypto is not available on all hosts.

    # 1. Drop Foreign Keys and Indexes
    try:
        op.execute('ALTER TABLE "schedule" DROP CONSTRAINT IF EXISTS "schedule_course_id_fkey"')
    except Exception:
        pass

    try:
        op.drop_index(op.f('ix_blogpost_id'), table_name='blogpost')
        op.drop_index(op.f('ix_course_id'), table_name='course')
        op.drop_index(op.f('ix_schedule_id'), table_name='schedule')
        op.drop_index(op.f('ix_service_id'), table_name='service')
        op.drop_index(op.f('ix_user_id'), table_name='user')
    except Exception:
        pass

    # 2. Convert IDs to UUID for each table.
    # After conversion, DROP DEFAULT — Python (uuid.uuid4) is the sole UUID
    # source; no database-level default is needed or desired.
    tables = ['user', 'blogpost', 'course', 'service', 'schedule']
    for table in tables:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN id DROP DEFAULT')
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN id TYPE UUID USING (LPAD(to_hex(id), 32, \'0\')::uuid)')
        # Leave no server default — Python generates UUIDs before INSERT.

    # Special handling for Schedule foreign key type
    op.execute('ALTER TABLE "schedule" ALTER COLUMN course_id TYPE UUID USING (LPAD(to_hex(course_id), 32, \'0\')::uuid)')

    # 3. Create normalized tables.
    # No server_default: Python supplies the UUID at INSERT time via uuid.uuid4.
    op.create_table('course_block',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('course_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['course.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('course_logistics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('course_id', sa.UUID(), nullable=False),
        sa.Column('duration', sa.String(), nullable=True),
        sa.Column('start_date', sa.String(), nullable=True),
        sa.Column('end_date', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('price_kes', sa.Float(), nullable=True),
        sa.Column('price_usd', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['course_id'], ['course.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('course_id')
    )

    # 4. Recreate Schedule Foreign Key
    op.create_foreign_key('schedule_course_id_fkey', 'schedule', 'course', ['course_id'], ['id'])

    # 5. Clean up legacy course columns
    op.drop_column('course', 'curriculum')
    op.drop_column('course', 'start_date')
    op.drop_column('course', 'duration')
    op.drop_column('course', 'price_kes')
    op.drop_column('course', 'end_date')
    op.drop_column('course', 'location')
    op.drop_column('course', 'price_usd')

def downgrade() -> None:
    pass
