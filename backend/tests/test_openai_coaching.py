"""Model decisions are untrusted; exercise the full local review/acceptance boundary."""
import json
import threading
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.coaching import CoachingReview
from app.models.plan import Plan, PlannedWorkout
from app.models.user import User
from app.core.workout_data import MI, prescription, segment
from app.services import coaching, openai_coach

client = TestClient(app)


def seed():
    monday = date.today() + timedelta(days=7-date.today().weekday())
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday+timedelta(days=6)).isoformat(),
                 prescribed_from=monday.isoformat(), is_active=True,
                 training_paces=json.dumps({'long_run_pace': 570, 'interval_pace': 390}),
                 load=json.dumps({'weekly_budgets': [30]}))
        db.add(p); db.flush()
        contract = prescription('threshold', 'time_intervals', [segment(2, seconds=360, fast=450, slow=450, recovery_seconds=120)])
        contract.update(warmup=segment(meters=1.5*MI), cooldown=segment(meters=1.5*MI))
        for i, typ, miles in [(0,'workout',6),(1,'easy',4),(2,'easy',4),(3,'easy',4),(4,'rest',0),(5,'long_run',8),(6,'rest',0)]:
            db.add(PlannedWorkout(plan_id=p.id,date=(monday+timedelta(days=i)).isoformat(),day_name='x',week_number=1,
                type=typ,title='2x6min Threshold' if typ=='workout' else typ,distance_miles=miles,
                prescription=json.dumps(contract) if typ=='workout' else None, warmup='1.5mi easy',cooldown='1.5mi easy'))
        a = Activity(user_id=1, source='manual', date=datetime.combine(date.today(),datetime.min.time()),
                     name='Private location',distance_meters=5*MI,duration_seconds=2700,feel_rating=7,
                     description='Easy run', feel_notes='Legs good')
        db.add(a);db.commit()
        return p.id,a.id,monday


def fake(monkeypatch, selection='first'):
    monkeypatch.setattr(settings,'openai_api_key','unit-test-secret')
    calls=[]
    def request(context, sources):
        calls.append(context)
        selected = context['candidates'][0]['id'] if selection=='first' else selection
        return openai_coach.CoachAdvice(summary='Controlled run; consider shorter work if recovery is incomplete.',
            plan_fit='consider_change', observations=['Feedback is positive.'], uncertainties=['No lactate measurement.'],
            research_ids=['quality-policy'], suggestions=[openai_coach.Suggestion(candidate_id=selected,reason='Preserves the current pace and recovery spacing.')]), {'input_tokens':100,'output_tokens':80}
    monkeypatch.setattr(coaching,'request_advice',request)
    return calls


def review(plan,activity=None):
    return client.post('/api/coaching/1/review',json={'plan_id':plan,'activity_id':activity})


def test_review_options_are_bounded_and_dry_runs_do_not_mutate(monkeypatch):
    plan,act,day=seed(); calls=fake(monkeypatch)
    r=review(plan,act);assert r.status_code==200,r.text
    data=r.json();assert data['status']=='ready' and len(calls)==1
    original=calls[0]['matched_prescription']
    assert original is None  # run predates the future plan, never invent a match
    assert calls[0]['run']['feel']==7 and 'Private location' not in json.dumps(calls[0])
    with SessionLocal() as db:
        pw=db.query(PlannedWorkout).filter_by(plan_id=plan,date=day.isoformat()).one()
        assert pw.title=='2x6min Threshold' and pw.original_prescription is None and pw.session_status is None
        for option in calls[0]['candidates']:
            if option.get('session_option_id'): continue  # expanded menus have independently tested dose limits
            new=option['replacement'];assert new['distance_miles']<=6
            if new['type']=='workout':
                p=json.loads(new['prescription']);assert p['category']=='threshold' and p['progression_eligible'] is False
                work=p['segments'][0]
                assert work['duration_seconds']*work['reps']<=720
                assert work['pace_range_sec_per_mile']=={'fast':450,'slow':450}
                assert work['recovery_seconds']>=120


def test_identical_review_is_durable_cached_and_gets_are_free(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch)
    first=review(plan,act).json(); second=review(plan,act).json()
    assert first['id']==second['id'] and len(calls)==1
    assert client.get(f'/api/coaching/1/latest?activity_id={act}').json()['stale'] is False
    assert len(calls)==1
    with SessionLocal() as db: assert db.query(CoachingReview).count()==1


def test_apply_requires_selected_option_and_is_idempotent(monkeypatch):
    plan,act,day=seed();fake(monkeypatch)
    data=review(plan,act).json(); url=f'/api/coaching/1/reviews/{data["id"]}/accept'
    assert client.post(url,json={'candidate_id':'invented'}).status_code==422
    option=data['suggestions'][0]
    assert client.post(url,json={'candidate_id':option['id']}).status_code==200
    assert client.post(url,json={'candidate_id':option['id']}).json()['already_applied'] is True
    with SessionLocal() as db:
        pw=db.query(PlannedWorkout).filter_by(plan_id=plan,date=day.isoformat()).one()
        assert json.loads(pw.original_prescription)['title']=='2x6min Threshold'
        assert pw.adjustment_note.startswith('Athlete accepted AI review')
        assert pw.session_status=='replaced'


@pytest.mark.parametrize('change',['feedback','new_run','goal','rest','prescription','activation','laps'])
def test_changed_context_rejects_old_advice(monkeypatch,change):
    plan,act,day=seed();fake(monkeypatch);data=review(plan,act).json()
    with SessionLocal() as db:
        if change=='feedback': db.get(Activity,act).feel_rating=3
        elif change=='new_run': db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=MI,duration_seconds=600))
        elif change=='goal':
            from app.models.user import Goal
            db.query(Goal).first().target_time_seconds=999
        elif change=='rest': db.get(User,1).rest_days='monday,friday'
        elif change=='prescription': db.query(PlannedWorkout).filter_by(plan_id=plan,date=day.isoformat()).one().distance_miles=5
        elif change=='activation': db.get(Plan,plan).is_active=False
        elif change=='laps': db.get(Activity,act).splits=json.dumps([{'intensity':'ACTIVE','distance_m':800,'duration_s':200}])
        db.commit()
    response=client.post(f'/api/coaching/1/reviews/{data["id"]}/accept',json={'candidate_id':data['suggestions'][0]['id']})
    assert response.status_code==409,response.text


@pytest.mark.parametrize('bad',['unknown-option','unknown-source','timeout','refusal'])
def test_invalid_or_unavailable_model_falls_back_without_mutation(monkeypatch,bad):
    plan,act,day=seed();fake(monkeypatch)
    def request(context,sources):
        if bad in {'timeout','refusal'}: raise RuntimeError('Do not leak unit-test-secret in logs')
        return openai_coach.CoachAdvice(summary='advice',plan_fit='consider_change',observations=[],uncertainties=[],
            research_ids=['fake-source'] if bad=='unknown-source' else [],
            suggestions=[openai_coach.Suggestion(candidate_id='fake-option',reason='x')] if bad=='unknown-option' else []),{}
    monkeypatch.setattr(coaching,'request_advice',request)
    data=review(plan,act).json();assert data['status']=='fallback' and data['suggestions']==[]
    with SessionLocal() as db:
        pw=db.query(PlannedWorkout).filter_by(plan_id=plan,date=day.isoformat()).one()
        assert pw.original_prescription is None


def test_daily_quota_counts_failures_and_retry_attempts(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch);monkeypatch.setattr(settings,'openai_coach_daily_limit',1)
    assert review(plan,act).json()['status']=='ready'
    with SessionLocal() as db: db.get(Activity,act).feel_notes='Changed feedback';db.commit()
    assert review(plan,act).status_code==429 and len(calls)==1
    assert client.get('/api/coaching/1/status').json()['reviews_today']==1


def test_unconfigured_fallback_and_no_key_exposure():
    plan,act,_=seed();data=review(plan,act).json()
    assert data['status']=='fallback' and data['model'] is None
    assert 'api_key' not in json.dumps(client.get('/api/coaching/1/status').json())


def test_other_athletes_cannot_review_or_accept(monkeypatch):
    plan,act,_=seed();fake(monkeypatch);data=review(plan,act).json()
    assert client.post('/api/coaching/2/review',json={'plan_id':plan}).status_code==404
    assert client.post(f'/api/coaching/2/reviews/{data["id"]}/accept',json={'candidate_id':data['suggestions'][0]['id']}).status_code==404


def test_preview_review_is_readonly_and_no_options(monkeypatch):
    plan,act,_=seed();monkeypatch.setattr(settings,'openai_api_key','unit-test-secret')
    with SessionLocal() as db: p=db.get(Plan,plan);p.is_active=False;p.preview_state='draft';db.commit()
    def request(context,sources):
        assert context['candidates']==[]
        return openai_coach.CoachAdvice(summary='Preview fits the goal.',plan_fit='consistent',observations=[],uncertainties=[],research_ids=[],suggestions=[]),{}
    monkeypatch.setattr(coaching,'request_advice',request)
    assert review(plan).json()['status']=='ready'


def test_transport_store_false_bounded_timeout_no_retries(monkeypatch):
    captured={}
    class FakeClient:
        def __init__(self,**kwargs):captured.update(kwargs);self.responses=self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def parse(self,**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(status='completed',output_parsed=openai_coach.CoachAdvice(summary='ok',plan_fit='consistent',observations=[],uncertainties=[],research_ids=[],suggestions=[]),usage=None)
    monkeypatch.setattr(openai_coach,'OpenAI',FakeClient)
    advice,_=openai_coach.request_advice({'run':None},[])
    assert captured['store'] is False and captured['max_retries']==0 and captured['max_output_tokens']==3000
    assert captured['text_format'] is openai_coach.CoachAdvice and advice.summary=='ok'


def test_concurrent_requests_reserve_once(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch)
    barrier=threading.Barrier(2);results=[]
    def request():
        barrier.wait();results.append(review(plan,act))
    threads=[threading.Thread(target=request) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert all(r.status_code==200 for r in results) and len(calls)==1


def test_failed_attempt_retry_is_delayed_and_charged_to_quota(monkeypatch):
    plan,act,_=seed();fake(monkeypatch)
    calls=[]
    def fail(*args): calls.append(1);raise TimeoutError('secret not logged')
    monkeypatch.setattr(coaching,'request_advice',fail)
    first=review(plan,act).json(); assert first['status']=='fallback'
    assert review(plan,act).json()['id']==first['id'] and len(calls)==1
    with SessionLocal() as db:
        db.get(CoachingReview,first['id']).created_at=datetime.now()-timedelta(minutes=6);db.commit()
    assert review(plan,act).json()['status']=='fallback' and len(calls)==2
    assert client.get('/api/coaching/1/status').json()['reviews_today']==2


def test_interrupted_reservation_can_be_recovered(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch)
    first=review(plan,act).json()
    with SessionLocal() as db:
        row=db.get(CoachingReview,first['id']);row.status='pending';row.created_at=datetime.now()-timedelta(minutes=6);db.commit()
    assert review(plan,act).json()['status']=='ready' and len(calls)==2


def test_provider_errors_do_not_log_credentials(monkeypatch,caplog):
    plan,act,_=seed();fake(monkeypatch)
    def fail(*args):raise RuntimeError('unit-test-secret highly private athlete payload')
    monkeypatch.setattr(coaching,'request_advice',fail)
    assert review(plan,act).json()['status']=='fallback'
    assert 'unit-test-secret' not in caplog.text and 'highly private' not in caplog.text


def test_final_validation_failure_rolls_back_audit_and_prescription(monkeypatch):
    from fastapi import HTTPException
    from app.api import plans
    plan,act,day=seed();fake(monkeypatch);data=review(plan,act).json()
    validate=plans._validate_schedule;calls=[]
    def guarded(plan,db):
        # Candidate trials have no audit note. Reject only actual acceptance.
        if db.query(PlannedWorkout).filter(PlannedWorkout.original_prescription.is_not(None)).count():
            calls.append(1);raise HTTPException(409,'New safety constraint rejected this change')
        return validate(plan,db)
    monkeypatch.setattr(plans,'_validate_schedule',guarded)
    r=client.post(f'/api/coaching/1/reviews/{data["id"]}/accept',json={'candidate_id':data['suggestions'][0]['id']})
    assert r.status_code==409 and calls==[1]
    with SessionLocal() as db:
        pw=db.query(PlannedWorkout).filter_by(plan_id=plan,date=day.isoformat()).one()
        assert pw.original_prescription is None and pw.title=='2x6min Threshold'
        assert db.get(CoachingReview,data['id']).applied_candidate_id is None


def test_auto_feedback_review_failure_preserves_saved_feedback(monkeypatch):
    plan,act,_=seed();fake(monkeypatch)
    with SessionLocal() as db:
        db.add(PlannedWorkout(plan_id=plan,date=date.today().isoformat(),day_name='x',week_number=1,
            type='easy',title='Run before plan',distance_miles=5));db.commit()
    def fail(*args):raise TimeoutError('unavailable')
    monkeypatch.setattr(coaching,'request_advice',fail)
    r=client.post(f'/api/plans/1/feedback/{date.today()}',json={'feel_rating':7,'feel_notes':'Good recovery'})
    assert r.status_code==200,r.text
    with SessionLocal() as db:
        assert db.get(Activity,act).feel_rating==7
        assert db.query(CoachingReview).one().status=='fallback'
    assert 'Solid day' in r.json()['coach_response']


def test_advice_is_generated_after_deterministic_feedback(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch)
    with SessionLocal() as db:
        db.add(PlannedWorkout(plan_id=plan,date=date.today().isoformat(),day_name='x',week_number=1,
            type='easy',title='Run before plan',distance_miles=5));db.commit()
    r=client.post(f'/api/plans/1/feedback/{date.today()}',json={'feel_rating':7,'feel_notes':'Good recovery'})
    assert r.status_code==200 and len(calls)==1
    assert calls[0]['run']['feel']==7 and calls[0]['run']['notes']=='Good recovery'
    assert 'Controlled run' in r.json()['coach_response']


def test_no_options_for_completed_day_or_rest_day(monkeypatch):
    plan,act,day=seed();fake(monkeypatch)
    with SessionLocal() as db:
        db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=6*MI,duration_seconds=3000));db.commit()
        context,_,_,_=coaching.build_context(1,db,act,plan)
        assert context['candidates']==[]


def test_malformed_laps_are_unknown_not_a_failed_request(monkeypatch):
    plan,act,_=seed();fake(monkeypatch)
    with SessionLocal() as db:db.get(Activity,act).splits='{not valid';db.commit()
    assert review(plan,act).status_code==200


def test_context_separates_weekly_quality_and_does_not_forbid_introductory_work(monkeypatch):
    plan,act,day=seed();calls=fake(monkeypatch)
    with SessionLocal() as db:
        db.add(PlannedWorkout(plan_id=plan,date=(day+timedelta(days=7)).isoformat(),day_name='x',week_number=2,
            type='workout',title='Threshold week two',distance_miles=5));db.commit()
    assert review(plan,act).status_code==200
    assert [len(w['quality_days']) for w in calls[0]['plan']['weekly_structure']]==[1,1]
    assert 'PER WEEK' in calls[0]['policy_interpretation']['initial_quality']
    assert calls[0]['run']['date']==date.today().isoformat()


def test_training_changed_during_model_call_is_marked_stale(monkeypatch):
    plan,act,_=seed();fake(monkeypatch)
    original=coaching.request_advice
    def request(context,sources):
        with SessionLocal() as other:other.get(Activity,act).feel_rating=3;other.commit()
        return original(context,sources)
    monkeypatch.setattr(coaching,'request_advice',request)
    data=review(plan,act).json()
    assert data['status']=='ready' and data['stale'] is True


def test_oversized_context_never_makes_a_provider_call(monkeypatch):
    def forbidden(**kwargs):raise AssertionError('Do not construct transport for oversized input')
    monkeypatch.setattr(openai_coach,'OpenAI',forbidden)
    with pytest.raises(ValueError,match='input budget'):
        openai_coach.request_advice({'notes':'x'*120001},[])


def test_continuous_alternative_has_an_interval_execution_contract():
    from app.services.coaching_options import _variants
    data=prescription('threshold','continuous',[segment(1,seconds=1200,fast=450,slow=450)],note='Stay controlled, not all-out.')
    data.update(warmup=segment(meters=MI),cooldown=segment(meters=MI))
    row=PlannedWorkout(type='workout',title='20min Tempo',distance_miles=6,prescription=json.dumps(data))
    variants=_variants(row,{'long_run_pace':570})
    assert variants
    contract=json.loads(variants[0]['prescription'])
    assert contract['format']=='time_intervals' and contract['segments'][0]['reps']==2
    assert 'Stay controlled, not all-out.' in contract['note']


def test_distance_alternative_title_retains_decimal_distance():
    from app.services.coaching_options import _variants
    data=prescription('intervals','track_intervals',[segment(2,meters=1.5*MI,fast=450,slow=450,recovery_seconds=120)])
    data.update(warmup=segment(meters=MI),cooldown=segment(meters=MI))
    row=PlannedWorkout(type='workout',title='2x1.5mi',distance_miles=6,prescription=json.dumps(data))
    assert '1.5mi' in _variants(row,{'long_run_pace':570})[0]['title']


def test_feedback_reviews_work_activity_not_larger_warmup(monkeypatch):
    plan,act,_=seed();calls=fake(monkeypatch)
    with SessionLocal() as db:
        db.add(PlannedWorkout(plan_id=plan,date=date.today().isoformat(),day_name='x',week_number=1,
            type='easy',title='Split recording day',distance_miles=5))
        warmup=db.get(Activity,act);warmup.distance_meters=4*MI;warmup.description='Warmup'
        work=Activity(user_id=1,source='manual',date=warmup.date,distance_meters=MI,duration_seconds=360,
            description='6x800 (3:00, 3:00, 3:00, 3:00, 3:00, 3:00)')
        db.add(work);db.commit();work_id=work.id
    r=client.post(f'/api/plans/1/feedback/{date.today()}',json={'feel_rating':7,'feel_notes':'Controlled reps'})
    assert r.status_code==200 and calls[0]['run']['id']==work_id
    assert calls[0]['run']['feel']==7


def test_opening_plan_does_not_stale_automatic_review(monkeypatch):
    plan,act,_=seed();fake(monkeypatch)
    with SessionLocal() as db:
        p=db.get(Plan,plan);p.start_date=date.today().isoformat();p.prescribed_from=date.today().isoformat()
        db.add(PlannedWorkout(plan_id=plan,date=date.today().isoformat(),day_name='x',week_number=1,type='easy',title='Easy',distance_miles=5))
        p.load=json.dumps({'weekly_budgets':[40]});db.commit()
    initial=review(plan,act).json();assert initial['status']=='ready'
    assert client.get('/api/plans/1/current').status_code==200
    latest=client.get(f'/api/coaching/1/latest?activity_id={act}').json()
    assert latest['id']==initial['id'] and latest['stale'] is False
    with SessionLocal() as db:db.get(Activity,act).feel_rating=2;db.commit()
    assert client.get(f'/api/coaching/1/latest?activity_id={act}').json()['stale'] is True


def concern_review(plan, concern):
    return client.post('/api/coaching/1/review', json={'plan_id': plan, 'athlete_concern': concern})


def test_athlete_concern_reaches_model_as_data_and_gets_its_own_review(monkeypatch):
    plan,_,_=seed();calls=fake(monkeypatch)
    plain=review(plan).json()
    asked=concern_review(plan,'  Too much   volume this week ').json()
    assert len(calls)==2 and 'athlete_request' not in calls[0]
    assert calls[1]['athlete_request']=='Too much volume this week'
    assert asked['id']!=plain['id'] and asked['athlete_concern']=='Too much volume this week'
    assert 'athlete_request' in openai_coach.INSTRUCTIONS
    # Same words again are a cache hit, not a second provider call.
    assert concern_review(plan,'Too much volume this week').json()['id']==asked['id'] and len(calls)==2
    # Blank concern is no concern.
    assert concern_review(plan,'   ').json()['id']==plain['id'] and len(calls)==2


def test_concern_review_is_fresh_and_applicable(monkeypatch):
    plan,_,day=seed();fake(monkeypatch)
    data=concern_review(plan,'Schedule conflict on Monday').json()
    latest=client.get(f'/api/coaching/1/latest?plan_id={plan}').json()
    assert latest['id']==data['id'] and latest['stale'] is False and latest['athlete_concern']=='Schedule conflict on Monday'
    option=data['suggestions'][0]
    r=client.post(f'/api/coaching/1/reviews/{data["id"]}/accept',json={'candidate_id':option['id']})
    assert r.status_code==200,r.text


def test_athlete_concern_is_bounded():
    plan,_,_=seed()
    assert concern_review(plan,'x'*501).status_code==422
