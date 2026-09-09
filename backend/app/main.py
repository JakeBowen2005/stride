from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.analysis import router as analysis_router
from app.api.plans import router as plans_router
from app.api.strava import router as strava_router
from app.api.users import router as users_router
from app.database import Base, engine, ensure_schema
import app.models  # noqa: F401 — registers all models so create_all picks them up

# Create all tables, then patch in any columns added to existing tables.
Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="Stride", description="AI-Powered Running Coach", version="0.1.0")

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(plans_router)
app.include_router(strava_router)
app.include_router(users_router)


@app.get("/")
def root():
    return {"app": "Stride", "version": "0.1.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}
