"""Science-backed coaching feedback via LLM with structured context injection.

Loads the relevant training science docs and athlete profile, then passes them
as system prompt context so the LLM response is grounded in real training
principles — not generic advice.
"""

from pathlib import Path

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.user import Goal, User

DOCS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs"

# Map goal distances to science doc filenames
SCIENCE_DOCS = {
    "5k": "5k-training-science.md",
    "10k": "10k-training-science.md",
    "half": "half-marathon-training-science.md",
    "marathon": "marathon-training-science.md",
    "50k": "ultra-training-science.md",
    "50mi": "ultra-training-science.md",
    "100k": "ultra-training-science.md",
    "100mi": "ultra-training-science.md",
}


def _load_doc(filename: str) -> str:
    """Load a doc file, return empty string if not found."""
    path = DOCS_DIR / filename
    if path.exists():
        return path.read_text()
    return ""


def _format_pace_sec(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def _build_recent_training(user_id: int, db: Session, days: int = 14) -> str:
    """Build a summary of recent training for context."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id, Activity.date >= cutoff)
        .order_by(Activity.date.asc())
        .all()
    )

    if not activities:
        return "No runs in the last 14 days."

    lines = []
    total_miles = 0
    for a in activities:
        miles = round(a.distance_meters / 1609.34, 1)
        total_miles += miles
        day_name = a.date.strftime("%a %b %d") if a.date else "?"
        pace = ""
        if a.average_pace_per_km:
            pace = _format_pace_sec(a.average_pace_per_km * 1.60934) + "/mi"
        hr = f", {int(a.average_heartrate)}bpm" if a.average_heartrate else ""
        feel = f", feel {a.feel_rating}/10" if a.feel_rating else ""
        wtype = f" [{a.workout_type}]" if a.workout_type else ""
        te = ""
        if a.aerobic_training_effect:
            te = f", Garmin TE {a.aerobic_training_effect:.1f} aerobic/{(a.anaerobic_training_effect or 0):.1f} anaerobic"
        lines.append(f"  {day_name}: {miles}mi at {pace}{hr}{feel}{te}{wtype} — {a.name}")

    header = f"Last {days} days: {round(total_miles, 1)}mi total, {len(activities)} runs"
    return header + "\n" + "\n".join(lines)


def _build_today_context(
    pw: PlannedWorkout, activities: list[Activity], feedback
) -> str:
    """Build context about today's specific run."""
    lines = []

    # What was prescribed
    lines.append(f"Prescribed: {pw.title} — {pw.distance_miles}mi")
    if pw.description:
        lines.append(f"  Details: {pw.description}")
    if pw.purpose:
        lines.append(f"  Purpose: {pw.purpose}")

    # What was actually done
    if activities:
        total_m = sum(a.distance_meters for a in activities)
        total_dur = sum(a.duration_seconds or 0 for a in activities)
        actual_miles = round(total_m / 1609.34, 2)
        pace = ""
        if total_m > 0 and total_dur > 0:
            pace = _format_pace_sec(total_dur / (total_m / 1609.34)) + "/mi"
        lines.append(f"Actual: {actual_miles}mi at {pace}")
        primary = max(activities, key=lambda a: a.distance_meters or 0)
        if primary.average_heartrate:
            lines.append(f"  Avg HR {int(primary.average_heartrate)}bpm, max {int(primary.max_heartrate or 0)}bpm")
        if primary.description:
            lines.append(f"  Workout detail: {primary.description[:500]}")
        if len(activities) > 1:
            lines.append(f"  ({len(activities)} separate activities)")
            for a in sorted(activities, key=lambda x: x.date):
                am = round(a.distance_meters / 1609.34, 2)
                lines.append(f"    - {a.name}: {am}mi")
    else:
        lines.append("Actual: no activity recorded")

    lines.extend(_wellness_lines(pw))

    # Feedback
    lines.append(f"Feel: {feedback.feel_rating}/10")
    if feedback.feel_notes:
        lines.append(f"Notes: \"{feedback.feel_notes}\"")
    if feedback.pace_assessment:
        lines.append(f"Pace vs target: {feedback.pace_assessment}")
    if feedback.swapped:
        lines.append(f"SWAPPED workout — did {feedback.actual_workout_type or 'something else'} instead")
        if feedback.swap_reason:
            lines.append(f"Reason: \"{feedback.swap_reason}\"")

    return "\n".join(lines)


def _wellness_lines(pw: PlannedWorkout) -> list[str]:
    """Garmin overnight data for the day of the run, if synced."""
    from sqlalchemy.orm import object_session

    from app.models.wellness import DailyWellness

    db = object_session(pw)
    if db is None or not pw.date:
        return []
    w = db.query(DailyWellness).filter(
        DailyWellness.user_id == pw.plan.user_id, DailyWellness.date == pw.date
    ).first()
    if not w:
        return []
    parts = []
    if w.sleep_seconds:
        parts.append(f"sleep {w.sleep_seconds / 3600:.1f}h" + (f" (score {w.sleep_score})" if w.sleep_score else ""))
    if w.hrv_last_night:
        rng = f", normal {w.hrv_baseline_low:.0f}-{w.hrv_baseline_high:.0f}" if w.hrv_baseline_low and w.hrv_baseline_high else ""
        parts.append(f"HRV {w.hrv_last_night:.0f}ms{rng}")
    if w.resting_hr:
        parts.append(f"resting HR {w.resting_hr:.0f}" + (f" (7d avg {w.resting_hr_7d_avg:.0f})" if w.resting_hr_7d_avg else ""))
    if w.readiness_score is not None:
        parts.append(f"Garmin readiness {w.readiness_score} ({(w.readiness_level or '').lower()})")
    if w.acwr:
        parts.append(f"acute:chronic load {w.acwr:.2f}")
    return [f"Recovery (Garmin): {', '.join(parts)}"] if parts else []


def _build_system_prompt(user_id: int, goal: Goal | None, db: Session) -> str:
    """Assemble the full system prompt with science docs and athlete context."""
    sections = []

    # Core identity
    sections.append(
        "You are a knowledgeable running coach. You give concise, science-backed "
        "feedback grounded in the training documents below. Reference specific "
        "principles when relevant. Keep responses to 2-4 sentences. Be honest — "
        "if they need to slow down, say so. If they crushed it, acknowledge it. "
        "If they're fatigued, suggest adjustments. Never be generic."
    )

    # Training principles (always included)
    principles = _load_doc("training-principles.md")
    if principles:
        sections.append("=== TRAINING PRINCIPLES ===\n" + principles)

    # Goal-specific science
    if goal and goal.race_distance:
        doc_name = SCIENCE_DOCS.get(goal.race_distance)
        if doc_name:
            science = _load_doc(doc_name)
            if science:
                sections.append(f"=== {goal.race_distance.upper()} TRAINING SCIENCE ===\n" + science)

    # Athlete profile
    profile = _load_doc("athlete-profile-jake.md")
    if profile:
        sections.append("=== ATHLETE PROFILE ===\n" + profile)

    return "\n\n".join(sections)


async def get_coach_feedback(
    user_id: int,
    pw: PlannedWorkout,
    activities: list[Activity],
    feedback,
    db: Session,
) -> str:
    """Get science-backed coach feedback for a completed run.

    Returns coach response string. Falls back to template if no API key.
    """
    # Get goal for context
    goal = db.query(Goal).filter(Goal.user_id == user_id, Goal.active == True).first()

    # Build context pieces
    recent = _build_recent_training(user_id, db)
    today = _build_today_context(pw, activities, feedback)

    # If no API key, use template fallback
    if not settings.anthropic_api_key:
        return _template_feedback(feedback, pw, activities)

    system_prompt = _build_system_prompt(user_id, goal, db)

    user_message = f"RECENT TRAINING:\n{recent}\n\nTODAY'S RUN:\n{today}\n\nGive me quick coach feedback on today's run."

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.coach_model,
            max_tokens=2048,
            output_config={"effort": "low"},  # short coaching notes don't need deep reasoning
            # The science docs are large and identical across calls — cache them
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text or _template_feedback(feedback, pw, activities)
    except anthropic.APIError as e:
        print(f"Coach LLM error: {e}")
        return _template_feedback(feedback, pw, activities)


def _template_feedback(feedback, pw: PlannedWorkout, activities: list[Activity]) -> str:
    """Template-based fallback when LLM is unavailable."""
    feel = feedback.feel_rating
    swapped = feedback.swapped

    if swapped:
        return (
            "Good call listening to your body. Swapping a workout for easy running "
            "when you're not feeling it prevents digging a fatigue hole. "
            "Quality over quantity — fresh legs make the next hard session more productive."
        )

    if feel <= 3:
        return (
            "Sounds like a tough day. If this persists for 2-3 days, consider adding "
            "an extra rest day or cutting back mileage. Per Principle 7 — adapt based "
            "on response. One bad day is normal; a pattern means you need recovery."
        )

    if feel <= 5:
        return (
            "Not your best day, and that's fine. Pay attention to sleep and stress — "
            "they affect running more than most people realize. If legs feel heavy again "
            "tomorrow, consider going shorter or taking the day off."
        )

    actual_miles = 0
    if activities:
        actual_miles = sum(a.distance_meters for a in activities) / 1609.34

    diff = actual_miles - pw.distance_miles if actual_miles > 0 else 0

    if feel >= 8 and pw.type == "workout":
        return (
            "Strong session. Nailing workouts like this builds both fitness and confidence. "
            "Make sure tomorrow's easy day is genuinely easy — the adaptation happens during recovery."
        )

    if feel >= 7:
        return (
            "Solid day. Consistent efforts like this are what build fitness over time. "
            "Keep the easy days easy and trust the process."
        )

    return (
        "Decent run in the books. Every mile counts toward the bigger picture. "
        "Keep showing up consistently and the fitness will follow."
    )
