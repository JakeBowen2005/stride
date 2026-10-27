"""Running hours as a second load measure: shadow budgets, recorded but not enforced.

docs/aerobic-hours.md phase 2. Miles stay the injury budget; time measures the aerobic
stimulus. These checks compute where an hours budget (R2), a longest-session guard (R3)
and deloads in time (R4) *would* bind, and save that on the block's load so Jake can
review 4–6 weeks of blocks before anything constrains a plan. They never change a plan.
Every threshold is Stride policy, not a validated injury threshold.
"""
import logging
from datetime import datetime, timedelta

from app.athlete_clock import today as athlete_today
from app.core.load_policy import training_level
from app.core.time_budget import estimated_minutes
from app.models.activity import Activity, runs_only

logger = logging.getLogger('stride.aerobic_hours')
MI = 1609.34
HOURS_TOLERANCE = 0.05  # planned easy pace is a range; absorb estimate error
SESSION_GROWTH = 0.10
SESSION_STEP_MILES = 1.0
SESSION_STEP_MINUTES = 10.0
SUSTAINED_WEEKS = 6


def _weekly(user_id: int, db, weeks: int, today) -> list[dict]:
    monday = today - timedelta(days=today.weekday())
    starts = [monday - timedelta(weeks=i) for i in range(weeks, 0, -1)]
    totals = {s: {'week_start': s.isoformat(), 'miles': 0.0, 'seconds': 0.0} for s in starts}
    acts = (db.query(Activity.date, Activity.distance_meters, Activity.duration_seconds)
            .filter(Activity.user_id == user_id, runs_only(),
                    Activity.date >= datetime.combine(starts[0], datetime.min.time()),
                    Activity.date < datetime.combine(monday, datetime.min.time())).all())
    for when, meters, seconds in acts:
        day = when.date()
        week = totals.get(day - timedelta(days=day.weekday()))
        if week:
            week['miles'] += (meters or 0) / MI
            week['seconds'] += max(0.0, seconds or 0)
    return [totals[s] for s in starts]


def history(user_id: int, db, today=None) -> dict:
    """R1: hours baseline and level, plus R7's display-only figures (peak and sustainable hours)."""
    today = today or athlete_today()
    weeks = _weekly(user_id, db, 104, today)
    hours = [w['seconds'] / 3600 for w in weeks]
    miles = [w['miles'] for w in weeks]
    baseline = sum(hours[-4:]) / 4
    level, _ = training_level(baseline, hours[-4:])
    # Highest weekly hours held for 6 straight weeks: the lowest week of the best 6-week run.
    sustained = max((min(hours[i:i + SUSTAINED_WEEKS]) for i in range(len(hours) - SUSTAINED_WEEKS + 1)), default=0.0)
    return {'hours_baseline': round(baseline, 2), 'hours_level': round(level, 2),
            'miles_baseline': round(sum(miles[-4:]) / 4, 1), 'peak_hours': round(max(hours, default=0), 2),
            'peak_miles': round(max(miles, default=0), 1), 'sustainable_hours': round(sustained, 2)}


def longest_recent(user_id: int, db, today=None) -> dict:
    """R3 reference: the longest run in distance and in moving time over the last 30 days, races excluded."""
    today = today or athlete_today()
    since = datetime.combine(today - timedelta(days=30), datetime.min.time())
    rows = (db.query(Activity.distance_meters, Activity.duration_seconds, Activity.event_type)
            .filter(Activity.user_id == user_id, runs_only(), Activity.date >= since,
                    Activity.date < datetime.combine(today, datetime.min.time())).all())
    rows = [r for r in rows if r.event_type != 'race']
    if not rows:
        return {'miles': None, 'minutes': None}
    return {'miles': round(max((r.distance_meters or 0) / MI for r in rows), 1),
            'minutes': round(max((r.duration_seconds or 0) / 60 for r in rows))}


def session_caps(longest: dict) -> dict:
    miles, minutes = longest.get('miles'), longest.get('minutes')
    return {'miles': None if not miles else round(max(miles * (1 + SESSION_GROWTH), miles + SESSION_STEP_MILES), 1),
            'minutes': None if not minutes else round(max(minutes * (1 + SESSION_GROWTH), minutes + SESSION_STEP_MINUTES))}


def shadow(plan_data: dict, user_id: int, db, easy_pace: float) -> dict:
    """What hours budgets and the session guard would say about this block. Never changes it."""
    load = plan_data.get('load') or {}
    hist = history(user_id, db)
    longest = longest_recent(user_id, db)
    mile_level = load.get('training_level') or load.get('baseline') or 0
    budgets = load.get('weekly_budgets') or []
    weeks_out, notes = [], []
    reference = dict(longest)
    for i, week in enumerate(plan_data.get('weeks', [])):
        days = [d for d in week['days'] if d.get('type') not in ('rest',) and (d.get('distance_miles') or 0) > 0]
        minutes = sum(estimated_minutes(d, easy_pace) for d in days if d['type'] != 'race')
        factor = (budgets[i] / mile_level) if i < len(budgets) and mile_level else None
        # Same growth/mode factor the mile budget got, so a deload week (R4) is cut in both units.
        budget_hours = round(hist['hours_level'] * factor, 2) if factor and hist['hours_level'] else None
        over = budget_hours is not None and minutes > budget_hours * 60 * (1 + HOURS_TOLERANCE)
        caps = session_caps(reference)
        flagged = []
        for d in days:
            if d['type'] == 'race':
                continue
            mins = estimated_minutes(d, easy_pace)
            if (caps['miles'] and d['distance_miles'] > caps['miles'] + 0.01) or (caps['minutes'] and mins > caps['minutes'] + 0.5):
                flagged.append({'date': d['date'], 'title': d.get('title'), 'miles': d['distance_miles'], 'minutes': round(mins)})
        weeks_out.append({'week_number': week.get('week_number', i + 1), 'planned_minutes': round(minutes),
                          'hours_budget': budget_hours, 'would_bind': over, 'session_caps': caps,
                          'sessions_over_cap': flagged})
        if over:
            notes.append(f"Week {week.get('week_number', i + 1)}: ≈{minutes / 60:.1f} h planned vs a {budget_hours:.1f} h time budget "
                         "(not enforced yet).")
        for f in flagged:
            notes.append(f"{f['date']}: {f['title']} ({f['miles']:g} mi, ≈{f['minutes']} min) is over 10% longer than your longest "
                         "run of the last 30 days (not enforced yet).")
        # Within a block, week 2 may step once more from week 1's planned longest run.
        longest_planned = max(days, key=lambda d: d['distance_miles'], default=None)
        if longest_planned and longest_planned['type'] != 'race':
            reference = {'miles': max(reference['miles'] or 0, longest_planned['distance_miles']),
                         'minutes': max(reference['minutes'] or 0, round(estimated_minutes(longest_planned, easy_pace)))}
    # R7: ramp headroom in both units (shadow only): the closer-to-peak unit would set the slower rate.
    headroom = {'miles': round(hist['miles_baseline'] / hist['peak_miles'], 2) if hist['peak_miles'] else None,
                'hours': round(hist['hours_baseline'] / hist['peak_hours'], 2) if hist['peak_hours'] else None}
    result = hist | {'longest_30d': longest, 'weeks': weeks_out, 'headroom': headroom, 'notes': notes, 'enforced': False}
    if notes:
        logger.info('Shadow hours budget would bind (%d notes)', len(notes))
    return result
