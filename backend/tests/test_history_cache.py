from datetime import date, datetime, timedelta

from app.database import SessionLocal
from app.models.activity import Activity
from app.models.history import DailyFact, DirtyDay
from app.services.history_facts import historical_profile, daily_facts
from app.services.history_cache import revision

MI = 1609.34


def run(db, day, miles=5):
    a = Activity(user_id=1, source='manual', date=datetime.combine(day, datetime.min.time()), distance_meters=miles*MI, duration_seconds=miles*600)
    db.add(a); db.flush()
    return a


def test_corrected_old_run_refreshes_its_week_and_historical_snapshot():
    today = date.today()
    with SessionLocal() as db:
        a = run(db, today-timedelta(days=80))
        run(db, today-timedelta(days=2))
        before = historical_profile(1, db); db.commit()
        assert len(before['weekly_history']) == 2
        a.distance_meters = 10*MI; db.commit()
        assert {r.date for r in db.query(DirtyDay)} == {a.date.date().isoformat()}
        after = historical_profile(1, db); db.commit()
        assert after['weekly_history'][0]['miles'] == 10
        assert after['historical_capacity']['longest_runs'][0]['miles'] == 10


def test_cached_profile_survives_session_restart_without_rebuilding(monkeypatch):
    import app.services.history_facts as facts
    with SessionLocal() as db:
        run(db, date.today()-timedelta(days=1)); expected = historical_profile(1, db); db.commit()
    monkeypatch.setattr(facts, '_profile', lambda *args: (_ for _ in ()).throw(AssertionError('Cache miss')))
    with SessionLocal() as db:
        assert historical_profile(1, db) == expected


def test_date_move_and_deletion_remove_old_day_and_walk_override_excludes_load():
    with SessionLocal() as db:
        day = date.today()-timedelta(days=20)
        a = run(db, day); daily_facts(1, db); db.commit()
        a.date += timedelta(days=8); db.commit()
        assert len(list(db.query(DirtyDay))) == 2
        profile = historical_profile(1, db); db.commit()
        assert len(profile['weekly_history']) == 1
        assert profile['weekly_history'][0]['week_start'] != (day-timedelta(days=day.weekday())).isoformat()
        a.activity_kind_override = 'walk'; db.commit()
        assert historical_profile(1, db)['coverage']['recorded_runs'] == 0
        a.activity_kind_override = 'run'; db.commit()
        historical_profile(1, db); db.commit()
        db.delete(a); db.commit()
        assert historical_profile(1, db)['coverage']['recorded_runs'] == 0


def test_rollback_does_not_invalidate_persisted_facts():
    with SessionLocal() as db:
        a = run(db, date.today()); historical_profile(1, db); db.commit()
        before = revision(1, db)
        a.distance_meters = 20*MI; db.flush(); db.rollback()
        assert revision(1, db) == before
        assert historical_profile(1, db)['coverage']['recorded_runs'] == 1
        assert not db.query(DirtyDay).count()


def test_bulk_activity_edit_cannot_leave_old_cache():
    with SessionLocal() as db:
        run(db, date.today()-timedelta(days=1)); historical_profile(1, db); db.commit()
        db.query(Activity).filter_by(user_id=1).update({'distance_meters': 10*MI}); db.commit()
        assert not db.query(DailyFact).count()
        assert historical_profile(1, db)['weekly_history'][0]['miles'] == 10


def test_historical_capacity_is_not_current_fitness_or_assumed_rest():
    with SessionLocal() as db:
        for week in range(30, 26, -1):
            for offset in range(4):
                run(db, date.today()-timedelta(weeks=week, days=offset), 10)
        run(db, date.today()-timedelta(days=date.today().weekday()+2), 2)
        profile = historical_profile(1, db)
        assert profile['historical_capacity']['sustained_blocks'][0]['average_mpw'] > 20
        assert profile['current']['recorded_mpw_last_4_weeks'] == .5
        assert profile['recording_gaps']
        assert any(w['recording_status'] == 'unknown' for w in profile['current']['last_12_completed_weeks'])


def test_baseline_api_reuses_snapshot_and_edit_invalidates_it(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import analyzer
    with SessionLocal() as db:
        run(db, date.today()-timedelta(days=8)); db.commit()
    client = TestClient(app)
    calls = []
    real = analyzer._analyze_athlete
    def count(*args):
        calls.append(1); return real(*args)
    monkeypatch.setattr(analyzer, '_analyze_athlete', count)
    first = client.get('/api/analysis/1/baseline')
    assert first.status_code == 200
    assert client.get('/api/analysis/1/baseline').json() == first.json()
    assert len(calls) == 1
    with SessionLocal() as db:
        db.query(Activity).one().distance_meters *= 2; db.commit()
    assert client.get('/api/analysis/1/baseline').status_code == 200
    assert len(calls) == 2
