"""Science-backed coaching feedback via LLM with structured context injection.

Loads the relevant training science docs and athlete profile, then passes them
as system prompt context so the LLM response is grounded in real training
principles — not generic advice.
"""

import os
from pathlib import Path

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.user import Goal, User

def _resolve_docs_dir() -> Path:
    """Find the training science docs.

    Locally these live at <repo>/docs. On Railway the service root is set to
    backend/, so that path does not exist there and every science doc silently
    resolved to "" -- the coach kept answering, just with none of the training
    context. Check the plausible locations and let STRIDE_DOCS_DIR override.
    """
    override = os.environ.get("STRIDE_DOCS_DIR")
    candidates = []
    if override:
        candidates.append(Path(override))
    here = Path(__file__).resolve()
    candidates += [
        here.parent.parent.parent.parent / "docs",  # <repo>/docs
        here.parent.parent.parent / "docs",         # backend/docs
        Path.cwd() / "docs",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[-1]


DOCS_DIR = _resolve_docs_dir()

# Map goal distances to science doc filenames
SCIENCE_DOCS = {
    "5k": "5k-training-science.md",
    "10k": "10k-training-science.md",
    "half": "half-marathon-training-science.md",
    "marathon": "marathon-training-science.md",
}


def _load_doc(filename: str) -> str:
    """Load a doc file, return empty string if not found."""
    path = DOCS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    print(f"[coach] WARNING: training doc not found: {path}")
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
        lines.append(f"  {day_name}: {miles}mi at {pace}{hr}{feel}{wtype} — {a.name}")

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
        if len(activities) > 1:
            lines.append(f"  ({len(activities)} separate activities)")
            for a in sorted(activities, key=lambda x: x.date):
                am = round(a.distance_meters / 1609.34, 2)
                lines.append(f"    - {a.name}: {am}mi")
    else:
        lines.append("Actual: no activity recorded")

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
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text
    except Exception as e:
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
