import json
from pathlib import Path
from datetime import date,datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User,Goal
from app.models.activity import Activity,PersonalRecord
from app.models.plan import Plan,PlannedWorkout
from app.models.coaching import CoachingJob,CoachingReview
from app.services.demo_seed import seed_demo

client=TestClient(app)
ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('scenario,phase',[('sub3-marathon','peak'),('sub17-5k','build'),('trail-100k','build')])
def test_synthetic_history_to_approved_block_feedback_and_revision(scenario,phase):
    profile=json.loads((ROOT/'demo/scenarios'/f'{scenario}.json').read_text())
    with SessionLocal() as db:
        db.query(Goal).delete();db.query(User).delete();db.commit()
        result=seed_demo(db,profile)
        assert result['quality_stage']=='dual' and result['phases'][0]==phase
        assert db.query(Activity).count()>=72
        assert db.query(Plan).filter_by(is_active=True).count()==1
        assert db.query(CoachingJob).count()==0 and db.query(CoachingReview).count()==0
        assert db.get(User,1).name.startswith('Demo')
        plan=db.query(Plan).filter_by(is_active=True).one()
        rows=db.query(PlannedWorkout).filter_by(plan_id=plan.id).all()
        assert all(json.loads(r.prescription)['schema_version']==1 for r in rows)
        if scenario=='trail-100k':
            assert any('Hill' in r.title or 'Climb' in r.title for r in rows)
            assert any(r.b2b for r in rows)
            assert any('Fuel' in (r.description or '') for r in rows)
        if scenario=='sub17-5k':
            # Dual stage = two sessions in every fully prescribed week; a week already
            # under way only gets the sessions still ahead of today.
            for week in {r.week_number for r in rows}:
                week_rows=[r for r in rows if r.week_number==week]
                ahead=sum(r.type=='workout' for r in week_rows if r.date>=date.today().isoformat())
                assert ahead==2 if min(r.date for r in week_rows)>=date.today().isoformat() else ahead<=2
        # Today's run is real synthetic evidence, not a feel-only completion claim.
        today=db.query(PlannedWorkout).filter_by(plan_id=plan.id,date=date.today().isoformat()).one()
        db.add(Activity(user_id=1,source='manual',name='Synthetic new easy run',date=datetime.now(),distance_meters=max(3,today.distance_miles)*1609.34,duration_seconds=max(3,today.distance_miles)*profile['easy_pace'],workout_type='easy'))
        db.commit()
    response=client.post(f'/api/plans/1/feedback/{date.today()}',json={'feel_rating':8,'feel_notes':'SYNTHETIC recovered well'})
    assert response.status_code==200,response.text
    current=client.get('/api/plans/1/current');assert current.status_code==200
    revised=client.post('/api/plans/1/preview',json={});assert revised.status_code==200,revised.text
    assert revised.json()['violations']==[]
    approved=client.post(f'/api/plans/1/drafts/{revised.json()["id"]}/approve')
    assert approved.status_code==200,approved.text



def _feedback_preview_approve(profile):
    with SessionLocal() as db:
        plan=db.query(Plan).filter_by(is_active=True).one()
        today=db.query(PlannedWorkout).filter_by(plan_id=plan.id,date=date.today().isoformat()).one()
        db.add(Activity(user_id=1,source='manual',name='Synthetic new easy run',date=datetime.now(),distance_meters=max(2,today.distance_miles)*1609.34,duration_seconds=max(2,today.distance_miles)*profile['easy_pace'],workout_type='easy'))
        db.commit()
    response=client.post(f'/api/plans/1/feedback/{date.today()}',json={'feel_rating':8,'feel_notes':'SYNTHETIC recovered well'})
    assert response.status_code==200,response.text
    assert client.get('/api/plans/1/current').status_code==200
    revised=client.post('/api/plans/1/preview',json={});assert revised.status_code==200,revised.text
    assert revised.json()['violations']==[]
    approved=client.post(f'/api/plans/1/drafts/{revised.json()["id"]}/approve')
    assert approved.status_code==200,approved.text


@pytest.mark.parametrize('scenario,phase',[('beginner-marathon','base'),('beginner-mileage','general'),('beginner-5k','base')])
def test_beginner_scenarios_are_conservative(scenario,phase):
    from app.core.plan_validator import is_hard
    profile=json.loads((ROOT/'demo/scenarios'/f'{scenario}.json').read_text())
    with SessionLocal() as db:
        db.query(Goal).delete();db.query(User).delete();db.commit()
        result=seed_demo(db,profile)  # raises on any validator violation
        assert result['quality_stage']!='dual'
        assert result['phases'][0]==phase
        if profile.get('goal_type')=='mileage':
            assert set(result['phases'])=={'general'} and result['race_date'] is None
        user,goal=db.get(User,1),db.query(Goal).one()
        assert user.name.startswith('Demo') and user.experience_level=='beginner'
        assert user.days_per_week==profile['days_per_week'] and user.rest_days==','.join(profile['rest_days'])
        assert goal.goal_type==profile.get('goal_type','race') and goal.target_weekly_mileage==profile.get('target_weekly_mileage')
        assert db.query(PersonalRecord).count()==len(profile['prs'])
        assert user.pr_10k is None
        # Easy-only history: no workout days, no laps.
        history=db.query(Activity).all()
        assert history and all(a.workout_type in ('easy','long_run') for a in history)
        assert all(not json.loads(a.splits or '[]') for a in history)
        plan=db.query(Plan).filter_by(is_active=True).one()
        rows=sorted(db.query(PlannedWorkout).filter_by(plan_id=plan.id).all(),key=lambda r:r.date)
        days=[{'date':r.date,'type':r.type,'distance_miles':r.distance_miles} for r in rows]
        for a,b in zip(days,days[1:]):
            assert not (is_hard(a) and is_hard(b)),(a,b)
        for week in (1,2):
            week_rows=[r for r in rows if r.week_number==week]
            assert sum(r.distance_miles>0 for r in week_rows)<=profile['days_per_week']
        # 10% rule: week one stays within ~1.1x the recent 4-week average.
        recent=sum(profile['weekly_miles'][-4:])/4
        assert sum(r.distance_miles for r in rows if r.week_number==1)<=recent*1.1+0.5
        assert not any(r.type=='workout' for r in rows if r.week_number==1)  # no early speed work
    _feedback_preview_approve(profile)


def test_seed_refuses_populated_database():
    with SessionLocal() as db:
        with pytest.raises(ValueError,match='Refusing'):seed_demo(db,{})


def test_demo_cli_refuses_existing_file_and_resolved_symlink(tmp_path):
    import subprocess,sys
    target=tmp_path/'existing.db';target.write_bytes(b'preserve this file')
    alias=tmp_path/'alias.db';alias.symlink_to(target)
    for path in (target,alias):
        result=subprocess.run([sys.executable,str(ROOT/'demo/seed.py'),'--scenario','sub3-marathon','--database',str(path)],capture_output=True,text=True)
        assert result.returncode!=0 and 'Refusing' in result.stderr
    assert target.read_bytes()==b'preserve this file'


def test_low_volume_long_run_not_shorter_than_easy_days():
    from app.core.plan_validator import fit_week_to_budget
    days=[{'date':f'2026-10-2{i}','type':t,'distance_miles':m} for i,(t,m) in enumerate([('easy',3),('easy',3),('long_run',2)])]
    notes=fit_week_to_budget(days,8,'easy')
    miles=[d['distance_miles'] for d in days]
    assert sum(miles)==8 and max(miles)==3  # same total, no longer single run
    assert miles[2]>=max(miles[:2]) and any('Long run set' in n for n in notes)
