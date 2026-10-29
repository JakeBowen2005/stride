"""Data migration 003: values only the unofficial garminconnect library provided are removed."""
import json
from datetime import datetime

from app.database import SessionLocal
from app.migrations import _remove_unofficial_garmin_metrics, scrub_unofficial
from app.models.activity import Activity
from app.models.history import ActivitySource, AnalysisSnapshot, SourceRevision
from app.models.wellness import DailyWellness


def test_scrub_nulls_unofficial_values_anywhere_and_keeps_everything_else():
    data = {'wellness': [{'date': '2026-10-01', 'readiness_score': 70, 'acwr': 1.2, 'hrv_last_night': 80}],
            'runs': [{'vo2max': 53.3, 'distance': 5000, 'nested': {'predicted_5k': 1200}}]}
    assert scrub_unofficial(data) == {
        'wellness': [{'date': '2026-10-01', 'readiness_score': None, 'acwr': None, 'hrv_last_night': 80}],
        'runs': [{'vo2max': None, 'distance': 5000, 'nested': {'predicted_5k': None}}]}


def test_migration_removes_stored_unofficial_metrics():
    with SessionLocal() as db:
        db.add(DailyWellness(user_id=1, date='2026-10-01', readiness_score=70, training_status='PRODUCTIVE', acwr=1.2,
                             vo2max=53.3, predicted_5k=1200, hrv_last_night=80, sleep_score=85))
        run = Activity(user_id=1, source='garmin', external_id='1', name='Run', date=datetime(2026, 10, 1, 7),
                       distance_meters=8000, duration_seconds=2400, vo2max=53.0, training_load=120)
        db.add(run)
        db.flush()
        source = ActivitySource(user_id=1, activity_id=run.id, provider='garmin', external_id='1')
        db.add(source)
        db.flush()
        db.add(SourceRevision(source_id=source.id, kind='legacy', content_hash='old',
                              payload=json.dumps({'vo2max': 53.0, 'training_load': 120})))
        db.add(AnalysisSnapshot(user_id=1, kind='coach-context', cache_key='k', revision=0, payload='{"acwr": 1.2}'))
        db.commit()
        _remove_unofficial_garmin_metrics(db)
        db.commit()
        day = db.query(DailyWellness).one()
        assert (day.readiness_score, day.training_status, day.acwr, day.vo2max, day.predicted_5k) == (None,) * 5
        assert (day.hrv_last_night, day.sleep_score) == (80, 85)
        run = db.query(Activity).one()
        assert run.vo2max is None and run.training_load == 120
        legacy = db.query(SourceRevision).one()
        assert json.loads(legacy.payload) == {'vo2max': None, 'training_load': 120} and legacy.content_hash != 'old'
        assert db.query(AnalysisSnapshot).count() == 0
