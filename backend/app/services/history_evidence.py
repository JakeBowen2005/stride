"""Source capture primitives and a bounded offline FIT reprocessing operation."""
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


def capture(source, kind, db, *, payload=None, blob=None, blob_reference=None):
    body = encoded(payload) if payload is not None else None
    digest = hashlib.sha256(kind.encode() + (blob if blob is not None else (body or '').encode())).hexdigest()
    if not db.query(SourceRevision.id).filter_by(source_id=source.id, content_hash=digest).first():
        from app.config import settings
        key, checksum = blob_reference or (None, None)
        if blob is not None and settings.fit_blob_bucket and blob_reference is None:
            from app.services.blob_store import put_fit
            key,checksum=put_fit(source.user_id,blob)
        db.add(SourceRevision(source_id=source.id, content_hash=digest, kind=kind, payload=body,
                              fit_bytes=None if key else blob, fit_blob_key=key, fit_sha256=checksum))
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


def reparse_fits(user_id, db, *, limit=100, force=False):
    """Reprocess retained evidence offline. No imports, Garmin calls or plan effects."""
    from app.models.activity import Activity
    from app.services.garmin_api import laps_from_fit
    from app.services.garmin import reanalyze_laps
    from app.services.coaching_jobs import enqueue_synced_run, release_synced_jobs
    from sqlalchemy import or_
    query = db.query(ActivitySource).filter(ActivitySource.user_id==user_id,ActivitySource.provider.in_(['garmin','fit_upload']))
    if not force:
        query = query.filter(or_(ActivitySource.parser_version.is_(None), ActivitySource.parser_version != PARSER_VERSION))
    # Skip sources without original evidence before the limit, so legacy rows cannot starve newer files.
    query = query.filter(db.query(SourceRevision.id).filter(SourceRevision.source_id == ActivitySource.id,
                                                          SourceRevision.kind == 'fit').exists())
    reparsed, failed = 0, 0
    changed = []
    for source in query.order_by(ActivitySource.id).limit(limit):
        original = db.query(SourceRevision).filter_by(source_id=source.id, kind='fit').order_by(SourceRevision.id.desc()).first()
        try:
            from app.services.blob_store import read_fit
            laps = laps_from_fit(read_fit(original,user_id))
            if not laps:
                failed += 1
                continue
            activity = db.get(Activity, source.activity_id)
            activity.splits = json.dumps(laps)
            source.parser_version, source.enrichment_status = PARSER_VERSION, 'complete'
            source.last_error, source.next_retry_at, source.attempts = None, None, 0
            changed.append(activity); reparsed += 1
        except Exception as exc:
            source.last_error = type(exc).__name__
            failed += 1
    if reparsed:
        reanalyze_laps(user_id, db)
        for activity in changed:
            enqueue_synced_run(activity, db)
        release_synced_jobs(user_id, db)
    db.commit()
    return {'reparsed': reparsed, 'failed': failed, 'parser_version': PARSER_VERSION}
