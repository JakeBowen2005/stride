"""Transactional, versioned data upgrades after additive schema creation.

Startup backs SQLite up before schema/data upgrades. Migrations never download
provider data. Legacy snapshots are explicitly distinct from original payloads.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def _adopt_sources(db):
    from app.models.activity import Activity
    from app.services.history_evidence import capture, source_for
    for activity in db.query(Activity).yield_per(100):
        source = source_for(activity, activity.source, activity.external_id or f'activity-{activity.id}', db)
        capture(source, 'legacy', db, payload={c.name: getattr(activity, c.name) for c in Activity.__table__.columns})
        source.enrichment_status = 'complete' if activity.source != 'garmin' or activity.splits not in (None, '', '[]') else 'pending'


def _initialize_revisions(db):
    from app.models.history import AthleteRevision
    from app.models.user import User
    for (user_id,) in db.query(User.id):
        if db.get(AthleteRevision, user_id) is None:
            db.add(AthleteRevision(user_id=user_id, revision=0))


# Values only the unofficial garminconnect library returned (before the Oct 2026 switch to
# the official Personal API). Stride no longer receives them, so it doesn't keep them.
UNOFFICIAL_WELLNESS = ('readiness_score', 'readiness_level', 'readiness_feedback', 'recovery_time_min',
                       'training_status', 'acute_load', 'chronic_load', 'acwr', 'load_balance_feedback',
                       'vo2max', 'predicted_5k', 'predicted_10k', 'predicted_half', 'predicted_marathon')
UNOFFICIAL_KEYS = frozenset(UNOFFICIAL_WELLNESS)


def scrub_unofficial(value):
    """The same JSON with every unofficial-metric value set to null (keys kept, shapes unchanged)."""
    if isinstance(value, dict):
        return {k: None if k in UNOFFICIAL_KEYS else scrub_unofficial(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_unofficial(v) for v in value]
    return value


def _remove_unofficial_garmin_metrics(db):
    import hashlib
    import json
    from app.models.activity import Activity
    from app.models.coaching import CoachingAttempt, CoachingReview
    from app.models.history import AnalysisSnapshot, SourceRevision
    from app.models.wellness import DailyWellness
    from app.services.history_evidence import encoded
    db.query(DailyWellness).update({getattr(DailyWellness, c): None for c in UNOFFICIAL_WELLNESS}, synchronize_session=False)
    db.query(Activity).filter(Activity.vo2max.isnot(None)).update({Activity.vo2max: None}, synchronize_session=False)
    for rev in db.query(SourceRevision).filter(SourceRevision.kind == 'legacy', SourceRevision.payload.isnot(None)).yield_per(100):
        data = json.loads(rev.payload)
        clean = scrub_unofficial(data)
        if clean != data:
            rev.payload = encoded(clean)
            rev.content_hash = hashlib.sha256(b'legacy' + rev.payload.encode()).hexdigest()
    for model, columns in ((CoachingReview, ('input_snapshot', 'result')), (CoachingAttempt, ('input_snapshot', 'result'))):
        for row in db.query(model).yield_per(100):
            for column in columns:
                raw = getattr(row, column)
                if raw:
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        continue
                    clean = scrub_unofficial(data)
                    if clean != data:
                        setattr(row, column, json.dumps(clean))
    db.query(AnalysisSnapshot).delete(synchronize_session=False)  # caches rebuild from the cleaned data


MIGRATIONS = [('001-source-evidence', _adopt_sources), ('002-history-facts', _initialize_revisions),
              ('003-remove-unofficial-garmin-metrics', _remove_unofficial_garmin_metrics)]


def migrate(bind):
    with bind.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
        applied = set(conn.execute(text('SELECT version FROM schema_migrations')).scalars())
        for version, upgrade in MIGRATIONS:
            if version in applied:
                continue
            with Session(bind=conn) as db:
                upgrade(db)
                db.flush()
            conn.execute(text('INSERT INTO schema_migrations (version) VALUES (:version)'), {'version': version})
