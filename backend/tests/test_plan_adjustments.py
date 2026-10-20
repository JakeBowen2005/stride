"""Priority 3: feedback adjustments are explicit, safe, and applied once."""

import json
import threading
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
import app.services.coach as coach

client = TestClient(app)
MI = 1609.34
TODAY = date.today()


def _plan(days: list[tuple[int, str, str, float]]):
    """days: (offset from today, type, title, miles)."""
    db = SessionLocal()
    p = Plan(user_id=1, start_date=(TODAY - timedelta(days=1)).isoformat(),
             end_date=(TODAY + timedelta(days=12)).isoformat(), is_active=True,
             prescribed_from=(TODAY - timedelta(days=1)).isoformat())
    db.add(p)
    db.flush()
    for off, typ, title, miles in days:
        db.add(PlannedWorkout(plan_id=p.id, date=(TODAY + timedelta(days=off)).isoformat(), day_name="x",
                              week_number=1, type=typ, title=title, description=f"{title} at 5:50-6:00/mi",
                              distance_miles=miles))
    db.add(WorkoutProgression(user_id=1, category="intervals", current_level=5, sessions_at_level=0, format_rotation=0))
    db.add(WorkoutProgression(user_id=1, category="threshold", current_level=3, sessions_at_level=0, format_rotation=0))
    db.commit()
    db.close()


def _run(off: int, miles: float, desc: str | None = None, ext="a"):
    db = SessionLocal()
    db.add(Activity(user_id=1, source="garmin", external_id=f"{ext}{off}{miles}", name="Run",
                    date=datetime.combine(TODAY + timedelta(days=off), datetime.min.time()).replace(hour=7),
                    distance_meters=miles * MI, duration_seconds=miles * 480, description=desc,
                    has_workout_description=bool(desc)))
    db.commit()
    db.close()


def _day(off: int) -> PlannedWorkout:
    db = SessionLocal()
    d = db.query(PlannedWorkout).filter(PlannedWorkout.date == (TODAY + timedelta(days=off)).isoformat()).one()
    db.expunge(d)
    db.close()
    return d


def test_explicit_skip_creates_no_replacement():
    _plan([(0, "workout", "6x800m", 7), (1, "easy", "Easy Run", 5), (3, "easy", "Easy Run", 5)])
    _run(0, 4)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 6, "swapped": True, "actual_workout_type": "easy", "desired_reschedule_type": "skip",
        "swap_reason": "felt tired, want intervals later",  # notes must not override the explicit choice
    }).json()
    assert r["plan_adjusted"] is False and r["changes"] == []
    assert _day(1).type == "easy" and _day(3).type == "easy"


def test_no_safe_slot_explains_instead_of_stacking():
    # Every remaining easy day is next to a hard day
    _plan([(0, "workout", "6x800m", 7), (1, "easy", "Easy Run", 5), (2, "long_run", "Long", 10)])
    _run(0, 4)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 6, "swapped": True, "actual_workout_type": "easy", "desired_reschedule_type": "intervals",
    }).json()
    assert r["changes"][0]["change"] == "not_rescheduled" and "dropped rather than stacked" in r["changes"][0]["reason"]
    assert _day(1).type == "easy"


def test_safe_slot_reschedules_and_records_original():
    _plan([(0, "workout", "6x800m", 7), (2, "easy", "Easy Run", 5), (3, "easy", "Easy Run", 5),
           (4, "easy", "Easy Run", 5), (6, "long_run", "Long", 10)])
    _run(0, 4)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 6, "swapped": True, "actual_workout_type": "easy", "desired_reschedule_type": "threshold",
    }).json()
    moved = r["changes"][0]
    assert moved["change"] == "rescheduled" and r["plan_adjusted"] is True
    day = _day((date.fromisoformat(moved["date"]) - TODAY).days)
    assert day.type == "workout" and json.loads(day.original_prescription)["type"] == "easy"


def test_split_recordings_use_the_workout_activity():
    _plan([(0, "workout", "6x800m", 7)])
    _run(0, 2.0, "Warmup", ext="w")
    _run(0, 3.0, "Garmin laps: 6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59) w/ 90s recovery", ext="m")
    _run(0, 2.5, "Cooldown", ext="c")  # longest non-work activity would have been picked before
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={"feel_rating": 8}).json()
    assert r["evaluation"]["evidence"] == "splits" and r["evaluation"]["decision"] == "advance"
    assert len(r["evaluation"]["activity_ids"]) == 3


def test_concurrent_duplicate_submissions_apply_once():
    _plan([(0, "workout", "6x800m", 7), (2, "workout", "2x10min Hard", 6), (4, "workout", "4x1mi", 8)])
    _run(0, 7, "Garmin laps: 6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)")
    results = []
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait()
        results.append(client.post(f"/api/plans/1/feedback/{TODAY}", json={"feel_rating": 3}).json())

    threads = [threading.Thread(target=submit) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r["side_effects_applied"] for r in results) == [False, True]
    db = SessionLocal()
    assert db.query(PlannedWorkout).filter(PlannedWorkout.type == "easy").count() == 1  # one downgrade only
    db.close()


def test_coach_failure_keeps_feedback_and_decision(monkeypatch):
    _plan([(0, "workout", "6x800m", 7)])
    _run(0, 7, "Garmin laps: 6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)")
    monkeypatch.setattr(coach.settings, "anthropic_api_key", "test-key")

    class Boom:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("LLM down")

    monkeypatch.setattr(coach, "_client", lambda: Boom())
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={"feel_rating": 8})
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["decision"] == "advance"
    assert "Progression decision: advance" in body["coach_response"]  # template carries the real decision
    db = SessionLocal()
    assert db.query(WorkoutProgression).filter_by(category="intervals").one().current_level == 6
    db.close()


def test_failed_side_effects_release_the_claim(monkeypatch):
    _plan([(0, "workout", "6x800m", 7)])
    _run(0, 7, "Garmin laps: 6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)")
    import app.api.plans as plans_api

    real = plans_api._apply_feedback_effects
    monkeypatch.setattr(plans_api, "_apply_feedback_effects", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    try:
        client.post(f"/api/plans/1/feedback/{TODAY}", json={"feel_rating": 8})
    except RuntimeError:
        pass
    assert _day(0).side_effects_applied_at is None and _day(0).feel_rating == 8  # feedback kept, claim released
    monkeypatch.setattr(plans_api, "_apply_feedback_effects", real)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={"feel_rating": 8}).json()
    assert r["side_effects_applied"] is True  # retry applies exactly once


def test_reschedule_respects_weekly_budget():
    _plan([(0, "workout", "6x800m", 7), (2, "easy", "Easy Run", 3), (3, "easy", "Easy Run", 3),
           (4, "easy", "Easy Run", 3), (6, "long_run", "Long", 8)])
    db = SessionLocal()
    p = db.query(Plan).filter(Plan.is_active == True).one()  # noqa: E712
    p.load = json.dumps({"weekly_budgets": [23.0, 23.0]})  # Actual source was 4 mi: replacement yields 24.5, over 23.5, and easy days are at the floor
    db.commit()
    db.close()
    _run(0, 4)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 6, "swapped": True, "actual_workout_type": "easy", "desired_reschedule_type": "intervals",
    }).json()
    assert r["changes"][0]["change"] == "not_rescheduled" and "budget" in r["changes"][0]["reason"]
