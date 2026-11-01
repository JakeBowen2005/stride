"""Account appearance and independently scoped plan previews."""
from alembic import op
import sqlalchemy as sa

revision = '0006_next_block_preview'
down_revision = '0005_multi_user_prep'
branch_labels = None
depends_on = None


def upgrade():
    for table, column in [('users', sa.Column('theme', sa.String(10), nullable=True)),
                          ('plans', sa.Column('preview_scope', sa.String(10), nullable=True))]:
        if column.name not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, column)


def downgrade():
    raise RuntimeError('Restore a verified snapshot to roll back schema changes.')
