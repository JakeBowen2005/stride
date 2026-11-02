"""Jake's Oct 19 – Nov 1 2026 block: the next block must build on what he actually ran.

He switched to a 75 mi/week mileage goal (a fresh ladder at level 1), ran every planned mile
(40 and 45 mi against 41 and 38) and swapped two workouts for harder ones: 3x8min threshold on a
3x1200m day and 2x12min threshold on a 3 mi tempo day. The old engine counted both swaps as not
done, held the block, cut it to one 2x6min threshold a week and repeated week 1 as week 2.
"""
import json
from datetime import date, datetime, timedelta

import time_machine
from fastapi.testclient import TestClient

from app.core.block_assessment import DayRecord, assess_block
from app.core.workout_ladders import level_for_work
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.user import Goal, User
from tests.test_substitution_matrix import EASY, R3x1200, D, T, TEMPO3, build, rx_reps

client = TestClient(app)
START = date(2026, 10, 19)
R6x400 = rx_reps("intervals", 6, meters=400, fast=340, slow=350, rest=90)

# (planned type, title, planned miles, prescription, ran miles, laps of the quality work)
BLOCK = [
    ("easy", "Easy Run", 5, None, 5.0, None),
    ("workout", "3x1200m Intervals", 6, R3x1200, 7.0, T(3, 8, 405)),
    ("easy", "Easy Run", 5, None, 5.0, None),
    ("workout", "6x400m Intervals", 5, R6x400, 5.0, D(6, 400, 345)),
    ("easy", "Easy Run", 5, None, 5.0, None),
    ("long_run", "Easy Long Run", 10, None, 10.0, None),
    ("easy", "Recovery Run", 3, None, 3.1, None),
    ("easy", "Easy Run + Strides", 6, None, 7.0, None),
    ("workout", "3mi Tempo Run", 6, TEMPO3, 7.0, T(2, 12, 405)),
    ("easy", "Easy Run", 5, None, 5.0, None),
    ("easy", "Easy Run", 6, None, 11.0, None),
    ("long_run", "Easy Long Run", 10, None, 10.0, None),
    ("easy", "Easy Run", 3, None, 3.1, None),
    ("easy", "Recovery Run", 3, None, 3.0, None),
]


def seed():
    with SessionLocal() as db:
        user = db.get(User, 1)
        user.experience_level, user.peak_weekly_mileage, user.current_weekly_mileage = "advanced", 70, 38
        user.rest_days, user.days_per_week, user.long_run_day = "", 7, "saturday"
        goal = db.query(Goal).filter_by(user_id=1).one()
        goal.goal_type, goal.race_distance, goal.target_time_seconds = "mileage", None, None
        goal.target_weekly_mileage = 75
        plan = Plan(user_id=1, start_date=str(START), end_date=str(START + timedelta(days=13)), block_number=1,
                    prescribed_from=str(START), is_active=True, load=json.dumps({"weekly_budgets": [39, 40]}),
                    athlete_snapshot=json.dumps({"experience_level": "advanced", "schedule_preferences": {
                        "rest_days": [], "long_run_day": "saturday", "days_per_week": 7}}))
        db.add(plan)
        db.flush()
        for i, (kind, title, planned, rx, ran, work) in enumerate(BLOCK):
            day = START + timedelta(days=i)
            db.add(PlannedWorkout(plan_id=plan.id, date=str(day), day_name=day.strftime("%A").lower(),
                                  week_number=i // 7 + 1, type=kind, title=title, distance_miles=planned,
                                  prescription=json.dumps(rx) if rx else None))
            laps = build(work, rest=120, mode="structured") if work else None
            db.add(Activity(user_id=1, source="garmin", external_id=f"block-{i}", name="Run",
                            date=datetime.combine(day, datetime.min.time()).replace(hour=7),
                            distance_meters=ran * 1609.34, duration_seconds=ran * EASY, feel_rating=7,
                            splits=json.dumps(laps) if laps else None))
        # Six steady weeks before the block: the history that makes him an advanced 38 mi/week runner
        for offset in range(1, 43):
            day = START - timedelta(days=offset)
            miles = 10 if day.weekday() == 5 else 3 if day.weekday() == 6 else 6
            if START - timedelta(days=14) <= day < START - timedelta(days=7):
                miles = 3  # a lighter week two weeks before the block: no deload due yet
            db.add(Activity(user_id=1, source="manual", date=datetime.combine(day, datetime.min.time()).replace(hour=7),
                            distance_meters=miles * 1609.34, duration_seconds=miles * EASY, feel_rating=7))
        db.commit()


def test_level_matches_demonstrated_threshold_dose():
    # Aerobic (mileage) threshold ladder: 2x6min is level 1, 3x8min (24 min) is level 7
    assert level_for_work("threshold", "mileage", 12) == 1
    assert level_for_work("threshold", "mileage", 24) == 7
    assert level_for_work("threshold", "mileage", 5) == 0


def test_harder_substitution_counts_and_a_full_block_builds():
    days = [DayRecord(date=f"d{i}", type=t, planned_miles=p, actual_miles=a, feel=7,
                      substituted=s, covered=c, execution_complete=None)
            for i, (t, p, a, s, c) in enumerate([("workout", 6, 7, True, True), ("workout", 6, 7, True, True),
                                                 ("workout", 5, 5, False, False)] + [("easy", 5, 5.5, False, False)] * 6)]
    assessment = assess_block(days)
    assert assessment.quality_done == 2 and assessment.decision == "build", assessment.reasons
    # A substitution with less work than planned is still not done
    days[0].covered = days[1].covered = False
    assert assess_block(days).quality_done == 0


def test_jakes_next_block_builds_on_what_he_ran():
    with time_machine.travel("2026-11-02 08:00:00", tick=False):
        seed()
        response = client.post("/api/plans/1/preview", json={"scope": "next"})
        assert response.status_code == 200, response.text
        plan = response.json()
    assert plan["assessment"]["decision"] == "build", plan["assessment"]["reasons"]
    assert plan["assessment"]["quality_done"] >= 2
    assert plan["quality_policy"]["stage"] in {"support", "dual"}
    titles = [[d["title"] for d in w["days"]] for w in plan["weeks"]]
    for week in plan["weeks"]:
        assert sum(d["type"] == "workout" for d in week["days"]) == 2, titles
    threshold = [t for week in titles for t in week if "Threshold" in t]
    assert threshold and "2x6min" not in threshold[0], titles
    assert titles[0] != titles[1], "week 2 should progress, not repeat week 1"
    budgets = plan["load"]["weekly_budgets"]
    assert budgets[0] >= 40 and budgets[1] <= budgets[0] * 1.1 + 0.5, budgets
    # A coach's week, not five identical easy days: a medium-long run, a recovery run after the
    # long run, and a steady finish on the long run every other week.
    for week in plan["weeks"]:
        by_title = {d["title"]: d["distance_miles"] for d in week["days"]}
        assert by_title["Medium-Long Run"] > by_title["Easy Run"] > by_title["Recovery Run"] >= 3, by_title
        days = week["days"]
        long_index = next(i for i, d in enumerate(days) if d["type"] == "long_run")
        assert days[long_index + 1]["title"] == "Recovery Run"
    longs = [d["title"] for w in plan["weeks"] for d in w["days"] if d["type"] == "long_run"]
    assert sorted(longs) == ["Easy Long Run", "Steady Finish Long Run"], longs
    long_criterion = next(c for c in plan["quality_policy"]["criteria"] if c["label"].startswith("Long run"))
    assert long_criterion["met"], plan["quality_policy"]


def test_a_preview_from_older_code_is_stale_and_caps_nothing(monkeypatch):
    """Nov 1: the flat 42.5 mi preview made before the fix kept showing after the deploy."""
    from app.api import plans
    with time_machine.travel("2026-10-31 08:00:00", tick=False):
        seed()
        monkeypatch.setattr(plans, "ENGINE_VERSION", "old-code")
        early = client.post("/api/plans/1/preview", json={"scope": "next", "provisional": True})
        assert early.status_code == 200, early.text
        with SessionLocal() as db:  # what the old engine built: a flat, low block
            draft = db.query(Plan).filter_by(preview_state="draft", preview_scope="next").one()
            data = json.loads(draft.preview_data)
            for week in data["weeks"]:
                week["target_mileage"] = 30
            draft.preview_data = json.dumps(data)
            db.commit()
        monkeypatch.setattr(plans, "ENGINE_VERSION", "new-code")
        assert client.get("/api/plans/1/draft", params={"scope": "next"}).json()["stale"] is True
    with time_machine.travel("2026-11-02 08:00:00", tick=False):
        plan = client.post("/api/plans/1/preview", json={"scope": "next"}).json()
    assert "preview_volume_caps" not in plan
    assert plan["load"]["weekly_budgets"][0] > 30, plan["load"]["weekly_budgets"]


def test_easy_days_stay_alike_for_beginners_and_low_mileage():
    from app.core.plan_engine import shape_easy_days
    def week():
        days = [{"date": f"2026-11-0{2 + i}", "type": t, "title": title, "distance_miles": 5}
                for i, (t, title) in enumerate([("easy", "Easy Run"), ("workout", "W"), ("easy", "Easy Run"),
                                                ("easy", "Easy Run"), ("easy", "Easy Run"), ("long_run", "Long"),
                                                ("easy", "Easy Run")])]
        return days
    for experience, miles in (("beginner", 45), ("advanced", 30)):
        days = week()
        shape_easy_days(days, miles, experience, "general", False)
        assert not any(d.get("easy_role") for d in days)
    days = week()
    shape_easy_days(days, 45, "advanced", "general", False)
    assert [d.get("easy_role") for d in days] == [None, None, "medium_long", None, None, None, "recovery"]


def test_long_run_moved_to_another_day_counts():
    longs = [DayRecord(date="sat", type="long_run", planned_miles=10, actual_miles=4, feel=7,
                       session_status="moved", week_longest=10.0)]
    days = longs + [DayRecord(date=f"d{i}", type="easy", planned_miles=5, actual_miles=5, feel=7) for i in range(6)]
    assert assess_block(days).long_runs_done == 1
    days[0].week_longest = 4.0
    assert assess_block(days).long_runs_done == 0
