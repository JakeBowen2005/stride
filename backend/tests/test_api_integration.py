"""End-to-end API tests against a real (temporary) database.

Covers the full loop the product depends on:
    seed activities -> set goal -> generate plan -> edit plan -> feedback -> summary

These use SQLite, so they do not catch Postgres-specific SQL problems. They do
catch every wiring mistake between the API, the models and the plan engine.
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("STRAVA_CLIENT_ID", "test")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test")

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path.replace(os.sep, '/')}"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, ensure_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.models.activity import Activity  # noqa: E402
from app.models.user import User  # noqa: E402

MARATHON_245 = 9900.0
METERS_PER_MILE = 1609.34


@pytest.fixture(scope="module")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    seed_athlete()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    try:
        os.unlink(_db_path)
    except OSError:
        pass


def seed_athlete():
    """An athlete with a real marathon block behind them, currently building.

    Roughly Jake-shaped: threshold and interval sessions logged with splits in
    the description, because that is what pace calibration reads.
    """
    db = SessionLocal()
    try:
        user = User(
            name="Test Athlete",
            units="miles",
            days_per_week=6,
            rest_days="sunday",
            long_run_day="saturday",
            experience_level="advanced",
            strava_athlete_id=999,
            strava_connected=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        today = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)

        # A year of history: a marathon build, then current base work. A year
        # is what the analyzer needs to classify the athlete as advanced, and
        # roughly what Jake's real Strava account holds.
        workouts = [
            ("Threshold", "Main set 3x2 miles (6:36,6:36,6:20) 0.25 mile jog rest", 11.0, 470),
            ("Mile repeats", "4x1 mile (6:24,6:19,6:25,6:11) 3 min jog rest", 9.0, 455),
            ("Track", "6x800 (3:01,3:04,3:02,3:05,3:03,3:04) 90s jog", 6.5, 450),
        ]

        for week in range(52):
            week_start = today - timedelta(days=(week * 7) + today.weekday())
            for day_offset, miles in ((0, 8.0), (2, 8.0), (4, 8.0)):
                d = week_start + timedelta(days=day_offset)
                db.add(_activity(user.id, d, miles, 540, f"Easy run wk{week}"))

            name, desc, miles, pace = workouts[week % len(workouts)]
            db.add(_activity(
                user.id, week_start + timedelta(days=1), miles, pace,
                name, description=desc, workout_type="workout", has_desc=True,
            ))

            long_miles = 14.0 + (week % 4)
            db.add(_activity(
                user.id, week_start + timedelta(days=5), long_miles, 520,
                "Long run", workout_type="long_run",
            ))

        db.commit()
    finally:
        db.close()


def _activity(user_id, when, miles, pace_per_mile, name,
              description=None, workout_type="easy", has_desc=False):
    meters = miles * METERS_PER_MILE
    duration = miles * pace_per_mile
    return Activity(
        user_id=user_id,
        source="strava",
        external_id=f"seed-{user_id}-{when.isoformat()}-{name}",
        name=name,
        date=when,
        distance_meters=meters,
        duration_seconds=duration,
        elapsed_seconds=duration,
        average_pace_per_km=(duration / (meters / 1000)),
        average_heartrate=150,
        average_cadence=85,
        description=description,
        has_workout_description=has_desc,
        workout_type=workout_type,
    )


# ── Health and analysis ───────────────────────────────────────────

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_baseline_analysis_reads_the_seeded_history(client):
    r = client.get("/api/analysis/1/baseline")
    assert r.status_code == 200
    data = r.json()
    assert data["overview"]["experience_level"] == "advanced"
    assert data["current_fitness"]["weekly_mileage_4w_avg"] > 30
    assert data["paces"]["recent_easy_pace"]


def test_acwr_is_a_seven_vs_twenty_eight_day_ratio(client):
    """Steady mileage must not read as a spike."""
    data = client.get("/api/analysis/1/baseline").json()
    acwr = data["injury_risk"]["acute_chronic_ratio"]
    assert 0.7 < acwr < 1.4, f"steady training reported ACWR of {acwr}"


def test_pace_calibration_parses_the_workout_descriptions(client):
    r = client.get("/api/analysis/1/calibrated-paces")
    assert r.status_code == 200
    data = r.json()
    assert data["data_points"].get("interval", 0) > 0
    # 800m splits of ~3:02 -> about 6:05/mi
    assert 340 < data["interval_pace"] < 380


# ── Goal and plan generation ──────────────────────────────────────

def test_set_marathon_goal(client):
    r = client.post("/api/users/1/goal", json={
        "goal_type": "race",
        "race_distance": "marathon",
        "target_time_seconds": MARATHON_245,
        "race_date": "2028-02-06",
        "description": "Sub-2:45 Surf City Marathon",
    })
    assert r.status_code == 200

    goal = client.get("/api/plans/1/goal").json()
    assert goal["distance"] == "marathon"
    assert goal["race_date"] == "2028-02-06"


def test_generate_plan(client):
    r = client.post("/api/plans/1/generate", json={})
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["weeks"]
    assert plan["pacing_guide"]["goal_race_pace"] == "6:17"
    # Far from race day, so no taper.
    assert plan["phase"] in ("base", "build")


def test_generated_plan_uses_marathon_workouts(client):
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    titles = " ".join(d["title"] for d in days if d["type"] == "workout")
    assert titles, "no workouts prescribed"
    # 5K ladder titles ("2x10min Hard", "20min Continuous Tempo") would mean
    # get_ladder() is ignoring the goal distance again.
    assert "min Hard" not in titles


def test_generated_plan_respects_no_back_to_back_hard_days(client):
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    hard = {"workout", "long_run", "race"}
    for prev, nxt in zip(days, days[1:]):
        assert not (prev["type"] in hard and nxt["type"] in hard)


def test_progression_state_seeded_against_the_marathon_ladder(client):
    """Levels are ladder-specific; a marathon goal must seed marathon levels."""
    from app.models.progression import WorkoutProgression

    db = SessionLocal()
    try:
        rows = db.query(WorkoutProgression).filter(WorkoutProgression.user_id == 1).all()
        assert len(rows) == 2
        for row in rows:
            assert row.distance == "marathon"
            assert row.current_level >= 1
    finally:
        db.close()


# ── Plan editing ──────────────────────────────────────────────────

def _first_day_of_type(client, wanted):
    plan = client.get("/api/plans/1/current").json()
    for week in plan["weeks"]:
        for day in week["days"]:
            if day["type"] == wanted:
                return day
    return None


def test_edit_a_planned_day(client):
    day = _first_day_of_type(client, "easy")
    r = client.patch(f"/api/plans/1/days/{day['date']}", json={
        "distance_miles": 6.5,
        "description": "Trail loop instead",
    })
    assert r.status_code == 200, r.text
    updated = r.json()["day"]
    assert updated["distance_miles"] == 6.5
    assert updated["description"] == "Trail loop instead"
    assert updated["title"] == day["title"], "untouched fields must survive"


def test_edit_rejects_an_unknown_type(client):
    day = _first_day_of_type(client, "easy")
    r = client.patch(f"/api/plans/1/days/{day['date']}", json={"type": "cycling"})
    assert r.status_code == 400


def test_swap_two_days(client):
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    workout = next(d for d in days if d["type"] == "workout")
    easy = next(d for d in days if d["type"] == "easy" and d["date"] != workout["date"])

    r = client.post(f"/api/plans/1/days/{workout['date']}/swap",
                    json={"with_date": easy["date"]})
    assert r.status_code == 200, r.text
    a, b = r.json()["swapped"]
    assert a["date"] == workout["date"] and a["title"] == easy["title"]
    assert b["date"] == easy["date"] and b["title"] == workout["title"]

    # swap back
    client.post(f"/api/plans/1/days/{workout['date']}/swap", json={"with_date": easy["date"]})


def test_swap_warns_about_back_to_back_hard_days_without_refusing(client):
    """Principle 4: respect the athlete. Warn, don't block."""
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    long_run = next(d for d in days if d["type"] == "long_run")
    day_before = next(
        d for d in days
        if d["date"] < long_run["date"] and d["type"] == "easy"
    )
    # Move a workout next to the long run.
    workout = next(d for d in days if d["type"] == "workout")
    r = client.post(f"/api/plans/1/days/{workout['date']}/swap",
                    json={"with_date": day_before["date"]})
    assert r.status_code == 200
    # It went through; whether it warns depends on where things landed.
    assert "warnings" in r.json()
    client.post(f"/api/plans/1/days/{workout['date']}/swap",
                json={"with_date": day_before["date"]})


def test_skip_a_day(client):
    day = _first_day_of_type(client, "easy")
    r = client.post(f"/api/plans/1/days/{day['date']}/skip")
    assert r.status_code == 200
    assert r.json()["day"]["type"] == "rest"
    assert r.json()["day"]["distance_miles"] == 0


def test_reroll_a_workout(client):
    day = _first_day_of_type(client, "workout")
    r = client.post(f"/api/plans/1/days/{day['date']}/reroll",
                    json={"category": "intervals"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "intervals"
    assert body["day"]["type"] == "workout"
    assert body["day"]["description"]
    assert "{" not in body["day"]["description"]


def test_editing_a_missing_day_404s(client):
    assert client.patch("/api/plans/1/days/1999-01-01",
                        json={"distance_miles": 5}).status_code == 404


# ── Feedback loop ─────────────────────────────────────────────────

def test_submit_feedback_returns_a_coach_response(client):
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    day = next(d for d in days if d["type"] == "workout")

    r = client.post(f"/api/plans/1/feedback/{day['date']}", json={
        "feel_rating": 8,
        "feel_notes": "Felt strong, splits were consistent",
        "pace_assessment": "on_target",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["coach_response"]
    assert body["feel_rating"] == 8


def test_low_feel_rating_downgrades_the_next_hard_day(client):
    plan = client.get("/api/plans/1/current").json()
    days = [d for w in plan["weeks"] for d in w["days"]]
    workouts = [d for d in days if d["type"] == "workout"]
    if len(workouts) < 2:
        pytest.skip("plan has only one workout to work with")

    target = workouts[0]
    client.post(f"/api/plans/1/feedback/{target['date']}", json={
        "feel_rating": 2,
        "feel_notes": "Legs are shot",
    })

    after = client.get("/api/plans/1/current").json()
    after_days = [d for w in after["weeks"] for d in w["days"]]
    later = [d for d in after_days if d["date"] > target["date"]]
    assert any("adjusted" in d["title"].lower() for d in later), (
        "a feel rating of 2 should have softened an upcoming hard day"
    )


# ── Weekly summary ────────────────────────────────────────────────

def test_weekly_summary(client):
    r = client.get("/api/plans/1/weekly-summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["actual_miles"] > 0
    assert data["run_count"] > 0
    assert data["narrative"]
    assert "week_start" in data and "week_end" in data


def test_weekly_summary_for_a_specific_week(client):
    from datetime import date

    monday = date.today() - timedelta(days=date.today().weekday() + 7)
    r = client.get(f"/api/plans/1/weekly-summary?week_start={monday.isoformat()}")
    assert r.status_code == 200
    assert r.json()["week_start"] == monday.isoformat()


def test_weekly_summary_rejects_a_bad_date(client):
    assert client.get("/api/plans/1/weekly-summary?week_start=nonsense").status_code == 400


# ── Goal switching ────────────────────────────────────────────────

def test_switching_goal_distance_reseeds_the_ladders(client):
    """Level 5 means a different workout on each ladder."""
    from app.models.progression import WorkoutProgression

    client.post("/api/users/1/goal", json={
        "goal_type": "race", "race_distance": "5k",
        "target_time_seconds": 1019.0, "race_date": "2027-06-01",
        "description": "Sub-17 5K",
    })
    assert client.post("/api/plans/1/generate", json={}).status_code == 200

    db = SessionLocal()
    try:
        rows = db.query(WorkoutProgression).filter(WorkoutProgression.user_id == 1).all()
        assert all(r.distance == "5k" for r in rows)
    finally:
        db.close()

    plan = client.get("/api/plans/1/current").json()
    titles = " ".join(
        d["title"] for w in plan["weeks"] for d in w["days"] if d["type"] == "workout"
    )
    assert "mi Threshold" not in titles, "5K goal should not use marathon cruise intervals"

    # put it back
    client.post("/api/users/1/goal", json={
        "goal_type": "race", "race_distance": "marathon",
        "target_time_seconds": MARATHON_245, "race_date": "2028-02-06",
        "description": "Sub-2:45 Surf City Marathon",
    })
    client.post("/api/plans/1/generate", json={})
