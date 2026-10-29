import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.load_policy import deload_due, plan_load
from app.core.plan_engine import calculate_plan_params
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.user import User, Goal

client = TestClient(app)


def test_alternating_weeks_are_natural_down_weeks():
    due, reason = deload_due([26, 28, 30, 32, 22, 33, 23, 38], 'advanced')
    assert not due and 'no automatic deload' in reason
    assert not deload_due([38, 38, 0, 38, 38, 38], 'advanced')[0]


def test_experienced_runner_can_build_from_repeatable_recent_week():
    result = plan_load(29, 75, 'advanced', 'mileage', 2, target_weekly_mileage=75, completed_weeks=[22, 33, 23, 38])
    assert result.baseline == 29 and result.planning_anchor == 38
    assert result.weekly_budgets == [40, 40] and result.mode == 'build'
    assert 'Last full week 38' in ' '.join(result.reasons)


@pytest.mark.parametrize('history,assessment,experience', [([38, 38, 0, 38], None, 'advanced'), ([10, 10, 10, 38], None, 'advanced'), ([22,33,23,38], 'recovery', 'advanced'), ([22,33,23,38], None, 'beginner')])
def test_recent_week_does_not_override_spike_or_recovery_rules(history, assessment, experience):
    load = plan_load(sum(history)/4, 75, experience, 'mileage', 2, target_weekly_mileage=75, completed_weeks=history, assessment=assessment)
    assert load.planning_anchor == load.baseline
    if assessment:
        assert load.mode == 'recovery'


def test_calendar_history_and_profile_experience_feed_preview():
    monday = date.today() - timedelta(days=date.today().weekday())
    with SessionLocal() as db:
        db.get(User, 1).experience_level = 'advanced'
        g = db.query(Goal).filter_by(active=True).one()
        g.goal_type, g.race_distance, g.target_weekly_mileage = 'mileage', None, 75
        # Exactly the user's recent pattern, distributed across six days per week.
        for weeks_ago, miles in enumerate([38, 23, 33, 22], 1):
            start = monday - timedelta(weeks=weeks_ago)
            for day in (0,1,2,3,5,6):
                db.add(Activity(user_id=1, source='manual', date=datetime.combine(start + timedelta(days=day), datetime.min.time()),
                                distance_meters=miles / 6 * 1609.34, duration_seconds=miles / 6 * 540, average_pace_per_km=540 / 1.60934))
        db.commit()
    r = client.post('/api/plans/1/preview')
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['athlete']['experience_level'] == 'advanced'
    assert not data['is_deload']
    # 2 weeks Mon-Wed, 3 weeks Thu-Sun (calculate_plan_params). A midweek start with no
    # runs yet this week prescribes only the remaining days at their normal size.
    budgets = data['load']['weekly_budgets']
    assert budgets[1:] == [40] * (calculate_plan_params()['num_weeks'] - 1)
    assert budgets[0] == 40 if date.today().weekday() == 0 else budgets[0] <= 40
    assert data['violations'] == []


def test_next_block_cannot_reopen_an_approved_current_block():
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source='manual', date=datetime.now() - timedelta(days=1), distance_meters=8000, duration_seconds=2700))
        db.add(Plan(user_id=1, start_date=date.today().isoformat(), end_date=(date.today()+timedelta(days=13)).isoformat()))
        db.commit()
    r = client.post('/api/plans/1/preview', json={'scope':'next'})
    assert r.status_code == 409 and 'Finish this block' in r.json()['detail']


@pytest.mark.parametrize("budget", [34, 33.7])
def test_replacement_rebalances_easy_miles_and_retains_originals(budget):
    monday = date.today() + timedelta(days=7 - date.today().weekday())
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
                 prescribed_from=monday.isoformat(), load=json.dumps({'weekly_budgets':[budget]}))
        db.add(p)
        db.flush()
        for i, typ, miles in [(0,'easy',5),(1,'workout',5),(2,'easy',5),(3,'easy',5),(4,'rest',0),(5,'long_run',9),(6,'easy',5)]:
            db.add(PlannedWorkout(plan_id=p.id, date=(monday+timedelta(days=i)).isoformat(), day_name='x', week_number=1,
                                  type=typ, title=typ, distance_miles=miles))
        db.add(Activity(user_id=1, source='manual', date=datetime.combine(monday, datetime.min.time()),
                        distance_meters=5.0095 * 1609.34, duration_seconds=2700))
        db.commit()
    with SessionLocal() as db:
        from app.models.user import User
        db.get(User,1).experience_level='advanced'; db.commit()
    menu=client.get(f'/api/plans/1/sessions/{monday+timedelta(days=1)}/options?category=intervals').json()
    option=next(o for o in menu['options'] if o['distance_miles']>5)
    r = client.post(f'/api/plans/1/sessions/{monday+timedelta(days=1)}', json={'action':'replace','replacement':'intervals','option_id':option['id']})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        days = db.query(PlannedWorkout).order_by(PlannedWorkout.date).all()
        assert days[1].type == 'workout' and days[1].session_status == 'replaced'
        assert sum(d.distance_miles for d in days) + .0095 <= budget + .5
        assert db.query(Activity).one().distance_meters == 5.0095 * 1609.34
        assert any(d.type == 'easy' and d.distance_miles < 5 and d.original_prescription for d in days)
        assert days[5].distance_miles == 9


def test_preview_read_does_not_invalidate_approval_of_existing_activity():
    from tests.test_plan_preview import seed
    seed()
    with SessionLocal() as db:
        active = db.query(Plan).filter_by(is_active=True).one()
        active.end_date = (date.today() + timedelta(days=13)).isoformat()
        db.add(PlannedWorkout(plan_id=active.id, date=date.today().isoformat(), day_name='x', week_number=1,
                              type='easy', title='Easy', distance_miles=5))
        db.add(Activity(user_id=1, source='manual', date=datetime.now(), distance_meters=8000, duration_seconds=2700, average_pace_per_km=337.5))
        db.commit()
    draft = client.post('/api/plans/1/preview').json()
    assert client.get('/api/plans/1/current').status_code == 200
    r = client.post(f"/api/plans/1/drafts/{draft['id']}/approve")
    assert r.status_code == 200, r.text


def test_current_revision_preserves_boundaries_in_second_week():
    from tests.test_plan_preview import seed
    seed()
    monday = date.today() - timedelta(days=date.today().weekday())
    start, end = monday - timedelta(weeks=1), monday + timedelta(days=6)
    with SessionLocal() as db:
        active = db.query(Plan).filter_by(is_active=True).one()
        active.start_date, active.end_date = start.isoformat(), end.isoformat()
        db.commit()
    r = client.post('/api/plans/1/preview')
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['start_date'] == start.isoformat() and data['end_date'] == end.isoformat()
    assert len(data['weeks']) == 2
    assert all(d['date'] <= end.isoformat() for w in data['weeks'] for d in w['days'])


def test_fatigue_veto_survives_revision_before_five_run_days():
    from tests.test_plan_preview import seed
    seed()
    with SessionLocal() as db:
        active = db.query(Plan).filter_by(is_active=True).one()
        active.end_date = (date.today() + timedelta(days=13)).isoformat()
        for days in (1, 2):
            day = datetime.now() - timedelta(days=days)
            db.add(Activity(user_id=1, source='manual', date=day, distance_meters=5000, duration_seconds=2000,
                            average_pace_per_km=400, feel_rating=3))
        db.commit()
    r = client.post('/api/plans/1/preview')
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['assessment']['decision'] == 'recovery'
    assert data['load']['mode'] == 'recovery'
    assert all(d['type'] != 'workout' for d in data['weeks'][0]['days'])


def test_historical_week_does_not_block_recovery_revision_approval():
    from tests.test_plan_preview import seed
    seed()
    monday = date.today() - timedelta(days=date.today().weekday())
    with SessionLocal() as db:
        active = db.query(Plan).filter_by(is_active=True).one()
        active.start_date, active.end_date = (monday-timedelta(weeks=1)).isoformat(), (monday+timedelta(days=6)).isoformat()
        for days in (1, 2):
            act = db.query(Activity).filter(Activity.date >= datetime.combine(date.today()-timedelta(days=days), datetime.min.time()),
                                             Activity.date < datetime.combine(date.today()-timedelta(days=days-1), datetime.min.time())).first()
            act.feel_rating = 3
        db.commit()
    r = client.post('/api/plans/1/preview')
    assert r.status_code == 200, r.text
    draft = r.json()
    historical = draft['weeks'][0]
    assert all(not day['prescribed'] for day in historical['days'])
    assert historical['budget_miles'] == pytest.approx(sum(day['distance_miles'] for day in historical['days']))
    assert draft['violations'] == []
    approved = client.post(f"/api/plans/1/drafts/{draft['id']}/approve")
    assert approved.status_code == 200, approved.text


def test_current_week_already_over_budget_gets_rest_not_extra_mileage():
    from app.core.plan_engine import generate_plan
    monday = date(2026, 10, 19)
    completed = {(monday+timedelta(days=i)).isoformat(): 10 for i in range(4)}
    plan = generate_plan('mileage', None, None, 29, 75, 'advanced', 6, ['friday'], 'saturday', 540,
                         start_date=monday, num_weeks=2, first_prescribe_date=monday+timedelta(days=4),
                         assessment='recovery', completed_by_date=completed, deload_is_due=False)
    week = plan['weeks'][0]
    assert week['budget_miles'] == 40
    assert sum(d['distance_miles'] for d in week['days'] if d['prescribed']) == 0
    assert plan['violations'] == []


@pytest.mark.parametrize('remaining', [2.0, 2.3, 3.0, 4.2, 5.5])
def test_small_remaining_allowance_cannot_force_long_run_over_budget(remaining):
    from app.core.plan_engine import generate_plan
    monday = date(2026, 10, 19)
    completed = {(monday+timedelta(days=i)).isoformat(): (20.3-remaining)/3 for i in range(3)}
    plan = generate_plan('mileage', None, None, 29, 75, 'advanced', 6, ['friday'], 'saturday', 540,
                         start_date=monday, num_weeks=2, first_prescribe_date=monday+timedelta(days=4),
                         assessment='recovery', completed_by_date=completed, deload_is_due=False)
    assert plan['violations'] == []
    week = plan['weeks'][0]
    assert week['target_mileage'] <= week['budget_miles'] + .5
    assert sum(d['distance_miles'] for d in week['days'] if not d['prescribed']) == pytest.approx(20.3-remaining, abs=.02)


@pytest.mark.parametrize('weekday', range(7))
def test_revised_blocks_keep_calendar_weekdays_even_with_non_monday_start(weekday):
    from app.core.plan_engine import generate_plan
    start = date(2026, 10, 19) + timedelta(days=weekday)
    result = generate_plan('mileage', None, None, 35, 75, 'advanced', 6, ['friday'], 'saturday', 540,
                           start_date=start, num_weeks=2, first_prescribe_date=start, deload_is_due=False)
    assert result['violations'] == []
    for week in result['weeks']:
        for day in week['days']:
            actual_weekday = date.fromisoformat(day['date']).weekday()
            assert day['day'] == ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'][actual_weekday]
            if actual_weekday == 4:
                assert day['type'] == 'rest'


@pytest.mark.parametrize('weekday', range(7))
def test_race_week_recovery_respects_preferred_rest_days(weekday):
    from app.core.periodization import WeekPhase
    from app.core.special_weeks import build_race_week
    start = date(2026, 10, 19) + timedelta(days=weekday)
    race = start + timedelta(days=1)
    paces = {'threshold_pace': 410, 'easy_pace_low': 540, 'easy_pace_high': 595}
    days = build_race_week(start, WeekPhase('race_week', race_date=race),
                           '5k', None, 20, [4], paces)
    assert [d['date'] for d in days if d['type'] == 'race'] == [race.isoformat()]
    for day in days:
        if date.fromisoformat(day['date']).weekday() == 4 and day['date'] != race.isoformat():
            assert day['type'] == 'rest'
