"""Point the app at a throwaway SQLite file *before* any app module is imported,
so API tests never touch the real stride.db and the Garmin poller stays off."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stride-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["GARMIN_POLL_MINUTES"] = "0"
os.environ["GARMIN_TOKENSTORE"] = os.path.join(_tmp, "garmin")
os.environ["ANTHROPIC_API_KEY"] = ""  # coach uses template responses
os.environ["OPENAI_API_KEY"] = ""  # all normal tests are offline, regardless of local .env
os.environ["OPENAI_AUTO_REVIEWS"] = "false"


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Empty schema + one athlete with an active 5K goal, for every test."""
    from app.database import Base, SessionLocal, engine
    from app.models.user import Goal, User

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(id=1, name="Test Runner", days_per_week=6, rest_days="friday", long_run_day="saturday"))
    db.add(Goal(user_id=1, goal_type="race", race_distance="5k", target_time_seconds=1020, active=True))
    db.commit()
    db.close()
    yield
