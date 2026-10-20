"""Explicit review generation and athlete-approved, revalidated suggestions."""
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.coaching import CoachingReview, CoachingJob
from app.models.plan import Plan, PlannedWorkout
from app.services.coaching import build_context, review_training, serialize_review

router = APIRouter(prefix='/api/coaching', tags=['coaching'])


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    activity_id: int | None = Field(default=None, gt=0)
    plan_id: int | None = Field(default=None, gt=0)


class AcceptRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    candidate_id: str = Field(max_length=100)


@router.get('/{user_id}/status')
def status(user_id: int, db: Session = Depends(get_db)):
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.query(func.coalesce(func.sum(CoachingReview.attempts), 0)).filter(
        CoachingReview.user_id == user_id, CoachingReview.created_at >= day,
        CoachingReview.model.is_not(None)).scalar()
    return {'configured': bool(settings.openai_api_key), 'model': settings.openai_coach_model,
            'reviews_today': used, 'daily_limit': settings.openai_coach_daily_limit}


@router.post('/{user_id}/review')
def create_review(user_id: int, req: ReviewRequest, db: Session = Depends(get_db)):
    return review_training(user_id, db, req.activity_id, req.plan_id)


@router.get('/{user_id}/jobs/{activity_id}')
def job_status(user_id: int, activity_id: int, db: Session = Depends(get_db)):
    row = db.query(CoachingJob).filter_by(user_id=user_id,activity_id=activity_id).order_by(CoachingJob.id.desc()).first()
    return {'enabled':settings.openai_auto_reviews, 'status':row.status if row else None,
            'attempts':row.attempts if row else 0, 'message':row.last_error if row else None}


@router.get('/{user_id}/latest')
def latest(user_id: int, activity_id: int | None = None, plan_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(CoachingReview).filter_by(user_id=user_id)
    if activity_id:
        query = query.filter_by(activity_id=activity_id)
    elif plan_id:
        query = query.filter_by(plan_id=plan_id, activity_id=None)
    else:
        raise HTTPException(422, 'Choose a run or plan')
    row = query.order_by(CoachingReview.id.desc()).first()
    if not row:
        return None
    _, _, fingerprint, _ = build_context(user_id, db, activity_id, plan_id)
    return serialize_review(row, stale=fingerprint != row.context_hash)


@router.post('/{user_id}/reviews/{review_id}/accept')
def accept(user_id: int, review_id: int, req: AcceptRequest, db: Session = Depends(get_db)):
    from app.api.plans import _begin_schedule_write, _get_activities_for_date, _mark_changed, _validate_schedule
    _begin_schedule_write(db)
    review = db.query(CoachingReview).filter_by(id=review_id, user_id=user_id).first()
    if not review:
        raise HTTPException(404, 'Review not found')
    if review.applied_candidate_id:
        if review.applied_candidate_id == req.candidate_id:
            return {'applied': True, 'already_applied': True}
        raise HTTPException(409, 'One suggestion was already applied. Review the updated plan before another change.')
    if review.status != 'ready':
        raise HTTPException(409, 'Only a completed AI review can suggest changes')
    result = json.loads(review.result)
    if req.candidate_id not in {s['candidate_id'] for s in result.get('suggestions', [])}:
        raise HTTPException(422, 'Choose a suggestion from this review')
    _, _, fingerprint, plan = build_context(user_id, db, review.activity_id, review.plan_id)
    if fingerprint != review.context_hash:
        raise HTTPException(409, 'Training, feedback or schedule changed. Request a fresh review before applying this suggestion.')
    if not plan or not plan.is_active:
        raise HTTPException(409, 'Only the active approved plan can be changed')
    candidate = next((c for c in json.loads(review.candidates) if c['id'] == req.candidate_id), None)
    if not candidate:
        raise HTTPException(422, 'Unknown suggestion')
    row = db.query(PlannedWorkout).filter_by(id=candidate['session_id'], plan_id=plan.id).first()
    if (not row or row.date < max(date.today().isoformat(), plan.prescribed_from or plan.start_date)
            or (row.type != 'workout' and not candidate.get('session_option_id')) or row.activity_id or row.moved_to
            or _get_activities_for_date(row.date, user_id, db)):
        raise HTTPException(409, 'This session is no longer editable')
    try:
        if candidate.get('session_option_id'):
            from app.services.session_options import apply_option
            apply_option(plan,row,candidate['category'],candidate['session_option_id'],f'Athlete accepted AI review #{review.id}',db)
            review.applied_candidate_id=req.candidate_id
            db.commit()
            return {'applied':True,'date':row.date,'already_applied':False}
        _mark_changed(row, f'Athlete accepted AI review #{review.id}, option {candidate["id"]}.')
        for key, value in candidate['replacement'].items():
            setattr(row, key, value)
        row.session_status = 'replaced'
        db.flush()
        _validate_schedule(plan, db)
        review.applied_candidate_id = req.candidate_id
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'applied': True, 'date': row.date, 'already_applied': False}
