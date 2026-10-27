"""Explicit schema upgrade entry point; web replicas can run in check-only mode."""
from pathlib import Path
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect, text
from app.database import engine
HEAD='0003_block_refresh_jobs'


def upgrade(bind=engine):
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    with bind.begin() as connection:
        if bind.dialect.name=='postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(68743101)'))
        config.attributes['connection']=connection
        command.upgrade(config,'head')
    check(bind)
    from app.migrations import migrate
    migrate(bind)


def check(bind=engine):
    with bind.connect() as conn:
        if not inspect(conn).has_table('alembic_version') or conn.execute(text('SELECT version_num FROM alembic_version')).scalar()!=HEAD:
            raise RuntimeError('Schema upgrade required: python -m app.schema')
        import json
        manifest=json.loads((Path(__file__).resolve().parents[1]/'migrations/schema_v1.json').read_text())
        for name,column in [('users','day_time_budgets'),('coaching_attempts','latency_ms')]:
            if column not in {c['name'] for c in inspect(conn).get_columns(name)}:
                raise RuntimeError('Schema drift detected in the schedule/analysis upgrade.')
        for table in manifest:
            if not inspect(conn).has_table(table['name']) or not {c['name'] for c in table['columns']} <= {c['name'] for c in inspect(conn).get_columns(table['name'])}:
                raise RuntimeError('Schema drift detected; restore a verified snapshot or apply an explicit repair migration.')


if __name__=='__main__':
    import app.models  # noqa: F401
    upgrade()
