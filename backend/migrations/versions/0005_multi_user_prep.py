"""Multi-user prep (docs/multi-user-design.md): terms acceptance, roles, device attribution, AI cost.

Also records AI consent for an athlete who has already been using AI reviews: consent is now
required in every mode, and existing use under the operator's own key is that consent.
"""
from alembic import op
import sqlalchemy as sa
revision='0005_multi_user_prep'
down_revision='0004_plan_change_requests'
branch_labels=None
depends_on=None


def _add(table, column):
    if column.name not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}:
        op.add_column(table, column)


def upgrade():
    _add('accounts', sa.Column('role', sa.String(20), nullable=True))
    _add('accounts', sa.Column('created_at', sa.DateTime(), nullable=True))
    _add('accounts', sa.Column('terms_accepted_at', sa.DateTime(), nullable=True))
    _add('accounts', sa.Column('terms_version', sa.String(20), nullable=True))
    _add('activities', sa.Column('device_name', sa.String(100), nullable=True))
    _add('coaching_attempts', sa.Column('cost_usd', sa.Float(), nullable=True))
    op.execute("UPDATE users SET ai_consent = true WHERE (ai_consent IS NULL OR ai_consent = false) AND id IN "
               "(SELECT user_id FROM coaching_reviews WHERE model IS NOT NULL)")


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
