"""Persistent version/revision keyed snapshots; no network and no model calls."""
import json
from datetime import datetime, timedelta

from app.models.history import AnalysisSnapshot, AthleteRevision


def revision(user_id, db, *, flush=True):
    if flush:
        db.flush()
    return db.query(AthleteRevision.revision).filter_by(user_id=user_id).scalar() or 0


def fresh(user_id, kind, cache_key, db):
    """A cached payload that is still current, read without writing anything (or None)."""
    row = db.query(AnalysisSnapshot).filter_by(user_id=user_id, kind=kind, cache_key=cache_key).first()
    return json.loads(row.payload) if row and row.revision == revision(user_id, db, flush=False) else None


def cached(user_id, kind, cache_key, db, build, *, persist=True):
    current = revision(user_id, db, flush=persist)
    if persist:
        # Operational caches expire; immutable model input snapshots remain on reviews.
        db.query(AnalysisSnapshot).filter(AnalysisSnapshot.user_id == user_id,
            AnalysisSnapshot.created_at < datetime.now()-timedelta(days=45)).delete(synchronize_session=False)
    row = db.query(AnalysisSnapshot).filter_by(user_id=user_id, kind=kind, cache_key=cache_key).first()
    if row and row.revision == current:
        return json.loads(row.payload)
    value = build()
    if not persist:
        return value
    if row is None:
        row = AnalysisSnapshot(user_id=user_id, kind=kind, cache_key=cache_key)
        db.add(row)
    row.revision, row.payload, row.created_at = current, json.dumps(value, default=_json), datetime.now()
    db.flush()
    return json.loads(row.payload)


def _json(value):
    if hasattr(value, 'item'):
        return value.item()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    raise TypeError(type(value).__name__)
