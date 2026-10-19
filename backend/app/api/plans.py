import json
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.plan_engine import calculate_plan_params, generate_plan
from app.core.workout_evaluator import (
    evaluate_workout,
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
    feel_rating: int = Field(ge=1, le=10)  # 1 = awful, 10 = felt amazing
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
    # Keep any category's evidence (threshold-only history is still evidence)
    current_workout_paces = calibrated if any(
        k in calibrated for k in ("interval_pace", "tempo_pace", "threshold_pace")
    ) else None

    rest_days = []
    if user.rest_days:
        rest_days = [d.strip().lower() for d in user.rest_days.split(",")]
    if not rest_days:
        rest_days = ["sunday"]

    # Calculate smart plan params (or use explicit start_date)
    if req and req.start_date:
        start = date.fromisoformat(req.start_date)
        params = {"start_date": start, "end_date": None, "num_weeks": 2, "first_prescribe_date": None}
    else:
        params = calculate_plan_params()

    fpd = params.get("first_prescribe_date") or params["start_date"]
    baseline = current_fitness["weekly_mileage_4w_avg"]

    # Real training already done in this block's first week, and real hard runs just
    # before it — so a midweek plan prescribes only what's left and can't stack a
    # workout on yesterday's long run.
    window_start = (min(params["start_date"], fpd) - timedelta(days=3)).isoformat()
    recent = _activities_by_date(user_id, window_start, (fpd - timedelta(days=1)).isoformat(), db)
    completed_by_date = {
        d: sum(a.distance_meters for a in acts) / 1609.34
        for d, acts in recent.items() if d >= params["start_date"].isoformat()
    }
    prior_hard_dates = {
        d for d, acts in recent.items()
        if (fpd - timedelta(days=3)).isoformat() <= d < fpd.isoformat()
        and any(_is_hard_activity(a, baseline) for a in acts)
    }

    # Assess the previous block (what was prescribed and actually run) — drives
    # build / hold / reduce / recovery for the next block's volume.
    prev_plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active == True).first()
    assessment = _assess_previous_block(prev_plan, db) if prev_plan else None

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
        race_date=date.fromisoformat(goal.race_date) if goal.race_date else None,
        terrain=goal.terrain,
        target_weekly_mileage=goal.target_weekly_mileage,
        assessment=assessment.decision if assessment else None,
        completed_by_date=completed_by_date,
        prior_hard_dates=prior_hard_dates,
        reported_mileage=user.current_weekly_mileage,
        allow_preview=not (assessment and assessment.decision in ("hold", "reduce", "recovery")),
    )
    if assessment:
        plan_data["notes"] = assessment.reasons + plan_data["notes"]

    goal_snapshot = {
        "type": goal.goal_type,
        "distance": goal.race_distance,
        "target_time": goal.target_time_seconds,
        "race_date": goal.race_date,
        "description": goal.description,
        "terrain": goal.terrain,
        "target_weekly_mileage": goal.target_weekly_mileage,
    }
    athlete_snapshot = {
        "name": user.name,
        "current_weekly_mileage": current_fitness["weekly_mileage_4w_avg"],
        "peak_weekly_mileage": current_fitness["peak_weekly_mileage"],
        "experience_level": analysis["overview"]["experience_level"],
        "injury_risk": analysis["injury_risk"]["assessment"],
    }

    # Persist atomically: the previous plan is only deactivated in the same commit
    # that saves its replacement, so a failure above leaves the old plan usable.
    db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active == True).update({"is_active": False})
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
        phases=json.dumps(plan_data.get("phases", [])),
        prescribed_from=(params.get("first_prescribe_date") or params["start_date"]).isoformat(),
        load=json.dumps(plan_data.get("load")),
        assessment=json.dumps(assessment.to_dict()) if assessment else None,
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

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(db_plan)

    # Return the full plan response
    plan_data["id"] = db_plan.id
    plan_data["assessment"] = assessment.to_dict() if assessment else None
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

    # One query for every activity in the plan window, grouped by local date
    by_date = _activities_by_date(db_plan.user_id, db_plan.start_date, db_plan.end_date, db)

    # Match past days to actual activities (store primary activity_id for backwards compat)
    for pw in planned_workouts:
        if pw.date > today or pw.type == "rest" or pw.activity_id:
            continue
        activities = by_date.get(pw.date)
        if activities:
            pw.activity_id = max(activities, key=lambda a: a.distance_meters).id
    db.commit()

    # Build response
    # Days before generation were history, not prescriptions. Older plans fall back to
    # created_at (stored in UTC, so it can be a day ahead in the evening — hence the new column).
    plan_created_date = db_plan.prescribed_from or (
        db_plan.created_at.date().isoformat() if db_plan.created_at else db_plan.start_date
    )

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
            activities = by_date.get(pw.date)
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
            "adjustment_note": pw.adjustment_note,
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
                "evaluation": json.loads(pw.evaluation) if pw.evaluation else None,
            } if pw.feel_rating or pw.swapped else None,
        }
        weeks_map[pw.week_number]["days"].append(day_data)

    phases = json.loads(db_plan.phases) if db_plan.phases else []
    weeks = []
    for wk_num in sorted(weeks_map.keys()):
        wk = weeks_map[wk_num]
        wk["phase"] = phases[wk_num - 1] if 0 < wk_num <= len(phases) else None
        budgets = (json.loads(db_plan.load) or {}).get("weekly_budgets", []) if db_plan.load else []
        wk["budget_miles"] = budgets[wk_num - 1] if 0 < wk_num <= len(budgets) else None
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
        # A plan whose last day is behind us shouldn't be shown as "current"
        "is_stale": db_plan.end_date < today,
        "phase": _current_phase(weeks, today),
        "load": json.loads(db_plan.load) if db_plan.load else None,
        "assessment": json.loads(db_plan.assessment) if db_plan.assessment else None,
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
        "terrain": goal.terrain,
        "elevation_gain_ft": goal.elevation_gain_ft,
        "target_weekly_mileage": goal.target_weekly_mileage,
    }


@router.post("/{user_id}/feedback/{feedback_date}")
def submit_feedback(
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

    activities = _get_activities_for_date(feedback_date, user_id, db)

    # Claim the side effects atomically. Only the first successful submission for a
    # day applies progression / rescheduling / fatigue changes; edits, retries and
    # concurrent duplicates update the rating and notes only.
    claimed = db.query(PlannedWorkout).filter(
        PlannedWorkout.id == pw.id, PlannedWorkout.side_effects_applied_at.is_(None)
    ).update({"side_effects_applied_at": datetime.now()}, synchronize_session=False) == 1

    # Save feedback to PlannedWorkout
    pw.feel_rating = req.feel_rating
    pw.feel_notes = req.feel_notes
    pw.pace_assessment = req.pace_assessment
    pw.swapped = req.swapped
    pw.swap_reason = req.swap_reason
    pw.actual_workout_type = req.actual_workout_type

    evidence_act = _work_evidence_activity(activities)
    if evidence_act:
        evidence_act.feel_rating = req.feel_rating
        evidence_act.feel_notes = req.feel_notes

    # Persist the athlete's input (and the claim) before anything that can fail
    db.commit()
    db.refresh(pw)

    evaluation = json.loads(pw.evaluation) if pw.evaluation else None
    changes: list[dict] = []
    if claimed:
        try:
            evaluation, changes = _apply_feedback_effects(user_id, db_plan, pw, activities, evidence_act, req, db)
            db.commit()
        except Exception:
            db.rollback()
            db.query(PlannedWorkout).filter(PlannedWorkout.id == pw.id).update(
                {"side_effects_applied_at": None}, synchronize_session=False
            )
            db.commit()
            raise

    # Coach explains the final, persisted decision (never raises; template fallback)
    from app.services.coach import get_coach_feedback
    decision_summary = _decision_summary(evaluation, changes)
    coach_response = get_coach_feedback(user_id, pw, activities, req, db, decision_summary=decision_summary)
    pw.coach_response = coach_response
    db.commit()

    return {
        "date": feedback_date,
        "feel_rating": pw.feel_rating,
        "pace_assessment": pw.pace_assessment,
        "swapped": pw.swapped,
        "coach_response": coach_response,
        "rescheduled_to": next((c["date"] for c in changes if c["change"] == "rescheduled"), None),
        "plan_adjusted": bool(changes),
        "changes": changes,
        "progression_decision": evaluation["decision"] if evaluation else None,
        "evaluation": evaluation,
        "side_effects_applied": claimed,
    }


def _work_evidence_activity(activities: list[Activity]) -> Activity | None:
    """The activity holding the workout's reps. Split recordings (warmup / workout /
    cooldown as separate activities) mean the longest one may be the warmup."""
    if not activities:
        return None
    from app.core.workout_evaluator import _extract_paced_reps, extract_splits_from_description

    def has_work(a: Activity) -> bool:
        d = a.description or ""
        return bool(extract_splits_from_description(d)) or bool(_extract_paced_reps(d)[1])

    with_work = [a for a in activities if has_work(a)]
    return max(with_work or activities, key=lambda a: a.distance_meters or 0)


def _snapshot(pw: PlannedWorkout) -> str:
    return json.dumps({k: getattr(pw, k) for k in ("type", "title", "description", "purpose", "distance_miles", "warmup", "cooldown")})


def _mark_changed(pw: PlannedWorkout, reason: str):
    if not pw.original_prescription:
        pw.original_prescription = _snapshot(pw)
    pw.adjustment_note = reason


def _apply_feedback_effects(user_id, db_plan, pw, activities, evidence_act, req, db) -> tuple[dict | None, list[dict]]:
    """Deterministic consequences of feedback. Caller owns the transaction."""
    changes: list[dict] = []
    evaluation = None
    feedback_date = pw.date

    # 1. Evaluate the workout and move ONE progression lever
    if pw.type == "workout" and not req.swapped:
        category = _detect_workout_category(pw.title)
        if category:
            only_one = len(activities) == 1
            ev = evaluate_workout(
                actual_description=evidence_act.description if evidence_act else None,
                # A whole-run average only means something when the run was one activity,
                # and even then it is weak evidence (never enough to advance)
                actual_avg_pace_sec=(evidence_act.average_pace_per_km * 1.60934)
                if (evidence_act and only_one and evidence_act.average_pace_per_km) else None,
                actual_distance_miles=sum(a.distance_meters for a in activities) / 1609.34 if activities else None,
                prescribed_type=pw.type,
                prescribed_pace_sec=_extract_prescribed_pace(pw.description),
                prescribed_name=pw.title,
                feel_rating=req.feel_rating,
            )
            evaluation = ev.to_dict() | {"category": category, "activity_ids": [a.id for a in activities]}
            pw.evaluation = json.dumps(evaluation)
            _update_progression_from_evaluation(
                user_id=user_id, category=category, evaluation_decision=ev.decision,
                workout_name=pw.title, workout_date=feedback_date, new_pace_sec=ev.new_pace_sec, db=db,
            )

    # 2. Swapped a hard workout: only an explicit choice reschedules
    if req.swapped and pw.type == "workout":
        choice = req.desired_reschedule_type
        if choice in {"tempo", "intervals", "threshold"}:
            slot, why_not = _find_safe_slot(db_plan, feedback_date, db)
            if slot:
                workout = _generate_swap_workout(user_id, choice, db_plan, db)
                _mark_changed(slot, f"Rescheduled {choice} workout after {feedback_date} was swapped.")
                slot.type = "workout"
                slot.title = workout["name"]
                slot.description = workout["structure"]
                slot.purpose = workout["purpose"]
                slot.distance_miles = workout.get("total_miles", pw.distance_miles)
                slot.warmup = workout.get("warmup")
                slot.cooldown = workout.get("cooldown")
                changes.append({"date": slot.date, "change": "rescheduled", "reason": slot.adjustment_note})
            else:
                changes.append({"date": None, "change": "not_rescheduled", "reason": why_not})

    # 3. Feel ≤ 4: the next unrun hard workout becomes easy
    if req.feel_rating <= 4 and not req.swapped:
        today = date.today().isoformat()
        next_hard = db.query(PlannedWorkout).filter(
            PlannedWorkout.plan_id == db_plan.id,
            PlannedWorkout.date > feedback_date,
            PlannedWorkout.date >= today,  # never rewrite the past
            PlannedWorkout.type == "workout",
            PlannedWorkout.activity_id == None,  # noqa: E711
        ).order_by(PlannedWorkout.date).first()
        if next_hard:
            reason = f"Adjusted to easy: you rated {feedback_date} {req.feel_rating}/10, so the next workout became recovery."
            _mark_changed(next_hard, reason)
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
            changes.append({"date": next_hard.date, "change": "downgraded", "reason": reason})

    if changes:
        db.flush()
    return evaluation, changes


def _decision_summary(evaluation: dict | None, changes: list[dict]) -> str | None:
    parts = []
    if evaluation:
        parts.append(f"Progression decision: {evaluation['decision']} — {evaluation['reason']}")
    for c in changes:
        parts.append(f"Schedule change ({c['change']}{' on ' + c['date'] if c['date'] else ''}): {c['reason']}")
    return "\n".join(parts) or None


def _find_safe_slot(db_plan: Plan, after_date: str, db: Session) -> tuple[PlannedWorkout | None, str | None]:
    """A future easy day with no run yet, on a non-rest day, with no hard day (planned
    workout, long run or race — or a real hard run) on either side. Never falls back
    to an unsafe day; returns the reason instead."""
    today = date.today().isoformat()
    floor = max(after_date, today)
    days = db.query(PlannedWorkout).filter(PlannedWorkout.plan_id == db_plan.id).order_by(PlannedWorkout.date).all()
    by_date = {d.date: d for d in days}
    acts = _activities_by_date(db_plan.user_id, db_plan.start_date, db_plan.end_date, db)
    for c in days:
        if c.date <= floor or c.type != "easy" or c.activity_id or acts.get(c.date):
            continue
        d = date.fromisoformat(c.date)
        neighbours = [(d - timedelta(days=1)).isoformat(), (d + timedelta(days=1)).isoformat()]
        if any(by_date.get(n) is not None and by_date[n].type in HARD_ACTIVITY_TYPES | {"race"} for n in neighbours):
            continue
        if any(a.workout_type in HARD_ACTIVITY_TYPES for n in neighbours for a in acts.get(n, [])):
            continue
        return c, None
    return None, ("No safe day left in this block for the extra workout: every remaining easy day sits next to a "
                  "hard day. It was dropped rather than stacked; your next block will include it.")


HARD_ACTIVITY_TYPES = {"workout", "race", "long_run"}


def _is_hard_activity(a: Activity, baseline_mpw: float) -> bool:
    """A real run that counts as a hard day for spacing: a classified workout/race/long
    run, or a run that's long relative to the athlete's week (≥8 mi and ≥25% of it)."""
    miles = (a.distance_meters or 0) / 1609.34
    return (a.workout_type in HARD_ACTIVITY_TYPES) or (miles >= 8 and miles >= 0.25 * baseline_mpw)


def _assess_previous_block(prev_plan: Plan, db: Session):
    from app.core.block_assessment import DayRecord, assess_block

    today = date.today().isoformat()
    start = prev_plan.prescribed_from or prev_plan.start_date
    by_date = _activities_by_date(prev_plan.user_id, prev_plan.start_date, prev_plan.end_date, db)
    records = []
    for pw in prev_plan.planned_workouts:
        if not (start <= pw.date < today):
            continue
        actual = sum(a.distance_meters for a in by_date.get(pw.date, [])) / 1609.34
        records.append(DayRecord(date=pw.date, type=pw.type, planned_miles=pw.distance_miles or 0,
                                 actual_miles=actual, feel=pw.feel_rating))
    return assess_block(records)


def _current_phase(weeks: list[dict], today: str) -> dict | None:
    """Phase of the week containing today (or the first week if the plan starts later)."""
    for wk in weeks:
        dates = [d["date"] for d in wk["days"]]
        if dates and dates[0] <= today <= dates[-1]:
            return wk.get("phase")
    return weeks[0].get("phase") if weeks else None


def _activities_by_date(user_id: int, start: str, end: str, db: Session) -> dict[str, list[Activity]]:
    """All activities between two ISO dates (inclusive), keyed by local calendar date.
    Range filter on the raw column so the (user_id, date) index is usable."""
    lo = datetime.fromisoformat(start)
    hi = datetime.fromisoformat(end) + timedelta(days=1)
    grouped: dict[str, list[Activity]] = {}
    for a in db.query(Activity).filter(Activity.user_id == user_id, Activity.date >= lo, Activity.date < hi):
        grouped.setdefault(a.date.date().isoformat(), []).append(a)
    return grouped


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

    # No commit here: the caller's transaction (plan generation) owns it
    db.flush()
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

    # One lever per decision: advance moves the level, recalibrate moves the pace.
    if evaluation_decision == "advance":
        prog.current_level = min(prog.current_level + 1, 12)
        prog.sessions_at_level = 0
        prog.format_rotation = (prog.format_rotation + 1) % 3
    elif evaluation_decision == "recalibrate":
        if new_pace_sec:
            prog.current_pace_sec = new_pace_sec
    elif evaluation_decision == "regress":
        prog.current_level = max(prog.current_level - 1, 1)
        prog.sessions_at_level = 0
    elif evaluation_decision == "hold":
        prog.sessions_at_level += 1
    # "insufficient": no evidence either way — level and session count unchanged

    db.add(prog)


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
