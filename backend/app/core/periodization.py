"""Race-date-aware periodization.

The plan engine generates rolling 2-3 week blocks, so it never sees a whole
training cycle at once. What it can do is ask, for any given week: how far out
is the race, and what does that imply about volume and intensity?

Sources: `docs/marathon-training-science.md` (taper research), Pfitzinger,
Daniels, and Jake's own Feb 2026 block which tapered 70 -> 45 -> 38 -> race.
"""

from __future__ import annotations

from datetime import date

# How many weeks of taper each race distance warrants.
#
# Marathon: PMC 2021 found strict 3-week tapers associated with finishes
# 5min 32sec (2.6%) faster. Shorter races need far less -- there is much less
# accumulated fatigue to shed and sharpness is lost quickly.
TAPER_WEEKS = {
    "marathon": 3,
    "half": 2,
    "10k": 1,
    "5k": 1,
}

# Volume as a fraction of recent peak, indexed by weeks remaining before
# race week. Bosquet's meta-analysis is emphatic that FREQUENCY and INTENSITY
# are maintained -- it is volume that comes down. Sessions get shorter, not
# fewer, and never easier.
TAPER_VOLUME = {
    "marathon": {3: 0.80, 2: 0.60, 1: 0.40},
    "half": {2: 0.75, 1: 0.50},
    "10k": {1: 0.60},
    "5k": {1: 0.60},
}

# Long run as a fraction of the normal allocation during taper.
TAPER_LONG_RUN = {
    "marathon": {3: 0.75, 2: 0.55, 1: 0.35},
    "half": {2: 0.70, 1: 0.45},
    "10k": {1: 0.60},
    "5k": {1: 0.55},
}

PHASE_BASE = "base"
PHASE_BUILD = "build"
PHASE_SPECIFIC = "specific"
PHASE_TAPER = "taper"
PHASE_RACE_WEEK = "race_week"
PHASE_OFFSEASON = "offseason"


def parse_race_date(race_date: str | date | None) -> date | None:
    """Accept an ISO string or a date, return a date or None."""
    if race_date is None:
        return None
    if isinstance(race_date, date):
        return race_date
    try:
        return date.fromisoformat(str(race_date)[:10])
    except (ValueError, TypeError):
        return None


def weeks_until_race(race_day: date | None, week_start: date) -> int | None:
    """Whole weeks from the START of a training week to race day.

    0 means race day falls inside this week. Negative means the race has
    already happened. None means no race is scheduled.
    """
    if race_day is None:
        return None
    delta_days = (race_day - week_start).days
    if delta_days < 0:
        return -1
    return delta_days // 7


def taper_weeks_for(distance: str | None) -> int:
    return TAPER_WEEKS.get((distance or "").lower(), 2)


def determine_phase(
    weeks_out: int | None,
    distance: str | None,
    current_mileage: float,
    has_workouts: bool,
) -> str:
    """Classify a training week by how far it sits from race day."""
    if weeks_out is None:
        # No race scheduled. Base if there's no volume yet, otherwise the
        # athlete is just training.
        return PHASE_OFFSEASON if has_workouts else PHASE_BASE
    if weeks_out < 0:
        return PHASE_OFFSEASON
    if weeks_out == 0:
        return PHASE_RACE_WEEK

    taper = taper_weeks_for(distance)
    if weeks_out <= taper:
        return PHASE_TAPER
    if not has_workouts:
        return PHASE_BASE
    if weeks_out <= taper + 6:
        return PHASE_SPECIFIC
    if weeks_out <= taper + 16:
        return PHASE_BUILD
    return PHASE_BASE


def taper_factors(weeks_out: int | None, distance: str | None) -> tuple[float | None, float | None]:
    """(volume_factor, long_run_factor) for a taper week, or (None, None).

    Race week is handled separately -- it is not a scaled version of a normal
    week, it is a race with a few shakeout runs around it.
    """
    if weeks_out is None or weeks_out <= 0:
        return None, None
    dist = (distance or "").lower()
    vol = TAPER_VOLUME.get(dist, {}).get(weeks_out)
    lr = TAPER_LONG_RUN.get(dist, {}).get(weeks_out)
    return vol, lr


def race_week_volume_factor(distance: str | None) -> float:
    """Race week volume as a fraction of recent peak, race itself excluded."""
    return 0.30 if (distance or "").lower() in ("marathon", "half") else 0.40


def phase_note(phase: str, weeks_out: int | None, distance: str | None) -> str | None:
    """A short explanation of what this phase is for, for the plan notes."""
    label = (distance or "race").upper() if distance else "race"

    if phase == PHASE_RACE_WEEK:
        return (
            f"Race week. Volume is low, but keep the frequency and keep a little "
            f"sharpness — short efforts at race pace a few days out. The fitness is "
            f"already banked; the only thing left to do is arrive fresh."
        )
    if phase == PHASE_TAPER:
        return (
            f"Taper — {weeks_out} week(s) to your {label}. Volume comes down, intensity "
            f"and frequency do NOT. Research is consistent on this: runners who cut "
            f"training days taper worse than runners who shorten sessions. You will feel "
            f"sluggish and doubt the plan around now. That is the taper working."
        )
    if phase == PHASE_SPECIFIC:
        return (
            f"Race-specific phase — {weeks_out} weeks out. Workouts now look like the "
            f"race: sustained efforts at goal pace, long runs carrying race-pace blocks. "
            f"This is where the {label} is actually built."
        )
    if phase == PHASE_BUILD:
        return (
            f"Build phase — {weeks_out} weeks out. Threshold work is the priority and "
            f"mileage keeps climbing. Race-specific sharpening comes later; right now "
            f"you are raising the ceiling everything else sits under."
        )
    if phase == PHASE_BASE:
        return (
            "Base phase. Easy volume and consistency. No amount of clever workouts "
            "substitutes for the aerobic foundation being built right now."
        )
    return None
