"""Off-plan quality sessions, auto-lap merging, and budget edits after running extra.

The lap fixture is the real shape of a 3x8min threshold run on a 3x1200m interval day:
Garmin auto-lapped every rep at 1.00 mi, leaving a 0.10-0.14 mi remainder lap.
"""
import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.session_match import executed_session, off_plan
from app.core.workout_data import MI, prescription, segment
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.services import coaching, openai_coach
from app.services.lap_analyzer import analyze_laps, summarize_workout
from app.services.quality_history import quality_history

client = TestClient(app)
EASY = 570


def lap(miles, seconds, hr, intensity="INTERVAL"):
    return {"distance_m": miles * MI, "duration_s": seconds, "heart_rate": hr, "intensity": intensity}


THRESHOLD_3X8 = [lap(1.0, 545, 134), lap(1.0, 504, 150), lap(0.22, 112, 155),
                 lap(1.0, 435.5, 172), lap(0.10, 44, 172), lap(0.22, 119.8, 158),
                 lap(1.0, 428.7, 174), lap(0.12, 51, 179), lap(0.21, 119.6, 169),
                 lap(1.0, 420.3, 178), lap(0.14, 59, 183), lap(1.0, 525, 160)]


def intervals_3x1200():
    p = prescription("intervals", "track_intervals", [segment(3, meters=1200, fast=370, slow=380, recovery_seconds=120)])
    p.update(easy_pace_sec_per_mile=EASY, warmup=segment(meters=1.5 * MI), cooldown=segment(meters=1.5 * MI))
    return p


def test_auto_lap_remainders_merge_into_time_reps():
    result = analyze_laps(THRESHOLD_3X8, EASY)
    assert result["label"] == "3x8min" and result["category"] == "threshold"
    assert [round(r["pace_sec_per_mile"] / 3) for r in result["reps"]] == [145, 143, 140]  # 7:15, 7:09, 6:59 ±3s
    assert all(r["average_hr"] for r in result["reps"]) and result["recovery_seconds"] == 120
    assert summarize_workout(THRESHOLD_3X8, EASY) == "Garmin laps: 3x8min threshold (7:16, 7:08, 7:00/mi) w/ 2min recovery"


def test_full_size_back_to_back_laps_stay_separate_reps():
    laps = [lap(1.0, 560, 140), lap(1.0, 410, 170), lap(1.0, 411, 171), lap(0.1, 70, 140), lap(1.0, 414, 172), lap(1.0, 560, 140)]
    assert analyze_laps(laps, EASY)["label"] == "3x1 mile"


def test_true_1200s_are_not_off_plan():
    laps = [lap(1.5, 855, 140)] + sum(([lap(0.746, 280, 175), lap(0.2, 120, 150)] for _ in range(3)), [])[:-1] + [lap(1.5, 855, 140)]
    executed = analyze_laps(laps, EASY)
    assert executed["label"] == "3x1200m" and off_plan(intervals_3x1200(), executed) is False


def seed_day(feel_notes="I did 3x8min threshold"):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=13)).isoformat(),
                    prescribed_from=monday.isoformat(), is_active=True, load=json.dumps({"weekly_budgets": [30, 30]}))
        db.add(plan); db.flush()
        for i in range(14):
            d = monday + timedelta(days=i)
            typ = "workout" if d == today else "rest" if i % 7 == 4 else "long_run" if i % 7 == 5 else "easy"
            miles = {"workout": 6.0, "rest": 0.0, "long_run": 8.0}.get(typ, 4.0)
            db.add(PlannedWorkout(plan_id=plan.id, date=d.isoformat(), day_name=d.strftime("%A").lower(), week_number=i // 7 + 1,
                                  type=typ, title="3x1200m Intervals" if typ == "workout" else typ, distance_miles=miles,
                                  prescription=json.dumps(intervals_3x1200()) if typ == "workout" else None))
        db.add(Activity(user_id=1, source="garmin", external_id="t1", name="Run", date=datetime.combine(today, datetime.min.time()).replace(hour=7),
                        distance_meters=7.0 * MI, duration_seconds=3364, average_heartrate=161, max_heartrate=185,
                        workout_type="workout", splits=json.dumps(THRESHOLD_3X8), feel_notes=feel_notes))
        db.commit()
        return plan.id, today


def test_off_plan_feedback_logs_what_was_run_and_is_never_a_failure():
    plan_id, today = seed_day()
    r = client.post(f"/api/plans/1/feedback/{today}", json={"feel_rating": 8, "feel_notes": "I did 3x8min threshold", "pace_assessment": "above"})
    assert r.status_code == 200, r.text
    evaluation = r.json()["evaluation"]
    assert evaluation["decision"] == "off_plan" and "3x8min Threshold" in evaluation["reason"]
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan_id, date=today.isoformat()).one()
        assert row.actual_workout_type == "threshold"
        history = quality_history(1, db)
    assert history["recent_failure"] is False
    current = client.get("/api/plans/1/current").json()
    day = next(d for w in current["weeks"] for d in w["days"] if d["date"] == today.isoformat())
    assert day["actual"]["workout"]["title"] == "3x8min Threshold" and day["actual"]["workout"]["off_plan"] is True


def test_stored_ambiguous_verdict_is_not_a_failure_either():
    """Rows evaluated before off-plan detection existed are re-read from their laps."""
    plan_id, today = seed_day()
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan_id, date=today.isoformat()).one()
        row.feel_rating, row.evaluation = 8, json.dumps({"decision": "insufficient", "evidence": "ambiguous_laps"})
        db.commit()
        assert quality_history(1, db)["recent_failure"] is False


def test_extra_miles_already_run_do_not_block_other_edits():
    plan_id, today = seed_day()
    with SessionLocal() as db:
        plan = db.get(Plan, plan_id)
        plan.load = json.dumps({"weekly_budgets": [26.0, 30]})  # ran 7.0 on a 6.0 day: week 1 now 27 vs 26
        db.commit()
    target = next((today + timedelta(days=i)).isoformat() for i in range(1, 7)
                  if (today + timedelta(days=i)).weekday() not in {4} and (today + timedelta(days=i)) > today)
    r = client.post(f"/api/plans/1/sessions/{target}", json={"action": "skip"})
    assert r.status_code == 200, r.text


def test_replacing_a_hard_day_in_a_full_week_still_offers_options():
    plan_id, today = seed_day()
    with SessionLocal() as db:
        rows = db.query(PlannedWorkout).filter_by(plan_id=plan_id, week_number=2).order_by(PlannedWorkout.date).all()
        for row, title in ((rows[1], "2x7min Threshold"), (rows[3], "3x1200m Intervals")):
            row.type, row.title, row.distance_miles = "workout", title, 6.0
            row.prescription = json.dumps(intervals_3x1200())
        db.commit()
        day = rows[1].date
    menu = client.get(f"/api/plans/1/sessions/{day}/options?category=threshold").json()
    assert len(menu["options"]) >= 2, menu["reasons"]


def test_coach_reads_the_run_that_was_actually_run(monkeypatch):
    from app.config import settings
    plan_id, today = seed_day()
    client.post(f"/api/plans/1/feedback/{today}", json={"feel_rating": 8, "feel_notes": "I did 3x8min threshold", "pace_assessment": "above"})
    monkeypatch.setattr(settings, "openai_api_key", "unit-test-secret")
    calls = []

    def request(context, sources):
        calls.append(context)
        return openai_coach.CoachAdvice(summary="Strong off-plan threshold.", plan_fit="consistent", observations=[],
                                        uncertainties=[], research_ids=[], suggestions=[]), {}
    monkeypatch.setattr(coaching, "request_advice", request)
    with SessionLocal() as db:
        activity_id = db.query(Activity).one().id
    assert client.post("/api/coaching/1/review", json={"activity_id": activity_id}).status_code == 200
    ctx = calls[-1]
    run = ctx["run"]
    assert run["detected_session"]["title"] == "3x8min Threshold"
    assert [r["pace"] for r in run["detected_session"]["reps"]] == ["7:16/mi", "7:08/mi", "7:00/mi"]
    assert run["athlete_feedback"] == {"feel_1_to_10": 8, "notes": "I did 3x8min threshold", "pace_vs_target": "above", "said_swapped": False}
    assert run["avg_pace"] and run["average_hr"] == 161 and len(run["laps"]) == 12 and run["laps"][3]["hr"] == 172
    assert ctx["run_vs_plan"].startswith("OFF-PLAN") and ctx["deterministic_evaluation"]["decision"] == "off_plan"
    assert ctx["training_summary"]["this_week"]["done_miles"] == 7.0 and ctx["training_summary"]["goal"]["race_distance"] == "5k"
    assert ctx["training_summary"]["recent_quality_sessions"][-1]["session"] == "3x8min Threshold"
    assert "laps" not in ctx["recent_runs"][-1]  # history stays one line per run
