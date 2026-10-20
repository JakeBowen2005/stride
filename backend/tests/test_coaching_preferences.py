from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.plan_engine import generate_plan
from app.database import SessionLocal
from app.main import app
from app.models.user import User, Goal
from app.models.activity import Activity

client = TestClient(app)


def build(**kwargs):
    args = dict(goal_type='mileage', goal_distance=None, target_time_seconds=None,
                current_weekly_mileage=29, peak_weekly_mileage=70, experience_level='advanced',
                days_per_week=6, rest_days=['sunday'], long_run_day='saturday', easy_pace_seconds=540,
                completed_weeks=[22,33,23,38], weekly_run_days=[4,5,4,6], recent_long_run_miles=10,
                target_weekly_mileage=75, start_date=date(2026,10,19), first_prescribe_date=date(2026,10,19),
                deload_is_due=False)
    args.update(kwargs)
    return generate_plan(**args)


def workouts(plan):
    return [[d for d in w['days'] if d['type'] == 'workout'] for w in plan['weeks']]


def test_advanced_rebuild_allows_threshold_and_light_second_within_budget():
    plan = build(workout_format='time')
    assert plan['violations'] == []
    for week, quality in zip(plan['weeks'], workouts(plan)):
        assert len(quality) == 2
        assert [d['prescription']['category'] for d in quality] == ['threshold', 'speed_support']
        assert quality[1]['title'] == '8x1min Light Fartlek'
        assert quality[1]['prescription']['segments'][0]['reps'] == 8
        assert quality[1]['prescription']['segments'][0]['pace_range_sec_per_mile'] is None
        assert 'min easy' in quality[0]['warmup']
        assert week['target_mileage'] <= week['budget_miles'] + .5
        assert all('Easy' in d['title'] for d in week['days'] if d['type'] == 'long_run')


@pytest.mark.parametrize('changes', [dict(experience_level='beginner'), dict(days_per_week=4),
    dict(completed_weeks=[0,20,25,38]), dict(weekly_run_days=[4,4,2,6]),
    dict(recent_long_run_miles=5), dict(assessment='hold'), dict(assessment='recovery'),
    dict(fatigue_recovery=True), dict(weekly_run_days=[])])
def test_second_stimulus_needs_recent_readiness_and_recovery(changes):
    assert all(len(w) <= 1 for w in workouts(build(**changes)))


def test_quality_does_not_preview_higher_level_while_adding_second_or_mileage():
    plan = build(progression_state={'threshold': {'current_level': 3, 'last_execution':'advance'}})
    work = workouts(plan)
    assert work[0][0]['prescription']['level'] == work[1][0]['prescription']['level'] == 3
    assert work[0][1]['title'] == '6x400m Relaxed Repetitions'


@pytest.mark.parametrize('rest,long_day,days', [(['tuesday'],'sunday',6), (['thursday'],'saturday',6),
    (['monday','friday'],'sunday',5), ([], 'wednesday',7)])
def test_preferences_preserve_rest_long_day_and_hard_spacing(rest,long_day,days):
    plan = build(rest_days=rest,long_run_day=long_day,days_per_week=days)
    assert plan['violations'] == []
    for week in plan['weeks']:
        assert sum(d['distance_miles']>0 for d in week['days']) <= days
        for day in week['days']:
            if day['day'] in rest:
                assert day['type'] == 'rest'
            if day['type'] == 'long_run':
                assert day['day'] == long_day


def test_time_bookends_do_not_change_work_paces_or_total_distance():
    a,b = build(),build(workout_format='time')
    for wa,wb in zip(workouts(a),workouts(b)):
        assert wa[0]['prescription']['segments'] == wb[0]['prescription']['segments']
        assert wa[0]['distance_miles'] == wb[0]['distance_miles']
        assert 'mi easy' in wa[0]['warmup'] and 'min easy' in wb[0]['warmup']


@pytest.mark.parametrize('payload', [{'long_run_day':'friday'}, {'days_per_week':7},
    {'rest_days':['saturday']}, {'rest_days':['friday','Friday']},
    {'rest_days':None}, {'days_per_week':None}, {'workout_format':None}])
def test_partial_profile_updates_validate_against_saved_preferences(payload):
    assert client.put('/api/users/1/profile',json=payload).status_code == 422
    assert client.get('/api/users/1').json()['rest_days'] == 'friday'


def test_profile_save_round_trip_and_clear_optional_age():
    payload = dict(age=21,units='km',workout_format='time',days_per_week=5,
                   rest_days=['monday','friday'],long_run_day='sunday')
    assert client.put('/api/users/1/profile',json=payload).status_code == 200
    user = client.get('/api/users/1').json()
    assert user['units']=='km' and user['workout_format']=='time' and user['days_per_week']==5
    assert user['rest_days']=='monday,friday' and user['long_run_day']=='sunday'
    assert client.put('/api/users/1/profile',json={'age':None}).status_code == 200
    assert client.get('/api/users/1').json()['age'] is None


def test_seven_days_with_no_rest_is_not_changed_into_sunday_rest():
    from tests.test_plan_preview import seed
    seed()
    from app.models.plan import Plan
    with SessionLocal() as db:
        db.query(Plan).filter_by(is_active=True).one().end_date = (date.today()+timedelta(days=13)).isoformat()
        db.commit()
    assert client.put('/api/users/1/profile',json={'days_per_week':7,'rest_days':[]}).status_code == 200
    draft = client.post('/api/plans/1/preview').json()
    assert draft['violations'] == []
    assert any(d['day']=='sunday' and d['distance_miles']>0 for w in draft['weeks'] for d in w['days'] if d['prescribed'])


def test_api_readiness_uses_completed_history_and_preferences_invalidates_preview():
    monday = date.today()-timedelta(days=date.today().weekday())
    with SessionLocal() as db:
        u=db.get(User,1)
        u.experience_level='advanced'
        db.query(Goal).filter_by(active=True).one().goal_type='mileage'
        db.query(Goal).filter_by(active=True).one().race_distance=None
        for week,total in enumerate([22,33,23,38]):
            for day in range(5):
                miles = 8 if day==4 else (total-8)/4
                db.add(Activity(user_id=1,source='manual',date=datetime.combine(monday-timedelta(weeks=4-week)+timedelta(days=day),datetime.min.time()),
                    distance_meters=miles*1609.34,duration_seconds=miles*540,average_pace_per_km=335.5))
        db.commit()
    draft=client.post('/api/plans/1/preview').json()
    assert any(d.get('prescription',{}).get('category')=='speed_support' for w in draft['weeks'] for d in w['days'])
    client.put('/api/users/1/profile',json={'workout_format':'time'})
    assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code==409


def test_one_week_spike_does_not_add_second_stimulus():
    assert all(len(w)<=1 for w in workouts(build(completed_weeks=[20,20,20,60])))


def test_changed_rest_preferences_do_not_break_approved_session_controls():
    import json
    from tests.test_session_controls import seed, action
    day = seed()
    assert client.put('/api/users/1/profile',json={'rest_days':['tuesday']}).status_code==200
    # Monday still follows the approved block's original Friday rest preference.
    result=action(day+timedelta(days=3),action='skip')
    assert result.status_code==200,result.text
    with SessionLocal() as db:
        from app.models.plan import Plan
        plan=db.query(Plan).filter_by(is_active=True).one()
        assert json.loads(plan.athlete_snapshot)['schedule_preferences']['rest_days']==['friday']
    assert client.put('/api/users/1/profile',json={'rest_days':['wednesday']}).status_code==200
    assert action(day+timedelta(days=1),action='skip').status_code==200


def test_weekdays_are_normalized_on_write():
    r=client.put('/api/users/1/profile',json={'rest_days':[' Friday '],'long_run_day':' Sunday '})
    assert r.status_code==200,r.text
    user=client.get('/api/users/1').json()
    assert user['rest_days']=='friday' and user['long_run_day']=='sunday'


def test_replacing_workout_honors_time_bookends_without_changing_intensity():
    from tests.test_session_controls import seed, action
    day=seed()
    assert client.put('/api/users/1/profile',json={'workout_format':'time'}).status_code==200
    response=action(day,action='replace',replacement='threshold')
    assert response.status_code==200,response.text
    plan=client.get('/api/plans/1/current').json()
    changed=plan['weeks'][0]['days'][0]
    assert 'min easy' in changed['warmup']
    assert changed['prescription']['warmup']['duration_seconds']>0
