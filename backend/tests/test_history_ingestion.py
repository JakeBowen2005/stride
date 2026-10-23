"""Offline replay of corrections, delayed evidence, doubles and provenance."""
import json
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.activity import Activity
from app.models.history import ActivitySource, SourceRevision
from app.services import garmin
from tests.test_api import FakeGarmin


def setup_client(monkeypatch, fake):
    monkeypatch.setattr(garmin, 'get_client', lambda: fake)
    monkeypatch.setattr(garmin, 'FULL_SYNC_DELAY', 0)


def test_full_sync_refreshes_old_metrics_and_preserves_feedback(monkeypatch):
    fake = FakeGarmin([1, 2])
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        activity = db.query(Activity).filter_by(external_id='2').one()
        activity.feel_rating, activity.feel_notes, activity.activity_kind_override = 8, 'My report', 'run'
        original = fake._run
        fake._run = lambda n, i: {**original(n, i), 'distance': 9000, 'movingDuration': 2900}
        garmin.sync_garmin(1, db, full=True)
        assert activity.distance_meters == 9000 and activity.duration_seconds == 2900
        assert (activity.feel_rating, activity.feel_notes, activity.activity_kind_override) == (8, 'My report', 'run')
        source = db.query(ActivitySource).filter_by(external_id='2').one()
        assert db.query(SourceRevision).filter_by(source_id=source.id, kind='summary').count() == 2
        garmin.sync_garmin(1, db, full=True)
        assert db.query(SourceRevision).filter_by(source_id=source.id, kind='summary').count() == 2


def test_failed_old_fit_repairs_outside_discovery_window_after_restart(monkeypatch):
    fake = FakeGarmin([1, 2, 3, 4, 5, 6])
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        source = db.query(ActivitySource).filter_by(external_id='6').one()
        source.next_retry_at = datetime.now() - timedelta(minutes=1)
        db.commit()
    with SessionLocal() as db:
        def laps(aid):
            fake.split_calls.append(aid)
            return [{'distance_m': 8000, 'duration_s': 2700}]
        fake.get_laps = laps
        result = garmin.sync_garmin(1, db)
        assert result['updated'] >= 1 and '6' in fake.split_calls
        assert json.loads(db.query(Activity).filter_by(external_id='6').one().splits)
        assert db.query(ActivitySource).filter_by(external_id='6').one().enrichment_status == 'complete'


def test_double_shakeout_does_not_take_manual_feedback(monkeypatch):
    fake = FakeGarmin([1, 2])
    original = fake._run
    fake._run = lambda n, i: {**original(n, i), 'startTimeLocal': f'2026-09-01 {7+n:02}:00:00', 'distance': 3000 if i == 1 else 8000}
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        manual = Activity(user_id=1, source='manual', external_id='manual-day', date=datetime(2026, 9, 1, 12),
                          distance_meters=8000, duration_seconds=2700, feel_rating=9)
        db.add(manual); db.commit()
        manual_id = manual.id
        garmin.sync_garmin(1, db)
        assert db.query(Activity).count() == 2
        assert db.get(Activity, manual_id).external_id == '2'
        assert db.query(Activity).filter_by(external_id='1').one().feel_rating is None
        assert db.query(ActivitySource).filter_by(provider='manual').one().activity_id == manual_id


def test_ambiguous_equal_distance_doubles_preserve_manual_record(monkeypatch):
    fake = FakeGarmin([1, 2])
    original = fake._run
    fake._run = lambda n, i: {**original(n, i), 'startTimeLocal': f'2026-09-01 {7+n:02}:00:00'}
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source='manual', external_id='manual-day', date=datetime(2026, 9, 1, 12),
                        distance_meters=8000, duration_seconds=2700, feel_rating=9))
        db.commit()
        garmin.sync_garmin(1, db)
        assert db.query(Activity).filter_by(source='manual').one().feel_rating == 9
        assert db.query(Activity).count() == 3


def test_collection_404_is_not_successful_empty_import():
    import httpx
    import pytest
    from app.services.garmin_api import PersonalApiClient
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='token') if r.method == 'POST' else httpx.Response(404)))
    with pytest.raises(httpx.HTTPStatusError):
        PersonalApiClient('fake', http=http).search_runs()


def test_weekly_reconciliation_discovers_a_late_old_upload(monkeypatch):
    from app.models.garmin import GarminConnection
    fake = FakeGarmin([1, 2, 3, 4, 5, 6])
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        fake.ids.append(7)  # uploaded now with an old recording date
        conn = db.query(GarminConnection).one()
        conn.last_reconciled_at = datetime.now() - timedelta(days=8)
        db.commit()
        assert garmin.sync_garmin(1, db)['new'] == 1
        assert db.query(Activity).filter_by(external_id='7').one()


def test_migration_adopts_old_lapless_rows_once_without_network():
    from sqlalchemy import create_engine, text
    from app.database import Base
    from app.migrations import migrate
    from app.models.user import User
    from sqlalchemy.orm import Session
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, name='Existing athlete')); db.flush()
        db.add(Activity(user_id=1, source='garmin', external_id='old', date=datetime(2020, 1, 1),
                        distance_meters=8000, duration_seconds=2700, feel_notes='keep'))
        db.commit()
    migrate(engine); migrate(engine)
    with Session(engine) as db:
        assert db.query(ActivitySource).one().enrichment_status == 'pending'
        assert db.query(SourceRevision).count() == 1
        assert db.query(Activity).one().feel_notes == 'keep'
        assert set(db.execute(text('SELECT version FROM schema_migrations')).scalars()) == {'001-source-evidence', '002-history-facts'}


def test_recovered_laps_enqueue_one_new_revision_not_a_history_storm(monkeypatch):
    from app.config import settings
    from app.models.coaching import CoachingJob
    from app.services.coaching_jobs import enqueue_synced_run
    monkeypatch.setattr(settings, 'openai_auto_reviews', True)
    with SessionLocal() as db:
        a = Activity(user_id=1, source='garmin', external_id='recent', date=datetime.now(), distance_meters=8000, duration_seconds=2700)
        db.add(a); db.flush()
        enqueue_synced_run(a, db); db.commit()
        a.splits = '[{"distance_m":8000,"duration_s":2700}]'
        enqueue_synced_run(a, db); db.commit()
        enqueue_synced_run(a, db); db.commit()
        assert db.query(CoachingJob).count() == 2
        assert db.query(CoachingJob).filter_by(status='waiting_sync').count() == 1


def tiny_fit():
    """A real minimal FIT lap: 800m, 360 timer seconds, 400 elapsed, active effort."""
    import struct
    fields = bytes([9, 4, 0x86, 8, 4, 0x86, 7, 4, 0x86, 15, 1, 2, 23, 1, 0])
    definition = bytes([0x40, 0, 0]) + struct.pack('<H', 19) + bytes([5]) + fields
    record = bytes([0]) + struct.pack('<IIIBB', 80000, 360000, 400000, 155, 0)
    data = definition + record
    return struct.pack('<BBHI4s', 12, 0x10, 100, len(data), b'.FIT') + data + b'\x00\x00'


def test_original_fit_is_retained_and_timer_time_survives_pause(monkeypatch):
    from app.services.garmin_api import laps_from_fit
    blob = tiny_fit()
    assert laps_from_fit(blob)[0]['duration_s'] == 360
    fake = FakeGarmin([1])
    fake.get_fit = lambda _: blob
    setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        assert db.query(SourceRevision).filter_by(kind='fit').one().fit_bytes == blob
        assert json.loads(db.query(Activity).one().splits)[0]['duration_s'] == 360


def test_exhausted_fit_is_not_retried_every_poll(monkeypatch):
    fake = FakeGarmin([1]); setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        source = db.query(ActivitySource).one()
        source.enrichment_status, source.attempts, source.next_retry_at = 'unavailable', 5, None
        db.commit(); fake.split_calls.clear()
        garmin.sync_garmin(1, db)
        assert fake.split_calls == []
        garmin.sync_garmin(1, db, full=True)
        assert fake.split_calls == ['1']


def test_old_repair_rate_limit_records_connection_backoff(monkeypatch):
    from app.models.garmin import GarminConnection
    from app.services.garmin_api import GarminRateLimited
    import pytest
    fake = FakeGarmin([1, 2, 3, 4, 5, 6]); setup_client(monkeypatch, fake)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        source = db.query(ActivitySource).filter_by(external_id='6').one()
        source.next_retry_at = datetime.now()-timedelta(minutes=1); db.commit()
        def limited(aid):
            if aid == '6': raise GarminRateLimited('limited')
            return []
        fake.get_laps = limited
        with pytest.raises(GarminRateLimited): garmin.sync_garmin(1, db)
        assert db.query(GarminConnection).one().backoff_until > datetime.now()


def test_fit_network_does_not_hold_database_writer(monkeypatch):
    from app.models.user import User
    fake = FakeGarmin([1]); setup_client(monkeypatch, fake)
    writes = []
    def network(aid):
        with SessionLocal() as other:
            other.get(User, 1).units = 'km'; other.commit()
        writes.append(aid)
        return []
    fake.get_laps = network
    with SessionLocal() as db:
        assert garmin.sync_garmin(1, db)['new'] == 1
        assert writes == ['1']
