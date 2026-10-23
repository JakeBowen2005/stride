"""Versioned, transactional data migrations after additive schema creation.

Startup's SQLite backup runs before this module. Existing source rows are adopted,
never presented as original Garmin payloads, and never downloaded during migration.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def migrate(bind):
    with bind.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
        if conn.execute(text("SELECT version FROM schema_migrations WHERE version='001-source-evidence'")).first():
            return
        with Session(bind=conn) as db:
            from app.models.activity import Activity
            from app.services.history_evidence import capture, source_for
            for activity in db.query(Activity).yield_per(100):
                source = source_for(activity, activity.source, activity.external_id or f'activity-{activity.id}', db)
                capture(source, 'legacy', db, payload={c.name: getattr(activity, c.name) for c in Activity.__table__.columns})
                source.enrichment_status = 'complete' if activity.source != 'garmin' or activity.splits not in (None, '', '[]') else 'pending'
            db.flush()
        conn.execute(text("INSERT INTO schema_migrations (version) VALUES ('001-source-evidence')"))
