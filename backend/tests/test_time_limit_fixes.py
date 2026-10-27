"""Daily time limits: reducing load is always allowed, and long runs move instead of shrinking."""
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.plan_engine import generate_plan
from app.database import SessionLocal
from app.main import app
from app.models.user import User
from tests.test_adaptation_edge_cases import _plan

client = TestClient(app)


def _limit_tomorrow(minutes):
    tomorrow = date.today() + timedelta(days=1)
    with SessionLocal() as db:
        db.get(User, 1).day_time_budgets = json.dumps({tomorrow.strftime("%A").lower(): minutes})
        db.commit()


def test_lower_availability_never_blocks_skipping_or_shortening():
    # Tomorrow's 7-mile run was approved before the athlete lowered that day to 30 minutes.
    _plan([(1, "easy", "Easy Run", 7.0), (2, "easy", "Easy Run", 4.0), (3, "easy", "Easy Run", 4.0)], budgets=[30, 30])
    _limit_tomorrow(30)
    today = date.today()
    skip_other = client.post(f"/api/plans/1/sessions/{today + timedelta(days=2)}", json={"action": "skip"})
    assert skip_other.status_code == 200, skip_other.text  # an untouched over-limit day doesn't block edits
    shorten = client.post(f"/api/plans/1/sessions/{today + timedelta(days=1)}",
                          json={"action": "replace", "replacement": "easy", "distance_miles": 5})
    assert shorten.status_code == 200, shorten.text  # still over 30 min, but shorter than before: allowed
    grow = client.post(f"/api/plans/1/sessions/{today + timedelta(days=3)}",
                       json={"action": "replace", "replacement": "easy", "distance_miles": 4})
    assert grow.status_code == 200  # that day has no limit


def test_edits_that_add_time_past_a_limit_are_still_refused():
    _plan([(1, "easy", "Easy Run", 3.0), (2, "easy", "Easy Run", 4.0)], budgets=[30, 30])
    _limit_tomorrow(30)
    r = client.post(f"/api/plans/1/sessions/{date.today() + timedelta(days=1)}",
                    json={"action": "replace", "replacement": "easy", "distance_miles": 6})
    assert r.status_code == 409 and "available 30 minutes" in r.json()["detail"]


def _plan_with(limits, experience="advanced", mpw=45):
    return generate_plan(goal_type="race", goal_distance="5k", target_time_seconds=1020, current_weekly_mileage=mpw,
                         peak_weekly_mileage=60, experience_level=experience, days_per_week=6, rest_days=["friday"],
                         long_run_day="saturday", easy_pace_seconds=480, start_date=date(2026, 10, 26), num_weeks=2,
                         first_prescribe_date=date(2026, 10, 26), race_date=date(2027, 2, 20),
                         completed_weeks=[mpw] * 8, weekly_run_days=[6] * 4, day_time_budgets=limits)


def test_a_long_run_that_does_not_fit_moves_to_the_nearest_roomy_day():
    free = _plan_with({})
    tight = _plan_with({"saturday": 60})
    for before, after in zip(free["weeks"], tight["weeks"]):
        original = next(d for d in before["days"] if d["type"] == "long_run")
        moved = next(d for d in after["days"] if d["type"] == "long_run")
        assert moved["day"].lower() == "sunday" and moved["distance_miles"] == original["distance_miles"]
        assert moved["distance_miles"] > max(d["distance_miles"] for d in after["days"] if d is not moved)
    assert any("Moved the long run" in n for n in tight["notes"])
    assert tight["violations"] == []


def test_a_long_run_is_only_cut_when_no_day_has_room():
    limits = {d: 60 for d in ("monday", "tuesday", "wednesday", "thursday", "saturday", "sunday")}
    plan = _plan_with(limits)
    longs = [d for w in plan["weeks"] for d in w["days"] if d["type"] == "long_run"]
    assert longs and all(d["distance_miles"] <= 60 * 60 / 480 + .05 for d in longs)
    assert any("fitted to 60 available minutes" in n for n in plan["notes"])
