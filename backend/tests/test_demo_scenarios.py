import json
from pathlib import Path
from datetime import date,datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User,Goal
from app.models.activity import Activity
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
            assert any('Hill' in r.title for r in rows)
            assert any(r.b2b for r in rows)
            assert any('Fuel' in (r.description or '') for r in rows)
        if scenario=='sub17-5k':assert sum(r.type=='workout' for r in rows)==4
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
