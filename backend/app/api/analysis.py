import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import Activity, PersonalRecord
from app.models.user import User
from app.services.analyzer import analyze_athlete, detect_prs, compute_weekly_mileage, classify_activities
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

    analysis = analyze_athlete(user_id, db)
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


# --- Activities endpoints for frontend ---

@router.get("/{user_id}/activities")
def get_activities_list(
    user_id: int,
    type: str | None = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
):
    """Get activities for the history tab."""
    query = db.query(Activity).filter(Activity.user_id == user_id)

    if type and type != "all":
        if type == "workouts":
            query = query.filter(Activity.workout_type.in_(["tempo", "intervals", "threshold", "fartlek", "hill_repeats", "time_trial", "race", "workout"]))
        elif type == "long_runs":
            query = query.filter(Activity.workout_type == "long_run")
        elif type == "easy":
            query = query.filter(Activity.workout_type.in_(["easy", "recovery", None]))

    activities = (
        query.order_by(Activity.date.desc())
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


QUALITY_TYPES = {"workout", "intervals", "threshold", "tempo", "fartlek"}


def _session(a: Activity, splits: list, easy_pace: float | None) -> dict | None:
    """What the laps show was run on a quality day, e.g. {"title": "3x8min Threshold", "category": "threshold"}."""
    if a.workout_type not in QUALITY_TYPES or not isinstance(splits, list) or not all(isinstance(s, dict) for s in splits):
        return None
    from app.core.session_match import session_title
    from app.services.lap_analyzer import analyze_laps
    found = analyze_laps(splits, easy_pace)
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
