"""Plain-language plan change requests (docs/plain-language-plan-changes.md)."""
from alembic import op
import sqlalchemy as sa
revision='0004_plan_change_requests'
down_revision='0003_block_refresh_jobs'
branch_labels=None
depends_on=None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('plan_change_requests'):
        return
    op.create_table('plan_change_requests',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('plan_id',sa.Integer(),sa.ForeignKey('plans.id'),nullable=False),
        sa.Column('created_at',sa.DateTime()),
        sa.Column('request_text',sa.Text(),nullable=False),
        sa.Column('thread',sa.Text()),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('source',sa.String(20)),
        sa.Column('safety',sa.String(20)),
        sa.Column('proposal',sa.Text()),
        sa.Column('rejections',sa.Text()),
        sa.Column('before_rows',sa.Text()),
        sa.Column('after_rows',sa.Text()),
        sa.Column('plan_fingerprint',sa.String(64),nullable=False),
        sa.Column('model',sa.String(100)),
        sa.Column('attempts',sa.Integer()),
        sa.Column('input_tokens',sa.Integer()),
        sa.Column('output_tokens',sa.Integer()),
        sa.Column('applied_at',sa.DateTime()),
        sa.Column('undone_at',sa.DateTime()))
    for column in ('user_id','plan_id','created_at'):
        op.create_index(f'ix_plan_change_requests_{column}','plan_change_requests',[column])


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
