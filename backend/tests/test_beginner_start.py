"""A real beginner: no recorded runs, a stated starting point, self-reported feedback."""
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core import developmental
from app.core.workout_evaluator import evaluate_workout
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import PlannedWorkout
from app.models.user import Goal, User
from tests.test_adaptation_edge_cases import _plan

client = TestClient(app)
TODAY = date.today()


def _beginner(minutes=None, mileage=None, goal="general"):
    with SessionLocal() as db:
        u = db.get(User, 1)
        u.experience_level, u.continuous_run_minutes, u.current_weekly_mileage = "beginner", minutes, mileage
        u.days_per_week, u.rest_days = 3, "monday,wednesday,friday,sunday"
        db.query(Goal).delete()
        db.add(Goal(user_id=1, goal_type=goal, active=True))
        db.commit()


def test_no_history_and_no_starting_point_explains_what_is_needed():
    r = client.post("/api/plans/1/preview", json={})
    assert r.status_code == 400 and "how long you can run" in r.json()["detail"]


def test_no_history_beginner_gets_run_walk_and_no_workouts():
    _beginner(minutes=1)
    r = client.post("/api/plans/1/preview", json={})
    assert r.status_code == 200, r.text
    plan = r.json()
    days = [d for w in plan["weeks"] for d in w["days"] if d["type"] != "rest" and d.get("prescribed", True)]
    assert days and all(d["title"].startswith("Run/Walk") for d in days)
    assert not any(d["type"] == "workout" for d in days)
    week1 = [d for d in plan["weeks"][0]["days"] if d["title"].startswith("Run/Walk")]
    assert "1min easy run + 2min walk" in week1[0]["description"]
    assert any("Run/walk start" in n for n in plan["notes"])


def test_continuous_runner_without_history_gets_short_easy_runs():
    _beginner(minutes=30)
    plan = client.post("/api/plans/1/preview", json={}).json()
    runs = [d for w in plan["weeks"] for d in w["days"] if d["type"] != "rest" and d.get("prescribed", True)]
    assert runs and not any(d["title"].startswith("Run/Walk") for d in runs)
    assert not any(d["type"] == "workout" for d in runs)  # workouts are earned with history
    assert sum(d["distance_miles"] for d in plan["weeks"][0]["days"]) <= 6.5


def test_run_walk_steps_need_two_runs_a_week_and_a_gap_drops_one_step():
    assert developmental.run_walk_stage(1, []) == 0
    assert developmental.run_walk_stage(1, [3, 2, 3]) == 3
    assert developmental.run_walk_stage(1, [3, 1, 3]) == 2  # one run that week repeats the step
    assert developmental.run_walk_stage(1, [3, 3, 3, 0]) == 2  # a missed week drops ONE step, not to the start
    assert developmental.run_walk_stage(1, [], week_index=1) == 1
    assert developmental.run_walk_stage(1, [], week_index=1, holding=True) == 0
    assert developmental.run_walk_stage(25, []) is None
    assert developmental.run_walk_stage(14, [2] * 4) is None  # graduated to continuous running
    assert developmental.stage_minutes(3) == 5 and developmental.stage_minutes(None) == 20


def test_run_walk_progress_counts_only_after_the_starting_point_and_is_banked():
    from tests.test_adaptation_edge_cases import _easy_run
    for back in (30, 29, 23, 22):  # two runs in each of two weeks BEFORE onboarding
        _easy_run(-back, 1.5, ext=f"pre{back}")
    r = client.put("/api/users/1/profile", json={"continuous_run_minutes": 1, "experience_level": "beginner",
                                                "days_per_week": 3, "rest_days": ["monday", "wednesday", "friday", "sunday"]})
    assert r.status_code == 200, r.text
    plan = client.post("/api/plans/1/preview", json={}).json()
    first = next(d for d in plan["weeks"][0]["days"] if d["title"].startswith("Run/Walk"))
    assert "1min easy run + 2min walk" in first["description"]  # earlier weeks are already in "1 minute"
    with SessionLocal() as db:
        assert db.get(User, 1).continuous_run_set_on is not None


def test_previous_block_plan_anchors_a_hold_so_missed_runs_dont_compound():
    from app.core.load_policy import plan_load
    weeks = [12, 12, 9, 9]
    held = plan_load(baseline=10.5, peak=12, experience="beginner", goal_type="general", num_weeks=2,
                     assessment="hold", completed_weeks=weeks, developmental=True,
                     previous_block={"weekly_budgets": [12, 12], "mode": "build"})
    assert held.weekly_budgets == [12, 12]
    reduced_again = plan_load(baseline=8, peak=12, experience="beginner", goal_type="general", num_weeks=2,
                              assessment="reduce", completed_weeks=[10, 9, 7, 6], developmental=True,
                              previous_block={"weekly_budgets": [10, 10], "mode": "reduce"})
    assert reduced_again.weekly_budgets == [10, 10]
    assert any("Second interrupted block" in r for r in reduced_again.reasons)


DEV = {"category": "development", "format": "continuous", "segments": [{"reps": 1, "duration_seconds": 600}]}


def test_self_reported_completion_is_distinct_from_measured_evidence():
    full = {"status": "full", "source": "self_reported"}
    ok = evaluate_workout(None, None, None, "workout", None, "10min Controlled Effort", 8, DEV, None, effort=6, reported=full)
    assert ok.decision == "advance" and ok.evidence == "self_reported"
    hard = evaluate_workout(None, None, None, "workout", None, "x", 8, DEV, None, effort=8, reported=full)
    assert hard.decision == "hold" and "8/10" in hard.reason
    unrated = evaluate_workout(None, None, None, "workout", None, "x", 8, DEV, None, reported=full)
    assert unrated.decision == "hold"
    missed = evaluate_workout(None, None, None, "workout", None, "x", 6, DEV, None, reported={"status": "not_done"})
    assert missed.decision == "hold" and "schedule" in missed.reason
    nothing = evaluate_workout(None, None, None, "workout", None, "x", 8, DEV, None)
    assert nothing.decision == "insufficient"


def test_self_report_never_advances_a_pace_ladder():
    threshold = {"category": "threshold", "format": "time_intervals",
                 "segments": [{"reps": 3, "duration_seconds": 480, "pace_range_sec_per_mile": {"fast": 400, "slow": 400}}]}
    # Measured but ambiguous laps: the self-report must not stand in for them on a paced ladder
    ambiguous = {"evidence_source": "garmin_inferred_work_laps", "confidence": "low", "completion": 1,
                 "rep_paces_sec_per_mile": [395, 396, 398], "target_paces_sec_per_mile": [400, 400, 400]}
    ev = evaluate_workout(None, None, None, "workout", None, "3x8min", 9, threshold, ambiguous, effort=6,
                          reported={"status": "full"})
    assert ev.decision not in {"advance", "recalibrate"}


def test_effort_rule_is_the_same_with_and_without_laps():
    measured = {"evidence_source": "garmin_labeled_laps", "confidence": "high", "completion": 1,
                "rep_paces_sec_per_mile": [600], "work_lap_paces_sec_per_mile": [600]}
    for effort, decision in ((7, "advance"), (8, "hold"), (9, "regress")):
        laps = evaluate_workout(None, None, None, "workout", None, "x", 8, DEV, measured, effort=effort)
        told = evaluate_workout(None, None, None, "workout", None, "x", 8, DEV, None, effort=effort,
                                reported={"status": "full"})
        assert laps.decision == told.decision == decision, (effort, laps.decision, told.decision)


def test_feedback_stores_effort_completion_and_manual_run():
    _plan([(0, "easy", "Easy Run", 3.0)])
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 7, "effort_rating": 4, "completion": "full",
        "manual_distance_miles": 3.1, "manual_duration_minutes": 33})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effort_rating"] == 4 and body["reported_completion"]["source"] == "self_reported"
    # Resubmitting edits the same manual run instead of adding a second one
    client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 7, "manual_distance_miles": 3.2, "manual_duration_minutes": 34})
    with SessionLocal() as db:
        runs = db.query(Activity).filter_by(source="manual").all()
        assert len(runs) == 1 and abs(runs[0].distance_meters / 1609.34 - 3.2) < .01


def test_manual_run_is_refused_next_to_a_recorded_run():
    from tests.test_adaptation_edge_cases import _easy_run
    _plan([(0, "easy", "Easy Run", 3.0)])
    _easy_run(0, 3)
    r = client.post(f"/api/plans/1/feedback/{TODAY}", json={
        "feel_rating": 7, "manual_distance_miles": 3, "manual_duration_minutes": 30})
    assert r.status_code == 409


def test_outlook_flags_a_marathon_gap_and_reports_milestones():
    from app.core.outlook import goal_outlook
    o = goal_outlook(goal_type="race", distance="marathon", race_weeks_away=8, destination=None, baseline=12,
                     recent_long_run=5, experience="beginner", run_days_recent=[3, 3, 3, 3], days_per_week=3,
                     development_level=2, run_walk_stage=None)
    keys = {m["key"]: m for m in o["milestones"]}
    assert keys["consistency"]["status"] == "done"
    assert keys["volume"]["target"] == 35 and keys["long_run"]["target"] == 16
    assert {g["milestone"] for g in o["gaps"]} >= {"volume", "long_run"}
    relaxed = goal_outlook(goal_type="race", distance="5k", race_weeks_away=30, destination=None, baseline=12,
                           recent_long_run=4, experience="beginner", run_days_recent=[3, 3, 3, 3],
                           days_per_week=3, development_level=2, run_walk_stage=None)
    assert relaxed["gaps"] == []


def test_mileage_goal_destination_drives_volume_milestone():
    from app.core.outlook import goal_outlook
    o = goal_outlook(goal_type="mileage", distance=None, race_weeks_away=None, destination=75, baseline=45,
                     recent_long_run=14, experience="advanced", run_days_recent=[6, 6, 6, 6], days_per_week=6,
                     development_level=None, run_walk_stage=None)
    vol = next(m for m in o["milestones"] if m["key"] == "volume")
    assert vol["target"] == 75 and vol["est_weeks"] > 0
    assert not any(m["key"] == "workouts" for m in o["milestones"])


def test_block_review_explains_completed_learned_changes_and_missing():
    from app.core.outlook import block_review
    r = block_review({"decision": "hold", "reasons": ["Mixed block"], "planned_miles": 20, "completed_miles": 17,
                      "completion": .85, "quality_planned": 2, "quality_done": 1, "quality_unknown": 1,
                      "quality_incomplete": 0, "quality_substituted": 0, "long_runs_planned": 2, "long_runs_done": 2,
                      "avg_feel": 6.5, "feel_count": 5}, {"weekly_budgets": [18, 18], "baseline": 17, "reasons": ["Holding"]})
    assert r["completed"][0].startswith("Ran 17 of 20")
    assert "consolidating" in r["learned"]
    assert r["changes"][0].startswith("Weekly volume: 18 → 18")
    assert any("no lap evidence" in m for m in r["missing"])
    assert r["why"] == ["Mixed block", "Holding"]
    assert block_review(None, None) is None


def test_goal_set_and_current_plan_include_outlook():
    _beginner(minutes=30, goal="general")
    r = client.post("/api/users/1/goal", json={"goal_type": "race", "race_distance": "5k",
                                              "race_date": (TODAY + timedelta(weeks=20)).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["outlook"]["milestones"]
    assert client.get("/api/plans/1/outlook").json()["milestones"]
