"""Dedicated worker: python -m app.services.worker (schema must be migrated first)."""
import asyncio
import logging
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.services import sync_jobs, coaching_jobs
from app.services.provider_connections import configured
from app.athlete_clock import athlete_zone


def schedule_due():
    from app.services.garmin import poll_due
    if settings.garmin_poll_minutes<=0:
        return
    from datetime import datetime,timedelta
    from sqlalchemy import or_
    from app.models.operations import ProviderCredential,SyncJob
    from app.models.garmin import GarminConnection
    with SessionLocal() as db:
        connected=db.query(ProviderCredential.user_id).filter(ProviderCredential.revoked_at.is_(None),ProviderCredential.ciphertext!='',or_(ProviderCredential.expires_at.is_(None),ProviderCredential.expires_at>datetime.utcnow()))
        identities=User.id.in_(connected)
        if settings.garmin_api_key:identities=or_(identities,User.id==settings.default_user_id)
        busy=db.query(SyncJob.user_id).filter(SyncJob.status.in_(['queued','running','retry']))
        due=datetime.now()-timedelta(minutes=settings.garmin_poll_minutes)
        rows=db.query(User.id,User.timezone).outerjoin(GarminConnection,GarminConnection.user_id==User.id).filter(
            identities,~User.id.in_(busy),or_(GarminConnection.last_sync_at.is_(None),GarminConnection.last_sync_at<due)).order_by(User.id).limit(100).all()

    for uid,zone in rows:
        with athlete_zone(zone,uid), SessionLocal() as db:
            if configured(uid,db) and poll_due(uid):
                db.commit()
                sync_jobs.enqueue(uid,db)


def delete_blobs():
    from app.models.operations import BlobDeletion
    from app.services.blob_store import _client
    with SessionLocal() as db:
        from app.services.sync_jobs import _write
        _write(db)
        row=db.query(BlobDeletion).with_for_update(skip_locked=True).first()
        if not row:
            db.commit();return False
        row_id,bucket,key=row.id,row.bucket,row.key
        db.commit()  # no writer held across S3 I/O; duplicate deletes are idempotent
        _client().delete_object(Bucket=bucket,Key=key)
        from sqlalchemy import delete
        db.execute(delete(BlobDeletion).where(BlobDeletion.id==row_id));db.commit()
        return True



def log_memory():
    """Current/peak RSS of this process, so a creep toward Render's 512MB limit shows in the logs."""
    try:
        status=dict(line.split(':',1) for line in open('/proc/self/status') if line.startswith(('VmRSS','VmHWM')))
    except OSError:
        return  # not Linux
    logging.getLogger('stride.worker').info('Memory rss=%s peak=%s',status['VmRSS'].strip(),status['VmHWM'].strip())


async def run():
    last_memory_log=0.0
    while True:
        if asyncio.get_running_loop().time()-last_memory_log>=600:
            last_memory_log=asyncio.get_running_loop().time()
            log_memory()
        worked=False
        for operation in (schedule_due,sync_jobs.process_one,coaching_jobs.process_one,delete_blobs):
            try:
                worked=bool(await asyncio.to_thread(operation)) or worked
            except Exception as exc:
                logging.getLogger('stride.worker').warning('Worker operation deferred (%s)',type(exc).__name__)
        await asyncio.sleep(1 if worked else 5)


if __name__=='__main__':
    asyncio.run(run())
