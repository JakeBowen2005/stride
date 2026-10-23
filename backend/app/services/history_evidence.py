"""Idempotent source capture and bounded, durable enrichment retries. No commits here."""
import hashlib
import json
from datetime import datetime, timedelta

from app.models.history import ActivitySource, SourceRevision, HistoryCoverage

PARSER_VERSION = 'fit-timer-v1'
RETRY_LIMIT = 5
REPAIR_BATCH = 10


def encoded(value):
    return json.dumps(value, sort_keys=True, default=str, separators=(',', ':'))


def source_for(activity, provider, external_id, db):
    db.flush()
    row = db.query(ActivitySource).filter_by(user_id=activity.user_id, provider=provider,
                                            external_id=str(external_id)).first()
    if row is None:
        row = ActivitySource(user_id=activity.user_id, activity_id=activity.id, provider=provider,
                             external_id=str(external_id), enrichment_status='pending', attempts=0)
        db.add(row)
        db.flush()
    return row


def capture(source, kind, db, *, payload=None, blob=None):
    body = encoded(payload) if payload is not None else None
    digest = hashlib.sha256(kind.encode() + (blob if blob is not None else (body or '').encode())).hexdigest()
    if not db.query(SourceRevision.id).filter_by(source_id=source.id, content_hash=digest).first():
        db.add(SourceRevision(source_id=source.id, content_hash=digest, kind=kind, payload=body, fit_bytes=blob))
        db.flush()
    source.last_seen_at = datetime.now()
    if kind == 'summary':
        changed = source.summary_hash != digest
        source.summary_hash = digest
        return changed
    return digest


def pending(source, error):
    source.attempts = (source.attempts or 0) + 1
    source.last_error = error  # exception type only: no response bodies or credentials
    source.enrichment_status = 'unavailable' if source.attempts >= RETRY_LIMIT else 'retry'
    source.next_retry_at = None if source.enrichment_status == 'unavailable' else datetime.now() + timedelta(minutes=min(1440, 5 * 2 ** source.attempts))


def coverage(user_id, stream, start, end, status, db):
    start, end = str(start), str(end)
    row = db.query(HistoryCoverage).filter_by(user_id=user_id, stream=stream, start_date=start, end_date=end).first()
    if row is None:
        row = HistoryCoverage(user_id=user_id, stream=stream, start_date=start, end_date=end)
        db.add(row)
    row.status, row.checked_at = status, datetime.now()
