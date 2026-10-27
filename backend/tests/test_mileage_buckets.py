"""History mileage: week/month/year buckets, zero-filled, planned from approved blocks only."""
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.athlete_clock import today
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout

client = TestClient(app)
MI = 1609.34


def _run(db, day: date, miles: float, key: str):
    db.add(Activity(user_id=1, source="garmin", external_id=key, name="Run",
                    date=datetime.combine(day, datetime.min.time()).replace(hour=7),
                    distance_meters=miles * MI, duration_seconds=int(miles * 480)))


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def test_weeks_without_runs_are_zero_not_missing():
    monday = _monday(today())
    db = SessionLocal()
    _run(db, monday - timedelta(weeks=3), 5, "a")
    _run(db, monday - timedelta(weeks=3) + timedelta(days=1), 4, "b")
    _run(db, monday, 6, "c")
    db.commit()
    db.close()

    rows = client.get("/api/analysis/1/mileage?bucket=week&count=4").json()
    assert [r["period_start"] for r in rows] == [(monday - timedelta(weeks=n)).isoformat() for n in (3, 2, 1, 0)]
    assert [r["actual"] for r in rows] == [9.0, 0.0, 0.0, 6.0]
    assert [r["runs"] for r in rows] == [2, 0, 0, 1]
    assert [r["partial"] for r in rows] == [False, False, False, True]
    assert all(r["planned"] is None for r in rows)


def test_months_cross_the_year_boundary():
    rows = client.get("/api/analysis/1/mileage?bucket=month&count=14").json()
    starts = [date.fromisoformat(r["period_start"]) for r in rows]
    assert len(starts) == 14 and all(s.day == 1 for s in starts)
    assert starts[-1] == today().replace(day=1)
    assert all((b.year * 12 + b.month) - (a.year * 12 + a.month) == 1 for a, b in zip(starts, starts[1:]))


def test_years_start_at_first_recorded_run():
    db = SessionLocal()
    _run(db, today().replace(year=today().year - 2, month=6, day=15), 10, "old")
    _run(db, today(), 3, "now")
    db.commit()
    db.close()

    rows = client.get("/api/analysis/1/mileage?bucket=year").json()
    assert [r["period_start"][:4] for r in rows] == [str(today().year - n) for n in (2, 1, 0)]
    assert [r["actual"] for r in rows] == [10.0, 0.0, 3.0]


def test_planned_uses_latest_approved_block_and_ignores_drafts_and_moves():
    monday = _monday(today())
    db = SessionLocal()
    old = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
               is_active=False)
    new = Plan(user_id=1, start_date=(monday + timedelta(days=3)).isoformat(),
               end_date=(monday + timedelta(days=6)).isoformat(), is_active=True)
    draft = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
                 is_active=False, preview_state="draft")
    db.add_all([old, new, draft])
    db.flush()

    def day(plan, offset, miles, **extra):
        d = monday + timedelta(days=offset)
        db.add(PlannedWorkout(plan_id=plan.id, date=d.isoformat(), day_name=d.strftime("%A").lower(),
                              week_number=1, type="easy", title="Easy", distance_miles=miles, **extra))

    day(old, 0, 4)    # counts: no later block covers Monday
    day(old, 4, 9)    # replaced by the new block's Friday
    day(new, 4, 5)
    day(new, 5, 6, moved_to=(monday + timedelta(days=6)).isoformat())  # source of a move
    day(new, 6, 6)    # move destination
    day(draft, 1, 20)
    db.commit()
    db.close()

    rows = client.get("/api/analysis/1/mileage?bucket=week&count=2").json()
    assert rows[0]["planned"] is None
    assert rows[1]["planned"] == 15.0


def test_unknown_athlete_and_bucket_are_rejected():
    assert client.get("/api/analysis/99/mileage").status_code == 404
    assert client.get("/api/analysis/1/mileage?bucket=decade").status_code == 422


def _easy(db, day: date, pace: float, hr: float, key: str, climb: float = 20):
    db.add(Activity(user_id=1, source="garmin", external_id=key, name="Easy", workout_type="easy",
                    date=datetime.combine(day, datetime.min.time()).replace(hour=7),
                    distance_meters=6 * MI, duration_seconds=int(6 * pace), average_heartrate=hr,
                    elevation_gain=climb))


def test_aerobic_efficiency_scales_runs_to_one_heart_rate_and_skips_hills():
    monday = _monday(today())
    db = SessionLocal()
    for week in range(8):
        # Same 540 s/mi at 150 bpm early on; later the same pace costs only 140 bpm (fitter).
        hr = 150 if week >= 4 else 140
        for d in range(3):
            _easy(db, monday - timedelta(weeks=week) + timedelta(days=d), 540, hr, f"e{week}{d}")
    _easy(db, monday - timedelta(weeks=1), 900, 150, "hill", climb=500)
    db.commit()
    db.close()

    data = client.get("/api/analysis/1/aerobic-efficiency?weeks=8").json()
    assert data["reference_heartrate"] in (140, 150)
    paces = [w["pace_sec_per_mile"] for w in data["weeks"]]
    assert len(paces) == 8 and paces[0] > paces[-1]
    assert data["change_sec_per_mile"] < 0
    assert all("hill" not in str(w["activity_ids"]) for w in data["weeks"])
    assert sum(w["runs"] for w in data["weeks"]) == 24


def test_aerobic_efficiency_without_heart_rate_is_empty():
    data = client.get("/api/analysis/1/aerobic-efficiency").json()
    assert data["weeks"] == [] and data["change_sec_per_mile"] is None


def test_running_time_moving_elapsed_walks_and_missing_durations():
    monday = _monday(today())
    db = SessionLocal()
    db.add(Activity(user_id=1, source="garmin", external_id="t1", name="Run", date=datetime.combine(monday, datetime.min.time()),
                    distance_meters=5 * MI, duration_seconds=2400, elapsed_seconds=2700))
    db.add(Activity(user_id=1, source="garmin", external_id="t2", name="Run", date=datetime.combine(monday, datetime.min.time()),
                    distance_meters=3 * MI, duration_seconds=1500, elapsed_seconds=None))  # legacy row: elapsed = moving
    db.add(Activity(user_id=1, source="manual", external_id="t3", name="Run", date=datetime.combine(monday, datetime.min.time()),
                    distance_meters=2 * MI, duration_seconds=0))
    db.add(Activity(user_id=1, source="garmin", external_id="w", name="Walk", workout_type="walk",
                    date=datetime.combine(monday, datetime.min.time()), distance_meters=2 * MI, duration_seconds=2000))
    db.commit()
    db.close()
    row = client.get("/api/analysis/1/mileage?bucket=week&count=1&include=walks").json()[0]
    assert row["actual"] == 10.0 and row["runs"] == 3
    assert row["actual_seconds"] == 3900 and row["elapsed_seconds"] == 4200
    assert row["runs_without_time"] == 1 and row["walk_seconds"] == 2000
    assert "walk_seconds" not in client.get("/api/analysis/1/mileage?bucket=week&count=1").json()[0]


def test_planned_time_uses_the_blocks_frozen_easy_pace():
    import json
    monday = _monday(today())
    db = SessionLocal()
    plan = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
                athlete_snapshot=json.dumps({"easy_pace_seconds": 600}))
    db.add(plan)
    db.flush()
    db.add(PlannedWorkout(plan_id=plan.id, date=monday.isoformat(), day_name="monday", week_number=1,
                          type="easy", title="Easy", distance_miles=6))
    db.add(PlannedWorkout(plan_id=plan.id, date=(monday + timedelta(days=1)).isoformat(), day_name="tuesday", week_number=1,
                          type="rest", title="Rest", distance_miles=0))
    db.commit()
    db.close()
    row = client.get("/api/analysis/1/mileage?bucket=week&count=1").json()[0]
    assert row["planned"] == 6.0 and row["planned_seconds"] == 3600
