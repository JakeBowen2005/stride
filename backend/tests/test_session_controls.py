import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout

client = TestClient(app)


def seed():
    # Next Monday avoids user fixture's Friday rest preference.
    monday = date.today() + timedelta(days=7 - date.today().weekday())
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=13)).isoformat(),
                 prescribed_from=monday.isoformat(), load=json.dumps({"weekly_budgets": [30, 30]}))
        db.add(p)
        db.flush()
        for i, typ, miles in [(0, "workout", 6), (1, "easy", 4), (2, "easy", 4), (3, "easy", 4), (4, "rest", 0), (5, "long_run", 8)]:
            db.add(PlannedWorkout(plan_id=p.id, date=(monday + timedelta(days=i)).isoformat(), day_name="x", week_number=1,
                                  type=typ, title="6x800m" if i == 0 else typ, distance_miles=miles))
        db.commit()
    return monday


def action(day, **body):
    return client.post(f"/api/plans/1/sessions/{day}", json=body)


def test_skip_without_activity_persists():
    day = seed()
    assert action(day, action="skip").status_code == 200
    result = client.get('/api/plans/1/current').json()['weeks'][0]['days'][0]
    assert result['session_status'] == 'skipped' and result['distance_miles'] == 0
    assert result['original_prescription']['distance_miles'] == 6
    assert action(day, action="skip").status_code == 409


def test_move_preserves_prescription_and_validates_spacing():
    day = seed()
    # Wednesday is isolated; Friday rest and Saturday long run stay untouched.
    assert action(day, action="move", target_date=(day + timedelta(days=2)).isoformat()).status_code == 200
    with SessionLocal() as db:
        rows = db.query(PlannedWorkout).order_by(PlannedWorkout.date).all()
        assert rows[0].session_status == 'moved' and rows[0].distance_miles == 0
        assert rows[2].type == 'workout' and rows[2].distance_miles == 6


def test_unsafe_move_rolls_back_everything():
    day = seed()
    r = action(day, action="move", target_date=(day + timedelta(days=4)).isoformat())
    assert r.status_code == 409  # Friday is a rest day and directly precedes the long run.
    with SessionLocal() as db:
        original = db.query(PlannedWorkout).filter_by(date=day.isoformat()).one()
        assert original.type == "workout" and original.original_prescription is None


def test_replacement_cannot_stack_or_exceed_budget():
    day = seed()
    assert action(day + timedelta(days=1), action="replace", replacement="intervals").status_code == 409
    assert action(day + timedelta(days=2), action="replace", replacement="easy", distance_miles=30).status_code == 409
    with SessionLocal() as db:
        assert db.query(PlannedWorkout).filter_by(date=(day + timedelta(days=2)).isoformat()).one().distance_miles == 4


def test_completed_activity_blocks_mutation_even_before_get_match():
    day = seed()
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source='manual', date=datetime.combine(day, datetime.min.time()), distance_meters=5000, duration_seconds=1800))
        db.commit()
    assert action(day, action="skip").status_code == 409


def test_other_athlete_cannot_change_plan():
    day = seed()
    assert client.post(f'/api/plans/2/sessions/{day}', json={'action': 'skip'}).status_code == 404
