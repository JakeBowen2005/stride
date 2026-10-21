"""Quality stages are earned by completed work/recovery, never by preview count."""
from datetime import date, datetime, timedelta
import json

import pytest
from fastapi.testclient import TestClient

from app.core.quality_policy import select_quality_policy
from app.core.plan_engine import generate_plan
from app.database import SessionLocal
from app.main import app
from app.models.user import User, Goal
from app.models.plan import Plan, PlannedWorkout
from app.models.activity import Activity

client=TestClient(app)
READY = {'primary_successes':4,'support_successes':4,'recent_primary_successes':2,'recent_support_successes':2,
         'long_run_successes':2,'latest_long_run_feel':7,'dual_weeks':0,'recovery_days':6,'recovery_average':7,
         'recent_low_feel':False,'recent_failure':False,'weekly_run_days':[6]*8}


def quality(experience='advanced', **changes):
    params=dict(goal_type='mileage',experience=experience,days_per_week=6,
        weekly_miles=[40]*8,weekly_run_days=[6]*4,recent_long_run_miles=10,evidence=READY)
    params.update(changes)
    return select_quality_policy(**params)


@pytest.mark.parametrize('tier',['beginner','intermediate','advanced','expert'])
def test_all_tiers_can_earn_two_workouts(tier):
    assert quality(tier).stage=='dual'


@pytest.mark.parametrize('evidence', [{}, READY|{'recovery_days':0}, READY|{'primary_successes':0},
    READY|{'recent_primary_successes':0}, READY|{'long_run_successes':0},
    READY|{'recent_failure':True}, READY|{'recent_low_feel':True}, READY|{'support_successes':0}])
def test_no_promotion_without_completed_quality_and_recovery(evidence):
    assert quality(evidence=evidence).stage!='dual'


@pytest.mark.parametrize('assessment',['hold','reduce','recovery'])
def test_recovery_always_overrides_expert_status(assessment):
    assert quality('expert',assessment=assessment).stage=='single'


def test_beginner_requires_more_demonstrated_training_than_advanced():
    evidence=READY|{'primary_successes':2,'support_successes':2}
    assert quality('advanced',evidence=evidence).stage=='dual'
    assert quality('beginner',evidence=evidence).stage!='dual'
    assert quality('advanced',weekly_miles=[40]*4).stage=='dual'
    assert quality('beginner',weekly_miles=[40]*4).stage!='dual'


def test_established_two_workout_history_does_not_require_light_sessions_again():
    assert quality(evidence=READY|{'dual_weeks':2,'support_successes':0,'recent_support_successes':0}).stage=='dual'


def full_plan(goal='mileage',distance=None,**changes):
    params=dict(goal_type=goal,goal_distance=distance,target_time_seconds=None,current_weekly_mileage=40,
        peak_weekly_mileage=70,experience_level='advanced',days_per_week=6,rest_days=['friday'],
        long_run_day='saturday',easy_pace_seconds=540,start_date=date(2026,10,19),first_prescribe_date=date(2026,10,19),
        completed_weeks=[40]*8,weekly_run_days=[6]*4,recent_long_run_miles=10,
        quality_evidence=READY,deload_is_due=False)
    params.update(changes)
    return generate_plan(**params)


def test_promotion_holds_volume_and_fits_two_substantial_goal_sessions():
    p=full_plan()
    assert p['quality_policy']['stage']=='dual' and p['load']['mode']=='hold'
    assert p['violations']==[]
    assert all(w['budget_miles']<=40 for w in p['weeks'])
    for w in p['weeks']:
        work=[d for d in w['days'] if d['type']=='workout']
        assert len(work)==2
        assert all(d['prescription']['category']!='speed_support' for d in work)
        assert work[1]['prescription']['role']=='secondary_quality'
        assert work[1]['prescription']['progression_eligible'] is False
    assert p['weeks'][0]['days'][3]['prescription']['category']=='threshold'
    assert p['weeks'][1]['days'][3]['prescription']['category']=='intervals'


@pytest.mark.parametrize('distance',['5k','10k','half','marathon','100mi'])
def test_goal_and_phase_change_pair_without_breaking_spacing(distance):
    p=full_plan('race',distance,race_date=date(2027,5,1))
    assert p['violations']==[]
    work=[d for d in p['weeks'][0]['days'] if d['type']=='workout']
    assert len(work)==2
    if distance in {'5k','10k'}:
        assert {d['prescription']['category'] for d in work}=={'threshold','intervals'}
    if distance in {'half','marathon'}:
        assert all(d['prescription']['category']=='threshold' for d in work)


def test_hard_long_run_spends_one_quality_slot():
    p=full_plan('race','marathon',current_weekly_mileage=65,completed_weeks=[65]*8,
        race_date=date(2026,12,5),quality_evidence=READY|{'dual_weeks':2},previous_quality_stage='dual')
    assert p['violations']==[]
    for w in p['weeks']:
        hard_long=[d for d in w['days'] if d['type']=='long_run' and any(x in d['title'].lower() for x in ['progress','steady','marathon','tempo'])]
        if hard_long:
            assert sum(d['type']=='workout' for d in w['days'])<=1


def seed_completed_stage():
    monday=date.today()-timedelta(days=date.today().weekday())
    from app.core.workout_data import prescription,segment
    with SessionLocal() as db:
        user=db.get(User,1);user.experience_level='advanced'
        goal=db.query(Goal).filter_by(active=True).one();goal.goal_type='mileage';goal.race_distance=None;goal.target_weekly_mileage=75
        plan=Plan(user_id=1,start_date=(monday-timedelta(weeks=8)).isoformat(),end_date=(monday-timedelta(days=1)).isoformat(),is_active=True,
                  athlete_snapshot=json.dumps({'quality_policy':{'stage':'support'}}))
        db.add(plan);db.flush()
        for week in range(8):
            for wd,miles in [(0,5),(1,6),(2,5),(3,6),(5,10),(6,8)]:
                day=monday-timedelta(weeks=8-week)+timedelta(days=wd)
                kind='threshold' if wd==1 else 'speed_support' if wd==3 else None
                splits=[]
                data=None
                if kind:
                    reps,seconds=(2,360) if kind=='threshold' else (8,60)
                    data=prescription(kind,'time_intervals',[segment(reps,seconds=seconds,fast=420 if kind=='threshold' else None,slow=420 if kind=='threshold' else None,recovery_seconds=60)])
                    splits=[{'intensity':'WARMUP','distance_m':1600,'duration_s':540}]
                    for rep in range(reps):
                        splits.append({'intensity':'ACTIVE','distance_m':seconds/420*1609.34,'duration_s':seconds})
                        if rep<reps-1:splits.append({'intensity':'RECOVERY','distance_m':150,'duration_s':60})
                activity=Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=miles*1609.34,
                    duration_seconds=miles*540,average_pace_per_km=335.5,feel_rating=7,splits=json.dumps(splits))
                db.add(activity)
                if kind or wd==5:
                    db.add(PlannedWorkout(plan_id=plan.id,date=day.isoformat(),day_name='x',week_number=week+1,
                        type='workout' if kind else 'long_run',title=kind or 'Easy Long Run',distance_miles=miles,
                        prescription=json.dumps(data) if data else None,feel_rating=7))
        db.commit()
    return monday


def test_real_completed_evidence_unlocks_dual_and_persists_after_approval():
    from app.services.quality_history import quality_history
    monday=seed_completed_stage()
    # Long runs count over a rolling 28 days; the seed fills whole past weeks only,
    # so on a Sunday the oldest of four Saturdays is 29 days back.
    long_runs=sum(monday-timedelta(weeks=k,days=-5)>=date.today()-timedelta(days=28) for k in range(1,9))
    with SessionLocal() as db:
        evidence=quality_history(1,db)
        assert evidence['primary_successes']>=7 and evidence['support_successes']>=7
        assert evidence['long_run_successes']==long_runs>=3
    a=client.post('/api/plans/1/preview').json()
    b=client.post('/api/plans/1/preview').json()
    assert a['quality_policy']['stage']==b['quality_policy']['stage']=='dual'
    assert a['quality_policy']['evidence']==b['quality_policy']['evidence']
    assert client.post(f"/api/plans/1/drafts/{b['id']}/approve").status_code==200
    assert client.get('/api/plans/1/current').json()['quality_policy']['stage']=='dual'


def test_feel_alone_and_whole_run_mileage_do_not_unlock_dual():
    from app.services.quality_history import quality_history
    seed_completed_stage()
    with SessionLocal() as db:
        db.query(Activity).update({'splits':None})
        db.commit()
        evidence=quality_history(1,db)
        assert evidence['primary_successes']==evidence['support_successes']==0
    p=client.post('/api/plans/1/preview').json()
    assert p['quality_policy']['stage']!='dual'


def test_expert_profile_is_persisted_and_controls_experience_policy():
    seed_completed_stage()
    assert client.put('/api/users/1/profile',json={'experience_level':'expert'}).status_code==200
    assert client.get('/api/users/1').json()['experience_level']=='expert'
    p=client.post('/api/plans/1/preview').json()
    assert p['athlete']['experience_level']=='expert'


@pytest.mark.parametrize('distance',['5k','10k',None])
def test_support_stage_keeps_one_primary_and_one_light_session(distance):
    p=full_plan('race' if distance else 'mileage',distance,quality_evidence={})
    assert p['quality_policy']['stage']=='support'
    for w in p['weeks']:
        work=[d for d in w['days'] if d['type']=='workout']
        assert len(work)==2
        cats=[d['prescription']['category'] for d in work]
        assert cats.count('speed_support')==1
        assert sum(c in {'threshold','intervals'} for c in cats)==1


def test_repreview_of_approved_dual_does_not_earn_volume_increase():
    p=full_plan(previous_quality_stage='dual')
    assert all(w['budget_miles']<=40 for w in p['weeks'])


def test_latest_long_run_recovery_must_be_known_and_positive():
    assert quality(evidence=READY|{'latest_long_run_feel':4}).stage!='dual'
    assert quality(evidence=READY|{'latest_long_run_feel':None}).stage!='dual'


def test_moved_destination_counts_without_a_current_plan_read():
    from app.services.quality_history import quality_history
    seed_completed_stage()
    with SessionLocal() as db:
        baseline=quality_history(1,db)['primary_successes']
        row=db.query(PlannedWorkout).filter(PlannedWorkout.title=='threshold').order_by(PlannedWorkout.date.desc()).first()
        row.session_status='moved';row.moved_from=(date.fromisoformat(row.date)-timedelta(days=1)).isoformat()
        db.commit()
        assert quality_history(1,db)['primary_successes']==baseline


def test_hills_count_as_substantial_evidence_without_flat_pace_calibration():
    from app.services.quality_history import quality_history
    seed_completed_stage()
    with SessionLocal() as db:
        rows=db.query(PlannedWorkout).filter(PlannedWorkout.title=='speed_support').all()
        for row in rows:
            data=json.loads(row.prescription);data['category']='hills';row.prescription=json.dumps(data)
        db.commit()
        evidence=quality_history(1,db)
        assert evidence['dual_weeks']>=2 and evidence['primary_successes']>=14


def test_experience_modifies_bounded_ramp_and_recovery_cadence():
    from app.core.load_policy import ramp_rate,deload_due
    assert ramp_rate(55,70,'expert','mileage')>ramp_rate(55,70,'advanced','mileage')
    assert ramp_rate(40,70,'advanced','mileage')>ramp_rate(40,70,'beginner','mileage')
    assert ramp_rate(25,70,'expert','mileage')<=.20
    assert ramp_rate(40,70,'expert','comeback')==.10
    assert deload_due([40]*7,'advanced')[0] is True
    assert deload_due([40]*7,'expert')[0] is False
    assert deload_due([40]*8,'expert')[0] is True
    assert deload_due([40]*7+[30],'expert')[0] is False


def test_week_quality_count_reflects_final_cross_week_safety_pass():
    p=full_plan(first_prescribe_date=date(2026,10,20),completed_by_date={'2026-10-19':10},prior_hard_dates={'2026-10-19'})
    for week in p['weeks']:
        assert week['quality_sessions']==sum(d['type']=='workout' and d.get('prescribed',True) for d in week['days'])


def test_completed_today_counts_for_recovery_but_future_activity_does_not():
    from app.services.quality_history import quality_history
    seed_completed_stage()
    with SessionLocal() as db:
        before=quality_history(1,db)['recovery_days']
        for day in [date.today(),date.today()+timedelta(days=1)]:
            db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),
                distance_meters=8000,duration_seconds=2700,feel_rating=7))
        db.commit()
        assert quality_history(1,db)['recovery_days']==before+1
