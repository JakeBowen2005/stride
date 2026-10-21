"""A day's run is never blended with other activities that day.

Real case: a 7.0 mi threshold run plus a 0.89 mi treadmill walk at 19:40/mi (recorded by the
watch as "treadmill_running"). The walk must not change the day's distance, pace or time, and is
never part of the running plan; a genuine second run (a double) is listed on its own.
"""
import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.workout_data import MI
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity, is_walk
from app.models.plan import Plan, PlannedWorkout
from app.services.garmin import parse_activity
from tests.test_off_plan_sessions import THRESHOLD_3X8, intervals_3x1200

client = TestClient(app)


def seed(extra):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
                    prescribed_from=monday.isoformat(), is_active=True, load=json.dumps({"weekly_budgets": [30]}))
        db.add(plan); db.flush()
        for i in range(7):
            d = monday + timedelta(days=i)
            workout = d == today
            db.add(PlannedWorkout(plan_id=plan.id, date=d.isoformat(), day_name="x", week_number=1,
                                  type="workout" if workout else "easy", title="3x1200m Intervals" if workout else "Easy",
                                  distance_miles=6.0 if workout else 4.0,
                                  prescription=json.dumps(intervals_3x1200()) if workout else None))
        at = datetime.combine(today, datetime.min.time())
        db.add(Activity(user_id=1, source="garmin", external_id="run", name="Fullerton Running", date=at.replace(hour=7),
                        distance_meters=7.0 * MI, duration_seconds=3364, average_heartrate=161, workout_type="workout",
                        splits=json.dumps(THRESHOLD_3X8)))
        db.add(extra(at))
        db.commit()


def today_row():
    current = client.get("/api/plans/1/current").json()
    return current, next(d for w in current["weeks"] for d in w["days"] if d["date"] == date.today().isoformat())


def walk(at):
    return Activity(user_id=1, source="garmin", external_id="walk", name="Treadmill Running", date=at.replace(hour=18),
                    distance_meters=0.89 * MI, duration_seconds=1127, average_heartrate=105,
                    activity_subtype="treadmill_running", workout_type="walk")


def test_walk_is_listed_but_never_blended_or_counted():
    seed(walk)
    current, day = today_row()
    actual = day["actual"]
    assert actual["distance_miles"] == 7.0 and actual["avg_pace"] == "8:00" and actual["duration_seconds"] == 3364
    assert actual["average_heartrate"] == 161 and actual["total_distance_miles"] == 7.0
    assert actual["other_runs"] == [] and actual["walks"][0]["distance_miles"] == 0.89
    assert day["comparison"]["distance_diff_miles"] == 1.0
    assert current["weeks"][0]["actual_mileage"] == 7.0
    assert day["actual"]["workout"]["title"] == "3x8min Threshold"


def test_a_double_is_listed_separately_and_counts_toward_the_week():
    seed(lambda at: Activity(user_id=1, source="garmin", external_id="pm", name="PM shakeout", date=at.replace(hour=18),
                             distance_meters=2.0 * MI, duration_seconds=1140, average_heartrate=130, workout_type="easy"))
    current, day = today_row()
    actual = day["actual"]
    assert actual["distance_miles"] == 7.0 and actual["avg_pace"] == "8:00"  # the workout, not a blend
    assert actual["other_runs"][0]["distance_miles"] == 2.0 and actual["total_distance_miles"] == 9.0
    assert day["comparison"]["distance_diff_miles"] == 1.0  # the double isn't "over prescribed"
    assert current["weeks"][0]["actual_mileage"] == 9.0


def test_walk_detection_and_sync_tagging():
    slow = Activity(distance_meters=0.89 * MI, duration_seconds=1127, activity_subtype="treadmill_running")
    jog = Activity(distance_meters=3 * MI, duration_seconds=3 * 780, activity_subtype="running")  # 13:00/mi beginner
    assert is_walk(slow) and not is_walk(jog)
    assert is_walk(Activity(distance_meters=MI, duration_seconds=600, activity_subtype="walking"))
    parsed = parse_activity({"activityId": 1, "activityType": {"typeKey": "treadmill_running"}, "distance": 0.89 * MI,
                             "movingDuration": 1127, "startTimeLocal": "2026-10-20 18:00:00"})
    assert parsed["workout_type"] == "walk"


def test_walks_stay_out_of_weekly_mileage_and_feedback():
    seed(walk)
    weeks = client.get("/api/analysis/1/weekly-mileage?weeks=1").json()
    assert round(weeks[-1]["actual"], 1) == 7.0
    r = client.post(f"/api/plans/1/feedback/{date.today()}", json={"feel_rating": 8})
    assert r.status_code == 200 and r.json()["evaluation"]["decision"] == "off_plan"
