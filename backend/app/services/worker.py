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
    with SessionLocal() as db:
        rows=[(u.id,u.timezone) for u in db.query(User)]
    for uid,zone in rows:
        with athlete_zone(zone), SessionLocal() as db:
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



async def run():
    while True:
        worked=False
        for operation in (schedule_due,sync_jobs.process_one,coaching_jobs.process_one,delete_blobs):
            try:
                worked=bool(await asyncio.to_thread(operation)) or worked
            except Exception as exc:
                logging.getLogger('stride.worker').warning('Worker operation deferred (%s)',type(exc).__name__)
        await asyncio.sleep(1 if worked else 5)


if __name__=='__main__':
    asyncio.run(run())
