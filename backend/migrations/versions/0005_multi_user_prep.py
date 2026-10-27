"""Multi-user prep (docs/multi-user-design.md): terms acceptance, roles, device attribution, AI cost.

Also records AI consent for the owner (owner mode never asked for it, and the owner's reviews run on
their own key): consent is now required in every mode. Invited athletes keep exactly the choice they made.
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
    from app.config import settings
    # Only the owner, only if they have no account yet (owner mode) or an owner account, and only
    # when they have actually used AI reviews under owner mode.
    op.execute(sa.text(
        "UPDATE users SET ai_consent = true WHERE id = :owner AND (ai_consent IS NULL OR ai_consent = false) "
        "AND id IN (SELECT user_id FROM coaching_reviews WHERE model IS NOT NULL) "
        "AND id NOT IN (SELECT user_id FROM accounts WHERE role IS NULL OR role != 'owner')"
    ).bindparams(owner=settings.default_user_id))


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
