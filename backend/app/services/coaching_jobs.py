"""Durable local jobs. Garmin import commits the job, a separate worker reviews it."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import asyncio
import logging
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, and_

from app.config import settings
from app.database import SessionLocal
from app.models.activity import Activity, is_walk
from app.models.coaching import CoachingJob

logger = logging.getLogger('stride.coaching_jobs')


def enqueue_synced_run(activity, db):
    """Caller owns the import transaction. Never enqueue paid historical backfill."""
    if is_walk(activity) or not settings.openai_auto_reviews or activity.date.date() < date.today()-timedelta(days=2) or activity.date.date() > date.today():
        return
    db.flush()
    evidence = [getattr(activity, key) for key in ('date', 'distance_meters', 'duration_seconds', 'splits', 'event_type', 'activity_kind_override', 'feel_rating', 'feel_notes', 'garmin_feel', 'garmin_rpe')]
    evidence = [float(v) if isinstance(v, (int, float)) else v for v in evidence]
    version = 'e2-' + hashlib.sha256(json.dumps(evidence, default=str).encode()).hexdigest()[:26]
    if not db.query(CoachingJob).filter_by(user_id=activity.user_id, activity_id=activity.id, version=version).first():
        db.query(CoachingJob).filter(CoachingJob.user_id == activity.user_id, CoachingJob.activity_id == activity.id,
            CoachingJob.status.in_(['queued', 'waiting_sync'])).update({'status': 'superseded'}, synchronize_session=False)
        db.add(CoachingJob(user_id=activity.user_id, activity_id=activity.id, version=version, status='waiting_sync'))


def release_synced_jobs(user_id, db):
    db.query(CoachingJob).filter_by(user_id=user_id, status='waiting_sync').update(
        {'status': 'queued', 'available_at': datetime.now(timezone.utc)}, synchronize_session=False)
    db.commit()


def process_one():
    if not settings.openai_auto_reviews or not settings.openai_api_key:
        return False
    from app.api.plans import _begin_schedule_write
    from app.services.coaching import review_training
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        _begin_schedule_write(db)
        job = db.query(CoachingJob).filter(or_(
            and_(CoachingJob.status=='queued', CoachingJob.available_at<=now),
            and_(CoachingJob.status=='running', CoachingJob.updated_at<now-timedelta(minutes=10)),
        )).order_by(CoachingJob.id).first()
        if not job:
            db.commit(); return False
        activity = db.get(Activity, job.activity_id)
        if not activity or is_walk(activity) or activity.date.date() < date.today()-timedelta(days=7):
            job.status, job.last_error = 'failed', 'Activity is not eligible for an automatic running review'
            db.commit(); return True
        if job.attempts >= 3:
            job.status, job.last_error = 'failed', 'Automatic retry limit reached; manual review remains available'
            db.commit(); return True
        lease_token = uuid4().hex
        job.lease_token = lease_token
        job.status, job.updated_at = 'running', now
        job.attempts += 1
        job_id, user_id, activity_id = job.id, job.user_id, job.activity_id
        db.commit()
    # Separate session: the import and job-claim transactions are already committed.
    quota_wait = False
    try:
        with SessionLocal() as db:
            review = review_training(user_id, db, activity_id=activity_id)
        state = 'done' if review['status']=='ready' else 'queued'
        error = None if state=='done' else 'Review unavailable; retry scheduled'
        review_id = review['id']
        delay = timedelta(minutes=5)
    except Exception as exc:
        state, error, review_id = 'queued', type(exc).__name__, None
        delay = timedelta(minutes=5)
        if isinstance(exc, HTTPException) and exc.status_code==429:
            error = 'Daily AI limit reached; queued for the next UTC day'
            quota_wait = True
            delay = (datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)-datetime.now(timezone.utc))
        logger.warning('Automatic review deferred (%s)', type(exc).__name__)
    with SessionLocal() as db:
        _begin_schedule_write(db)
        job = db.query(CoachingJob).filter_by(id=job_id,lease_token=lease_token).first()
        if not job:return True  # a recovered lease owns completion now
        job.lease_token = None
        if quota_wait:job.attempts=max(0,job.attempts-1)
        job.status, job.last_error, job.review_id = state, error, review_id
        job.available_at = datetime.now(timezone.utc)+delay
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
    return True


async def coaching_worker():
    while True:
        try:
            worked = await asyncio.to_thread(process_one)
        except Exception as exc:
            logger.warning('Coaching worker unavailable (%s)', type(exc).__name__)
            worked = False
        await asyncio.sleep(1 if worked else 5)
