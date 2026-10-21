"""End-to-end API tests against a temp SQLite DB (see conftest.py)."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.garmin import GarminConnection
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.services import garmin

client = TestClient(app)
MI = 1609.34


def _seed_runs(days: int = 60, skip_recent: int = 0):
    db = SessionLocal()
    for i in range(skip_recent, days):
        d = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0) - timedelta(days=i + 1)
        if d.weekday() == 4:
            continue
        db.add(Activity(user_id=1, source="garmin", external_id=f"g{i}", name="Run", date=d,
                        distance_meters=6 * MI, duration_seconds=6 * 540, average_pace_per_km=540 / 1.60934))
    db.commit()
    db.close()


def _preview_and_approve():
    result = client.post("/api/plans/1/generate")
    assert result.status_code == 200, result.text
    approved = client.post(f"/api/plans/1/drafts/{result.json()['id']}/approve")
    assert approved.status_code == 200, approved.text
    return result


def test_generate_plan_prescribes_today():
    _seed_runs()
    r = _preview_and_approve()
    assert r.status_code == 200, r.text
    db = SessionLocal()
    plan = db.query(Plan).filter(Plan.is_active == True).one()  # noqa: E712
    assert plan.prescribed_from == date.today().isoformat()
    db.close()
    current = client.get("/api/plans/1/current").json()
    today = next(d for w in current["weeks"] for d in w["days"] if d["date"] == date.today().isoformat())
    assert today["prescribed"] is True
    assert current["is_stale"] is False


def _workout_day_with_run() -> str:
    """Active plan whose day today is a 6x800m workout, plus a matching run."""
    db = SessionLocal()
    today = date.today().isoformat()
    plan = Plan(user_id=1, start_date=today, end_date=(date.today() + timedelta(days=13)).isoformat(),
                is_active=True, prescribed_from=today)
    db.add(plan)
    db.flush()
    db.add(PlannedWorkout(plan_id=plan.id, date=today, day_name="monday", week_number=1, type="workout",
                          title="6x800m", description="6x800m at 5:50-6:00/mi", distance_miles=6.5))
    db.add(PlannedWorkout(plan_id=plan.id, date=(date.today() + timedelta(days=2)).isoformat(), day_name="wed",
                          week_number=1, type="workout", title="2x10min Hard", distance_miles=5.5))
    db.add(PlannedWorkout(plan_id=plan.id, date=(date.today() + timedelta(days=4)).isoformat(), day_name="fri",
                          week_number=1, type="workout", title="4x1mi", distance_miles=8))
    db.add(Activity(user_id=1, source="garmin", external_id="w1", name="Track", date=datetime.now(),
                    distance_meters=6.5 * MI, duration_seconds=6.5 * 420,
                    description="Garmin laps: 6x800 (2:55, 2:56, 2:54, 2:55, 2:56, 2:55)", has_workout_description=True))
    db.add(WorkoutProgression(user_id=1, category="intervals", current_level=5, sessions_at_level=0, format_rotation=0))
    db.commit()
    db.close()
    return today


def test_feedback_resubmit_does_not_repeat_side_effects():
    today = _workout_day_with_run()
    body = {"feel_rating": 3, "pace_assessment": "on_target"}

    first = client.post(f"/api/plans/1/feedback/{today}", json=body)
    assert first.status_code == 200, first.text
    db = SessionLocal()
    level_after_first = db.query(WorkoutProgression).filter_by(category="intervals").one().current_level
    easy_after_first = db.query(PlannedWorkout).filter(PlannedWorkout.type == "easy").count()
    db.close()
    assert easy_after_first == 1  # feel 3 downgraded exactly the next hard day

    second = client.post(f"/api/plans/1/feedback/{today}", json={**body, "feel_notes": "edited"})
    assert second.status_code == 200
    assert second.json()["plan_adjusted"] is False
    db = SessionLocal()
    assert db.query(WorkoutProgression).filter_by(category="intervals").one().current_level == level_after_first
    assert db.query(PlannedWorkout).filter(PlannedWorkout.type == "easy").count() == 1  # not a second downgrade
    assert db.query(PlannedWorkout).filter_by(date=today).one().feel_notes == "edited"
    db.close()


def test_feedback_rating_is_validated():
    today = _workout_day_with_run()
    assert client.post(f"/api/plans/1/feedback/{today}", json={"feel_rating": 11}).status_code == 422


class FakeGarmin:
    def __init__(self, ids):
        self.ids = ids
        self.split_calls = []

    def get_full_name(self):
        return "Test Runner"

    def get_activities(self, start, limit):
        page = self.ids[start:start + limit]
        return [{"activityId": i, "activityName": "Run", "activityType": {"typeKey": "running"},
                 "startTimeLocal": (datetime(2026, 9, 1) - timedelta(days=n + start)).strftime("%Y-%m-%d %H:%M:%S"),
                 "distance": 8000, "duration": 2700, "movingDuration": 2700} for n, i in enumerate(page)]

    def get_activity_splits(self, aid):
        self.split_calls.append(aid)
        return {"lapDTOs": []}

    def get_activity(self, aid):
        return {}


def test_interrupted_full_import_resumes(monkeypatch):
    monkeypatch.setattr(garmin, "FULL_SYNC_DELAY", 0)
    fake = FakeGarmin(list(range(1, 151)))  # 150 runs, newest first
    monkeypatch.setattr(garmin, "get_client", lambda: fake)
    db = SessionLocal()
    # Simulate an import that died after storing the 40 newest runs
    for n, i in enumerate(range(1, 41)):
        db.add(Activity(user_id=1, source="garmin", external_id=str(i), name="Run",
                        date=datetime(2026, 9, 1) - timedelta(days=n), distance_meters=8000, duration_seconds=2700))
    db.add(GarminConnection(user_id=1, connected=True, full_sync_done=False))
    db.commit()

    result = garmin.sync_garmin(1, db)
    assert result["new"] == 110  # backfilled the rest instead of stopping at the first known run
    assert "1" not in fake.split_calls  # didn't redo already-imported runs
    assert db.query(GarminConnection).filter_by(user_id=1).one().full_sync_done is True
    db.close()


def test_garmin_status_get_does_not_write():
    r = client.get("/api/garmin/status/1")
    assert r.status_code == 200 and r.json()["connected"] is False
    db = SessionLocal()
    assert db.query(GarminConnection).count() == 0
    db.close()


def test_wellness_endpoint_shape():
    r = client.get("/api/wellness/1?days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["today"] is None and body["history"] == [] and body["signals"] == []
    assert body["freshness"] == "absent"


def test_stale_wellness_never_drives_signals():
    from app.models.wellness import DailyWellness

    db = SessionLocal()
    db.add(DailyWellness(user_id=1, date=(date.today() - timedelta(days=2)).isoformat(),
                         hrv_last_night=50, hrv_baseline_low=78, readiness_score=30, readiness_level="POOR"))
    db.commit()
    db.close()
    body = client.get("/api/wellness/1?days=7").json()
    assert body["freshness"] == "stale" and body["today"] is None and body["signals"] == []
    assert body["latest"]["readiness_score"] == 30 and body["as_of"] == (date.today() - timedelta(days=2)).isoformat()


def _past_block(run_fraction: float, feel: int | None = None):
    """An active plan covering the last 14 days, plus runs covering run_fraction of it."""
    db = SessionLocal()
    start = date.today() - timedelta(days=14)
    plan = Plan(user_id=1, start_date=start.isoformat(), end_date=(date.today() - timedelta(days=1)).isoformat(),
                is_active=True, prescribed_from=start.isoformat(), block_number=1)
    db.add(plan)
    db.flush()
    for i in range(14):
        d = start + timedelta(days=i)
        kind = "rest" if d.weekday() == 4 else ("long_run" if d.weekday() == 5 else ("workout" if d.weekday() in (1, 3) else "easy"))
        miles = 0 if kind == "rest" else (10 if kind == "long_run" else 5)
        from app.core.workout_data import prescription, segment
        from tests.test_workout_data import run_work
        import json
        contract = prescription("threshold", "time_intervals", [segment(2, seconds=360, fast=435, slow=435, recovery_seconds=120)]) if kind == "workout" else None
        db.add(PlannedWorkout(plan_id=plan.id, date=d.isoformat(), day_name="x", week_number=i // 7 + 1,
                              type=kind, title=kind, distance_miles=miles, feel_rating=feel if miles else None,
                              prescription=json.dumps(contract) if contract else None))
        if miles and (i % 10) / 10 < run_fraction:
            db.add(Activity(user_id=1, source="garmin", external_id=f"b{i}", name="Run",
                            date=datetime.combine(d, datetime.min.time()).replace(hour=7),
                            distance_meters=miles * MI, duration_seconds=miles * 540,
                            average_pace_per_km=540 / 1.60934,
                            splits=run_work(contract).splits if contract else None))
    db.commit()
    db.close()


def test_two_block_cycle_well_run_block_builds():
    _seed_runs(40)
    _past_block(1.0, feel=7)
    r = _preview_and_approve()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assessment"]["decision"] == "build"
    # Seeded history is weeks of steady loaded running, so a history-based deload is
    # also due; the build shows in week 1, the deload in the first full future week.
    assert body["load"]["mode"] in ("build", "deload")
    if body['load']['mode'] == 'deload':
        assert min(body['load']['weekly_budgets']) < body['load']['baseline']
    else:
        assert body["load"]["weekly_budgets"][0] > body["load"]["baseline"]
    current = client.get("/api/plans/1/current").json()
    assert current["assessment"]["decision"] == "build"  # persisted, survives reload
    assert any("planned miles" in n for n in current["notes"])


def test_two_block_cycle_interrupted_block_reduces():
    _seed_runs(60, skip_recent=14)  # history, then a 2-week interruption
    _past_block(0.3)
    body = client.post("/api/plans/1/generate").json()
    assert body["assessment"]["decision"] == "reduce"
    assert body["load"]["mode"] == "reduce"
    assert all(b < body["load"]["baseline"] for b in body["load"]["weekly_budgets"])


def test_failed_generation_keeps_previous_plan(monkeypatch):
    _seed_runs(40)
    _past_block(1.0)
    import app.api.plans as plans_api

    def boom(**kw):
        raise RuntimeError("engine failure")

    monkeypatch.setattr(plans_api, "generate_plan", boom)
    with pytest.raises(RuntimeError):
        client.post("/api/plans/1/generate")
    db = SessionLocal()
    active = db.query(Plan).filter(Plan.is_active == True).all()  # noqa: E712
    assert len(active) == 1 and active[0].block_number == 1
    db.close()


def test_mileage_goal_flows_into_plan():
    _seed_runs(40)
    db = SessionLocal()
    db.query(Goal).update({"active": False})
    db.add(Goal(user_id=1, goal_type="mileage", target_weekly_mileage=75, active=True))
    db.commit()
    db.close()
    body = client.post("/api/plans/1/generate").json()
    assert body["load"]["destination"] == 75
    assert body["goal"]["target_weekly_mileage"] == 75
    assert max(body["load"]["weekly_budgets"]) < 75


def test_profile_update_is_idempotent_and_validated():
    body = {"age": 21, "units": "miles", "days_per_week": 6, "rest_days": ["friday"], "long_run_day": "saturday",
            "current_weekly_mileage": 31, "pr_5k_seconds": 1106}
    for _ in range(2):  # re-running setup updates the same athlete, no duplicates
        r = client.put("/api/users/1/profile", json=body)
        assert r.status_code == 200, r.text
    db = SessionLocal()
    assert db.query(User).count() == 1
    u = db.query(User).one()
    assert u.rest_days == "friday" and u.pr_5k == 1106 and u.current_weekly_mileage == 31
    db.close()
    assert client.put("/api/users/1/profile", json={"rest_days": ["saturday"], "long_run_day": "saturday"}).status_code == 422
    assert client.put("/api/users/1/profile", json={"days_per_week": 7, "rest_days": ["sunday"]}).status_code == 422
    assert client.put("/api/users/1/profile", json={"units": "kilometers"}).status_code == 422


def test_long_finished_block_is_not_assessed():
    _seed_runs(40)
    db = SessionLocal()
    old = date.today() - timedelta(days=120)
    db.add(Plan(user_id=1, start_date=old.isoformat(), end_date=(old + timedelta(days=13)).isoformat(),
                is_active=True, prescribed_from=old.isoformat()))
    db.commit()
    db.close()
    body = client.post("/api/plans/1/generate").json()
    assert body["assessment"] is None  # months-old block is history, not evidence
