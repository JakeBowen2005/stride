import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.analysis import router as analysis_router
from app.api.garmin import router as garmin_router, _sync_in_new_session
from app.api.plans import router as plans_router
from app.api.wellness import router as wellness_router
from app.api.users import router as users_router
from app.database import Base, add_missing_columns, engine
from app.services.garmin import GarminNotConnected, has_tokens
import app.models  # noqa: F401 — registers all models so create_all picks them up

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("stride")

# Create new tables, then add any new columns to existing ones
Base.metadata.create_all(bind=engine)
add_missing_columns()


async def garmin_auto_sync():
    """Poll Garmin for new runs. Garmin offers no webhooks for personal use,
    so polling every few minutes is how new watch uploads appear automatically."""
    await asyncio.sleep(5)  # let the server finish starting
    while True:
        if has_tokens():
            try:
                result = await asyncio.to_thread(_sync_in_new_session, settings.default_user_id, False)
                if result.get("new") or result.get("merged"):
                    logger.info("Garmin auto-sync: %s", result.get("message"))
            except GarminNotConnected:
                pass
            except Exception as e:
                logger.warning("Garmin auto-sync failed: %s", e)
        await asyncio.sleep(max(settings.garmin_poll_minutes, 1) * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if settings.garmin_poll_minutes > 0:
        task = asyncio.create_task(garmin_auto_sync())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Stride", description="AI-Powered Running Coach", version="0.2.0", lifespan=lifespan)

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
