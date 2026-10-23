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


MIGRATIONS = [('001-source-evidence', _adopt_sources), ('002-history-facts', _initialize_revisions)]


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
