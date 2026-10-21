import json
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.activity import Activity, is_walk, activity_classification
from app.models.coaching import CoachingJob
from app.services.coaching import build_context
from app.services.load_history import completed_week_load
from tests.test_separate_activities import seed, walk

client = TestClient(app)
MI = 1609.34


@pytest.mark.parametrize('subtype,event', [('trail_running','race'), ('running',None), ('treadmill_running',None), ('ultra_run',None), ('run_walk_run',None)])
def test_pace_alone_never_excludes_running(subtype,event):
    activity=Activity(activity_subtype=subtype,event_type=event,distance_meters=62*MI,duration_seconds=62*18*60)
    assert not is_walk(activity)
    assert activity_classification(activity)['kind']=='run'
    activity.activity_kind_override='walk'
    assert is_walk(activity)
    activity.activity_kind_override='run'
    assert not is_walk(activity)


def test_legacy_trail_exclusion_is_repaired_but_treadmill_label_requires_confirmation():
    trail=Activity(activity_subtype='trail_running',workout_type='walk',distance_meters=MI,duration_seconds=1200)
    treadmill=Activity(activity_subtype='treadmill_running',workout_type='walk',distance_meters=MI,duration_seconds=1200)
    assert not is_walk(trail)
    assert is_walk(treadmill) and activity_classification(treadmill)['needs_review']


def test_walk_is_not_reviewed_or_queued_and_correction_is_persistent(monkeypatch):
    from app.services import coaching_jobs
    seed(walk)
    monkeypatch.setattr(coaching_jobs.settings,'openai_auto_reviews',True)
    with SessionLocal() as db:
        activity=db.query(Activity).filter_by(workout_type='walk').one()
        activity_id=activity.id
        with pytest.raises(HTTPException,match='walking activity'):
            build_context(1,db,activity_id=activity.id)
        coaching_jobs.enqueue_synced_run(activity,db)
        db.commit()
        assert db.query(CoachingJob).count()==0
    assert client.put(f'/api/analysis/1/activities/{activity_id}/kind',json={'kind':'run'}).status_code==200
    with SessionLocal() as db:
        assert db.get(Activity,activity_id).activity_kind_override=='run'
        assert not is_walk(db.get(Activity,activity_id))
    corrected=client.put(f'/api/analysis/1/activities/{activity_id}/kind',json={'kind':'walk'})
    assert corrected.json()['classification']['kind']=='walk'
    assert client.put(f'/api/analysis/2/activities/{activity_id}/kind',json={'kind':'run'}).status_code==404


def test_double_context_never_borrows_primary_reps():
    seed(lambda at: Activity(user_id=1,source='manual',name='Evening easy',date=at.replace(hour=18),
        distance_meters=2*MI,duration_seconds=1200,workout_type='easy'))
    with SessionLocal() as db:
        easy=db.query(Activity).filter_by(name='Evening easy').one()
        context,*_=build_context(1,db,activity_id=easy.id)
        assert context['run']['id']==easy.id
        assert context['run']['detected_session'] is None
        assert context['matched_prescription'] is None
        primary=db.query(Activity).filter_by(source='garmin').one()
        context,*_=build_context(1,db,activity_id=primary.id)
        assert context['run']['detected_session']['matched_activity_ids']==[primary.id]
        assert context['run']['miles']==7
    current=client.get('/api/plans/1/current').json()
    actual=next(d['actual'] for w in current['weeks'] for d in w['days'] if d['date']==date.today().isoformat())
    assert actual['activity_id']==primary.id


def test_calendar_load_uses_completed_weeks_zeros_and_matches_baseline():
    today=date.today();monday=today-timedelta(days=today.weekday())
    with SessionLocal() as db:
        for i,miles in enumerate([22,33,23,38]):
            day=monday-timedelta(weeks=4-i)
            db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=miles*MI,duration_seconds=miles*600))
        # A huge current-week run, a future run and a walk must not affect the ratio.
        for day,kind in [(today,'easy'),(today+timedelta(days=10),'easy'),(monday-timedelta(days=2),'walk')]:
            db.add(Activity(user_id=1,source='manual',date=datetime.combine(day,datetime.min.time()),distance_meters=100*MI,duration_seconds=60000,workout_type=kind))
        db.commit()
        load=completed_week_load(1,db)
        assert load['acute_miles']==38 and load['baseline_miles']==29
        assert load['ratio']==1.31
        assert load['acute_week_end']==(monday-timedelta(days=1)).isoformat()
        assert load['weeks'][0]['miles']==0
    baseline=client.get('/api/analysis/1/baseline').json()
    assert baseline['current_fitness']['weekly_mileage_4w_avg']==29
    assert baseline['injury_risk']['acute_chronic_ratio']==1.31
    assert baseline['workload']['policy_version']=='calendar-load-v1'


def test_readiness_distinguishes_database_failure(monkeypatch):
    assert client.get('/ready').status_code==200
    from app import database
    def broken():raise RuntimeError('private database path must not leak')
    monkeypatch.setattr(database,'SessionLocal',broken)
    response=client.get('/ready')
    assert response.status_code==503 and 'private' not in response.text
    assert client.get('/health').status_code==200


def test_legacy_ultra_and_run_walk_training_are_restored():
    for subtype in ('ultra_run', 'run_walk_run'):
        activity=Activity(activity_subtype=subtype,workout_type='walk',distance_meters=20*MI,duration_seconds=20*1200)
        assert not is_walk(activity)


def test_operational_status_is_sanitized_and_distinguishes_remote_failure(tmp_path,monkeypatch):
    folder=tmp_path/'private-backups';folder.mkdir()
    (folder/'status.json').write_text(json.dumps({'last_local_success':'2026-10-20T12:00:00+00:00','restore_verified':True,
        'last_remote_error_type':'AccessDenied','last_error_type':'AccessDenied','last_backup':'private-file.sqlite3',
        'table_counts':{'private_table':100},'last_remote_key':'private-bucket/key'}))
    monkeypatch.setenv('STRIDE_BACKUP_DIR',str(folder));monkeypatch.setenv('STRIDE_BACKUP_S3_BUCKET','private-bucket')
    response=client.get('/api/analysis/1/operations')
    assert response.status_code==200
    info=response.json()['backup']
    assert info['restore_verified'] and info['offsite_configured']
    assert info['offsite_last_success_at'] is None and info['offsite_error_type']=='AccessDenied'
    assert 'private' not in response.text and 'table_counts' not in response.text


def test_additive_migration_protects_preexisting_data_before_reclassification(tmp_path):
    import os,sqlite3,subprocess,sys
    from pathlib import Path
    from app.database import engine
    source=tmp_path/'legacy.db'
    with sqlite3.connect(engine.url.database) as original, sqlite3.connect(source) as legacy:
        original.backup(legacy)
        legacy.execute('ALTER TABLE activities DROP COLUMN activity_kind_override')
        legacy.execute('ALTER TABLE coaching_reviews DROP COLUMN policy_version')
        legacy.execute('ALTER TABLE planned_workouts DROP COLUMN feedback_activity_id')
        legacy.execute('ALTER TABLE planned_workouts DROP COLUMN feedback_history')
        legacy.execute("INSERT INTO activities (user_id,source,date,distance_meters,duration_seconds,activity_subtype,workout_type,event_type,has_workout_description,user_highlighted) VALUES (1,'manual','2026-10-19',100000,60000,'ultra_run','walk','race',0,0)")
        legacy.commit()
    folder=tmp_path/'backups'
    env={**os.environ,'DATABASE_URL':f'sqlite:///{source}','STRIDE_BACKUP_DIR':str(folder),'STRIDE_BACKUP_S3_BUCKET':'',
        'GARMIN_POLL_MINUTES':'0','OPENAI_API_KEY':'','ANTHROPIC_API_KEY':'','OPENAI_AUTO_REVIEWS':'false','ATHLETE_PROFILE_DOC':''}
    run=subprocess.run([sys.executable,'-c','import app.main'],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True)
    assert run.returncode==0,run.stderr.decode()[-500:]
    with sqlite3.connect(source) as migrated:
        assert migrated.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert migrated.execute('SELECT workout_type FROM activities').fetchone()[0]=='race'
        assert 'activity_kind_override' in {r[1] for r in migrated.execute('PRAGMA table_info(activities)')}
    status=json.loads((folder/'status.json').read_text())
    with sqlite3.connect(folder/status['last_backup']) as backup:
        assert backup.execute('SELECT workout_type FROM activities').fetchone()[0]=='walk'
        assert 'activity_kind_override' not in {r[1] for r in backup.execute('PRAGMA table_info(activities)')}
        assert backup.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1


def test_classification_correction_archives_feedback_without_giving_it_to_the_double():
    from app.models.plan import PlannedWorkout
    from app.services.coaching import build_context
    seed(lambda at: Activity(user_id=1,source='manual',name='Unrated double',date=at.replace(hour=18),distance_meters=2*MI,duration_seconds=1200,workout_type='easy'))
    with SessionLocal() as db:
        primary=db.query(Activity).filter_by(source='garmin').one()
        primary_id=primary.id
        double_id=db.query(Activity).filter_by(name='Unrated double').one().id
        row=db.query(PlannedWorkout).filter_by(date=date.today().isoformat()).one()
        row.activity_id=primary_id;row.feedback_activity_id=primary_id
        row.feel_rating=8;row.feel_notes='This belongs to the primary workout'
        row.evaluation=json.dumps({'decision':'advance','activity_ids':[primary_id]})
        row.side_effects_applied_at=datetime.now()
        db.commit()
    assert client.put(f'/api/analysis/1/activities/{primary_id}/kind',json={'kind':'walk'}).status_code==200
    with SessionLocal() as db:
        context,*_=build_context(1,db,activity_id=double_id)
        assert context['run']['athlete_feedback']['feel_1_to_10'] is None
        assert context['run']['athlete_feedback']['notes'] is None
        assert context['deterministic_evaluation']['decision']!='advance'
        row=db.query(PlannedWorkout).filter_by(date=date.today().isoformat()).one()
        assert row.side_effects_applied_at is not None
        assert json.loads(row.feedback_history)[0]['evaluation']['decision']=='advance'
