import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.coaching import router as coaching_router
from app.api.analysis import router as analysis_router
from app.api.garmin import router as garmin_router, _sync_in_new_session
from app.api.plans import router as plans_router
from app.api.wellness import router as wellness_router
from app.api.users import router as users_router
from app.database import Base, add_missing_columns, engine
from app.services.garmin import GarminNotConnected, clear_backoff, has_api_key, poll_due
import app.models  # noqa: F401 — registers all models so create_all picks them up

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("stride")

# Protect existing data BEFORE schema migration or stored-data reclassification,
# including direct uvicorn/local startup. Tests point settings at disposable files.
def _protect_existing_database():
    import os
    from app.services.backups import backup_once, database_path
    if settings.database_url.startswith('sqlite:///'):
        source = database_path(settings.database_url)
        if source.exists():
            from pathlib import Path
            backup_once(source, Path(os.environ.get('STRIDE_BACKUP_DIR', str(source.parent / 'backups'))),
                        keep=int(os.environ.get('STRIDE_BACKUP_KEEP', '28')), reason='before-app-migration')


_protect_existing_database()

# Create new tables, then add any new columns to existing ones
Base.metadata.create_all(bind=engine)
add_missing_columns()


def _refresh_lap_summaries():
    """Tag walks and re-read stored lap summaries with the current analyzer. Never blocks startup."""
    from app.database import SessionLocal
    from app.models.activity import Activity, is_walk
    from app.services.garmin import refresh_lap_summaries
    try:
        with SessionLocal() as db:
            rows = db.query(Activity).all()
            # Repair old pace-only exclusions for explicit outdoor runs/races.
            for activity in rows:
                if activity.workout_type == "walk" and not is_walk(activity):
                    activity.workout_type = "race" if activity.event_type == "race" else "easy"
            walks = [a for a in rows if is_walk(a) and a.workout_type != "walk"]
            for activity in walks:
                activity.workout_type = "walk"
            db.commit()
            changed = refresh_lap_summaries(db)
        if walks:
            logger.info("Tagged %d walks (not part of the running plan)", len(walks))
        if changed:
            logger.info("Refreshed %d stored Garmin lap summaries", changed)
    except Exception as e:  # noqa: BLE001 — a summary refresh must never stop the API
        logger.warning("Lap summary refresh skipped: %s", type(e).__name__)


_refresh_lap_summaries()


async def garmin_auto_sync():
    """Check Garmin for new runs. The Personal API is pull-only (no webhooks), but a check
    is a single date-windowed request, and opening the app also syncs. The loop wakes
    every minute and only calls Garmin when `poll_due` says the last sync is old enough."""
    await asyncio.sleep(5)  # let the server finish starting
    if has_api_key():
        await asyncio.to_thread(clear_backoff, settings.default_user_id)
    while True:
        if has_api_key():
            try:
                if await asyncio.to_thread(poll_due, settings.default_user_id):
                    result = await asyncio.to_thread(_sync_in_new_session, settings.default_user_id, False)
                    if result.get("new") or result.get("merged"):
                        logger.info("Garmin auto-sync: %s", result.get("message"))
            except GarminNotConnected:
                pass
            except Exception as e:
                logger.warning("Garmin auto-sync failed: %s", e)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.garmin_poll_minutes > 0:
        task = asyncio.create_task(garmin_auto_sync())
    from app.services.coaching_jobs import coaching_worker
    coach_task = asyncio.create_task(coaching_worker()) if settings.openai_auto_reviews else None
    yield
    for running in (task, coach_task):
        if running:
            running.cancel()
    await asyncio.gather(*(running for running in (task, coach_task) if running), return_exceptions=True)


app = FastAPI(title="Stride", description="AI-Powered Running Coach", version="0.2.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(coaching_router)
app.include_router(analysis_router)
app.include_router(garmin_router)
app.include_router(plans_router)
app.include_router(users_router)
app.include_router(wellness_router)


@app.get("/")
def root():
    return {"app": "Stride", "version": "0.2.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Bounded SQL readiness, distinct from process liveness (/health)."""
    from fastapi import HTTPException
    from sqlalchemy import text
    from app.database import SessionLocal
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT id FROM users LIMIT 1")).first()
    except Exception:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ready"}
