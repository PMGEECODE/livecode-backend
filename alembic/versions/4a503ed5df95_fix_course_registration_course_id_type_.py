"""Fix course_registration course_id type and foreign key

Revision ID: 4a503ed5df95
Revises: 87a5f1a502e5
Create Date: 2026-05-18 22:48:18.871696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a503ed5df95'
down_revision: Union[str, Sequence[str], None] = '87a5f1a502e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if table exists
    table_exists = conn.execute(sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'course_registration')")).scalar()
    if not table_exists:
        return

    # Check column types
    res_id = conn.execute(sa.text("SELECT data_type FROM information_schema.columns WHERE table_name = 'course_registration' AND column_name = 'id'")).scalar()
    res_cid = conn.execute(sa.text("SELECT data_type FROM information_schema.columns WHERE table_name = 'course_registration' AND column_name = 'course_id'")).scalar()

    if res_id == 'uuid' and res_cid == 'uuid':
        return # Already correct

    # Safe drops using IF EXISTS
    op.execute('ALTER TABLE "course_registration" DROP CONSTRAINT IF EXISTS "course_registration_course_id_fkey"')
    op.execute('DROP INDEX IF EXISTS "ix_course_registration_course_id"')
    op.execute('DROP INDEX IF EXISTS "ix_course_registration_email"')
    op.execute('DROP INDEX IF EXISTS "ix_course_registration_id"')

    # Handle id conversion
    if res_id in ('integer', 'bigint', 'character varying', 'text'):
        op.execute('ALTER TABLE "course_registration" ALTER COLUMN id DROP DEFAULT')
        if res_id in ('integer', 'bigint'):
            op.execute('ALTER TABLE "course_registration" ALTER COLUMN id TYPE UUID USING (LPAD(to_hex(id), 32, \'0\')::uuid)')
        else:
            op.execute('ALTER TABLE "course_registration" ALTER COLUMN id TYPE UUID USING id::uuid')
        op.execute('ALTER TABLE "course_registration" ALTER COLUMN id SET DEFAULT gen_random_uuid()')

    # Handle course_id conversion
    if res_cid in ('integer', 'bigint', 'character varying', 'text'):
        if res_cid in ('integer', 'bigint'):
            op.execute('ALTER TABLE "course_registration" ALTER COLUMN course_id TYPE UUID USING (LPAD(to_hex(course_id), 32, \'0\')::uuid)')
        else:
            op.execute('ALTER TABLE "course_registration" ALTER COLUMN course_id TYPE UUID USING course_id::uuid')

    # Re-create FK and indexes
    op.create_foreign_key('course_registration_course_id_fkey', 'course_registration', 'course', ['course_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_course_registration_course_id'), 'course_registration', ['course_id'], unique=False)
    op.create_index(op.f('ix_course_registration_email'), 'course_registration', ['email'], unique=False)
    op.create_index(op.f('ix_course_registration_id'), 'course_registration', ['id'], unique=False)


def downgrade() -> None:
    pass
