"""Post-run coach note: the shared OpenAI review when configured, else a template.

The training decision is always made in code first; this only explains it.
"""

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import Activity
from app.models.plan import PlannedWorkout

logger = logging.getLogger("stride.coach")

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


def get_coach_feedback(
    user_id: int,
    pw: PlannedWorkout,
    activities: list[Activity],
    feedback,
    db: Session,
    decision_summary: str | None = None,
) -> str:
    """Get science-backed coach feedback for a completed run.

    Returns coach response string. Falls back to template without an OpenAI key.
    """
    if settings.openai_api_key:
        # The shared review also examines the upcoming plan and stores optional,
        # validated suggestions. It never mutates training on a model's behalf.
        try:
            from app.services.coaching import review_training
            from app.api.plans import _work_evidence_activity
            activity = _work_evidence_activity(activities)
            review = review_training(user_id, db, activity_id=activity.id if activity else None)
            base = review['summary'] if review['status'] == 'ready' else _template_feedback(feedback, pw, activities)
            return f"{base}\n\nStride's applied decision: {decision_summary}" if decision_summary else base
        except Exception as exc:
            db.rollback()
            logger.warning('OpenAI feedback unavailable (%s); using saved training decision', type(exc).__name__)
            base = _template_feedback(feedback, pw, activities)
            return f"{base}\n\n{decision_summary}" if decision_summary else base
    base = _template_feedback(feedback, pw, activities)
    return f"{base}\n\n{decision_summary}" if decision_summary else base


def _template_feedback(feedback, pw: PlannedWorkout, activities: list[Activity]) -> str:
    """Template-based fallback when LLM is unavailable."""
    feel = feedback.feel_rating
    swapped = feedback.swapped
    if feel is None and not swapped:
        return ("Thanks for the notes. Your coach review reads them alongside your watch data "
                "and laps, and it will appear shortly.")

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
