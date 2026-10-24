from datetime import datetime,timedelta
import json
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.activity import Activity
from app.core.workout_data import prescription,segment
from app.core.time_budget import fit_availability,estimated_minutes


def controlled(reps=1,seconds=600):
    p=prescription('development','controlled',[segment(reps,seconds=seconds,recovery_seconds=60 if reps>1 else None)])
    p.update(warmup=segment(seconds=600),cooldown=segment(seconds=600),progression_eligible=True)
    return {'date':'2026-10-20','day':'tuesday','type':'workout','title':'Controlled effort','description':'','distance_miles':4,'prescription':p}


def test_time_limits_keep_bookends_and_do_not_invent_progression_credit():
    full=controlled()
    fit_availability([{'days':[full]}],{'tuesday':30},600)
    assert estimated_minutes(full,600)<=30.1
    assert full['prescription']['segments'][0]['duration_seconds']==600
    assert full['prescription']['progression_eligible'] is True  # only easy padding removed
    shorter=controlled(5,120)
    fit_availability([{'days':[shorter]}],{'tuesday':30},600)
    assert estimated_minutes(shorter,600)<=30.1
    assert shorter['prescription']['segments'][0]['reps']<5
    assert shorter['prescription']['progression_eligible'] is False
    assert shorter['title']=='Controlled session · time fitted'
    assert shorter['prescription']['warmup']['duration_seconds']==600
    assert shorter['prescription']['cooldown']['duration_seconds']==600


def test_time_fit_preserves_completed_days_and_makes_long_run_longest():
    days=[{'date':'2026-10-20','day':'tuesday','type':'easy','title':'Done','distance_miles':8,'prescribed':False},
          {'date':'2026-10-22','day':'thursday','type':'easy','title':'Easy','distance_miles':6},
          {'date':'2026-10-24','day':'saturday','type':'long_run','title':'Long','distance_miles':9}]
    fit_availability([{'days':days}],{'saturday':50,'tuesday':15},600,developing=True)
    assert days[0]['distance_miles']==8
    assert days[2]['distance_miles']==5
    assert days[1]['distance_miles']<=5/1.2


def test_saved_daily_time_changes_plan_and_blocks_overlong_manual_changes():
    from tests.test_api import _seed_runs,_preview_and_approve
    client=TestClient(app)
    _seed_runs()
    limits={d:45 for d in ['monday','tuesday','wednesday','thursday','saturday','sunday']}
    assert client.put('/api/users/1/profile',json={'day_time_budgets':limits}).status_code==200
    r=_preview_and_approve()
    assert r.json()['expectations']
    for w in r.json()['weeks']:
        for d in w['days']:
            if d.get('prescribed',True) and d['type'] not in {'rest','race'}:
                assert estimated_minutes(d,r.json()['athlete']['easy_pace_seconds'])<=45.1
    assert client.put('/api/users/1/profile',json={'day_time_budgets':{'tuesday':3}}).status_code==422


def test_trends_cache_invalidates_after_feedback_and_keeps_unknown_work_unknown():
    from app.athlete_clock import today
    from app.services.longitudinal import analyze
    with SessionLocal() as db:
        run=Activity(user_id=1,source='manual',name='Quality without laps',date=datetime.combine(today()-timedelta(days=2),datetime.min.time()),
                     distance_meters=5000,duration_seconds=1800,workout_type='workout')
        db.add(run);db.commit()
        first=analyze(1,db);db.commit()
        assert first['quality_sessions'][0]['work_minutes'] is None
        run.effort_rating=6;db.commit()
        second=analyze(1,db);db.commit()
        assert second['quality_sessions'][0]['effort']==6
        assert second['comparable_easy_runs'] is None
        assert first['quality_sessions'][0]['effort'] is None


def test_global_ai_budget_blocks_before_any_provider_call(monkeypatch):
    from app.config import settings
    from app.services import coaching
    from tests.test_api import _seed_runs,_preview_and_approve
    _seed_runs();_preview_and_approve()
    monkeypatch.setattr(settings,'openai_api_key','test-only-key')
    monkeypatch.setattr(settings,'openai_coach_global_daily_limit',0)
    monkeypatch.setattr(coaching,'request_advice',lambda *args:(_ for _ in ()).throw(AssertionError('No provider call allowed')))
    response=TestClient(app).post('/api/coaching/1/review',json={})
    assert response.status_code==429,response.text


def test_evaluation_requires_real_coach_labels_and_rejects_unknown_evidence():
    from app.services.coaching_eval import evaluate,CRITERIA
    case={'case_id':'missing-laps','context':{'candidates':[],'historical_profile':{'insights':[]}},'review':{'suggestions':[],'history_insight_ids':[]}}
    assert evaluate(case)['status']=='needs_coach_review'
    case['coach_labels']={key:True for key in CRITERIA}
    assert evaluate(case)['status']=='pass'
    case['review']['history_insight_ids']=['invented']
    assert evaluate(case)['status']=='fail'


def test_true_beginner_time_adaptation_preserves_run_walk():
    from app.core.developmental import run_walk_day
    d={'date':'2026-10-20','day':'tuesday'}
    run_walk_day(d,0,720)
    fit_availability([{'days':[d]}],{'tuesday':15},720,developing=True)
    assert d['prescription']['format']=='run_walk'
    assert d['prescription']['segments'][0]['recovery_seconds']>0
    assert estimated_minutes(d,720)<=15.1


def test_quality_moves_to_roomier_easy_day_before_reducing_earned_dose():
    session=controlled(5,120)
    thursday={'date':'2026-10-22','day':'thursday','type':'easy','title':'Easy','distance_miles':3}
    long={'date':'2026-10-24','day':'saturday','type':'long_run','title':'Long','distance_miles':6}
    week={'days':[session,thursday,long]}
    notes=fit_availability([week],{'tuesday':30,'thursday':45,'saturday':90},600)
    assert session['type']=='easy'
    assert thursday['type']=='workout'
    assert thursday['prescription']['segments'][0]['reps']==5
    assert thursday['prescription']['progression_eligible'] is True
    assert any('Moved the full quality dose' in n for n in notes)


def test_history_cursor_does_not_skip_same_timestamp_recordings():
    client=TestClient(app)
    stamp=datetime.now()-timedelta(days=1)
    with SessionLocal() as db:
        for i in range(3):db.add(Activity(user_id=1,source='manual',name=str(i),date=stamp,distance_meters=3000,duration_seconds=1200))
        db.commit()
    first=client.get('/api/analysis/1/activities',params={'limit':1}).json()[0]
    second=client.get('/api/analysis/1/activities',params={'limit':1,'before_date':first['date'],'before_id':first['id']}).json()[0]
    assert first['id']!=second['id']
    assert client.get('/api/analysis/1/activities?limit=100000').status_code==422


def test_off_plan_completion_reaches_coach_as_subjective_evidence():
    from app.services.coaching import _run
    run=Activity(id=42,user_id=1,source='manual',name='Off plan',date=datetime.now(),distance_meters=5000,duration_seconds=1800,reported_completion='all',effort_rating=6)
    feedback=_run(run)['athlete_feedback']
    assert feedback['reported_completion']=={'completion':'all','evidence_source':'self_reported'}
    assert feedback['effort_1_to_10']==6
