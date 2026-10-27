"""Frozen beta schema; adopt additive owner databases without rebuilding their rows."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa
revision='0001_invite_beta'
down_revision=None
branch_labels=None
depends_on=None


def _type(c):
    return {'INTEGER':sa.Integer,'FLOAT':sa.Float,'BOOLEAN':sa.Boolean,'DATETIME':sa.DateTime,
            'BLOB':sa.LargeBinary,'TEXT':sa.Text}.get(c['type'],lambda:sa.String(c.get('length')))()


def upgrade():
    manifest=json.loads((Path(__file__).parents[1]/'schema_v1.json').read_text())
    bind=op.get_bind()
    for table in manifest:
        inspector=sa.inspect(bind)
        existing={c['name'] for c in inspector.get_columns(table['name'])} if inspector.has_table(table['name']) else None
        columns=[sa.Column(c['name'],_type(c),primary_key=c['pk'],nullable=c['nullable']) for c in table['columns']]
        if existing is None:
            constraints=[sa.ForeignKeyConstraint(f['columns'],f['targets'],ondelete=f['ondelete']) for f in table['foreign_keys']]
            constraints += [sa.UniqueConstraint(*u) for u in table['unique']]
            op.create_table(table['name'],*columns,*constraints)
        else:
            for column in columns:
                if column.name not in existing:
                    # Old records cannot satisfy a new required field automatically.
                    # This baseline only introduces optional fields to old tables.
                    column.nullable=True
                    op.add_column(table['name'],column)
        indexes={i['name'] for i in sa.inspect(bind).get_indexes(table['name'])}
        for index in table['indexes']:
            if index['name'] not in indexes:
                op.create_index(index['name'],table['name'],index['columns'],unique=index['unique'])


def downgrade():
    raise RuntimeError('Restore a verified pre-migration backup instead of dropping athlete data.')
