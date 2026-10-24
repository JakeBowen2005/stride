from datetime import datetime,timedelta
import threading

from app.config import settings
from app.database import SessionLocal
from app.models.activity import Activity
from app.models.coaching import CoachingJob
from app.services import coaching_jobs,coaching


def seed(monkeypatch,age=0):
    monkeypatch.setattr(settings,'openai_auto_reviews',True)
    monkeypatch.setattr(settings,'openai_api_key','test-provider-key')
    with SessionLocal() as db:
        a=Activity(user_id=1,source='garmin',external_id='new-run',date=datetime.now()-timedelta(days=age),distance_meters=8000,duration_seconds=2700,feel_notes='Felt smooth.')
        db.add(a);db.flush();coaching_jobs.enqueue_synced_run(a,db);db.commit();return a.id


def test_enqueue_is_transactional_recent_only_and_idempotent(monkeypatch):
    act=seed(monkeypatch)
    with SessionLocal() as db:
        coaching_jobs.enqueue_synced_run(db.get(Activity,act),db);db.commit()
        assert db.query(CoachingJob).count()==1 and db.query(CoachingJob).one().status=='waiting_sync'
        old=Activity(user_id=1,source='garmin',date=datetime.now()-timedelta(days=100),distance_meters=8000,duration_seconds=2700,feel_notes='Old run.')
        db.add(old);db.flush();coaching_jobs.enqueue_synced_run(old,db);db.commit()
        assert db.query(CoachingJob).count()==1
        new=Activity(user_id=1,source='garmin',date=datetime.now(),distance_meters=8000,duration_seconds=2700,feel_notes='New run.')
        db.add(new);db.flush();coaching_jobs.enqueue_synced_run(new,db);db.rollback()
        assert db.query(CoachingJob).count()==1


def test_job_waits_for_sync_and_reviews_without_mutating_feedback(monkeypatch):
    act=seed(monkeypatch);calls=[]
    def review(user,db,activity_id):
        calls.append(activity_id)
        # network work happens outside the claim transaction
        with SessionLocal() as other: assert other.get(Activity,activity_id).feel_rating is None
        return {'status':'ready','id':None}
    monkeypatch.setattr(coaching,'review_training',review)
    assert coaching_jobs.process_one() is False
    with SessionLocal() as db:coaching_jobs.release_synced_jobs(1,db)
    assert coaching_jobs.process_one() is True and calls==[act]
    assert coaching_jobs.process_one() is False
    with SessionLocal() as db:assert db.query(CoachingJob).one().status=='done' and db.get(Activity,act).feel_rating is None


def test_crashed_running_job_is_recovered(monkeypatch):
    seed(monkeypatch)
    with SessionLocal() as db:
        job=db.query(CoachingJob).one();job.status='running';job.updated_at=datetime.now()-timedelta(minutes=11);job.attempts=1;db.commit()
    monkeypatch.setattr(coaching,'review_training',lambda *args,**kwargs:{'status':'ready','id':None})
    assert coaching_jobs.process_one()
    with SessionLocal() as db:assert db.query(CoachingJob).one().status=='done'


def test_provider_failure_is_bounded_and_secret_safe(monkeypatch,caplog):
    seed(monkeypatch)
    with SessionLocal() as db:coaching_jobs.release_synced_jobs(1,db)
    def fail(*args,**kwargs):raise RuntimeError('test-provider-key secret payload')
    monkeypatch.setattr(coaching,'review_training',fail)
    for i in range(4):
        with SessionLocal() as db:db.query(CoachingJob).one().available_at=datetime.now()-timedelta(seconds=1);db.commit()
        assert coaching_jobs.process_one()
    with SessionLocal() as db:assert db.query(CoachingJob).one().status=='failed' and db.query(CoachingJob).one().attempts==3
    assert 'test-provider-key' not in caplog.text and 'secret payload' not in caplog.text


def test_concurrent_workers_claim_one_job(monkeypatch):
    act=seed(monkeypatch);calls=[]
    with SessionLocal() as db:coaching_jobs.release_synced_jobs(1,db)
    def review(*args,**kwargs):calls.append(act);return {'status':'ready','id':None}
    monkeypatch.setattr(coaching,'review_training',review)
    threads=[threading.Thread(target=coaching_jobs.process_one) for _ in range(2)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert calls==[act]


def test_synced_runs_wait_for_the_athletes_comment(monkeypatch):
    """No paid review of a run nobody has described: the comment starts it, immediately."""
    monkeypatch.setattr(settings,'openai_auto_reviews',True)
    with SessionLocal() as db:
        a=Activity(user_id=1,source='garmin',external_id='silent',date=datetime.now(),distance_meters=8000,duration_seconds=2700)
        db.add(a);db.flush();coaching_jobs.enqueue_synced_run(a,db);db.commit()
        assert db.query(CoachingJob).count()==0
        a.feel_notes='Legs heavy early, smooth after mile two.'
        coaching_jobs.enqueue_synced_run(a,db,ready=True);db.commit()
        job=db.query(CoachingJob).one()
        assert job.status=='queued'  # no wait for another sync


def test_garmin_store_enqueues_new_and_merged_recent_runs_once_commented(monkeypatch):
    from app.services.garmin import _store_activity
    from types import SimpleNamespace
    monkeypatch.setattr(settings,'openai_auto_reviews',True)
    fake=SimpleNamespace(get_activity_splits=lambda _:{'lapDTOs':[]},get_activity=lambda _:{})
    with SessionLocal() as db:
        parsed={'source':'garmin','external_id':'fresh-1','date':datetime.now(),'distance_meters':8000,'duration_seconds':2700,'name':'New run'}
        assert _store_activity(fake,1,{},parsed,db,570)=='new'
        db.commit();assert db.query(CoachingJob).count()==0  # synced, not yet commented
        db.query(Activity).filter_by(external_id='fresh-1').one().feel_notes='Easy and relaxed.'
        assert _store_activity(fake,1,{},parsed,db,570)=='updated'
        db.commit();assert db.query(CoachingJob).count()==1
        assert _store_activity(fake,1,{},parsed,db,570)=='updated'
        db.commit();assert db.query(CoachingJob).count()==1
        legacy=Activity(user_id=1,source='strava',external_id='old',date=datetime.now()-timedelta(hours=2),distance_meters=7000,duration_seconds=2400,feel_notes='Logged by hand.')
        db.add(legacy);db.commit()
        merged={**parsed,'external_id':'fresh-2','date':legacy.date,'distance_meters':7000,'duration_seconds':2400}
        assert _store_activity(fake,1,{},merged,db,570)=='merged'
        db.commit();assert db.query(CoachingJob).count()==2


def test_sync_releases_jobs_after_wellness_attempt(monkeypatch):
    from app.api import garmin
    from app.services import coaching_jobs
    seed(monkeypatch);events=[]
    monkeypatch.setattr(garmin,'sync_garmin',lambda *args,**kwargs:events.append('runs') or {'status':'ok','new':1})
    monkeypatch.setattr(garmin,'sync_wellness',lambda *args:events.append('wellness') or {'status':'ok'})
    original=coaching_jobs.release_synced_jobs
    def release(*args):events.append('release');original(*args)
    monkeypatch.setattr(coaching_jobs,'release_synced_jobs',release)
    assert garmin._sync_in_new_session(1,False)['status']=='ok'
    assert events==['runs','wellness','release']


def test_quota_wait_is_deferred_without_exhausting_failure_retries(monkeypatch):
    from fastapi import HTTPException
    seed(monkeypatch)
    with SessionLocal() as db:coaching_jobs.release_synced_jobs(1,db)
    def quota(*args,**kwargs):raise HTTPException(429,'Daily cap')
    monkeypatch.setattr(coaching,'review_training',quota)
    assert coaching_jobs.process_one()
    with SessionLocal() as db:
        job=db.query(CoachingJob).one();assert job.status=='queued' and job.attempts==0
        assert job.available_at>datetime.now()+timedelta(minutes=1)
