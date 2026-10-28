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


def work_minutes(option):
    data=option['prescription'];easy=data['easy_pace_sec_per_mile']
    total=0
    for seg in data['segments']:
        pace=(seg.get('pace_range_sec_per_mile') or {}).get('slow') or easy*.85
        total+=seg['reps']*(seg.get('duration_seconds') or seg['distance_meters']/MI*pace)
    return total/60


def test_advanced_menu_is_three_varied_full_doses_and_budget_cuts_are_reviewable():
    plan,day=seed();response=menu(day+timedelta(days=1),'threshold');assert response.status_code==200,response.text
    options=response.json()['options']
    assert len(options)==3 and len({o['shape'] for o in options})==3
    # An advanced runner never sees a token 2x3min dose.
    assert all(work_minutes(o)>=19.5 for o in options)
    # Not everything is time-based: at least one measured-distance session.
    assert any(any(s.get('distance_meters') for s in o['prescription']['segments']) for o in options)
    choice=next(o for o in options if any(c['date']!=o['date'] for c in o['changes']))
    cruise=[s for o in options for s in o['prescription']['segments'] if o['shape']!='continuous']
    assert all(s['pace_range_sec_per_mile']=={'fast':450,'slow':450} for s in cruise)
    with SessionLocal() as db:
        assert db.query(PlannedWorkout).filter_by(plan_id=plan,date=choice['date']).one().title=='2x6min Threshold'
        assert all(r.original_prescription is None for r in db.query(PlannedWorkout))
    r=client.post(f'/api/plans/1/sessions/{choice["date"]}',json={'action':'replace','replacement':'threshold','option_id':choice['id']})
    assert r.status_code==200,r.text
    with SessionLocal() as db:
        rows=db.query(PlannedWorkout).filter_by(plan_id=plan).all()
        assert sum(r.distance_miles for r in rows)<=35.5
        changed=[r for r in rows if r.original_prescription]
        assert len(changed)>=2 and any(r.title==choice['title'] for r in changed)
        assert all(r.adjustment_note for r in changed)


def test_beginner_does_not_receive_advanced_threshold_dose():
    _,day=seed('beginner');data=menu(day+timedelta(days=1),'threshold').json()
    assert data['options'] and all(work_minutes(o)<=16.5 for o in data['options'])


def test_taper_menu_reduces_dose_but_keeps_intensity():
    _,day=seed(phase='taper');data=menu(day+timedelta(days=1),'threshold').json()
    assert data['options'] and all(work_minutes(o)<=15.5 for o in data['options'])
    reps=[s for o in data['options'] if o['shape']!='continuous' for s in o['prescription']['segments']]
    assert reps and all(s['pace_range_sec_per_mile']['slow']==450 for s in reps)


def test_menu_text_has_no_dangling_step_joiner():
    _,day=seed();options=menu(day+timedelta(days=1),'threshold').json()['options']
    assert options and not any('Then Comfortably' in o['description'] or 'Then Settle' in o['description'] for o in options)


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
    second=menu(day+timedelta(days=3),'long_run').json()
    assert second['options']==[] and 'use Switch' in second['reasons'][0]
    options=menu(day+timedelta(days=5),'long_run').json()['options']
    # Durations, never past the cap, never shorter than an hour or than the week's easy runs.
    plan=client.get('/api/plans/1/current').json()
    week=next(w for w in plan['weeks'] if any(d['date']==options[0]['date'] for d in w['days']))
    longest_easy=max(d['distance_miles'] for d in week['days'] if d['type']=='easy')
    assert options and all(o['distance_miles']<=35*.35 and o['distance_miles']>longest_easy for o in options)
    assert all(o['title'].endswith('min Easy Long Run') and int(o['title'].split('min')[0])>=75 for o in options)


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
        option=next(c for c in context['candidates'] if c.get('session_option_id') and any(ch['date']!=c['date'] for ch in c['changes']))
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
        assert any(row.title==chosen['replacement']['title'] for row in rows)
        assert sum(row.distance_miles for row in rows)<=35.5


def test_high_mileage_easy_runs_are_not_replaced_by_short_workout_average_paces():
    from app.services.analyzer import analyze_athlete
    with SessionLocal() as db:
        for days,typ,miles,pace in [(1,'easy',10,510),(3,'easy',9,510),(2,'threshold',7,425),(4,'intervals',6,410)]:
            db.add(Activity(user_id=1,source='manual',date=datetime.now()-timedelta(days=days),workout_type=typ,distance_meters=miles*MI,duration_seconds=miles*pace,average_pace_per_km=pace/1.60934))
        db.commit();analysis=analyze_athlete(1,db)
        assert analysis['paces']['recent_easy_pace']=='8:30'
        assert analysis['paces']['easy_pace']=='8:30'


def test_concurrent_menu_and_latest_review_are_read_only():
    """Listing alternatives must work beside a SQLite writer, without DML/savepoints."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy import event

    from app.database import engine
    from app.models.coaching import CoachingReview
    from app.services.coaching_options import snapshot

    plan_id, day = seed()
    with SessionLocal() as db:
        db.add(CoachingReview(user_id=1, plan_id=plan_id, context_hash='old-context',
                              status='fallback', result='{}'))
        db.commit()
        before = [(row.id, snapshot(row), row.original_prescription, row.adjustment_note)
                  for row in db.query(PlannedWorkout).order_by(PlannedWorkout.id)]

    def reject_writes(conn, cursor, statement, parameters, context, executemany):
        verb = statement.lstrip().split()[0].upper()
        assert verb not in {'UPDATE', 'INSERT', 'DELETE', 'SAVEPOINT', 'RELEASE'}, statement

    barrier = Barrier(2)

    def get_menu():
        barrier.wait(timeout=10)
        return client.get(f'/api/plans/1/sessions/{day+timedelta(days=1)}/options?category=threshold')

    def get_latest():
        barrier.wait(timeout=10)
        return client.get(f'/api/coaching/1/latest?plan_id={plan_id}')

    # An unrelated open writer makes any attempted dry-run UPDATE fail, rather
    # than relying on thread timing to reproduce SQLITE_BUSY_SNAPSHOT.
    with engine.connect() as writer:
        writer.exec_driver_sql('BEGIN IMMEDIATE')
        event.listen(engine, 'before_cursor_execute', reject_writes)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(get_menu)
                second = pool.submit(get_latest)
                menu_response = first.result(timeout=30)
                latest_response = second.result(timeout=30)
            assert menu_response.status_code == 200, menu_response.text
            assert menu_response.json()['options']
            assert latest_response.status_code == 200, latest_response.text
            assert latest_response.json()['stale'] is True
        finally:
            event.remove(engine, 'before_cursor_execute', reject_writes)
            writer.rollback()
    with SessionLocal() as db:
        after = [(row.id, snapshot(row), row.original_prescription, row.adjustment_note)
                 for row in db.query(PlannedWorkout).order_by(PlannedWorkout.id)]
    assert before == after
