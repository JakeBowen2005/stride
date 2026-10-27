import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import Activity, PersonalRecord, activity_classification, is_walk
from app.models.user import User
from app.services.analyzer import analyze_athlete, detect_prs, compute_mileage, compute_weekly_mileage, classify_activities
from app.services.pace_calibrator import calibrate_paces

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

METERS_TO_MILES = 0.000621371
METERS_TO_FEET = 3.28084


@router.get("/{user_id}/baseline")
def get_baseline(user_id: int, db: Session = Depends(get_db)):
    """Analyze all running data and return athlete baseline assessment."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.info['history_cache_write'] = True
    from app.api.plans import _begin_schedule_write
    _begin_schedule_write(db)
    analysis = analyze_athlete(user_id, db)
    db.commit()
    return analysis


@router.get("/{user_id}/calibrated-paces")
def get_calibrated_paces(user_id: int, weeks: int = Query(default=12), db: Session = Depends(get_db)):
    """Get training paces calibrated from real workout descriptions."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return calibrate_paces(user_id, db, weeks_back=weeks)


@router.get("/{user_id}/prs")
def get_prs(user_id: int, db: Session = Depends(get_db)):
    """Get all personal records for a user."""
    prs = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == user_id)
        .order_by(PersonalRecord.distance_miles.asc())
        .all()
    )
    return [
        {
            "id": pr.id,
            "distance": pr.distance_label,
            "distance_miles": pr.distance_miles,
            "time_seconds": pr.time_seconds,
            "time_formatted": _format_time(pr.time_seconds),
            "pace_per_mile": _format_pace(pr.pace_per_mile),
            "date": pr.date.isoformat() if pr.date else None,
        }
        for pr in prs
    ]


@router.post("/{user_id}/detect-prs")
def run_pr_detection(user_id: int, db: Session = Depends(get_db)):
    """Run PR detection on all activities."""
    prs = detect_prs(user_id, db)
    return {"personal_records": prs, "count": len(prs)}


@router.post("/{user_id}/classify")
def run_classification(user_id: int, db: Session = Depends(get_db)):
    """Classify all activities by workout type."""
    return classify_activities(user_id, db)


@router.get("/{user_id}/weekly-mileage")
def get_weekly_mileage(user_id: int, weeks: int = Query(default=52), db: Session = Depends(get_db)):
    """Get weekly mileage data."""
    return compute_weekly_mileage(user_id, db, weeks)


@router.get("/{user_id}/mileage")
def get_mileage(user_id: int, bucket: Literal["week", "month", "year"] = "week",
                count: int | None = Query(default=None, ge=1, le=104), db: Session = Depends(get_db)):
    """Recorded vs planned miles per week, month or year, with empty periods filled in."""
    if not db.get(User, user_id):
        raise HTTPException(404, "Athlete not found")
    return compute_mileage(user_id, db, bucket, count)


# --- Activities endpoints for frontend ---

@router.get("/{user_id}/activities")
def get_activities_list(
    user_id: int,
    type: str | None = None,
    limit: int = Query(default=100,ge=1,le=200),
    offset: int = Query(default=0,ge=0),
    before_date: datetime | None = None,
    before_id: int | None = Query(default=None,ge=1),
    db: Session = Depends(get_db),
):
    """Get activities for the history tab."""
    query = db.query(Activity).filter(Activity.user_id == user_id)

    if before_date is not None:
        from sqlalchemy import or_,and_
        query=query.filter(or_(Activity.date<before_date,and_(Activity.date==before_date,Activity.id<before_id))) if before_id else query.filter(Activity.date<before_date)
    if type and type != "all":
        if type == "workouts":
            query = query.filter(Activity.workout_type.in_(["tempo", "intervals", "threshold", "fartlek", "hill_repeats", "time_trial", "race", "workout"]))
        elif type == "long_runs":
            query = query.filter(Activity.workout_type == "long_run")
        elif type == "easy":
            query = query.filter(Activity.workout_type.in_(["easy", "recovery", None]))

    activities = (
        query.order_by(Activity.date.desc(),Activity.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    from app.services.garmin import recent_easy_pace
    easy = recent_easy_pace(user_id, db)
    return [_format_activity(a, easy) for a in activities]


@router.get("/{user_id}/activities/{activity_id}")
def get_activity_detail(user_id: int, activity_id: int, db: Session = Depends(get_db)):
    """Get single activity detail."""
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == user_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _format_activity(activity)


class ReviewData(BaseModel):
    feel_rating: int = Field(ge=1, le=10)
    notes: str | None = None


@router.post("/{user_id}/activities/{activity_id}/review")
def submit_review(user_id: int, activity_id: int, data: ReviewData, db: Session = Depends(get_db)):
    """Submit post-run feel rating and notes."""
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.user_id == user_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity.feel_rating = data.feel_rating
    activity.feel_notes = data.notes
    db.commit()

    return {"message": "Review saved", "activity_id": activity_id}


from app.api.plans import FeedbackRequest


@router.post("/{user_id}/activities/{activity_id}/feedback")
def activity_feedback(user_id: int, activity_id: int, data: FeedbackRequest, db: Session = Depends(get_db)):
    """An answer belongs to one recording, including doubles and previous blocks.

    Only the primary recording of an active prescribed session may apply the
    existing exactly-once day adjustments. Historical/off-plan answers remain
    evidence for the next assessment, never retroactive progression credit.
    """
    from app.api.plans import _begin_schedule_write, _get_activities_for_date, _work_evidence_activity, submit_feedback
    from app.models.plan import Plan, PlannedWorkout
    from app.services.coaching_jobs import enqueue_synced_run, release_synced_jobs
    from app.api.plans import require_comment
    require_comment(data)
    from app.services.garmin import refresh_watch_rating
    refresh_watch_rating(user_id, db.query(Activity).filter_by(user_id=user_id, id=activity_id).first(), db)
    _begin_schedule_write(db)
    activity = db.query(Activity).filter_by(user_id=user_id, id=activity_id).first()
    if activity is None:
        raise HTTPException(404, "Activity not found")
    day = activity.date.date().isoformat()
    plan = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    pw = db.query(PlannedWorkout).filter_by(plan_id=plan.id, date=day).first() if plan else None
    primary = _work_evidence_activity(_get_activities_for_date(day, user_id, db))
    result = {}
    if pw and pw.type != 'rest' and primary and primary.id == activity.id:
        result = submit_feedback(user_id, day, data, db)
    activity.feel_notes = data.feel_notes
    # Comment-only answers keep any earlier app rating; feel/effort otherwise come from the watch
    if data.feel_rating is not None:
        activity.feel_rating = data.feel_rating
    if data.effort_rating is not None:
        activity.effort_rating = data.effort_rating
    if data.completion is not None:
        activity.reported_completion = data.completion
    enqueue_synced_run(activity, db, ready=True)
    db.commit()
    release_synced_jobs(user_id, db)
    return {**result, 'activity_id': activity.id, 'feel_rating': activity.feel_rating,
            'effort_rating': activity.effort_rating, 'reported_completion': {'status':activity.reported_completion,'source':'self_reported'} if activity.reported_completion else None,
            'coach_response': result.get('coach_response', 'Feedback saved for your next training assessment.')}


QUALITY_TYPES = {"workout", "intervals", "threshold", "tempo", "fartlek"}


def _session(a: Activity, splits: list, easy_pace: float | None) -> dict | None:
    """What the laps show was run on a quality day, e.g. {"title": "3x8min Threshold", "category": "threshold"}."""
    if a.workout_type not in QUALITY_TYPES or not isinstance(splits, list) or not all(isinstance(s, dict) for s in splits):
        return None
    from app.core.session_match import session_title
    from app.services.lap_analyzer import analyze_laps
    found = analyze_laps(splits, easy_pace, a.feel_notes)
    return {"title": session_title(found), "category": found["category"]} if found else None


def _format_activity(a: Activity, easy_pace: float | None = None) -> dict:
    """Format an activity for the frontend."""
    dist_miles = a.distance_meters * METERS_TO_MILES if a.distance_meters else 0
    pace_per_mile = (a.duration_seconds / dist_miles) if dist_miles > 0 else 0

    splits = []
    if a.splits:
        try:
            splits = json.loads(a.splits)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "classification": activity_classification(a),
        "id": a.id,
        "external_id": a.external_id,
        "source": a.source,
        "date": a.date.isoformat() if a.date else None,
        "type": a.workout_type or "easy",
        "title": a.name or "Run",
        "description": a.description,
        "distance_miles": round(dist_miles, 2),
        "duration_seconds": round(a.duration_seconds) if a.duration_seconds else 0,
        "avg_pace": _format_pace(pace_per_mile),
        "avg_heart_rate": round(a.average_heartrate) if a.average_heartrate else None,
        "max_heart_rate": round(a.max_heartrate) if a.max_heartrate else None,
        "elevation_gain_ft": round(a.elevation_gain * METERS_TO_FEET) if a.elevation_gain else None,
        "cadence": round(a.average_cadence * 2) if a.average_cadence else None,
        "splits": splits,
        "session": _session(a, splits, easy_pace),
        "feel_rating": a.feel_rating,
        "effort_rating": a.effort_rating, "reported_completion": a.reported_completion,
        "watch_feel": a.watch_feel, "watch_effort": a.watch_effort,
        "watch_feel_label": a.watch_feel_label, "watch_effort_label": a.watch_effort_label,
        "notes": a.feel_notes,
        "coach_analysis": None,  # Stored reviews use /api/coaching so freshness is explicit
        "suffer_score": a.suffer_score,
        "strava_workout_type": a.strava_workout_type,
        "event_type": a.event_type,
        "activity_subtype": a.activity_subtype,
        "aerobic_training_effect": a.aerobic_training_effect,
        "anaerobic_training_effect": a.anaerobic_training_effect,
        "training_effect_label": a.training_effect_label,
        "training_load": a.training_load,
        "vo2max": a.vo2max,
        "avg_ground_contact_time": a.avg_ground_contact_time,
        "avg_vertical_oscillation": a.avg_vertical_oscillation,
        "calories": a.calories,
    }


def _format_pace(seconds_per_mile: float | None) -> str:
    if not seconds_per_mile or seconds_per_mile <= 0:
        return "0:00/mi"
    minutes = int(seconds_per_mile // 60)
    secs = int(seconds_per_mile % 60)
    return f"{minutes}:{secs:02d}/mi"


def _format_time(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = int(total_seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class ActivityKind(BaseModel):
    kind: Literal['run', 'walk', 'auto']


@router.put("/{user_id}/activities/{activity_id}/kind")
def correct_activity_kind(user_id: int, activity_id: int, data: ActivityKind, db: Session = Depends(get_db)):
    from app.api.plans import _begin_schedule_write
    _begin_schedule_write(db)
    activity = db.query(Activity).filter_by(id=activity_id, user_id=user_id).first()
    if not activity:
        raise HTTPException(404, "Activity not found")
    activity.activity_kind_override = None if data.kind == 'auto' else data.kind
    if data.kind == 'auto':
        activity.workout_type = None  # return to provider semantics; no preserved legacy label
    activity.workout_type = 'walk' if is_walk(activity) else 'race' if activity.event_type == 'race' else 'workout' if activity.has_workout_description else 'easy'
    # A reclassified activity invalidates matched execution evidence, never replays
    # progression or rewrites an approved prescription. The athlete may revise it.
    from app.models.plan import PlannedWorkout
    from app.models.plan import Plan
    rows = db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == user_id, PlannedWorkout.date == activity.date.date().isoformat()).all()
    if activity.workout_type == 'walk':
        for row in rows:
            verdict = json.loads(row.evaluation) if row.evaluation else {}
            ids = verdict.get('activity_ids') or []
            if row.activity_id != activity.id and row.feedback_activity_id != activity.id and activity.id not in ids:
                continue
            history = json.loads(row.feedback_history or '[]')
            history.append({'reason':'Source activity corrected to walking', 'activity_id':activity.id,
                'feel_rating':row.feel_rating, 'feel_notes':row.feel_notes, 'pace_assessment':row.pace_assessment,
                'evaluation':verdict, 'execution':row.execution, 'coach_response':row.coach_response})
            row.feedback_history = json.dumps(history)
            row.activity_id = row.feedback_activity_id = None
            row.feel_rating = row.feel_notes = row.pace_assessment = None
            row.evaluation = row.execution = row.coach_response = None
            row.session_status = 'not_logged'
            # Keep the effects claim: correcting identity must not replay past progression.
    db.commit()
    return _format_activity(activity)


@router.get("/{user_id}/operations")
def operations(user_id: int, db: Session = Depends(get_db)):
    import os
    from pathlib import Path
    from sqlalchemy import func
    from app.config import settings
    from app.models.coaching import CoachingJob
    from app.services.coaching import VERSION
    if not db.get(User, user_id):
        raise HTTPException(404, "Athlete not found")
    counts = dict(db.query(CoachingJob.status, func.count(CoachingJob.id)).filter_by(user_id=user_id).group_by(CoachingJob.status).all())
    oldest = db.query(func.min(CoachingJob.available_at)).filter(CoachingJob.user_id == user_id, CoachingJob.status.in_(['queued','waiting_sync'])).scalar()
    # Do not reveal backup filenames, table counts, credentials or bucket/key names.
    folder = os.environ.get('STRIDE_BACKUP_DIR')
    if not folder and settings.database_url.startswith('sqlite:///'):
        from app.services.backups import database_path
        folder = str(database_path(settings.database_url).parent / 'backups')
    try:
        info = json.loads((Path(folder) / 'status.json').read_text()) if folder else {}
    except (OSError, ValueError, TypeError):
        info = {}
    from app.models.coaching import CoachingAttempt,CoachingReview
    from app.athlete_clock import day_start_utc
    day=day_start_utc()
    usage=db.query(func.count(CoachingAttempt.id),func.coalesce(func.sum(CoachingAttempt.input_tokens),0),
        func.coalesce(func.sum(CoachingAttempt.output_tokens),0),func.avg(CoachingAttempt.latency_ms)).join(CoachingReview,CoachingReview.id==CoachingAttempt.review_id).filter(CoachingReview.user_id==user_id,CoachingAttempt.created_at>=day).one()
    return {'ai_usage':{'attempts_today':usage[0],'input_tokens_today':usage[1],'output_tokens_today':usage[2],
                       'mean_latency_ms':round(usage[3]) if usage[3] is not None else None,'daily_review_limit':settings.openai_coach_daily_limit},
            'queue': {'queued': counts.get('queued',0)+counts.get('waiting_sync',0), 'running':counts.get('running',0),
                      'failed':counts.get('failed',0), 'oldest_queued_at':oldest.isoformat() if oldest else None},
            'backup': {'configured': bool(info.get('last_local_success')), 'offsite_configured':bool(os.environ.get('STRIDE_BACKUP_S3_BUCKET')),
                       'last_success_at':info.get('last_local_success'), 'offsite_last_success_at':info.get('last_remote_success'),
                       'offsite_error_type':info.get('last_remote_error_type'), 'restore_verified':bool(info.get('restore_verified')),
                       'last_error_type':info.get('last_error_type'), 'storage':info.get('storage')}, 'app': {'policy_version':VERSION}}


@router.get("/{user_id}/history")
def get_history(user_id: int, db: Session = Depends(get_db)):
    from app.services.history_facts import historical_profile
    from app.services.history_cache import revision
    if not db.get(User, user_id):
        raise HTTPException(404, "Athlete not found")
    from app.api.plans import _begin_schedule_write
    _begin_schedule_write(db)
    result = historical_profile(user_id, db)
    result['revision'] = revision(user_id, db)
    db.commit()
    return result


@router.post('/{user_id}/history/reparse-fits')
def reparse_history(user_id: int, force: bool = False, limit: int = Query(default=100, ge=1, le=200), db: Session = Depends(get_db)):
    from app.api.plans import _begin_schedule_write
    from app.services.history_evidence import reparse_fits
    if not db.get(User, user_id):
        raise HTTPException(404, 'Athlete not found')
    _begin_schedule_write(db)
    return reparse_fits(user_id, db, limit=limit, force=force)


from fastapi import Request


@router.post('/{user_id}/import-fit')
async def upload_fit(user_id:int,request:Request,db:Session=Depends(get_db)):
    from app.services.fit_import import MAX_BYTES,import_fit
    if int(request.headers.get('content-length') or 0)>MAX_BYTES:
        raise HTTPException(413,'FIT file exceeds 10 MiB.')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>MAX_BYTES:
            raise HTTPException(413,'FIT file exceeds 10 MiB.')
    try:
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(import_fit,user_id,bytes(body),db)
    except ValueError as exc:
        db.rollback();raise HTTPException(422,str(exc))
    except Exception:
        db.rollback();raise HTTPException(422,'Unable to import this FIT file. Check it is an original running activity.')


@router.get('/{user_id}/aerobic-efficiency')
def aerobic_efficiency_trend(user_id:int,weeks:int=Query(default=26,ge=4,le=104),db:Session=Depends(get_db)):
    from app.services.longitudinal import aerobic_efficiency
    if not db.get(User,user_id):raise HTTPException(404,'Athlete not found')
    return aerobic_efficiency(user_id,db,weeks)


@router.get('/{user_id}/trends')
def training_trends(user_id:int,db:Session=Depends(get_db)):
    from app.api.plans import _begin_schedule_write
    from app.athlete_clock import today
    from app.services.history_cache import fresh
    from app.services.longitudinal import VERSION, analyze
    if not db.get(User,user_id):raise HTTPException(404,'Athlete not found')
    hit=fresh(user_id,VERSION,today().isoformat(),db)
    if hit is not None:
        return hit  # a page view shouldn't take the database writer lock
    _begin_schedule_write(db)
    result=analyze(user_id,db)
    db.commit()
    return result
