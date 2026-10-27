from app.athlete_clock import today as athlete_today
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


REVIEW_WINDOW_DAYS = 7  # matches the Today list of recent runs awaiting a comment


def enqueue_synced_run(activity, db, ready=False):
    """Queue the automatic run review, then the block's coach perspective. Caller owns the transaction.

    The block refresh is queued after the run review so it runs second and sees the run's
    comment and review too; it doesn't wait for a comment (a new run alone changes the week)."""
    if is_walk(activity) or not settings.openai_auto_reviews or activity.date.date() > athlete_today():
        return
    if activity.date.date() < athlete_today()-timedelta(days=REVIEW_WINDOW_DAYS):
        return
    from app.models.user import User
    if not db.get(User,activity.user_id).ai_consent:  # every mode, the owner included
        return
    db.flush()
    version = _evidence_version(activity)
    _enqueue_run_review(activity, version, db, ready)
    _enqueue_block_refresh(activity, version, db, ready)


def _evidence_version(activity):
    evidence = [getattr(activity, key) for key in ('date', 'distance_meters', 'duration_seconds', 'splits', 'event_type', 'activity_kind_override', 'feel_rating', 'feel_notes', 'effort_rating', 'reported_completion', 'garmin_feel', 'garmin_rpe')]
    evidence = [float(v) if isinstance(v, (int, float)) else v for v in evidence]
    return 'e2-' + hashlib.sha256(json.dumps(evidence, default=str).encode()).hexdigest()[:26]


def _enqueue_block_refresh(activity, version, db, ready):
    """Refresh the active plan's coach perspective once per change to a run's evidence."""
    from app.models.plan import Plan
    version = 'b' + version[1:]  # (user, activity, version) is unique: the run review holds 'e2-…'
    plan = db.query(Plan).filter_by(user_id=activity.user_id, is_active=True).first()
    if not plan:
        return
    if db.query(CoachingJob).filter_by(user_id=activity.user_id, activity_id=activity.id, plan_id=plan.id,
                                       version=version).first():
        return
    # One pending refresh per athlete: the newest run's job covers every earlier one
    db.query(CoachingJob).filter(CoachingJob.user_id == activity.user_id, CoachingJob.plan_id.isnot(None),
        CoachingJob.status.in_(['queued', 'waiting_sync'])).update({'status': 'superseded'}, synchronize_session=False)
    db.add(CoachingJob(user_id=activity.user_id, activity_id=activity.id, plan_id=plan.id, version=version,
                       status='queued' if ready else 'waiting_sync', available_at=datetime.now(timezone.utc)))


def _enqueue_run_review(activity, version, db, ready):
    """The run's own review.

    The review starts from the athlete's comment: without one, a synced run waits
    (no paid review of a run nobody has described yet). `ready` is the comment being
    saved right now, so the job is queued immediately; a later Garmin change to a
    commented run (laps, watch rating) re-queues it after that sync completes.
    Never enqueues paid historical backfill."""
    if len((activity.feel_notes or '').strip()) < 3:
        return
    existing = db.query(CoachingJob).filter_by(user_id=activity.user_id, activity_id=activity.id, version=version,
                                               plan_id=None).first()
    if existing and not (ready and existing.status != 'running'):
        return
    db.query(CoachingJob).filter(CoachingJob.user_id == activity.user_id, CoachingJob.activity_id == activity.id,
        CoachingJob.plan_id.is_(None), CoachingJob.status.in_(['queued', 'waiting_sync'])).update({'status': 'superseded'}, synchronize_session=False)
    if existing:
        # Saving the comment again always asks for a review: one of the same evidence and
        # unchanged training is served from cache (free); a stale one is redone.
        existing.status, existing.attempts, existing.last_error = 'queued', 0, None
        existing.available_at = datetime.now(timezone.utc)
        return
    db.add(CoachingJob(user_id=activity.user_id, activity_id=activity.id, version=version,
                       status='queued' if ready else 'waiting_sync',
                       available_at=datetime.now(timezone.utc)))


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
        )).order_by(CoachingJob.id).with_for_update(skip_locked=True).first()
        if not job:
            db.commit(); return False
        activity = db.get(Activity, job.activity_id)
        from app.models.user import User
        from app.athlete_clock import athlete_zone
        athlete=db.get(User,job.user_id)
        with athlete_zone(athlete.timezone if athlete else None,job.user_id):
            calendar_day=athlete_today()
        if not activity or is_walk(activity) or activity.date.date() < calendar_day-timedelta(days=7):
            job.status, job.last_error = 'failed', 'Activity is not eligible for an automatic running review'
            db.commit(); return True
        if job.plan_id:
            from app.models.plan import Plan
            plan = db.get(Plan, job.plan_id)
            if not plan or not plan.is_active:
                job.status = 'superseded'  # a newer plan replaced it; its own runs refresh that one
                db.commit(); return True
        if job.attempts >= 3:
            job.status, job.last_error = 'failed', 'Automatic retry limit reached; manual review remains available'
            db.commit(); return True
        lease_token = uuid4().hex
        job.lease_token = lease_token
        job.status, job.updated_at = 'running', now
        job.attempts += 1
        job_id, user_id, activity_id, plan_id = job.id, job.user_id, job.activity_id, job.plan_id
        db.commit()
    # Separate session: the import and job-claim transactions are already committed.
    quota_wait = False
    try:
        with SessionLocal() as db:
            from app.models.user import User
            from app.athlete_clock import athlete_zone
            athlete=db.get(User,user_id)
            with athlete_zone(athlete.timezone if athlete else None,user_id):
                review = (review_training(user_id, db, plan_id=plan_id) if plan_id
                          else review_training(user_id, db, activity_id=activity_id))
        state = 'done' if review['status']=='ready' else 'queued'
        error = None if state=='done' else 'Review unavailable; retry scheduled'
        review_id = review['id']
        delay = timedelta(minutes=5)
    except Exception as exc:
        state, error, review_id = 'queued', type(exc).__name__, None
        delay = timedelta(minutes=5)
        if isinstance(exc, HTTPException) and exc.status_code==429:
            error = 'Daily AI limit reached; waiting for the allowance to reset'
            quota_wait = True
            # The check costs nothing; hourly retries pick up the athlete's midnight reset or a raised limit
            delay = timedelta(hours=1)
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
