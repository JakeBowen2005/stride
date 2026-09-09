"""Weekly training summary.

Aggregates planned vs actual for a week, then asks the coach LLM to narrate
it against the science docs. The numbers are computed here rather than by the
model — the model interprets, it does not calculate.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.user import Goal, User

METERS_PER_MILE = 1609.34


def _format_pace(seconds_per_mile: float | None) -> str | None:
    if not seconds_per_mile or seconds_per_mile <= 0:
        return None
    minutes = int(seconds_per_mile // 60)
    secs = int(seconds_per_mile % 60)
    return f"{minutes}:{secs:02d}"


def week_bounds(day: date) -> tuple[date, date]:
    """Monday-to-Sunday week containing `day`."""
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _activities_between(user_id: int, start: date, end: date, db: Session) -> list[Activity]:
    return (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= datetime.combine(start, time.min),
            Activity.date < datetime.combine(end + timedelta(days=1), time.min),
        )
        .order_by(Activity.date.asc())
        .all()
    )


def build_weekly_stats(user_id: int, week_start: date, db: Session) -> dict:
    """Planned vs actual for one week. Pure aggregation, no LLM."""
    start, end = week_bounds(week_start)
    activities = _activities_between(user_id, start, end, db)

    actual_miles = sum(a.distance_meters for a in activities) / METERS_PER_MILE
    actual_seconds = sum(a.duration_seconds or 0 for a in activities)
    avg_pace = (actual_seconds / actual_miles) if actual_miles > 0 else None

    # Planned side: whatever the active plan prescribed for these dates.
    plan = (
        db.query(Plan)
        .filter(Plan.user_id == user_id, Plan.is_active.is_(True))
        .first()
    )
    planned_days: list[PlannedWorkout] = []
    if plan:
        planned_days = (
            db.query(PlannedWorkout)
            .filter(
                PlannedWorkout.plan_id == plan.id,
                PlannedWorkout.date >= start.isoformat(),
                PlannedWorkout.date <= end.isoformat(),
            )
            .order_by(PlannedWorkout.date)
            .all()
        )

    planned_miles = sum(d.distance_miles for d in planned_days)

    # Workout execution: did the hard days happen?
    workout_days = [d for d in planned_days if d.type in ("workout", "long_run")]
    completed_workouts = []
    missed_workouts = []
    for day in workout_days:
        ran = [a for a in activities if a.date and a.date.date().isoformat() == day.date]
        day_miles = sum(a.distance_meters for a in ran) / METERS_PER_MILE if ran else 0
        record = {
            "date": day.date,
            "title": day.title,
            "type": day.type,
            "planned_miles": day.distance_miles,
            "actual_miles": round(day_miles, 2),
            "feel_rating": day.feel_rating,
            "pace_assessment": day.pace_assessment,
            "swapped": day.swapped,
        }
        # "Completed" means they got most of the way through it, not that they
        # nailed it — judging execution is the coach's job, not arithmetic.
        if day_miles >= day.distance_miles * 0.7:
            completed_workouts.append(record)
        else:
            missed_workouts.append(record)

    feels = [d.feel_rating for d in planned_days if d.feel_rating]
    avg_feel = round(sum(feels) / len(feels), 1) if feels else None

    # Trailing context: is this week up or down against the recent norm?
    four_weeks_ago = start - timedelta(days=28)
    trailing = _activities_between(user_id, four_weeks_ago, start - timedelta(days=1), db)
    trailing_avg = (sum(a.distance_meters for a in trailing) / METERS_PER_MILE / 4) if trailing else 0

    hr_activities = [(a.average_heartrate, a.duration_seconds or 0) for a in activities if a.average_heartrate]
    avg_hr = None
    if hr_activities:
        total_dur = sum(d for _, d in hr_activities)
        if total_dur > 0:
            avg_hr = round(sum(hr * d for hr, d in hr_activities) / total_dur)

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "planned_miles": round(planned_miles, 1),
        "actual_miles": round(actual_miles, 1),
        "miles_delta": round(actual_miles - planned_miles, 1),
        "run_count": len(activities),
        "planned_run_count": len([d for d in planned_days if d.type != "rest"]),
        "total_duration_seconds": round(actual_seconds),
        "avg_pace": _format_pace(avg_pace),
        "avg_heartrate": avg_hr,
        "avg_feel": avg_feel,
        "trailing_4wk_avg_miles": round(trailing_avg, 1),
        "vs_trailing_avg": round(actual_miles - trailing_avg, 1),
        "completed_workouts": completed_workouts,
        "missed_workouts": missed_workouts,
        "runs": [
            {
                "date": a.date.date().isoformat() if a.date else None,
                "name": a.name,
                "miles": round(a.distance_meters / METERS_PER_MILE, 2),
                "pace": _format_pace((a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None),
                "heartrate": a.average_heartrate,
                "feel": a.feel_rating,
                "description": a.description,
            }
            for a in activities
        ],
    }


def _stats_for_prompt(stats: dict) -> str:
    lines = [
        f"Week of {stats['week_start']}",
        f"Mileage: {stats['actual_miles']}mi actual vs {stats['planned_miles']}mi planned "
        f"({stats['miles_delta']:+.1f})",
        f"Runs: {stats['run_count']} of {stats['planned_run_count']} planned",
        f"4-week trailing average: {stats['trailing_4wk_avg_miles']}mi/wk "
        f"(this week {stats['vs_trailing_avg']:+.1f})",
    ]
    if stats["avg_pace"]:
        lines.append(f"Average pace across all runs: {stats['avg_pace']}/mi")
    if stats["avg_heartrate"]:
        lines.append(f"Average HR: {stats['avg_heartrate']}bpm")
    if stats["avg_feel"]:
        lines.append(f"Average feel rating: {stats['avg_feel']}/10")

    if stats["completed_workouts"]:
        lines.append("\nKey sessions completed:")
        for w in stats["completed_workouts"]:
            feel = f", felt {w['feel_rating']}/10" if w["feel_rating"] else ""
            lines.append(
                f"  {w['date']} — {w['title']}: {w['actual_miles']}mi "
                f"(planned {w['planned_miles']}mi){feel}"
            )
    if stats["missed_workouts"]:
        lines.append("\nKey sessions missed or cut short:")
        for w in stats["missed_workouts"]:
            lines.append(
                f"  {w['date']} — {w['title']}: {w['actual_miles']}mi "
                f"(planned {w['planned_miles']}mi)"
            )

    if stats["runs"]:
        lines.append("\nEvery run this week:")
        for r in stats["runs"]:
            desc = f" — {r['description'][:120]}" if r.get("description") else ""
            lines.append(f"  {r['date']}: {r['miles']}mi at {r['pace'] or '?'}/mi{desc}")

    return "\n".join(lines)


async def build_weekly_summary(user_id: int, week_start: date, db: Session) -> dict:
    """Stats plus a coach narrative. Falls back to stats-only without an API key."""
    stats = build_weekly_stats(user_id, week_start, db)

    if not settings.anthropic_api_key:
        stats["narrative"] = _template_narrative(stats)
        stats["narrative_source"] = "template"
        return stats

    import anthropic

    from app.services.coach import _build_system_prompt

    goal = db.query(Goal).filter(Goal.user_id == user_id, Goal.active.is_(True)).first()
    system_prompt = _build_system_prompt(user_id, goal, db)

    user_message = (
        f"{_stats_for_prompt(stats)}\n\n"
        "Write this week's training recap. Cover: what actually happened versus what was "
        "planned, how the key sessions went, any fatigue or trend signals worth flagging, "
        "and what next week should focus on. Be specific and reference the numbers. "
        "If something is off — mileage spiking, feel ratings dropping, workouts getting "
        "missed — say so directly. 4-6 sentences."
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        stats["narrative"] = response.content[0].text
        stats["narrative_source"] = "llm"
    except Exception as e:  # noqa: BLE001 — a failed summary must not 500
        print(f"Weekly summary LLM error: {e}")
        stats["narrative"] = _template_narrative(stats)
        stats["narrative_source"] = "template"

    return stats


def _template_narrative(stats: dict) -> str:
    """Deterministic fallback when the LLM is unavailable."""
    parts = []
    delta = stats["miles_delta"]
    if stats["actual_miles"] == 0:
        return "No runs logged this week."

    if abs(delta) <= 3:
        parts.append(
            f"{stats['actual_miles']}mi against a {stats['planned_miles']}mi plan — on target."
        )
    elif delta > 0:
        parts.append(
            f"{stats['actual_miles']}mi against a {stats['planned_miles']}mi plan, "
            f"{delta:.1f}mi over. Extra easy miles are fine; extra hard miles are how you get hurt."
        )
    else:
        parts.append(
            f"{stats['actual_miles']}mi against a {stats['planned_miles']}mi plan, "
            f"{abs(delta):.1f}mi short."
        )

    if stats["missed_workouts"]:
        titles = ", ".join(w["title"] for w in stats["missed_workouts"])
        parts.append(f"Missed or cut short: {titles}.")
    elif stats["completed_workouts"]:
        parts.append(f"All {len(stats['completed_workouts'])} key sessions went down.")

    if stats["avg_feel"] is not None:
        if stats["avg_feel"] <= 4:
            parts.append(
                f"Average feel was {stats['avg_feel']}/10 — that is a fatigue signal, not a bad week. "
                f"Consider pulling back before it becomes an injury."
            )
        elif stats["avg_feel"] >= 8:
            parts.append(f"Average feel {stats['avg_feel']}/10 — you're absorbing the work well.")

    trailing = stats["trailing_4wk_avg_miles"]
    if trailing > 0 and stats["actual_miles"] > trailing * 1.3:
        parts.append(
            f"Heads up: this week was {stats['vs_trailing_avg']:+.1f}mi against a "
            f"{trailing}mi trailing average. That is a sharp spike — hold here before building further."
        )

    return " ".join(parts)
