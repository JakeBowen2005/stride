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
    # Read-only: no row yet just means "never connected"
    conn = db.query(GarminConnection).filter(GarminConnection.user_id == user_id).first() or GarminConnection(
        user_id=user_id, connected=False, full_sync_done=False
    )
    return {
        "api_key_present": has_api_key(),
        "connected": conn.connected and has_api_key(),
        "display_name": conn.display_name,
        "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
        "last_new_activity_at": conn.last_new_activity_at.isoformat() if conn.last_new_activity_at else None,
        "last_error": conn.last_error,
        "full_sync_done": bool(conn.full_sync_done),
        "backoff_until": conn.backoff_until.isoformat() if conn.backoff_until else None,
        "full_sync_job": _full_sync_jobs.get(user_id),
    }


@router.post("/sync/{user_id}")
async def garmin_sync(user_id: int, db: Session = Depends(get_db)):
    """Pull new runs from Garmin (incremental; first ever sync pulls full history)."""
    if not db.query(User).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")
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
    if not has_api_key():
        raise HTTPException(status_code=409, detail="Garmin not connected. Set GARMIN_API_KEY (a Garmin Connect Personal API key).")
    job = _full_sync_jobs.get(user_id)
    if job and job["state"] == "running":
        return job

    _full_sync_jobs[user_id] = {"state": "running", "result": None}

    async def run():
        try:
            result = await asyncio.to_thread(_sync_in_new_session, user_id, True)
            _full_sync_jobs[user_id] = {"state": "done", "result": result}
        except Exception:
            logger.exception("Full Garmin import failed")
            _full_sync_jobs[user_id] = {"state": "error", "result": "Import failed. Check the Stride terminal for details."}

    task = asyncio.create_task(run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return _full_sync_jobs[user_id]


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
