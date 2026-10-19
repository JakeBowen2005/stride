"""Exercise additive migrations only against a disposable copy of a legacy DB."""
import shutil
from sqlalchemy import create_engine, inspect, text

from app import database


def test_legacy_database_copy_adds_nullable_contract_columns(tmp_path, monkeypatch):
    source = tmp_path / 'legacy.db'
    old = create_engine(f'sqlite:///{source}')
    with old.begin() as conn:
        conn.execute(text('CREATE TABLE plans (id INTEGER PRIMARY KEY, user_id INTEGER, is_active BOOLEAN)'))
        conn.execute(text('INSERT INTO plans VALUES (1, 1, 1)'))
        conn.execute(text('CREATE TABLE planned_workouts (id INTEGER PRIMARY KEY, plan_id INTEGER, date TEXT)'))
        conn.execute(text("INSERT INTO planned_workouts VALUES (1, 1, '2026-06-01')"))
        conn.execute(text('CREATE TABLE workout_progressions (id INTEGER PRIMARY KEY, user_id INTEGER, category TEXT)'))
    old.dispose()
    copied = tmp_path / 'migration-copy.db'
    shutil.copyfile(source, copied)
    migrated = create_engine(f'sqlite:///{copied}')
    monkeypatch.setattr(database, 'engine', migrated)
    database.add_missing_columns()
    database.add_missing_columns()  # idempotent on restart
    columns = {c['name'] for c in inspect(migrated).get_columns('planned_workouts')}
    assert {'session_status', 'prescription', 'execution', 'b2b'} <= columns
    with migrated.connect() as conn:
        assert conn.execute(text('SELECT date, prescription FROM planned_workouts')).one() == ('2026-06-01', None)
    untouched = create_engine(f'sqlite:///{source}')
    assert 'prescription' not in {c['name'] for c in inspect(untouched).get_columns('planned_workouts')}
    migrated.dispose()
    untouched.dispose()
