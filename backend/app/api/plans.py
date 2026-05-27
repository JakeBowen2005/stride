from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.plan_engine import generate_plan
from app.database import get_db
from app.models.user import Goal, User
from app.services.analyzer import analyze_athlete
from app.services.pace_calibrator import calibrate_paces

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanRequest(BaseModel):
    start_date: str | None = None  # ISO date, defaults to next Monday


@router.post("/{user_id}/generate")
def generate_training_plan(user_id: int, req: PlanRequest = None, db: Session = Depends(get_db)):
    """Generate a 2-week training plan based on athlete data and active goal."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    goal = db.query(Goal).filter(Goal.user_id == user_id, Goal.active == True).first()
    if not goal:
        raise HTTPException(status_code=400, detail="No active goal set. Set a goal first via POST /api/users/{user_id}/goal")

    analysis = analyze_athlete(user_id, db)
    if "error" in analysis:
        raise HTTPException(status_code=400, detail="Not enough data to generate a plan. Sync activities first.")

    current_fitness = analysis["current_fitness"]
    paces = analysis["paces"]

    easy_pace_str = paces.get("recent_easy_pace") or paces.get("easy_pace")
    easy_pace_seconds = _parse_pace(easy_pace_str) if easy_pace_str else 540

    # Calibrate workout paces from real Strava descriptions
    calibrated = calibrate_paces(user_id, db)
    current_workout_paces = calibrated if "interval_pace" in calibrated else None

    # Parse rest days
    rest_days = []
    if user.rest_days:
        rest_days = [d.strip().lower() for d in user.rest_days.split(",")]
    if not rest_days:
        rest_days = ["sunday"]  # default

    start = None
    if req and req.start_date:
        start = date.fromisoformat(req.start_date)

    plan = generate_plan(
        goal_type=goal.goal_type,
        goal_distance=goal.race_distance,
        target_time_seconds=goal.target_time_seconds,
        current_weekly_mileage=current_fitness["weekly_mileage_4w_avg"],
        peak_weekly_mileage=current_fitness["peak_weekly_mileage"],
        experience_level=analysis["overview"]["experience_level"],
        days_per_week=user.days_per_week or 6,
        rest_days=rest_days,
        long_run_day=user.long_run_day or "saturday",
        easy_pace_seconds=easy_pace_seconds,
        current_workout_paces=current_workout_paces,
        start_date=start,
    )

    plan["goal"] = {
        "type": goal.goal_type,
        "distance": goal.race_distance,
        "target_time": goal.target_time_seconds,
        "race_date": goal.race_date,
        "description": goal.description,
    }
    plan["athlete"] = {
        "name": user.name,
        "current_weekly_mileage": current_fitness["weekly_mileage_4w_avg"],
        "peak_weekly_mileage": current_fitness["peak_weekly_mileage"],
        "experience_level": analysis["overview"]["experience_level"],
        "injury_risk": analysis["injury_risk"]["assessment"],
    }

    return plan


@router.get("/{user_id}/goal")
def get_active_goal(user_id: int, db: Session = Depends(get_db)):
    """Get user's active goal."""
    goal = db.query(Goal).filter(Goal.user_id == user_id, Goal.active == True).first()
    if not goal:
        return None
    return {
        "id": goal.id,
        "type": goal.goal_type,
        "distance": goal.race_distance,
        "target_time": goal.target_time_seconds,
        "race_date": goal.race_date,
        "description": goal.description,
    }


def _parse_pace(pace_str: str) -> float:
    """Parse 'M:SS' pace string to total seconds."""
    parts = pace_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])
