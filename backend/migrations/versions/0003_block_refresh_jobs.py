"""Coaching jobs that refresh a plan's coach perspective after a run syncs."""
from alembic import op
import sqlalchemy as sa
revision='0003_block_refresh_jobs'
down_revision='0002_schedule_minutes'
branch_labels=None
depends_on=None


def upgrade():
    if 'plan_id' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('coaching_jobs')}:
        op.add_column('coaching_jobs',sa.Column('plan_id',sa.Integer(),nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
