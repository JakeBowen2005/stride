import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.workout_data import day_prescription, execution_from_activities, loads, render
from app.core.plan_engine import calculate_plan_params, generate_plan
from app.core.workout_evaluator import (
    evaluate_workout,
)
from app.database import get_db
from app.models.activity import Activity, runs_only
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.services.analyzer import analyze_athlete
from app.services.pace_calibrator import calibrate_paces

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanRequest(BaseModel):
    start_date: date | None = None  # ISO date, defaults to smart calculation
    lighter: bool = False
    scope: Literal["current", "next"] = "current"


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
    """Generate an inactive preview; approval is the only activation path."""
    _begin_schedule_write(db)
    req = req or PlanRequest()
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
    if user.rest_days is None:
        rest_days = ["sunday"]

    # Current-block revision preserves its boundaries. A true next block is
    # available after completion; it never silently replaces today's schedule.
    active = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    if req.scope == 'next':
        if not active:
            raise HTTPException(409, "Approve a current block first")
        if date.today().isoformat() <= active.end_date:
            raise HTTPException(409, "Finish this block before creating the next one; use current-block revision for changes now")
        if req.start_date and req.start_date.isoformat() <= active.end_date:
            raise HTTPException(422, "A next block cannot start inside the previous block")
    if req.start_date:
        start = req.start_date
        params = {"start_date": start, "end_date": None, "num_weeks": 2, "first_prescribe_date": None}
    elif req.scope == 'current' and active and active.start_date <= date.today().isoformat() <= active.end_date:
        start, end = date.fromisoformat(active.start_date), date.fromisoformat(active.end_date)
        params = {"start_date": start, "end_date": end, "num_weeks": ((end - start).days // 7) + 1,
                  "first_prescribe_date": date.today()}
    else:
        params = calculate_plan_params()
    fpd = params.get("first_prescribe_date") or params["start_date"]
    baseline = current_fitness["weekly_mileage_4w_avg"]
    if (params['start_date'] <= date.today() and fpd <= date.today()
            and _get_activities_for_date(date.today().isoformat(), user_id, db)):
        # A recorded run today is completed load, not another open prescription.
        fpd = date.today() + timedelta(days=1)
        params['first_prescribe_date'] = fpd

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

    # Deloads come from what was actually run, not from how many times a plan was generated
    from app.core.load_policy import deload_due
    from app.services.analyzer import compute_weekly_mileage

    this_monday = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    weekly = {w['week_start']: w['actual'] for w in compute_weekly_mileage(user_id, db, weeks=10)}
    monday = date.fromisoformat(this_monday)
    full_weeks = [weekly.get((monday - timedelta(weeks=i)).isoformat(), 0) for i in range(8, 0, -1)]
    baseline = round(sum(full_weeks[-4:]) / 4, 1)
    is_deload_due, deload_reason = deload_due(full_weeks, analysis["overview"]["experience_level"])

    # Assess the previous block (what was prescribed and actually run) — drives
    # build / hold / reduce / recovery for the next block's volume.
    # Only a block that ended recently says anything about the coming one — a plan
    # that ran out months ago is history, not evidence (the baseline already reflects it).
    prev_plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.is_active == True).first()
    recent_cutoff = (params["start_date"] - timedelta(days=ASSESSMENT_MAX_GAP_DAYS)).isoformat()
    assessment = _assess_previous_block(prev_plan, db) if prev_plan and prev_plan.end_date >= recent_cutoff else None

    fatigue = _recent_fatigue_assessment(user_id, active, db)
    if fatigue:
        severity = {None: 0, 'build': 0, 'hold': 1, 'reduce': 2, 'recovery': 3}
        if not assessment or severity[fatigue.decision] >= severity[assessment.decision]:
            assessment = fatigue

    # Determine block number — reuse on overlapping regeneration, increment on new block
    last_plan = db.query(Plan).filter(Plan.user_id == user_id, Plan.preview_state.is_(None)).order_by(Plan.id.desc()).first()
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
    progression_state = _load_progression_state(user_id, db, goal.race_distance or goal.goal_type)

    quality_activities = db.query(Activity).filter(Activity.user_id == user_id, runs_only(),
        Activity.date >= datetime.combine(monday - timedelta(weeks=4), datetime.min.time()),
        Activity.date < datetime.combine(date.today() + timedelta(days=1), datetime.min.time())).all()
    from app.services.quality_history import quality_history
    quality_evidence = quality_history(user_id, db)
    prior_quality = (json.loads(active.athlete_snapshot or '{}').get('quality_policy') or {}).get('stage') if active else None
    effective_assessment = "recovery" if req.lighter else assessment.decision if assessment else None
    plan_data = generate_plan(
        goal_type=goal.goal_type,
        goal_distance=goal.race_distance,
        target_time_seconds=goal.target_time_seconds,
        current_weekly_mileage=baseline,
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
        assessment=effective_assessment,
        completed_by_date=completed_by_date,
        prior_hard_dates=prior_hard_dates,
        reported_mileage=user.current_weekly_mileage, completed_weeks=full_weeks,
        fatigue_recovery=bool(fatigue),
        workout_format=user.workout_format or 'distance',
        quality_evidence=quality_evidence, previous_quality_stage=prior_quality,
        weekly_run_days=[len({a.date.date() for a in quality_activities
                             if monday - timedelta(weeks=i) <= a.date.date() < monday - timedelta(weeks=i-1)})
                         for i in range(4, 0, -1)],
        recent_long_run_miles=max((a.distance_meters / 1609.34 for a in quality_activities
                                  if date.today() - timedelta(days=28) <= a.date.date() <= date.today()), default=0),
        allow_preview=not (assessment and assessment.decision in ("hold", "reduce", "recovery")),
        deload_is_due=is_deload_due and effective_assessment not in ("reduce", "recovery"),
    )
    plan_data["notes"].insert(0, "Reduced recovery load already provides a lighter block; no additional deload added."
                              if is_deload_due and effective_assessment in ("reduce", "recovery") else deload_reason)
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
        "quality_policy": plan_data["quality_policy"],
        "current_weekly_mileage": baseline,
        "peak_weekly_mileage": current_fitness["peak_weekly_mileage"],
        "experience_level": analysis["overview"]["experience_level"],
        "injury_risk": analysis["injury_risk"]["assessment"],
        "schedule_preferences": {'rest_days': rest_days, 'days_per_week': user.days_per_week or 6,
                                 'long_run_day': user.long_run_day or 'saturday'},
    }

    # Persist atomically: the previous plan is only deactivated in the same commit
    # that saves its replacement, so a failure above leaves the old plan usable.
    preview = True
    db.query(Plan).filter_by(user_id=user_id, preview_state="draft").update({"preview_state": "superseded"})
    db_plan = Plan(
        user_id=user_id,
        start_date=plan_data["start_date"],
        end_date=plan_data["end_date"],
        block_number=plan_data["block_number"],
        is_deload=plan_data["is_deload"],
        is_active=not preview,
        pacing_guide=json.dumps(plan_data["pacing_guide"]),
        training_paces=json.dumps(plan_data["training_paces"]),
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
            day["prescription"] = day_prescription(day)
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
                prescription=json.dumps(day["prescription"]),
                b2b=day.get("b2b", False),
            )
            db.add(pw)

    plan_data["goal"] = goal_snapshot
    plan_data["athlete"] = athlete_snapshot
    plan_data["assessment"] = assessment.to_dict() if assessment else None
    if preview:
        plan_data["id"] = db_plan.id
        plan_data["preview"] = True
        db_plan.preview_data = json.dumps(plan_data)
        db_plan.preview_state = "draft"
        db_plan.preview_context = _preview_fingerprint(user_id, db)
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


def _preview_fingerprint(user_id: int, db: Session) -> str:
    """Reject approval after training, goal, preferences or active schedule changes."""
    user = db.get(User, user_id)
    goals = db.query(Goal).filter_by(user_id=user_id, active=True).all()
    active = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    activities = db.query(Activity).filter(Activity.user_id == user_id, runs_only()).order_by(Activity.id).all()
    completed_dates = {a.date.date().isoformat() for a in activities}
    def stable_day(workout):
        snapshot = json.loads(_snapshot(workout))
        if workout.date in completed_dates:
            snapshot['session_status'] = 'completed'
        return json.dumps(snapshot, sort_keys=True) + str(workout.feel_rating) + str(workout.evaluation)
    data = {
        "today": date.today().isoformat(),
        "user": {c.name: getattr(user, c.name) for c in User.__table__.columns},
        "goals": [{c.name: getattr(g, c.name) for c in Goal.__table__.columns} for g in goals],
        "active": active.id if active else None,
        "schedule": [stable_day(w) for w in active.planned_workouts] if active else [],
        "activities": [(a.id, a.date, a.distance_meters, a.duration_seconds, a.description, a.splits, a.feel_rating)
                       for a in activities],
        "progression": [(p.id, p.current_level, p.current_pace_sec, p.updated_at)
                        for p in db.query(WorkoutProgression).filter_by(user_id=user_id).order_by(WorkoutProgression.id)],
    }
    return hashlib.sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()


@router.post("/{user_id}/preview")
def preview_plan(user_id: int, req: PlanRequest | None = None, db: Session = Depends(get_db)):
    return generate_training_plan(user_id, req or PlanRequest(), db)


@router.get("/{user_id}/draft")
def pending_draft(user_id: int, db: Session = Depends(get_db)):
    draft = db.query(Plan).filter_by(user_id=user_id, preview_state="draft").order_by(Plan.id.desc()).first()
    return json.loads(draft.preview_data) if draft else None


@router.post("/{user_id}/drafts/{plan_id}/approve")
def approve_draft(user_id: int, plan_id: int, db: Session = Depends(get_db)):
    # Serialize approvals before reading their context; two approvals cannot both win.
    _begin_schedule_write(db)
    try:
        draft = db.query(Plan).filter_by(id=plan_id, user_id=user_id).first()
        if not draft or draft.preview_state != "draft":
            raise HTTPException(409, "This preview is no longer awaiting approval")
        if draft.preview_context != _preview_fingerprint(user_id, db):
            raise HTTPException(409, "Your training or settings changed. Generate a fresh preview before approving.")
        data = json.loads(draft.preview_data)
        if data.get("violations"):
            raise HTTPException(409, "This preview has unresolved schedule constraints")
        _validate_schedule(draft, db)
        db.query(Plan).filter_by(user_id=user_id, is_active=True).update({"is_active": False})
        draft.is_active = True
        draft.preview_state = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"id": draft.id, "approved": True}


@router.post("/{user_id}/drafts/{plan_id}/discard")
def discard_draft(user_id: int, plan_id: int, db: Session = Depends(get_db)):
    changed = db.query(Plan).filter_by(id=plan_id, user_id=user_id, preview_state="draft").update({"preview_state": "discarded"})
    db.commit()
    return {"discarded": bool(changed)}


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
    walks_by_date = _walks_by_date(db_plan.user_id, db_plan.start_date, db_plan.end_date, db)

    # Match past days to actual activities (store primary activity_id for backwards compat)
    for pw in planned_workouts:
        if pw.date > today or pw.activity_id:
            continue
        activities = by_date.get(pw.date)
        if activities:
            pw.activity_id = max(activities, key=lambda a: a.distance_meters).id
            pw.session_status = "completed"
    db.commit()

    # Build response
    # Days before generation were history, not prescriptions. Older plans fall back to
    # created_at (stored in UTC, so it can be a day ahead in the evening — hence the new column).
    plan_created_date = db_plan.prescribed_from or (
        db_plan.created_at.date().isoformat() if db_plan.created_at else db_plan.start_date
    )

    weeks_map: dict[int, dict] = {}
    easy_cache: dict = {}
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
                actual = _build_actual_aggregated(activities, walks_by_date.get(pw.date))
                actual["workout"] = _executed_summary(pw, activities, user_id, db, easy_cache)
                if is_prescribed:
                    comparison = _build_comparison_aggregated(pw, activities)

        day_data = {
            "date": pw.date,
            "day": pw.day_name,
            "type": pw.type,
            "title": pw.title,
            "description": (render(loads(pw.prescription)) if loads(pw.prescription) else pw.description) if is_prescribed else None,
            "prescription": loads(pw.prescription) if is_prescribed else None,
            "execution": loads(pw.execution),
            "purpose": pw.purpose if is_prescribed else None,
            "distance_miles": pw.distance_miles,
            "warmup": pw.warmup if is_prescribed else None,
            "cooldown": pw.cooldown if is_prescribed else None,
            "prescribed": is_prescribed,
            "adjustment_note": pw.adjustment_note,
            "session_status": "completed" if actual else (pw.session_status or "not_logged"),
            "moved_to": pw.moved_to,
            "moved_from": pw.moved_from,
            "original_prescription": json.loads(pw.original_prescription) if pw.original_prescription else None,
            "actual": actual,
            "comparison": comparison,
            "walks": [_activity_line(a) for a in walks_by_date.get(pw.date, [])],
            "feedback": {
                "feel_rating": pw.feel_rating,
                "feel_notes": pw.feel_notes,
                "pace_assessment": pw.pace_assessment,
                "swapped": pw.swapped,
                "swap_reason": pw.swap_reason,
                "actual_workout_type": pw.actual_workout_type,
                "coach_response": pw.coach_response,
                "evaluation": _displayed_evaluation(pw, actual),
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
                actual_mileage += d["actual"]["total_distance_miles"]  # doubles count; walks never do
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
        "quality_policy": json.loads(db_plan.athlete_snapshot or "{}").get("quality_policy"),
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


class SessionAction(BaseModel):
    action: Literal["skip", "replace", "move"]
    target_date: date | None = None
    replacement: Literal["easy", "rest", "threshold", "intervals", "long_run"] | None = None
    option_id: str | None = Field(default=None, max_length=64)
    distance_miles: float | None = Field(default=None, gt=0, le=30, allow_inf_nan=False)
    reason: str = Field(default="Changed by athlete", max_length=500)


def _validate_schedule(plan: Plan, db: Session):
    """Validate mutations against real runs, rest preferences and stored budgets."""
    from app.core.plan_validator import validate_plan

    user = db.get(User, plan.user_id)
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    schedule = json.loads(plan.athlete_snapshot or '{}').get('schedule_preferences')
    rest_days = schedule['rest_days'] if schedule is not None else (user.rest_days or '').split(',')
    rest = [names.index(d.strip()) for d in rest_days if d.strip() in names]
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
    acts = _activities_by_date(plan.user_id, (date.fromisoformat(plan.start_date) - timedelta(days=1)).isoformat(), plan.end_date, db)
    load = json.loads(plan.load or "{}")
    budgets = load.get("weekly_budgets", [])
    baseline = load.get("baseline")
    if baseline is None:
        baseline = json.loads(plan.athlete_snapshot or "{}").get("current_weekly_mileage")
    if baseline is None:
        baseline = analyze_athlete(plan.user_id, db).get("current_fitness", {}).get("weekly_mileage_4w_avg", 0)
    weeks = {}
    if not budgets:
        # Old blocks have no saved load policy. Their original weekly total is the
        # ceiling; changing a session cannot create an unlimited legacy budget.
        for row in rows:
            original = json.loads(row.original_prescription) if row.original_prescription else {}
            while len(budgets) < row.week_number:
                budgets.append(0)
            budgets[row.week_number - 1] += original.get("distance_miles", row.distance_miles)
    for row in rows:
        w = weeks.setdefault(row.week_number, {"week_number": row.week_number, "days": []})
        if row.week_number <= len(budgets) and "budget_miles" not in w:
            w["budget_miles"] = budgets[row.week_number - 1]
        actuals = acts.get(row.date, [])
        if actuals:
            # Miles already run beyond the plan are history, not a proposal. The NET overrun of
            # completed days widens the week's ceiling so it never blocks an unrelated edit; a short
            # day offsets a long one, so no new room is created.
            w["overrun"] = w.get("overrun", 0.0) + sum(a.distance_meters for a in actuals) / 1609.34 - row.distance_miles
        # Completed work cannot be altered to make a proposed change fit.
        w["days"].append({"date": row.date, "type": "workout" if any(_is_hard_activity(a, baseline) for a in actuals) else row.type,
                           "distance_miles": sum(a.distance_meters for a in actuals) / 1609.34 if actuals else row.distance_miles,
                           "b2b": bool(row.b2b),
                           "prescribed": not actuals and row.date >= (plan.prescribed_from or plan.start_date)})
    for w in weeks.values():
        if "budget_miles" in w:
            w["budget_miles"] += max(0.0, w.pop("overrun", 0.0))
        w.pop("overrun", None)
    prior = {d for d, runs in acts.items() if d < plan.start_date and any(_is_hard_activity(a, baseline) for a in runs)}
    errors = validate_plan(list(weeks.values()), rest, prior)
    if errors:
        raise HTTPException(409, detail="; ".join(e["message"] for e in errors))


@router.get("/{user_id}/sessions/{session_date}/options")
def session_options(user_id: int, session_date: date, category: Literal["threshold", "intervals", "long_run"], db: Session = Depends(get_db)):
    from app.services.session_options import build_session_options
    plan = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    if not plan: raise HTTPException(404, "No active plan")
    row = db.query(PlannedWorkout).filter_by(plan_id=plan.id,date=session_date.isoformat()).first()
    if not row: raise HTTPException(404, "Session not found")
    return build_session_options(plan,row,category,db)


@router.post("/{user_id}/sessions/{session_date}")
def change_session(user_id: int, session_date: date, req: SessionAction, db: Session = Depends(get_db)):
    _begin_schedule_write(db)
    plan = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    if not plan:
        raise HTTPException(404, "No active plan")
    source = db.query(PlannedWorkout).filter_by(plan_id=plan.id, date=session_date.isoformat()).first()
    if not source:
        raise HTTPException(404, "Session not found")
    if source.date < (plan.prescribed_from or plan.start_date) or source.type == "race":
        raise HTTPException(409, "History and race days cannot be changed here")
    if source.activity_id or _get_activities_for_date(source.date, user_id, db):
        raise HTTPException(409, "This day already has a recorded activity")
    if source.session_status in {"skipped", "moved"}:
        raise HTTPException(409, "This session has already been skipped or moved")
    if req.action != "skip" and source.date < date.today().isoformat():
        raise HTTPException(409, "Only today's or future sessions can be replaced or moved")
    try:
        if req.action == 'replace' and req.replacement in {'threshold','intervals','long_run'}:
            from app.services.session_options import apply_option, build_session_options
            option_id = req.option_id
            if not option_id:
                menu = build_session_options(plan,source,req.replacement,db)
                if not menu['options']: raise HTTPException(409, '; '.join(menu['reasons']))
                option_id = menu['options'][0]['id']  # legacy clients still get a policy-validated option
            apply_option(plan,source,req.replacement,option_id,req.reason,db)
            db.commit()
            return {'date':source.date,'session_status':source.session_status,'moved_to':source.moved_to}
        if req.action == "move":
            target = db.query(PlannedWorkout).filter_by(plan_id=plan.id, date=req.target_date.isoformat() if req.target_date else "").first()
            if not target or target.date <= source.date or target.date < date.today().isoformat():
                raise HTTPException(422, "Choose a later day in this block")
            if target.type not in {"easy", "rest"} or target.activity_id or _get_activities_for_date(target.date, user_id, db):
                raise HTTPException(409, "Choose an unrun easy or rest day")
            if target.session_status in {"skipped", "moved", "replaced"}:
                raise HTTPException(409, "The destination has already been changed")
            _mark_changed(target, f"Moved from {source.date}: {req.reason}")
            for key in ("type", "title", "description", "purpose", "distance_miles", "warmup", "cooldown", "prescription", "b2b"):
                setattr(target, key, getattr(source, key))
            target.b2b = False
            target.session_status = "moved"
            target.moved_from = source.date
            source.moved_to = target.date
        elif req.action == "replace":
            if not req.replacement:
                raise HTTPException(422, "Choose a replacement")
            _mark_changed(source, req.reason)
            source.type = req.replacement
            source.title = "Rest Day" if source.type == "rest" else "Easy Run"
            source.description = "Rest and recover." if source.type == "rest" else "Conversational effort, truly easy."
            source.distance_miles = 0 if source.type == "rest" else req.distance_miles or min(source.distance_miles or 3, 6)
            source.warmup = source.cooldown = None
            source.prescription = json.dumps(day_prescription({"type": source.type, "distance_miles": source.distance_miles, "description": source.description}))
            source.b2b = False
            source.b2b = False
            source.session_status = "replaced"
        if req.action in {"skip", "move"}:
            _mark_changed(source, f"{req.action.title()}: {req.reason}")
            source.type, source.title, source.description = "rest", "Session moved" if req.action == "move" else "Session skipped", req.reason
            source.distance_miles = 0
            source.warmup = source.cooldown = None
            source.session_status = "moved" if req.action == "move" else "skipped"
            source.prescription = json.dumps(day_prescription({"type": "rest", "distance_miles": 0, "description": source.description}))
            source.b2b = False
        db.flush()
        _validate_schedule(plan, db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"date": source.date, "session_status": source.session_status, "moved_to": source.moved_to}


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
    return json.dumps({k: getattr(pw, k) for k in ("type", "title", "description", "purpose", "distance_miles", "warmup", "cooldown", "prescription", "b2b", "session_status", "moved_to", "moved_from")})


def _mark_changed(pw: PlannedWorkout, reason: str):
    if not pw.original_prescription:
        pw.original_prescription = _snapshot(pw)
    pw.adjustment_note = reason


def _apply_feedback_effects(user_id, db_plan, pw, activities, evidence_act, req, db) -> tuple[dict | None, list[dict]]:
    """Deterministic consequences of feedback. Caller owns the transaction."""
    changes: list[dict] = []
    evaluation = None
    feedback_date = pw.date

    # 1. Evaluate the workout and move ONE progression lever. A clearly different quality
    #    session (3x8min threshold on a 3x1200m day) is logged as off-plan instead.
    off_plan_eval = _off_plan_evaluation(user_id, pw, activities, db) if pw.type == "workout" and not req.swapped else None
    if off_plan_eval:
        evaluation = off_plan_eval | {"feel": req.feel_rating, "activity_ids": [a.id for a in activities]}
        pw.evaluation = json.dumps(evaluation)
        pw.actual_workout_type = req.actual_workout_type or evaluation["executed"]["category"]
    elif pw.type == "workout" and not req.swapped:
        prescribed = loads(pw.prescription)
        category = (prescribed["category"] if prescribed["category"] in {"threshold", "intervals"} else None) if prescribed else _detect_workout_category(pw.title)
        if category:
            execution = execution_from_activities(activities, prescribed) if prescribed else None
            if execution:
                pw.execution = json.dumps(execution)
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
                prescription=prescribed, execution=execution,
            )
            state = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category, program_key=_plan_program(db_plan)).first()
            if prescribed and ev.decision == "advance" and (
                prescribed.get('progression_eligible') is False
                or prescribed.get('phase') in {'base', 'taper', 'race_week', 'recovery'}
                or (state and prescribed.get('level', 1) < state.current_level)
            ):
                ev.decision = "hold"
                ev.reason = "Completed the phase- or budget-adapted session well. Holding the program level until its full prescription is demonstrated."
            if prescribed and prescribed.get('progression_eligible') is False:
                ev.new_pace_sec = None
                if ev.decision == 'recalibrate':
                    ev.decision = 'hold'
                    ev.reason = 'Controlled secondary dose completed; use the full primary prescription before changing pace.'
            elif prescribed and prescribed.get('goal_pace'):
                # Goal-pace reps move race-pace evidence (calibrator), not interval/threshold pace.
                ev.new_pace_sec = None
                if ev.decision == 'recalibrate':
                    ev.decision = 'hold'
                    ev.reason = ('Goal-pace reps ran faster than the step with control. Logged as race-pace evidence; '
                                 'the next goal-pace step uses it. Interval pace is unchanged.')
            evaluation = ev.to_dict() | {"category": category, "activity_ids": [a.id for a in activities]}
            pw.evaluation = json.dumps(evaluation)
            if not prescribed:
                pw.execution = json.dumps({"schema_version": 1, "category": category, "format": "legacy",
                    "evidence_source": ev.evidence, "confidence": "medium" if ev.evidence == "splits" else "low",
                    "matched_activity_ids": [a.id for a in activities], "segments": [], "completion": ev.completion,
                    "rep_paces_sec_per_mile": [], "actual_pace_sec_per_mile": ev.actual_pace_sec})
            if prescribed and ev.new_pace_sec and prescribed.get("base_pace_sec_per_mile"):
                # Evaluator compares work pace, progression stores template base.
                # Broken threshold is base-10, so retain that offset on updates.
                targets = [s["pace_range_sec_per_mile"] for s in prescribed['segments'] if s.get('pace_range_sec_per_mile')]
                if len(targets) == 1 and not prescribed['segments'][0].get('category') == 'strides':
                    target = sum(targets[0].values()) / 2
                    mapped_pace = prescribed['base_pace_sec_per_mile'] + ev.new_pace_sec - target
                else:
                    mapped_pace = None
            else:
                mapped_pace = ev.new_pace_sec
            _update_progression_from_evaluation(
                user_id=user_id, category=category, evaluation_decision=ev.decision,
                workout_name=pw.title, workout_date=feedback_date, new_pace_sec=mapped_pace, db=db,
                program=_plan_program(db_plan),
            )

    # 2. Swapped a hard workout: only an explicit choice reschedules
    if req.swapped and pw.type == "workout":
        choice = req.desired_reschedule_type
        if choice in {"tempo", "intervals", "threshold"}:
            slot, why_not = _find_safe_slot(db_plan, feedback_date, db)
            workout = _generate_swap_workout(user_id, choice, db_plan, db, slot.date) if slot else None
            if slot and not _fits_week_budget(db_plan, slot, workout.get("total_miles", pw.distance_miles), db):
                slot, why_not = None, (
                    "The extra workout doesn't fit that week's mileage budget without overloading it, "
                    "so it was dropped rather than added on top."
                )
            if slot:
                _mark_changed(slot, f"Rescheduled {choice} workout after {feedback_date} was swapped.")
                slot.prescription = json.dumps(workout.get("prescription"))
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
            next_hard.prescription = json.dumps(day_prescription({"type": "easy", "distance_miles": next_hard.distance_miles, "description": next_hard.description}))
            next_hard.b2b = False
            changes.append({"date": next_hard.date, "change": "downgraded", "reason": reason})

    if changes:
        db.flush()
    return evaluation, changes


def easy_pace_for(prescribed: dict | None, user_id: int, db: Session) -> float | None:
    """The easy-pace reference lap detection uses: the prescription's, else recent runs'."""
    if prescribed and prescribed.get("easy_pace_sec_per_mile"):
        return prescribed["easy_pace_sec_per_mile"]
    from app.services.garmin import recent_easy_pace
    return recent_easy_pace(user_id, db)


def _off_plan_evaluation(user_id: int, pw: PlannedWorkout, activities: list[Activity], db: Session) -> dict | None:
    from app.core.session_match import executed_session, off_plan, off_plan_evaluation
    prescribed = loads(pw.prescription)
    if not prescribed or not activities:
        return None
    executed = executed_session(activities, easy_pace_for(prescribed, user_id, db))
    return off_plan_evaluation(pw.title, executed) if off_plan(prescribed, executed) else None


def _decision_summary(evaluation: dict | None, changes: list[dict]) -> str | None:
    parts = []
    if evaluation:
        parts.append(f"Progression decision: {evaluation['decision']} — {evaluation['reason']}")
    for c in changes:
        parts.append(f"Schedule change ({c['change']}{' on ' + c['date'] if c['date'] else ''}): {c['reason']}")
    return "\n".join(parts) or None


def _fits_week_budget(db_plan: Plan, slot: PlannedWorkout, new_miles: float, db: Session) -> bool:
    """Would putting new_miles on slot keep its week within budget? Unrun easy days in
    that week may shrink (down to 3 mi) to make room; the week's total never grows."""
    from app.core.plan_validator import BUDGET_OVER_TOLERANCE, MIN_EASY

    budgets = (json.loads(db_plan.load) or {}).get("weekly_budgets", []) if db_plan.load else []
    week = db.query(PlannedWorkout).filter_by(plan_id=db_plan.id, week_number=slot.week_number).order_by(PlannedWorkout.date).all()
    def original_miles(row):
        return json.loads(row.original_prescription).get('distance_miles', row.distance_miles) if row.original_prescription else row.distance_miles
    budget = budgets[slot.week_number - 1] if 0 < slot.week_number <= len(budgets) else sum(original_miles(row) for row in week)
    acts = _activities_by_date(db_plan.user_id, min(d.date for d in week), max(d.date for d in week), db)
    actual_miles = lambda row: sum(a.distance_meters for a in acts.get(row.date, [])) / 1609.34 if acts.get(row.date) else row.distance_miles
    total = sum(actual_miles(row) for row in week if row.id != slot.id) + new_miles
    # Extra miles already run on completed days are history; they never block this change.
    budget += max(0.0, sum(actual_miles(row) - row.distance_miles for row in week if row.id != slot.id and acts.get(row.date)))
    # Trim to the budget itself. Half-mile rounding tolerance isn't free training.
    over = total - budget
    if over <= BUDGET_OVER_TOLERANCE:
        return True
    today = date.today().isoformat()
    flexible = sorted([d for d in week if d.id != slot.id and d.type == 'easy' and d.date > today
                       and d.date >= (db_plan.prescribed_from or db_plan.start_date)
                       and not d.activity_id and not acts.get(d.date)
                       and d.session_status not in {'skipped', 'moved', 'replaced'}], key=lambda d: (-d.distance_miles, d.date))
    cuts = []
    import math
    for row in flexible:
        room = max(0, row.distance_miles - MIN_EASY)
        cut = min(room, math.ceil(over * 2 - 1e-9) / 2)
        if cut > 0:
            cuts.append((row, cut))
            over -= cut
        if over <= 0:
            break
    if over > BUDGET_OVER_TOLERANCE:
        return False
    for row, cut in cuts:
        _mark_changed(row, f"Shortened {cut:g} mi to fit your replacement workout within this week's budget.")
        row.distance_miles = round(row.distance_miles - cut, 2)
        row.prescription = json.dumps(day_prescription({'type': row.type, 'distance_miles': row.distance_miles, 'description': row.description}))
    return True


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
ASSESSMENT_MAX_GAP_DAYS = 7  # assess the previous block only if it ended within a week of the new one


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
    for a in db.query(Activity).filter(Activity.user_id == user_id, Activity.date >= lo, Activity.date < hi, runs_only()):
        grouped.setdefault(a.date.date().isoformat(), []).append(a)
    return grouped


def _walks_by_date(user_id: int, start: str, end: str, db: Session) -> dict[str, list[Activity]]:
    """Walks in the window, for display only: they are never part of the running plan."""
    lo = datetime.fromisoformat(start)
    hi = datetime.fromisoformat(end) + timedelta(days=1)
    grouped: dict[str, list[Activity]] = {}
    for a in db.query(Activity).filter(Activity.user_id == user_id, Activity.date >= lo, Activity.date < hi,
                                       Activity.workout_type == "walk"):
        grouped.setdefault(a.date.date().isoformat(), []).append(a)
    return grouped


def _get_activities_for_date(date_str: str, user_id: int, db: Session) -> list[Activity]:
    """All runs for a user on a date (walks are never part of the running plan)."""
    return db.query(Activity).filter(
        Activity.user_id == user_id,
        func.date(Activity.date) == date_str,
        runs_only(),
    ).all()


def _format_pace(pace_seconds_per_mile: float) -> str:
    """Format pace in seconds to mm:ss string."""
    mins = int(pace_seconds_per_mile // 60)
    secs = int(pace_seconds_per_mile % 60)
    return f"{mins}:{secs:02d}"


def _executed_summary(pw: PlannedWorkout, activities: list[Activity], user_id: int, db: Session, easy_cache: dict) -> dict | None:
    """What was actually run, from Garmin laps: title, reps and whether it differs from the plan."""
    from app.core.session_match import executed_session, off_plan, session_title
    prescribed = loads(pw.prescription)
    if prescribed and prescribed.get("easy_pace_sec_per_mile"):
        easy = prescribed["easy_pace_sec_per_mile"]
    else:
        if "easy" not in easy_cache:
            easy_cache["easy"] = easy_pace_for(None, user_id, db)
        easy = easy_cache["easy"]
    executed = executed_session(activities, easy)
    if not executed:
        return None
    return {"title": session_title(executed), "label": executed["label"], "category": executed["category"],
            "kind": executed["kind"], "reps": executed["reps"], "recovery_seconds": executed["recovery_seconds"],
            "work_miles": executed["work_miles"], "off_plan": pw.type == "workout" and off_plan(prescribed, executed)}


def _displayed_evaluation(pw: PlannedWorkout, actual: dict | None) -> dict | None:
    """Stored verdict, unless the laps show an off-plan session it was judged against wrongly."""
    stored = json.loads(pw.evaluation) if pw.evaluation else None
    workout = (actual or {}).get("workout")
    # Only re-read verdicts that left the ladder alone; an applied regress/advance stays visible.
    if workout and workout["off_plan"] and (stored or {}).get("decision") in {None, "insufficient", "hold"}:
        from app.core.session_match import off_plan_evaluation
        return off_plan_evaluation(pw.title, workout) | {"feel": pw.feel_rating}
    return stored


def _activity_line(a: Activity) -> dict:
    miles = (a.distance_meters or 0) / 1609.34
    return {"id": a.id, "name": a.name, "distance_miles": round(miles, 2),
            "avg_pace": _format_pace(a.duration_seconds / miles) if miles and a.duration_seconds else None,
            "duration_seconds": a.duration_seconds, "average_heartrate": a.average_heartrate}


def _build_actual_aggregated(activities: list[Activity], walks: list[Activity] | None = None) -> dict:
    """The day's run, never a blend: stats come from the run holding the prescribed work (or the
    longest run). Other runs that day (a double) are listed with their own numbers and count toward
    weekly miles; walks are listed but are never part of the running plan."""
    primary = _work_evidence_activity(activities)
    line = _activity_line(primary)
    others = [a for a in sorted(activities, key=lambda a: a.date) if a.id != primary.id]
    return {
        "distance_miles": line["distance_miles"],
        "avg_pace": line["avg_pace"],
        "duration_seconds": primary.duration_seconds or 0,
        "average_heartrate": primary.average_heartrate,
        "description": primary.description,
        "feel_rating": primary.feel_rating,
        "name": primary.name,
        "activity_count": len(activities),
        "total_distance_miles": round(sum(a.distance_meters for a in activities) / 1609.34, 2),
        "other_runs": [_activity_line(a) for a in others],
        "walks": [_activity_line(a) for a in walks or []],
    }


def _build_comparison_aggregated(pw: PlannedWorkout, activities: list[Activity]) -> dict | None:
    """The day's run against its prescription (a second run or a walk is not 'over prescribed')."""
    primary = _work_evidence_activity(activities)
    line = _activity_line(primary)
    actual_miles = line["distance_miles"]
    distance_diff = round(actual_miles - pw.distance_miles, 2)
    pace_str = f"{line['avg_pace']}/mi" if line["avg_pace"] else ""
    hr_str = f", {int(primary.average_heartrate)}bpm" if primary.average_heartrate else ""
    if distance_diff > 0:
        diff_label = f"+{distance_diff:.1f}mi over prescribed"
    elif distance_diff < 0:
        diff_label = f"{distance_diff:.1f}mi under prescribed"
    else:
        diff_label = "exact distance"
    return {"distance_diff_miles": distance_diff, "summary": f"{actual_miles}mi at {pace_str}{hr_str}. {diff_label}."}


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
    from app.core.workout_ladders import program_key
    key = program_key(goal_distance)
    result = {}
    for category in ("intervals", "threshold"):
        prog = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category, program_key=key).first()
        if not prog:
            legacy = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category, program_key=None).first()
            if legacy and goal_distance == "5k":
                # The old program was explicitly the 5K ladder.
                prog = legacy
                prog.program_key = key
            else:
                prior = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category).order_by(WorkoutProgression.updated_at.desc()).first()
                cutoff = date.today() - timedelta(days=84)
                pace = prior.current_pace_sec if prior and prior.last_workout_date and prior.last_workout_date >= cutoff else None
                prog = WorkoutProgression(user_id=user_id, category=category, program_key=key,
                                          current_level=1, current_pace_sec=pace, sessions_at_level=0, format_rotation=0)
                db.add(prog)
        db.flush()
        result[category] = {"current_level": prog.current_level, "current_pace_sec": prog.current_pace_sec,
                            "format_rotation": prog.format_rotation, "last_execution": prog.last_execution,
                            "sessions_at_level": prog.sessions_at_level, "program_key": key}

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
    program: str | None = None,
):
    """Update the WorkoutProgression record based on an evaluation decision."""
    prog = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category, program_key=program).first()

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


def _generate_swap_workout(user_id: int, desired_type: str, db_plan: Plan, db: Session, session_date: str | None = None) -> dict:
    """Generate a workout from the ladder based on user's desired type."""
    from app.core.workout_ladders import get_workout_at_level
    from app.services.pace_calibrator import calibrate_paces as _calibrate

    category_map = {"tempo": "threshold", "threshold": "threshold", "intervals": "intervals"}
    category = category_map.get(desired_type, "threshold")

    goal_snapshot = json.loads(db_plan.goal_snapshot) if db_plan.goal_snapshot else {}
    goal_distance = goal_snapshot.get("distance") or goal_snapshot.get("type") or "general"
    prog = db.query(WorkoutProgression).filter_by(user_id=user_id, category=category, program_key=_plan_program(db_plan)).first()
    level = prog.current_level if prog else 1
    paces = json.loads(db_plan.training_paces) if db_plan.training_paces else {}
    if not paces:
        from app.core.plan_engine import _build_current_paces
        guide = json.loads(db_plan.pacing_guide or "{}")
        easy = _parse_pace(guide.get("easy", "9:00").split("-")[0]) or 540
        paces = _build_current_paces(easy, _calibrate(user_id, db))
    if prog and prog.current_pace_sec:
        from app.core.plan_engine import effective_paces
        paces = effective_paces(paces, {category: {"current_pace_sec": prog.current_pace_sec}})
    phases = json.loads(db_plan.phases or "[]")
    week_index = max(0, (date.fromisoformat(session_date or db_plan.start_date) - date.fromisoformat(db_plan.start_date)).days // 7)
    phase = phases[week_index].get("phase", "general") if week_index < len(phases) else "general"

    from app.core.quality_policy import format_bookends
    user = db.get(User, user_id)
    return format_bookends(get_workout_at_level(category, level, paces, goal_distance, phase),
                           paces, user.workout_format or 'distance')


def _plan_program(plan: Plan) -> str | None:
    from app.core.workout_ladders import program_key
    goal = json.loads(plan.goal_snapshot or "{}")
    return program_key(goal.get("distance") or goal.get("type")) if goal else None


def _begin_schedule_write(db: Session):
    """Serialize read/validate/write decisions for this single-athlete SQLite app."""
    from sqlalchemy import text
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _recent_fatigue_assessment(user_id: int, active: Plan | None, db: Session):
    """Feel evidence can justify recovery before a block has five run days."""
    from app.core.block_assessment import BlockAssessment
    cutoff = date.today() - timedelta(days=6)
    ratings = {}
    def add(day, feel):
        if cutoff.isoformat() <= day <= date.today().isoformat() and feel is not None:
            ratings[day] = min(ratings.get(day, 10), feel)
    for act in db.query(Activity).filter(Activity.user_id == user_id, Activity.date >= datetime.combine(cutoff, datetime.min.time()), Activity.feel_rating.isnot(None), runs_only()):
        add(act.date.date().isoformat(), act.feel_rating)
    if active:
        for day in active.planned_workouts:
            add(day.date, day.feel_rating)
    low = sum(feel <= 4 for feel in ratings.values())
    if low >= 2:
        decision = 'recovery'
        reason = 'Two or more low feel ratings in the last seven days: reduce volume and keep the remaining current week easy.'
    elif ratings and ratings[max(ratings)] <= 4 and (date.today() - date.fromisoformat(max(ratings))).days <= 2:
        decision = 'hold'
        reason = 'Your latest rated run felt poor: no mileage uplift, and the remaining current week stays easy before reassessing.'
    else:
        return None
    return BlockAssessment(decision=decision, reasons=[reason], feel_count=len(ratings), low_feels=low,
                           avg_feel=round(sum(ratings.values()) / len(ratings), 1))
