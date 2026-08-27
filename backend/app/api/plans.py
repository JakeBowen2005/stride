import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.plan_engine import calculate_plan_params, generate_plan
from app.core.workout_evaluator import (
    evaluate_workout,
    extract_splits_from_description,
    determine_starting_level,
)
from app.database import get_db
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.services.analyzer import analyze_athlete
from app.services.pace_calibrator import calibrate_paces

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanRequest(BaseModel):
    start_date: str | None = None  # ISO date, defaults to smart calculation


class FeedbackRequest(BaseModel):
    feel_rating: int  # 1-10
    feel_notes: str | None = None
    pace_assessment: str | None = None  # above, on_target, below, skipped
    swapped: bool = False
    swap_reason: str | None = None
    actual_workout_type: str | None = None  # what they did if swapped
    desired_reschedule_type: str | None = None  # what they want rescheduled as


@router.post("/{user_id}/generate")
def generate_training_plan(user_id: int, req: PlanRequest = None, db: Session = Depends(get_db)):
    """Generate a training plan, persist it, and return it."""
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

    calibrated = calibrate_paces(user_id, db)
    current_workout_paces = calibrated if "interval_pace" in calibrated else None

    rest_days = []
    if user.rest_days:
        rest_days = [d.strip().lower() for d in user.rest_days.split(",")]
    if not rest_days:
        rest_days = ["sunday"]

    # Deactivate any existing active plan
    db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active == True).update(
        {"is_active": False}
    )

    # Calculate smart plan params (or use explicit start_date)
    if req and req.start_date:
        start = date.fromisoformat(req.start_date)
        params = {"start_date": start, "end_date": None, "num_weeks": 2, "first_prescribe_date": None}
    else:
        params = calculate_plan_params()

    # Determine block number — reuse on overlapping regeneration, increment on new block
    last_plan = db.query(Plan).filter(Plan.user_id == user_id).order_by(Plan.id.desc()).first()
    if last_plan:
        new_start = params["start_date"]
        old_end = date.fromisoformat(last_plan.end_date)
        if new_start <= old_end:
            block_number = last_plan.block_number
        else:
            block_number = last_plan.block_number + 1
    else:
        block_number = 1

    # Load or initialize workout progression state
    progression_state = _load_progression_state(user_id, db, goal.race_distance or "5k")

    plan_data = generate_plan(
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
        start_date=params["start_date"],
        end_date=params.get("end_date"),
        num_weeks=params["num_weeks"],
        first_prescribe_date=params.get("first_prescribe_date"),
        block_number=block_number,
        progression_state=progression_state,
    )

    goal_snapshot = {
        "type": goal.goal_type,
        "distance": goal.race_distance,
        "target_time": goal.target_time_seconds,
        "race_date": goal.race_date,
        "description": goal.description,
    }
    athlete_snapshot = {
        "name": user.name,
        "current_weekly_mileage": current_fitness["weekly_mileage_4w_avg"],
        "peak_weekly_mileage": current_fitness["peak_weekly_mileage"],
        "experience_level": analysis["overview"]["experience_level"],
        "injury_risk": analysis["injury_risk"]["assessment"],
    }

    # Persist to DB
    db_plan = Plan(
        user_id=user_id,
        start_date=plan_data["start_date"],
        end_date=plan_data["end_date"],
        block_number=plan_data["block_number"],
        is_deload=plan_data["is_deload"],
        is_active=True,
        pacing_guide=json.dumps(plan_data["pacing_guide"]),
        notes=json.dumps(plan_data["notes"]),
        goal_snapshot=json.dumps(goal_snapshot),
        athlete_snapshot=json.dumps(athlete_snapshot),
    )
    db.add(db_plan)
    db.flush()  # get the plan ID

    for week in plan_data["weeks"]:
        for day in week["days"]:
            pw = PlannedWorkout(
                plan_id=db_plan.id,
                date=day["date"],
                day_name=day["day"],
                week_number=week["week_number"],
                type=day["type"],
                title=day["title"],
                description=day.get("description"),
                purpose=day.get("purpose"),
                distance_miles=day["distance_miles"],
                warmup=day.get("warmup"),
                cooldown=day.get("cooldown"),
            )
            db.add(pw)

    db.commit()
    db.refresh(db_plan)

    # Return the full plan response
    plan_data["id"] = db_plan.id
    plan_data["goal"] = goal_snapshot
    plan_data["athlete"] = athlete_snapshot
    return plan_data


@router.get("/{user_id}/current")
def get_current_plan(user_id: int, db: Session = Depends(get_db)):
    """Get the active plan with matched actual activities on past days."""
    db_plan = db.query(Plan).filter(
        Plan.user_id == user_id, Plan.is_active == True
    ).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="No active plan")

    planned_workouts = db.query(PlannedWorkout).filter(
        PlannedWorkout.plan_id == db_plan.id
    ).order_by(PlannedWorkout.date).all()

    today = date.today().isoformat()

    # Match past days to actual activities (store primary activity_id for backwards compat)
    for pw in planned_workouts:
        if pw.date > today or pw.type == "rest":
            continue
        if pw.activity_id:
            continue  # already matched

        activities = _get_activities_for_date(pw.date, db_plan.user_id, db)
        if activities:
            # Store the primary (longest) activity for the FK
            primary = max(activities, key=lambda a: a.distance_meters)
            pw.activity_id = primary.id
            db.add(pw)

    db.commit()

    # Build response
    plan_created_date = db_plan.created_at.date().isoformat() if db_plan.created_at else db_plan.start_date

    weeks_map: dict[int, dict] = {}
    for pw in planned_workouts:
        if pw.week_number not in weeks_map:
            weeks_map[pw.week_number] = {
                "week_number": pw.week_number,
                "target_mileage": 0,
                "days": [],
            }

        is_prescribed = pw.date >= plan_created_date

        actual = None
        comparison = None
        # Get ALL activities for this date (not just the matched one)
        if pw.activity_id:
            activities = _get_activities_for_date(pw.date, db_plan.user_id, db)
            if activities:
                actual = _build_actual_aggregated(activities)
                if is_prescribed:
                    comparison = _build_comparison_aggregated(pw, activities)

        day_data = {
            "date": pw.date,
            "day": pw.day_name,
            "type": pw.type,
            "title": pw.title,
            "description": pw.description if is_prescribed else None,
            "purpose": pw.purpose if is_prescribed else None,
            "distance_miles": pw.distance_miles,
            "warmup": pw.warmup if is_prescribed else None,
            "cooldown": pw.cooldown if is_prescribed else None,
            "prescribed": is_prescribed,
            "actual": actual,
            "comparison": comparison,
            "feedback": {
                "feel_rating": pw.feel_rating,
                "feel_notes": pw.feel_notes,
                "pace_assessment": pw.pace_assessment,
                "swapped": pw.swapped,
                "swap_reason": pw.swap_reason,
                "actual_workout_type": pw.actual_workout_type,
                "coach_response": pw.coach_response,
            } if pw.feel_rating or pw.swapped else None,
        }
        weeks_map[pw.week_number]["days"].append(day_data)

    weeks = []
    for wk_num in sorted(weeks_map.keys()):
        wk = weeks_map[wk_num]
        wk["target_mileage"] = round(sum(d["distance_miles"] for d in wk["days"]), 1)
        # Calculate actual mileage from matched activities
        actual_mileage = 0
        for d in wk["days"]:
            if d["actual"]:
                actual_mileage += d["actual"]["distance_miles"]
        wk["actual_mileage"] = round(actual_mileage, 1)
        weeks.append(wk)

    return {
        "id": db_plan.id,
        "start_date": db_plan.start_date,
        "end_date": db_plan.end_date,
        "block_number": db_plan.block_number,
        "is_deload": db_plan.is_deload,
        "weeks": weeks,
        "pacing_guide": json.loads(db_plan.pacing_guide) if db_plan.pacing_guide else {},
        "notes": json.loads(db_plan.notes) if db_plan.notes else [],
        "goal": json.loads(db_plan.goal_snapshot) if db_plan.goal_snapshot else {},
        "athlete": json.loads(db_plan.athlete_snapshot) if db_plan.athlete_snapshot else {},
    }


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


@router.post("/{user_id}/feedback/{feedback_date}")
async def submit_feedback(
    user_id: int, feedback_date: str, req: FeedbackRequest, db: Session = Depends(get_db)
):
    """Submit post-run feedback for a specific day and get coach response."""
    # Find the active plan and the planned workout for this date
    db_plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active == True).first()
    if not db_plan:
        raise HTTPException(status_code=404, detail="No active plan")

    pw = db.query(PlannedWorkout).filter(
        PlannedWorkout.plan_id == db_plan.id,
        PlannedWorkout.date == feedback_date,
    ).first()
    if not pw:
        raise HTTPException(status_code=404, detail="No planned workout for this date")

    # Save feedback to PlannedWorkout
    pw.feel_rating = req.feel_rating
    pw.feel_notes = req.feel_notes
    pw.pace_assessment = req.pace_assessment
    pw.swapped = req.swapped
    pw.swap_reason = req.swap_reason
    pw.actual_workout_type = req.actual_workout_type

    # Also save feel_rating + notes to the matched Activity
    activities = _get_activities_for_date(feedback_date, user_id, db)
    if activities:
        primary = max(activities, key=lambda a: a.distance_meters)
        primary.feel_rating = req.feel_rating
        primary.feel_notes = req.feel_notes

    # Get coach response
    from app.services.coach import get_coach_feedback
    coach_response = await get_coach_feedback(user_id, pw, activities, req, db)
    pw.coach_response = coach_response

    # Evaluate workout and update progression state (only for hard workout days)
    evaluation_decision = None
    if pw.type == "workout" and not req.swapped:
        # Determine which category this workout belongs to
        workout_category = _detect_workout_category(pw.title)
        if workout_category:
            # Get the prescribed pace for comparison
            prescribed_pace = _extract_prescribed_pace(pw.description)

            # Get actual description from Strava
            actual_desc = None
            actual_avg_pace = None
            actual_dist = None
            if activities:
                primary = max(activities, key=lambda a: a.distance_meters)
                actual_desc = primary.description
                if primary.average_pace_per_km:
                    actual_avg_pace = primary.average_pace_per_km * 1.60934  # km to mile
                actual_dist = primary.distance_meters / 1609.34

            eval_result = evaluate_workout(
                actual_description=actual_desc,
                actual_avg_pace_sec=actual_avg_pace,
                actual_distance_miles=actual_dist,
                prescribed_type=pw.type,
                prescribed_pace_sec=prescribed_pace,
                prescribed_name=pw.title,
                feel_rating=req.feel_rating,
            )
            evaluation_decision = eval_result.decision

            _update_progression_from_evaluation(
                user_id=user_id,
                category=workout_category,
                evaluation_decision=eval_result.decision,
                workout_name=pw.title,
                workout_date=feedback_date,
                new_pace_sec=eval_result.new_pace_sec,
                db=db,
            )

    # If a hard workout was swapped, reschedule based on user intent
    rescheduled_date = None
    if req.swapped and pw.type == "workout":
        hard_swap_types = {"tempo", "intervals", "threshold"}
        # Use explicit desired_reschedule_type if provided, fall back to parsing swap_reason
        reschedule_type = req.desired_reschedule_type
        if not reschedule_type and req.swap_reason:
            reason_lower = req.swap_reason.lower()
            for ht in hard_swap_types:
                if ht in reason_lower:
                    reschedule_type = ht
                    break
        wants_hard = reschedule_type in hard_swap_types

        if wants_hard:
            # User wants a specific hard workout — find a safe slot and generate from ladder
            safe_day = _find_safe_easy_day(db_plan.id, feedback_date, db)
            if safe_day:
                workout = _generate_swap_workout(user_id, reschedule_type, db_plan, db)
                safe_day.type = "workout"
                safe_day.title = workout["name"]
                safe_day.description = workout["structure"]
                safe_day.purpose = workout["purpose"]
                safe_day.distance_miles = workout.get("total_miles", pw.distance_miles)
                safe_day.warmup = workout.get("warmup")
                safe_day.cooldown = workout.get("cooldown")
                rescheduled_date = safe_day.date
            else:
                # No safe slot — fall back to copying original
                next_easy = _find_next_easy_day(db_plan.id, feedback_date, db)
                if next_easy:
                    _copy_workout_to_day(pw, next_easy)
                    rescheduled_date = next_easy.date
        else:
            # User chose easy/recovery/rest — copy original workout forward
            next_easy = _find_next_easy_day(db_plan.id, feedback_date, db)
            if next_easy:
                _copy_workout_to_day(pw, next_easy)
                rescheduled_date = next_easy.date

    # If feel rating is low (fatigued), reduce intensity of next hard day
    if req.feel_rating <= 4 and not req.swapped:
        next_hard = db.query(PlannedWorkout).filter(
            PlannedWorkout.plan_id == db_plan.id,
            PlannedWorkout.date > feedback_date,
            PlannedWorkout.type == "workout",
            PlannedWorkout.activity_id == None,
        ).order_by(PlannedWorkout.date).first()

        if next_hard:
            # Downgrade next hard workout to easy — fatigue recovery
            next_hard.type = "easy"
            next_hard.title = "Easy Run (adjusted — recovery)"
            next_hard.description = (
                "Originally a workout, adjusted to easy based on fatigue feedback. "
                "Conversational pace — let your body recover."
            )
            next_hard.purpose = "Recovery from accumulated fatigue. Easy days let your body absorb training."
            next_hard.distance_miles = min(next_hard.distance_miles, 4.0)
            next_hard.warmup = None
            next_hard.cooldown = None

    db.commit()

    return {
        "date": feedback_date,
        "feel_rating": pw.feel_rating,
        "pace_assessment": pw.pace_assessment,
        "swapped": pw.swapped,
        "coach_response": coach_response,
        "rescheduled_to": rescheduled_date,
        "plan_adjusted": True,
        "progression_decision": evaluation_decision,
    }


def _get_activities_for_date(date_str: str, user_id: int, db: Session) -> list[Activity]:
    """Get all activities for a user on a specific date."""
    return db.query(Activity).filter(
        Activity.user_id == user_id,
        func.date(Activity.date) == date_str,
    ).all()


def _format_pace(pace_seconds_per_mile: float) -> str:
    """Format pace in seconds to mm:ss string."""
    mins = int(pace_seconds_per_mile // 60)
    secs = int(pace_seconds_per_mile % 60)
    return f"{mins}:{secs:02d}"


def _build_actual_aggregated(activities: list[Activity]) -> dict:
    """Build actual run data aggregated across all activities on this date."""
    total_distance_m = sum(a.distance_meters for a in activities)
    total_duration = sum(a.duration_seconds or 0 for a in activities)
    distance_miles = round(total_distance_m / 1609.34, 2)

    # Weighted average pace
    avg_pace = None
    if total_distance_m > 0 and total_duration > 0:
        pace_per_mile = total_duration / (total_distance_m / 1609.34)
        avg_pace = _format_pace(pace_per_mile)

    # Weighted average HR (by duration)
    avg_hr = None
    hr_activities = [(a.average_heartrate, a.duration_seconds or 0) for a in activities if a.average_heartrate]
    if hr_activities:
        total_hr_dur = sum(dur for _, dur in hr_activities)
        if total_hr_dur > 0:
            avg_hr = round(sum(hr * dur for hr, dur in hr_activities) / total_hr_dur, 1)

    # Primary activity = longest one (for name/description)
    primary = max(activities, key=lambda a: a.distance_meters)

    result = {
        "distance_miles": distance_miles,
        "avg_pace": avg_pace,
        "duration_seconds": total_duration,
        "average_heartrate": avg_hr,
        "description": primary.description,
        "feel_rating": primary.feel_rating,
        "name": primary.name,
        "activity_count": len(activities),
    }

    # Include individual activities if more than one
    if len(activities) > 1:
        result["activities"] = [
            {
                "name": a.name,
                "distance_miles": round(a.distance_meters / 1609.34, 2),
                "avg_pace": _format_pace(a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None,
                "duration_seconds": a.duration_seconds,
            }
            for a in sorted(activities, key=lambda a: a.date)
        ]

    return result


def _build_comparison_aggregated(pw: PlannedWorkout, activities: list[Activity]) -> dict | None:
    """Build comparison between prescribed and actual (aggregated)."""
    total_distance_m = sum(a.distance_meters for a in activities)
    total_duration = sum(a.duration_seconds or 0 for a in activities)
    actual_miles = round(total_distance_m / 1609.34, 2)
    distance_diff = round(actual_miles - pw.distance_miles, 2)

    pace_str = ""
    if total_distance_m > 0 and total_duration > 0:
        pace_per_mile = total_duration / (total_distance_m / 1609.34)
        pace_str = f"{_format_pace(pace_per_mile)}/mi"

    hr_activities = [(a.average_heartrate, a.duration_seconds or 0) for a in activities if a.average_heartrate]
    hr_str = ""
    if hr_activities:
        total_hr_dur = sum(dur for _, dur in hr_activities)
        if total_hr_dur > 0:
            avg_hr = sum(hr * dur for hr, dur in hr_activities) / total_hr_dur
            hr_str = f", {int(avg_hr)}bpm"

    if distance_diff > 0:
        diff_label = f"+{distance_diff:.1f}mi over prescribed"
    elif distance_diff < 0:
        diff_label = f"{distance_diff:.1f}mi under prescribed"
    else:
        diff_label = "exact distance"

    count_note = f" ({len(activities)} activities)" if len(activities) > 1 else ""
    summary = f"{actual_miles}mi at {pace_str}{hr_str}. {diff_label}.{count_note}"

    return {
        "distance_diff_miles": distance_diff,
        "summary": summary,
    }


def _parse_pace(pace_str: str) -> float:
    """Parse 'M:SS' pace string to total seconds. Returns 540 (9:00/mi) on failure."""
    try:
        parts = pace_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 540.0


def _detect_workout_category(title: str) -> str | None:
    """Detect whether a planned workout is intervals or threshold from its title."""
    if not title:
        return None
    t = title.lower()
    # Interval indicators: Nx800, Nx1K, Nx400, NxMile patterns
    # Require the interval pattern (NxDIST) to avoid matching "12-mile long run" as intervals
    if any(kw in t for kw in ["800", "400", "1k", "1mi", "1200", "200"]) or re.search(r'\dx.*mile', t):
        return "intervals"
    # Threshold/tempo indicators
    if any(kw in t for kw in ["threshold", "tempo", "hard", "sandwich", "continuous"]):
        return "threshold"
    return None


def _extract_prescribed_pace(description: str) -> float | None:
    """Extract the prescribed pace (in sec/mi) from a workout description string.

    Looks for patterns like "at 6:50/mi" or "6:00-6:10/mi".
    """
    if not description:
        return None

    # Match "at M:SS/mi" or "M:SS-M:SS/mi" (take the slower end of range)
    match = re.search(r'(\d+:\d{2})\s*/mi', description)
    if match:
        pace_str = match.group(1)
        parts = pace_str.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return None

    # Match range: "M:SS-M:SS/mi" — take the slower (second) pace
    range_match = re.search(r'(\d+:\d{2})-(\d+:\d{2})\s*/mi', description)
    if range_match:
        pace_str = range_match.group(2)  # slower end
        parts = pace_str.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return None

    return None


def _load_progression_state(user_id: int, db: Session, goal_distance: str = "5k") -> dict:
    """Load or initialize workout progression state for plan generation.

    Returns dict like:
        {
            "intervals": {"current_level": 5, "current_pace_sec": 352, ...},
            "threshold": {"current_level": 1, "current_pace_sec": 410, ...},
        }
    """
    result = {}

    for category in ("intervals", "threshold"):
        prog = db.query(WorkoutProgression).filter(
            WorkoutProgression.user_id == user_id,
            WorkoutProgression.category == category,
        ).first()

        if prog:
            result[category] = {
                "current_level": prog.current_level,
                "current_pace_sec": prog.current_pace_sec,
                "format_rotation": prog.format_rotation,
                "last_execution": prog.last_execution,
                "sessions_at_level": prog.sessions_at_level,
            }
        else:
            # Initialize from recent Strava workout history
            recent_descriptions = _get_recent_workout_descriptions(user_id, db)
            starting_level = determine_starting_level(category, recent_descriptions, None)

            prog = WorkoutProgression(
                user_id=user_id,
                category=category,
                current_level=starting_level,
                sessions_at_level=0,
                format_rotation=0,
            )
            db.add(prog)
            db.flush()

            result[category] = {
                "current_level": starting_level,
                "current_pace_sec": None,
                "format_rotation": 0,
                "last_execution": None,
                "sessions_at_level": 0,
            }

    db.commit()
    return result


def _get_recent_workout_descriptions(user_id: int, db: Session, weeks: int = 8) -> list[str]:
    """Get recent workout descriptions from Strava for starting level detection."""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)

    activities = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.has_workout_description == True,
        Activity.date >= cutoff,
    ).order_by(Activity.date.desc()).limit(20).all()

    return [a.description for a in activities if a.description]


def _update_progression_from_evaluation(
    user_id: int,
    category: str,
    evaluation_decision: str,
    workout_name: str,
    workout_date: str,
    new_pace_sec: float | None,
    db: Session,
):
    """Update the WorkoutProgression record based on an evaluation decision."""
    prog = db.query(WorkoutProgression).filter(
        WorkoutProgression.user_id == user_id,
        WorkoutProgression.category == category,
    ).first()

    if not prog:
        return

    prog.last_workout_date = date.fromisoformat(workout_date)
    prog.last_workout_name = workout_name
    prog.last_execution = evaluation_decision

    if evaluation_decision == "advance":
        prog.current_level = min(prog.current_level + 1, 12)
        prog.sessions_at_level = 0
        prog.format_rotation = (prog.format_rotation + 1) % 3
        if new_pace_sec:
            prog.current_pace_sec = new_pace_sec
    elif evaluation_decision == "recalibrate":
        prog.current_level = min(prog.current_level + 1, 12)
        prog.sessions_at_level = 0
        if new_pace_sec:
            prog.current_pace_sec = new_pace_sec
    elif evaluation_decision == "regress":
        prog.current_level = max(prog.current_level - 1, 1)
        prog.sessions_at_level = 0
    else:  # hold
        prog.sessions_at_level += 1

    db.add(prog)


def _find_next_easy_day(plan_id: int, after_date: str, db: Session) -> PlannedWorkout | None:
    """Find the next unmatched easy day after a given date."""
    return db.query(PlannedWorkout).filter(
        PlannedWorkout.plan_id == plan_id,
        PlannedWorkout.date > after_date,
        PlannedWorkout.type == "easy",
        PlannedWorkout.activity_id == None,
    ).order_by(PlannedWorkout.date).first()


def _find_safe_easy_day(plan_id: int, after_date: str, db: Session) -> PlannedWorkout | None:
    """Find next easy day where neither the day before nor after is a hard workout."""
    candidates = db.query(PlannedWorkout).filter(
        PlannedWorkout.plan_id == plan_id,
        PlannedWorkout.date > after_date,
        PlannedWorkout.type == "easy",
        PlannedWorkout.activity_id == None,
    ).order_by(PlannedWorkout.date).all()

    for c in candidates:
        d = date.fromisoformat(c.date)
        prev = (d - timedelta(days=1)).isoformat()
        nxt = (d + timedelta(days=1)).isoformat()

        prev_day = db.query(PlannedWorkout).filter(
            PlannedWorkout.plan_id == plan_id, PlannedWorkout.date == prev
        ).first()
        next_day = db.query(PlannedWorkout).filter(
            PlannedWorkout.plan_id == plan_id, PlannedWorkout.date == nxt
        ).first()

        prev_hard = prev_day and prev_day.type == "workout"
        next_hard = next_day and next_day.type == "workout"

        if not prev_hard and not next_hard:
            return c
    return None


def _generate_swap_workout(user_id: int, desired_type: str, db_plan: Plan, db: Session) -> dict:
    """Generate a workout from the ladder based on user's desired type."""
    from app.core.workout_ladders import get_workout_at_level
    from app.services.pace_calibrator import calibrate_paces as _calibrate

    category_map = {"tempo": "threshold", "threshold": "threshold", "intervals": "intervals"}
    category = category_map.get(desired_type, "threshold")

    prog = db.query(WorkoutProgression).filter(
        WorkoutProgression.user_id == user_id,
        WorkoutProgression.category == category,
    ).first()
    level = prog.current_level if prog else 1

    calibrated = _calibrate(user_id, db)
    paces = calibrated if "interval_pace" in calibrated else {}

    goal_snapshot = json.loads(db_plan.goal_snapshot) if db_plan.goal_snapshot else {}
    goal_distance = goal_snapshot.get("distance", "5k")

    return get_workout_at_level(category, level, paces, goal_distance)


def _copy_workout_to_day(source: PlannedWorkout, target: PlannedWorkout):
    """Copy workout prescription from one PlannedWorkout to another."""
    target.type = source.type
    target.title = source.title
    target.description = source.description
    target.purpose = source.purpose
    target.distance_miles = source.distance_miles
    target.warmup = source.warmup
    target.cooldown = source.cooldown
