"""One durable sync job per athlete, claimed atomically across worker processes."""
import json
import secrets
from datetime import timedelta
from sqlalchemy import or_, and_
from app.database import SessionLocal
from app.models.operations import SyncJob
from app.models.user import User
from app.services.accounts import utcnow


def _write(db):
    if db.bind.dialect.name=='sqlite':
        from sqlalchemy import text
        db.execute(text('BEGIN IMMEDIATE'))


def enqueue(user_id,db,full=False):
    _write(db)
    if db.bind.dialect.name=='postgresql':
        from sqlalchemy import text
        db.execute(text('SELECT pg_advisory_xact_lock(68743200,:uid)'),{'uid':user_id})
    job=db.query(SyncJob).filter_by(user_id=user_id).with_for_update().first()
    if job and job.status in {'queued','running','retry'}:
        db.commit()
        return describe(job)
    if job is None:
        job=SyncJob(user_id=user_id);db.add(job)
    job.status,job.full,job.attempts='queued',int(full),0
    job.available_at,job.error,job.result=utcnow(),None,None
    db.commit()
    return describe(job)


def describe(job):
    return {'state': 'running' if job.status in {'queued','running','retry'} else 'error' if job.status=='error' else 'done',
            'status':job.status,'result':json.loads(job.result) if job.result else None,
            'error':job.error,'attempts':job.attempts}


def process_one():
    now=utcnow()
    with SessionLocal() as db:
        _write(db)
        job=db.query(SyncJob).filter(or_(and_(SyncJob.status.in_(['queued','retry']),SyncJob.available_at<=now),
              and_(SyncJob.status=='running',SyncJob.lease_until<now))).order_by(SyncJob.available_at).with_for_update(skip_locked=True).first()
        if not job:
            db.commit();return False
        token=secrets.token_hex(24)
        job.status,job.lease_token,job.lease_until='running',token,now+timedelta(minutes=30)
        job.attempts+=1
        uid,full=job.user_id,bool(job.full)
        user=db.get(User,uid)
        zone=user.timezone if user else None
        db.commit()
    error,result=None,None
    try:
        from app.api.garmin import _sync_in_new_session
        from app.athlete_clock import athlete_zone
        with athlete_zone(zone):
            result=_sync_in_new_session(uid,full)
    except Exception as exc:
        error=type(exc).__name__
    with SessionLocal() as db:
        _write(db)
        job=db.query(SyncJob).filter_by(user_id=uid,lease_token=token).with_for_update().first()
        if not job:
            db.commit();return True
        job.lease_token,job.lease_until=None,None
        waiting=result and result.get('status') in {'busy','backoff'}
        if waiting:
            job.attempts=max(0,job.attempts-1)
        job.status='retry' if (error or waiting) and job.attempts<5 else 'error' if error else 'done'
        job.error=error
        job.result=json.dumps(result) if result else None
        job.available_at=utcnow()+timedelta(minutes=min(60,5*2**job.attempts))
        db.commit()
    return True


def heartbeat(user_id,db):
    # Called between provider requests; it does not hold a writer during I/O.
    job=db.get(SyncJob,user_id)
    if job and job.status=='running' and job.lease_until < utcnow()+timedelta(minutes=25):
        job.lease_until=utcnow()+timedelta(minutes=30)
        db.commit()
