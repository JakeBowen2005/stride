from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

def _normalize_db_url(url: str) -> str:
    """Railway and Heroku hand out `postgres://` URLs.

    SQLAlchemy 2.x dropped that alias and only recognises `postgresql://`,
    so a working DATABASE_URL from the platform fails at import time.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # Pin the driver explicitly. requirements.txt ships psycopg 3; without the
    # dialect suffix SQLAlchemy defaults to psycopg2, which is not installed.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_db_url(settings.database_url)
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Managed Postgres drops idle connections; without pre-ping the first
    # query after an idle period fails instead of reconnecting.
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Lightweight additive migrations ───────────────────────────────
#
# There is no Alembic in this project yet, and Base.metadata.create_all()
# only creates missing TABLES -- it will not add a column to a table that
# already exists. This closes that gap for the simple additive case so a
# schema change doesn't silently break an existing stride.db.
#
# If the schema starts needing renames, drops or backfills, replace this
# with real Alembic migrations.

_ADDITIVE_COLUMNS = [
    # (table, column, DDL type + default)
    ("workout_progressions", "distance", "VARCHAR DEFAULT '5k' NOT NULL"),
]


def ensure_schema() -> None:
    """Add any missing columns listed in _ADDITIVE_COLUMNS. Idempotent."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl in _ADDITIVE_COLUMNS:
            if table not in existing_tables:
                continue  # create_all already built it with the column
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            print(f"[schema] added {table}.{column}")
