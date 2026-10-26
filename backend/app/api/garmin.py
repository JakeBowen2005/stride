from app.config import settings
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.garmin import GarminConnection
from app.models.user import User
from app.services.garmin import GarminNotConnected, has_api_key, sync_garmin
from app.services.wellness import sync_wellness

router = APIRouter(prefix="/api/garmin", tags=["garmin"])
logger = logging.getLogger("stride.garmin")

# Background full-sync status, keyed by user id (single-process app)
_full_sync_jobs: dict[int, dict] = {}
_background_tasks: set[asyncio.Task] = set()


@router.get("/status/{user_id}")
def garmin_status(user_id: int, db: Session = Depends(get_db)):
    from app.services.provider_connections import configured, connection_issue
    from app.models.operations import SyncJob
    from app.services.sync_jobs import describe
    present=configured(user_id,db)
    durable=db.get(SyncJob,user_id)
    # Read-only: no row yet just means "never connected"
    conn = db.query(GarminConnection).filter(GarminConnection.user_id == user_id).first() or GarminConnection(
        user_id=user_id, connected=False, full_sync_done=False
    )
    return {
        "api_key_present": present,
        "connection_issue": connection_issue(user_id, db),
        "can_reconnect": user_id == settings.default_user_id and bool(settings.garmin_api_key.strip()),
        "business_pending": user_id != settings.default_user_id,
        "owner_key_storage_ready": user_id == settings.default_user_id and bool(settings.provider_encryption_keys),
        "connected": conn.connected and present,
        "display_name": conn.display_name,
        "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        "last_new_activity_at": conn.last_new_activity_at.isoformat() if conn.last_new_activity_at else None,
        "last_error": conn.last_error,
        "full_sync_done": bool(conn.full_sync_done),
        "backoff_until": conn.backoff_until.isoformat() if conn.backoff_until else None,
        "full_sync_job": describe(durable) if durable else _full_sync_jobs.get(user_id),
    }


@router.post("/sync/{user_id}")
async def garmin_sync(user_id: int, db: Session = Depends(get_db)):
    """Pull new runs from Garmin (incremental; first ever sync pulls full history)."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")
    from app.services.provider_connections import connection_issue
    issue = connection_issue(user_id, db)
    if issue:
        raise HTTPException(409, issue)
    from datetime import datetime
    conn = db.query(GarminConnection).filter_by(user_id=user_id).first()
    if conn and conn.backoff_until and conn.backoff_until > datetime.now():
        return {"status": "backoff", "message": conn.last_error or "Garmin sync is paused. Try again shortly."}
    if settings.accounts_enabled or not settings.embedded_workers:
        from app.services.sync_jobs import enqueue
        db.commit()
        return enqueue(user_id,db)
    try:
        return await asyncio.to_thread(_sync_in_new_session, user_id, False)
    except GarminNotConnected as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        logger.exception("Garmin sync failed")
        raise HTTPException(status_code=502, detail="Garmin sync failed. Check the Stride terminal for details.")


@router.post("/full-sync/{user_id}")
async def garmin_full_sync(user_id: int, db: Session = Depends(get_db)):
    """Re-walk the entire Garmin history in the background (takes a few minutes)."""
    from app.services.provider_connections import configured
    from app.services.sync_jobs import enqueue
    if not configured(user_id,db):
        raise HTTPException(409,'Garmin is not connected for this athlete.')
    db.commit()
    return enqueue(user_id,db,full=True)


def _sync_in_new_session(user_id: int, full: bool) -> dict:
    db = SessionLocal()
    try:
        result = sync_garmin(user_id, db, full=full)
        if result.get("status") != "ok":
            return result  # busy / backing off: don't spend more Garmin requests on wellness
        # Sleep / HRV etc. ride along (throttled inside; never fails the run sync)
        try:
            result["wellness"] = sync_wellness(user_id, db)
        except Exception as e:
            db.rollback()
            result["wellness"] = {"status": "error", "message": str(e)}
        if result.get('status') == 'ok':
            from app.services.coaching_jobs import release_synced_jobs
            release_synced_jobs(user_id, db)
        return result
    finally:
        db.close()


from pydantic import BaseModel, Field


class PersonalConnection(BaseModel):
    api_key:str=Field(min_length=20,max_length=4096)


@router.post('/connect/{user_id}')
def connect_personal(user_id:int,data:PersonalConnection,db:Session=Depends(get_db)):
    from app.config import settings
    from app.models.operations import ProviderCredential
    from app.services.provider_connections import cipher
    if user_id!=settings.default_user_id:
        raise HTTPException(409,'Separate Garmin accounts require the approved Business integration. Import FIT files in the meantime.')
    row=db.get(ProviderCredential,user_id)
    if row is None:
        row=ProviderCredential(user_id=user_id,kind='garmin_personal');db.add(row)
    try:
        row.ciphertext=cipher().encrypt(data.api_key.encode()).decode()
    except GarminNotConnected:
        raise HTTPException(503,'Private provider credential storage is not configured.')
    row.revoked_at=None
    row.kind='garmin_personal'
    row.expires_at=None
    conn=db.query(GarminConnection).filter_by(user_id=user_id).first()
    if conn:
        conn.connected=False
        conn.backoff_until=None
        conn.last_error=None
    # A replacement key must not inherit a failed job's retry delay.
    from app.models.operations import SyncJob
    job=db.get(SyncJob,user_id)
    if job and job.status in {'retry','error'}:
        job.status,job.lease_token='cancelled',None
    db.commit()
    return {'saved':True,'verified':False,'message':'Key saved privately. Sync to verify it.'}


@router.post('/reconnect/{user_id}')
def reconnect_server_key(user_id: int, db: Session = Depends(get_db)):
    """Explicitly re-enable the owner's existing server key after disconnect/rotation."""
    from app.api.plans import _begin_schedule_write
    from app.models.operations import ProviderCredential, SyncJob
    from app.services.sync_jobs import enqueue
    if user_id != settings.default_user_id:
        raise HTTPException(409, 'The server Garmin key is available only to its owner.')
    if not settings.garmin_api_key.strip():
        raise HTTPException(409, 'Add GARMIN_API_KEY in Render Environment, save and redeploy, then reconnect.')
    _begin_schedule_write(db)
    if not db.get(User, user_id):
        raise HTTPException(404, 'User not found')
    job = db.get(SyncJob, user_id)
    from app.services.accounts import utcnow
    if job and job.status == 'running' and job.lease_until and job.lease_until > utcnow():
        raise HTTPException(409, 'A sync is still running. Wait for it to finish before reconnecting.')
    row = db.get(ProviderCredential, user_id)
    if row is None:
        row = ProviderCredential(user_id=user_id)
        db.add(row)
    row.kind, row.ciphertext, row.revoked_at, row.expires_at = 'garmin_environment', '', None, None
    conn = db.query(GarminConnection).filter_by(user_id=user_id).first()
    if conn:
        conn.connected, conn.last_error, conn.backoff_until = False, None, None
    if job:
        job.status, job.lease_token = 'cancelled', None
    db.commit()
    return enqueue(user_id, db)


@router.post('/disconnect/{user_id}')
def disconnect(user_id:int,db:Session=Depends(get_db)):
    from app.models.operations import ProviderCredential,SyncJob
    row=db.get(ProviderCredential,user_id)
    if row is None:
        row=ProviderCredential(user_id=user_id,kind='disabled',ciphertext='');db.add(row)
    from app.services.accounts import utcnow
    row.ciphertext,row.revoked_at='',utcnow()
    from app.services.provider_connections import _personal_client,_owner_client
    _personal_client.cache_clear();_owner_client.cache_clear()
    job=db.get(SyncJob,user_id)
    if job:
        job.status,job.lease_token='cancelled',None
    conn=db.query(GarminConnection).filter_by(user_id=user_id).first()
    if conn:conn.connected=False
    db.commit()
    return {'disconnected':True,'message':'Stored credentials removed; revoke the key at Garmin too.'}
