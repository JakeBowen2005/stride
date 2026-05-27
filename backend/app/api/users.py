from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import Activity
from app.models.user import Goal, User

router = APIRouter(prefix="/api/users", tags=["users"])


class OnboardingData(BaseModel):
    name: str
    age: int | None = None
    units: str = "miles"
    workout_format: str = "distance"
    years_running: float | None = None
    current_weekly_mileage: float | None = None
    peak_weekly_mileage: float | None = None
    pr_5k_seconds: float | None = None
    pr_10k_seconds: float | None = None
    pr_half_seconds: float | None = None
    pr_marathon_seconds: float | None = None
    days_per_week: int = 6
    rest_days: str | None = None
    long_run_day: str = "saturday"


class WorkoutHighlight(BaseModel):
    activity_id: int
    notes: str | None = None  # "5x1K at 3:45 with 90sec rest, felt strong"
    feel_rating: int | None = None  # 1-10


class WorkoutHighlights(BaseModel):
    workouts: list[WorkoutHighlight]


class GoalData(BaseModel):
    goal_type: str  # "race", "mileage", "general", "comeback"
    race_distance: str | None = None
    target_time_seconds: float | None = None
    race_date: str | None = None
    target_weekly_mileage: float | None = None
    description: str | None = None


@router.post("/onboard")
def onboard_user(data: OnboardingData, db: Session = Depends(get_db)):
    """Create or update user with onboarding data."""
    user = User(
        name=data.name,
        age=data.age,
        units=data.units,
        workout_format=data.workout_format,
        years_running=data.years_running,
        current_weekly_mileage=data.current_weekly_mileage,
        peak_weekly_mileage=data.peak_weekly_mileage,
        pr_5k=data.pr_5k_seconds,
        pr_10k=data.pr_10k_seconds,
        pr_half=data.pr_half_seconds,
        pr_marathon=data.pr_marathon_seconds,
        days_per_week=data.days_per_week,
        rest_days=data.rest_days,
        long_run_day=data.long_run_day,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"user_id": user.id, "message": f"Welcome, {user.name}!"}


@router.post("/{user_id}/goal")
def set_goal(user_id: int, data: GoalData, db: Session = Depends(get_db)):
    """Set a training goal for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Deactivate previous goals
    db.query(Goal).filter(Goal.user_id == user_id, Goal.active == True).update({"active": False})

    goal = Goal(
        user_id=user_id,
        goal_type=data.goal_type,
        race_distance=data.race_distance,
        target_time_seconds=data.target_time_seconds,
        race_date=data.race_date,
        target_weekly_mileage=data.target_weekly_mileage,
        description=data.description,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)

    return {"goal_id": goal.id, "message": "Goal set successfully"}


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get user profile."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "name": user.name,
        "age": user.age,
        "units": user.units,
        "years_running": user.years_running,
        "current_weekly_mileage": user.current_weekly_mileage,
        "peak_weekly_mileage": user.peak_weekly_mileage,
        "pr_5k": user.pr_5k,
        "pr_10k": user.pr_10k,
        "pr_half": user.pr_half,
        "pr_marathon": user.pr_marathon,
        "days_per_week": user.days_per_week,
        "rest_days": user.rest_days,
        "strava_connected": user.strava_connected,
        "experience_level": user.experience_level,
    }


@router.get("/{user_id}/onboarding/workouts")
def get_candidate_workouts(user_id: int, db: Session = Depends(get_db)):
    """Surface activities that look like workouts for the user to highlight during onboarding.

    Picks activities based on:
    - Strava workout_type (1=race, 3=workout)
    - Faster than their median pace (likely quality sessions)
    - Has a workout description from Strava
    Returns most recent 20 candidates.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    all_activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .order_by(Activity.date.desc())
        .all()
    )
    if not all_activities:
        return {"workouts": [], "message": "No activities found. Sync Strava first."}

    # Calculate median pace to find faster-than-normal runs
    paces = [
        a.average_pace_per_km * 1.60934
        for a in all_activities
        if a.average_pace_per_km and a.distance_meters > 3000
    ]
    median_pace = sorted(paces)[len(paces) // 2] if paces else 600

    candidates = []
    seen_ids = set()
    for a in all_activities:
        if a.id in seen_ids:
            continue

        is_candidate = False
        pace_per_mile = (a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None
        distance_miles = a.distance_meters / 1609.34

        # Strava flagged as workout or race
        if a.strava_workout_type in (1, 3):
            is_candidate = True
        # Has workout description
        elif a.has_workout_description:
            is_candidate = True
        # Faster than median and decent distance (likely a quality session)
        elif pace_per_mile and pace_per_mile < median_pace * 0.95 and distance_miles >= 4:
            is_candidate = True
        # Long run (10+ miles)
        elif distance_miles >= 10:
            is_candidate = True

        if is_candidate:
            seen_ids.add(a.id)
            candidates.append({
                "activity_id": a.id,
                "name": a.name,
                "date": a.date.isoformat() if a.date else None,
                "distance_miles": round(distance_miles, 2),
                "duration_seconds": a.duration_seconds,
                "pace_per_mile": _seconds_to_pace(pace_per_mile) if pace_per_mile else None,
                "average_heartrate": a.average_heartrate,
                "strava_workout_type": a.strava_workout_type,
                "description": a.description,
                "already_highlighted": a.user_highlighted,
            })

    return {
        "workouts": candidates,
        "total_candidates": len(candidates),
        "message": "Select any workouts that went well and tell us about them — splits, effort, how it felt. This helps us calibrate your training paces.",
    }


@router.post("/{user_id}/onboarding/workouts")
def highlight_workouts(user_id: int, data: WorkoutHighlights, db: Session = Depends(get_db)):
    """User highlights workouts that represent their current fitness during onboarding.

    Stores their notes and feel rating on each activity so the plan engine
    and analyzer can use real workout data to calibrate paces.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    highlighted = 0
    for wo in data.workouts:
        activity = (
            db.query(Activity)
            .filter(Activity.id == wo.activity_id, Activity.user_id == user_id)
            .first()
        )
        if not activity:
            continue

        activity.user_highlighted = True
        activity.user_workout_notes = wo.notes
        if wo.feel_rating is not None:
            activity.feel_rating = wo.feel_rating
        highlighted += 1

    db.commit()

    return {
        "highlighted": highlighted,
        "message": f"Got it — {highlighted} workout(s) saved. We'll use these to dial in your training paces.",
    }


def _seconds_to_pace(seconds_per_unit: float) -> str:
    minutes = int(seconds_per_unit // 60)
    secs = int(seconds_per_unit % 60)
    return f"{minutes}:{secs:02d}"
