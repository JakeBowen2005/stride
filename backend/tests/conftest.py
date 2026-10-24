"""Point the app at a throwaway SQLite file *before* any app module is imported,
so API tests never touch the real stride.db and the Garmin poller stays off."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="stride-test-")
os.environ["FIT_BLOB_BUCKET"] = ""
os.environ["SCHEMA_AUTO_UPGRADE"] = "true"
os.environ["EMBEDDED_WORKERS"] = "false"
os.environ["STRIDE_ACCOUNTS_ENABLED"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["GARMIN_POLL_MINUTES"] = "0"
os.environ["GARMIN_API_KEY"] = ""  # never call the real Garmin API, regardless of local .env
os.environ["ANTHROPIC_API_KEY"] = ""  # coach uses template responses
os.environ["OPENAI_API_KEY"] = ""  # all normal tests are offline, regardless of local .env
os.environ["OPENAI_AUTO_REVIEWS"] = "false"


import pytest  # noqa: E402

# STRIDE_TEST_DATE=2026-10-21 (or a weekday name, e.g. "wed") freezes the whole
# suite to that day, so weekday-sensitive plan logic can be checked on all 7
# days: `for d in mon tue wed thu fri sat sun; do STRIDE_TEST_DATE=$d pytest -q; done`
# Travel starts here, at conftest import, so module-level `date.today()` in test
# files (evaluated at collection) sees the frozen day too.
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _test_date():
    from datetime import date, timedelta

    raw = os.environ.get("STRIDE_TEST_DATE", "").strip().lower()
    if not raw:
        return None
    if raw[:3] in _WEEKDAYS:  # fixed reference week: Mon 2026-10-19 .. Sun 2026-10-25
        return date(2026, 10, 19) + timedelta(days=_WEEKDAYS.index(raw[:3]))
    return date.fromisoformat(raw)


_traveller = None
if (_day := _test_date()) is not None:
    import datetime as _dt

    import time_machine

    _traveller = time_machine.travel(_dt.datetime.combine(_day, _dt.time(9)), tick=True)
    _traveller.start()


def pytest_report_header(config):
    return f"STRIDE_TEST_DATE: {_day:%a %Y-%m-%d}" if _traveller else None


def pytest_unconfigure(config):
    if _traveller:
        _traveller.stop()


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
