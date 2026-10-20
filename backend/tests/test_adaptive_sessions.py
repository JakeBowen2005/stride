import json
from datetime import date,datetime,timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.plan import Plan,PlannedWorkout
from app.models.activity import Activity
from app.core.workout_data import MI,prescription,segment

client=TestClient(app)


def seed(experience='advanced',phase='general'):
    monday=date.today()+timedelta(days=7-date.today().weekday())
    historical=date.today()-timedelta(days=date.today().weekday(),weeks=8)
    with SessionLocal() as db:
        db.get(User,1).experience_level=experience
        for w in range(8):
            for d in range(6):
                day=historical+timedelta(weeks=w,days=d)
                miles=15 if d==5 else 5
                db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=miles*MI,duration_seconds=miles*570,average_pace_per_km=570/1.60934,workout_type='long_run' if d==5 else 'easy',feel_rating=8))
        plan=Plan(user_id=1,start_date=monday.isoformat(),end_date=(monday+timedelta(days=6)).isoformat(),prescribed_from=monday.isoformat(),load=json.dumps({'weekly_budgets':[35]}),phases=json.dumps([{'phase':phase}]),training_paces=json.dumps({'long_run_pace':570,'broken_threshold_pace':450,'tempo_pace':460,'interval_pace':390,'interval_pace_fast':380}))
        db.add(plan);db.flush()
        contract=prescription('threshold','time_intervals',[segment(2,seconds=360,fast=450,slow=450,recovery_seconds=120)])
        contract.update(warmup=segment(meters=1.5*MI),cooldown=segment(meters=1.5*MI))
        for i,typ,miles in [(0,'easy',5),(1,'workout',5),(2,'easy',5),(3,'easy',5),(4,'rest',0),(5,'long_run',10),(6,'easy',5)]:
            db.add(PlannedWorkout(plan_id=plan.id,date=(monday+timedelta(days=i)).isoformat(),day_name='x',week_number=1,type=typ,title='2x6min Threshold' if i==1 else typ,distance_miles=miles,prescription=json.dumps(contract) if i==1 else None))
        db.commit();return plan.id,monday


def menu(day,category):return client.get(f'/api/plans/1/sessions/{day}/options?category={category}')


def test_advanced_can_choose_three_by_eight_and_budget_cuts_are_reviewable():
    plan,day=seed();response=menu(day+timedelta(days=1),'threshold');assert response.status_code==200,response.text
    options=response.json()['options'];choice=next(o for o in options if o['title']=='3x8min Threshold')
    assert any(c['date']!=choice['date'] for c in choice['changes'])
    assert choice['prescription']['segments'][0]['pace_range_sec_per_mile']=={'fast':450,'slow':450}
    with SessionLocal() as db:
        assert db.query(PlannedWorkout).filter_by(plan_id=plan,date=choice['date']).one().title=='2x6min Threshold'
        assert all(r.original_prescription is None for r in db.query(PlannedWorkout))
    r=client.post(f'/api/plans/1/sessions/{choice["date"]}',json={'action':'replace','replacement':'threshold','option_id':choice['id']})
    assert r.status_code==200,r.text
    with SessionLocal() as db:
        rows=db.query(PlannedWorkout).filter_by(plan_id=plan).all()
        assert sum(r.distance_miles for r in rows)<=35.5
        changed=[r for r in rows if r.original_prescription]
        assert len(changed)>=2 and any(r.title=='3x8min Threshold' for r in changed)


def test_beginner_does_not_receive_advanced_threshold_dose():
    _,day=seed('beginner');data=menu(day+timedelta(days=1),'threshold').json()
    assert data['options'] and all(sum(s['reps']*(s.get('duration_seconds') or 0) for s in o['prescription']['segments'])<=720 for o in data['options'])
    assert not any(o['title']=='3x8min Threshold' for o in data['options'])


def test_taper_menu_reduces_dose():
    _,day=seed(phase='taper');data=menu(day+timedelta(days=1),'threshold').json()
    assert data['options'] and all(sum(s['reps']*s['duration_seconds'] for s in o['prescription']['segments'])<=480 for o in data['options'])


def test_easy_to_quality_honors_earned_slots_and_spacing():
    _,day=seed()
    assert menu(day+timedelta(days=2),'intervals').json()['options']==[] # next to Tuesday
    assert menu(day+timedelta(days=3),'threshold').json()['options']==[] # second substantial not earned
    support=menu(day+timedelta(days=3),'intervals').json()
    assert support['options'] and all(o['prescription']['category']=='speed_support' for o in support['options'])


def test_first_interval_workout_has_multiple_formats_when_slot_is_available():
    plan,day=seed()
    with SessionLocal() as db:
        row=db.query(PlannedWorkout).filter_by(plan_id=plan,type='workout').one();row.type='easy';row.prescription=None;db.commit()
    options=menu(day+timedelta(days=1),'intervals').json()['options']
    assert len(options)>=3 and len({o['title'] for o in options})==len(options)


def test_new_run_invalidates_old_option_even_without_current_plan_get():
    _,day=seed();choice=menu(day+timedelta(days=1),'threshold').json()['options'][0]
    with SessionLocal() as db:
        db.add(Activity(user_id=1,source='manual',date=datetime.now(),distance_meters=MI,duration_seconds=600));db.commit()
    r=client.post(f'/api/plans/1/sessions/{choice["date"]}',json={'action':'replace','replacement':'threshold','option_id':choice['id']})
    assert r.status_code==409


def test_long_run_has_lengths_but_cannot_add_second_main_long_run():
    _,day=seed()
    assert menu(day+timedelta(days=3),'long_run').json()['options']==[]
    options=menu(day+timedelta(days=5),'long_run').json()['options']
    assert len(options)>=2 and all(o['distance_miles']<=35*.35 for o in options)


def test_recovery_feedback_removes_hard_and_long_options():
    _,day=seed()
    with SessionLocal() as db:
        db.add(Activity(user_id=1,source='manual',date=datetime.now(),distance_meters=MI,duration_seconds=600,feel_rating=2));db.commit()
    assert menu(day+timedelta(days=1),'threshold').json()['options']==[]
    assert menu(day+timedelta(days=5),'long_run').json()['options']==[]


def test_phase_deload_and_b2b_caps_override_earned_dual_stage(monkeypatch):
    from app.services import session_options
    from app.core.quality_policy import QualityPolicy
    plan,day=seed()
    original=session_options.context_for
    def dual(*args):
        ctx=original(*args);ctx['quality']=QualityPolicy('dual','test established dual',[],ctx['evidence']);return ctx
    monkeypatch.setattr(session_options,'context_for',dual)
    for phase in ({'phase':'taper','max_workouts':1},{'phase':'build','back_to_back':True}):
        with SessionLocal() as db:db.get(Plan,plan).phases=json.dumps([phase]);db.commit()
        assert menu(day+timedelta(days=3),'threshold').json()['options']==[]
    with SessionLocal() as db:
        p=db.get(Plan,plan);p.phases=json.dumps([{'phase':'general'}]);p.is_deload=True;db.commit()
    assert menu(day+timedelta(days=3),'threshold').json()['options']==[]


def test_ultra_minimum_duration_cannot_exceed_final_long_run_cap():
    from app.models.user import Goal
    plan,day=seed()
    with SessionLocal() as db:
        g=db.query(Goal).one();g.race_distance='100k';g.terrain='trail'
        p=db.get(Plan,plan);p.load=json.dumps({'weekly_budgets':[10]})
        for row in db.query(PlannedWorkout).filter_by(plan_id=plan):row.distance_miles=1 if row.type!='rest' else 0
        db.commit()
    data=menu(day+timedelta(days=5),'long_run').json()
    assert data['options']==[]  # 75min helper floor cannot fit 3.5mi cap


def test_ai_selected_expanded_option_uses_same_atomic_menu_and_cuts(monkeypatch):
    from app.config import settings
    from app.services import coaching
    from app.services.openai_coach import CoachAdvice,Suggestion
    plan,day=seed()
    monkeypatch.setattr(settings,'openai_api_key','unit-test-key')
    def request(context,sources):
        option=next(c for c in context['candidates'] if c.get('session_option_id') and c['replacement']['title']=='3x8min Threshold')
        return CoachAdvice(summary='Consider this earned-menu alternative.',plan_fit='consider_change',observations=[],uncertainties=[],research_ids=[],suggestions=[Suggestion(candidate_id=option['id'],reason='Same validated athlete menu.')]),{}
    monkeypatch.setattr(coaching,'request_advice',request)
    review=client.post('/api/coaching/1/review',json={'plan_id':plan}).json()
    assert review['status']=='ready'
    chosen=review['suggestions'][0]
    assert any(c['date']!=chosen['date'] for c in chosen['changes'])
    r=client.post(f'/api/coaching/1/reviews/{review["id"]}/accept',json={'candidate_id':chosen['id']})
    assert r.status_code==200,r.text
    with SessionLocal() as db:
        rows=db.query(PlannedWorkout).filter_by(plan_id=plan).all()
        assert any(row.title=='3x8min Threshold' for row in rows)
        assert sum(row.distance_miles for row in rows)<=35.5


def test_high_mileage_easy_runs_are_not_replaced_by_short_workout_average_paces():
    from app.services.analyzer import analyze_athlete
    with SessionLocal() as db:
        for days,typ,miles,pace in [(1,'easy',10,510),(3,'easy',9,510),(2,'threshold',7,425),(4,'intervals',6,410)]:
            db.add(Activity(user_id=1,source='manual',date=datetime.now()-timedelta(days=days),workout_type=typ,distance_meters=miles*MI,duration_seconds=miles*pace,average_pace_per_km=pace/1.60934))
        db.commit();analysis=analyze_athlete(1,db)
        assert analysis['paces']['recent_easy_pace']=='8:30'
        assert analysis['paces']['easy_pace']=='8:30'
