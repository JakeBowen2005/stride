"""Day builders for race weeks and ultra-specific training.

Kept separate from plan_engine.py so the standard week builder stays readable.
All functions return day dicts in the same shape plan_engine uses:
    {date, day, type, title, description, purpose, distance_miles, warmup, cooldown}
"""

from datetime import date, timedelta

from app.core.pacing import format_pace, pace_range
from app.core.periodization import (
    RACE_DISTANCE_MILES,
    ULTRA_LONG_RUN_CAP_MIN,
    ULTRA_LONG_RUN_SHARE,
    WeekPhase,
    is_ultra,
)

from app.core.plan_validator import HARD_TYPES  # noqa: F401  (re-exported for callers/tests)

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

RACE_LABELS = {
    "5k": "5K", "10k": "10K", "half": "Half Marathon", "marathon": "Marathon",
    "50k": "50K", "50mi": "50 Mile", "100k": "100K", "100mi": "100 Mile",
}


def _round_half(d: float) -> float:
    return round(d * 2) / 2


def _fmt_duration(minutes: float) -> str:
    minutes = int(round(minutes / 5) * 5)
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h else f"{m}min"


def _day(day_date: date, type_: str, title: str, description: str, purpose: str,
         miles: float, warmup: str | None = None, cooldown: str | None = None) -> dict:
    return {
        "date": day_date.isoformat(), "day": DAY_NAMES[day_date.weekday()],
        "type": type_, "title": title, "description": description, "purpose": purpose,
        "distance_miles": miles, "warmup": warmup, "cooldown": cooldown,
    }


def _rest(day_date: date, why: str = "Full rest. Recovery is when your body adapts and gets stronger.") -> dict:
    return _day(day_date, "rest", "Rest Day", why, "Physical and mental recovery.", 0)


# ── Race week ───────────────────────────────────────────────────

def _sharpener(distance: str, paces: dict) -> dict:
    """Short race-week session: a few minutes at race pace to stay sharp, nothing that tires you."""
    grp = paces.get("goal_race_pace")
    thr = format_pace(paces["threshold_pace"])
    if distance == "5k":
        target = f"{format_pace(grp)}/mi (goal 5K pace)" if grp else "5K effort"
        return {"title": "Race-Week Sharpener: 4x400m", "miles": 5.0,
                "description": f"4x400m at {target} with 2min jog. Smooth and controlled, not all-out.",
                "warmup": "2mi easy + 4 strides", "cooldown": "1.5mi easy"}
    if distance == "10k":
        target = f"{format_pace(grp)}/mi (goal 10K pace)" if grp else "10K effort"
        return {"title": "Race-Week Sharpener: 3x1K", "miles": 5.5,
                "description": f"3x1K at {target} with 2min jog. Should feel easier than race day will.",
                "warmup": "2mi easy + 4 strides", "cooldown": "1.5mi easy"}
    if distance in ("half", "marathon"):
        label = "HMP" if distance == "half" else "MP"
        target = f"{format_pace(grp)}/mi (goal {label})" if grp else f"goal {label} effort"
        return {"title": f"Race-Week Sharpener: 2x1mi at {label}", "miles": 5.0,
                "description": f"2x1mi at {target} with 3min jog. Lock in the rhythm, then stop.",
                "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy"}
    # Ultras: no real speed, just wake the legs up
    return {"title": "Race-Week Sharpener: Steady Pickups", "miles": 5.0,
            "description": f"40-45min easy with 4x1min at steady effort (~{thr}/mi or slower), 2min easy between.",
            "warmup": None, "cooldown": None}


def _race_day(day_date: date, distance: str, target_time: float | None, paces: dict) -> dict:
    miles = RACE_DISTANCE_MILES[distance]
    label = RACE_LABELS[distance]
    if is_ultra(distance):
        desc = (
            "Start slower than feels right — low Zone 2 for the first quarter. Hike the steep climbs from the start. "
            "Fuel from the first 30 minutes: 60-90g carbs/hr, 300-600mg sodium/hr, drink to thirst. "
            "Treat problems early (hot spots, nausea, lows) — the race is a series of problems to solve."
        )
        if target_time:
            desc = f"Goal: {_fmt_duration(target_time / 60)}. " + desc
    else:
        pace = f"{format_pace(target_time / miles)}/mi" if target_time else "goal effort"
        desc = f"Goal pace {pace}. Start controlled — the first mile should feel easy. Warm up 10-15min + strides."
        if distance in ("half", "marathon"):
            desc += " Take carbs every 30-40min (marathon: 60-90g/hr). Even or slightly negative split."
    return _day(day_date, "race", f"RACE DAY — {label}", desc,
                "Everything has been building to this. Trust the training.", round(miles, 1))


def build_race_week(
    week_start: date, phase: WeekPhase, distance: str, target_time: float | None,
    target_mileage: float, rest_indices: list[int], paces: dict,
) -> list[dict]:
    race_idx = phase.race_date.weekday()
    race_miles = RACE_DISTANCE_MILES[distance]
    if target_time and not is_ultra(distance):
        # Sharpener at the exact goal pace (training paces are rounded to 5s)
        paces = {**paces, "goal_race_pace": target_time / race_miles}
    easy_range = pace_range(paces["easy_pace_low"], paces["easy_pace_high"])
    long_ultra = distance in ("50mi", "100k", "100mi")

    sharpener_idx = None
    for i in range(race_idx - 3, -1, -1):  # ≥3 days out, never right before the race
        if i not in rest_indices:
            sharpener_idx = i
            break
    sharp = _sharpener(distance, paces) if sharpener_idx is not None else None

    pre_race_easy = [i for i in range(race_idx) if i not in rest_indices and i != sharpener_idx and i != race_idx - 1]
    budget = max(target_mileage - (sharp["miles"] if sharp else 0) - 2.5, 0)
    per_easy = _round_half(min(max(budget / len(pre_race_easy), 2.0), 5.0)) if pre_race_easy else 0

    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        if i == race_idx:
            days.append(_race_day(d, distance, target_time, paces))
        elif i > race_idx:
            if i == race_idx + 1 or long_ultra:
                days.append(_rest(d, "Post-race rest. Walk, eat, sleep. No running."))
            else:
                days.append(_day(d, "easy", "Recovery Jog", f"20-30min very easy ({easy_range}/mi or slower), or rest if sore.",
                                 "Blood flow to speed recovery — no training stimulus.", 2.5))
        elif i == sharpener_idx:
            days.append(_day(d, "workout", sharp["title"], sharp["description"],
                             "Keeps the legs sharp during the taper without adding fatigue.",
                             sharp["miles"], sharp["warmup"], sharp["cooldown"]))
        elif i == race_idx - 1 and i not in rest_indices:
            days.append(_day(d, "easy", "Pre-Race Shakeout", f"15-20min very easy + 4x15sec relaxed strides. Lay out your gear tonight.",
                             "Loosen up and settle nerves. Nothing more.", 2.0))
        elif i in rest_indices:
            days.append(_rest(d))
        else:
            days.append(_day(d, "easy", "Easy Run", f"Easy and short. ({easy_range}/mi or slower)",
                             "Stay loose while the taper does its work.", per_easy))
    return days


# ── Ultra long runs, back-to-backs, hills ──────────────────────

def ultra_long_run(
    day_date: date, distance: str, target_mileage: float, phase: WeekPhase, paces: dict, terrain: str | None,
) -> dict:
    """Time-on-feet long run with fueling target."""
    trail = terrain in ("trail", "mountain")
    pace = paces["easy_pace_high"] * (1.12 if trail else 1.0)  # trail miles are slower
    miles = target_mileage * ULTRA_LONG_RUN_SHARE.get(distance, 0.33)
    cap = ULTRA_LONG_RUN_CAP_MIN.get(distance, 300)
    if phase.phase in ("taper", "race_week"):
        cap *= 0.6
    minutes = min(miles * pace / 60, cap)
    minutes = max(minutes, 75)
    miles = _round_half(minutes * 60 / pace)

    where = "on trail" if trail else "on road/flat"
    parts = [f"{_fmt_duration(minutes)} {where} (~{miles:g}mi), easy conversational effort."]
    if trail:
        parts.append("Power-hike grades steeper than ~15% — practice it, it's a race skill.")
    if phase.phase == "peak":
        parts.append("Run the middle third at goal race effort on race-like terrain.")
    if phase.fueling_g_per_hr:
        parts.append(f"Fuel {phase.fueling_g_per_hr}g carbs/hr + 300-600mg sodium/hr with race-day products.")
    title = "Ultra Long Run" if phase.phase != "peak" else "Race-Effort Long Run"
    return _day(day_date, "long_run", title, " ".join(parts),
                "Builds durability and time on feet, and trains the gut to take in fuel while running.", miles)


def back_to_back_day(day_date: date, main: dict, paces: dict, terrain: str | None,
                     before_main: bool = False) -> dict:
    """The shorter run of a back-to-back pair (~55% of the main long run).

    Normally the day after the long run; when that's a rest day it goes the day
    before, and tomorrow's long run becomes the run on tired legs.
    """
    trail = terrain in ("trail", "mountain")
    pace = paces["easy_pace_high"] * (1.12 if trail else 1.0)
    miles = _round_half(main["distance_miles"] * 0.55)
    minutes = miles * pace / 60
    if before_main:
        title = "Back-to-Back Long Run (day 1, shorter)"
        desc = (f"{_fmt_duration(minutes)} (~{miles:g}mi) easy, hiking the climbs. "
                "Tomorrow's long run starts on these tired legs — that's the point.")
    else:
        title = "Back-to-Back Long Run (day 2)"
        desc = f"{_fmt_duration(minutes)} (~{miles:g}mi) easy on tired legs. Keep it truly easy and hike the climbs."
    return _day(day_date, "long_run", title, desc,
                "Running on pre-fatigued legs mimics the back half of an ultra, with less damage than one huge run.",
                miles)


def hill_session(phase: str) -> dict:
    """Hill work in place of track intervals for trail/mountain ultras."""
    if phase == "base":
        return {"name": "Short Hill Repeats: 8x60sec",
                "structure": "8x60sec uphill at 5K effort on a 6-10% grade, jog back down.",
                "purpose": "Power and running economy with little impact. Strength work disguised as running.",
                "warmup": "2mi easy", "cooldown": "1.5mi easy", "total_miles": 6.0}
    if phase == "peak":
        return {"name": "Long Climbs + Controlled Descent",
                "structure": "4x6min uphill at half-marathon effort, jog down. Finish with 10min of controlled downhill running (quick, light steps).",
                "purpose": "Race-specific climbing, plus downhill conditioning that protects your quads on race day.",
                "warmup": "2mi easy", "cooldown": "1.5mi easy", "total_miles": 8.0}
    return {"name": "Long Hill Repeats: 6x3min",
            "structure": "6x3min uphill at 10K-half effort, jog down recovery.",
            "purpose": "VO2max work disguised as climbing. Raises the ceiling for sustained ascents.",
            "warmup": "2mi easy", "cooldown": "1.5mi easy", "total_miles": 7.0}


# ── Safety net ──────────────────────────────────────────────────
# The hard-day rule lives in plan_validator so generation and every later schedule
# mutation share one implementation.
from app.core.plan_validator import enforce_no_back_to_back_hard  # noqa: E402,F401
