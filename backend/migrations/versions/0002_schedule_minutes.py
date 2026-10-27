"""Per-weekday time availability."""
from alembic import op
import sqlalchemy as sa
revision='0002_schedule_minutes'
down_revision='0001_invite_beta'
branch_labels=None
depends_on=None


def upgrade():
    if 'day_time_budgets' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}:
        op.add_column('users',sa.Column('day_time_budgets',sa.Text(),nullable=True))

    if 'latency_ms' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('coaching_attempts')}:
        op.add_column('coaching_attempts',sa.Column('latency_ms',sa.Integer(),nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
