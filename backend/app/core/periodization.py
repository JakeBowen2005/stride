"""Race-date periodization: which training phase each week is in.

Phases are counted backwards from race day (CLAUDE.md "Periodization"):
    base → build → peak → taper → race week → post-race recovery

Goals without a race date (mileage, general fitness, comeback) stay in a fluid
"general" phase — no rigid blocks, just the conservative mileage ramp.

Lengths come from docs/*-training-science.md and docs/ultra-training-science.md.
Everything here is pure (no DB) so it can be unit tested directly.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

RACE_DISTANCE_MILES = {
    "5k": 3.10686,
    "10k": 6.21371,
    "half": 13.1094,
    "marathon": 26.2188,
    "50k": 31.0686,
    "50mi": 50.0,
    "100k": 62.1371,
    "100mi": 100.0,
}

ULTRA_DISTANCES = {"50k", "50mi", "100k", "100mi"}

# Taper length in days before race day (race week included)
TAPER_DAYS = {
    "5k": 7, "10k": 10, "half": 10, "marathon": 14,
    "50k": 10, "50mi": 14, "100k": 14, "100mi": 21,
}

# Weeks of peak (race-specific) and build work immediately before the taper
PEAK_WEEKS = {"5k": 3, "10k": 4, "half": 4, "marathon": 5, "50k": 4, "50mi": 5, "100k": 5, "100mi": 6}
BUILD_WEEKS = {"5k": 4, "10k": 4, "half": 5, "marathon": 5, "50k": 4, "50mi": 5, "100k": 6, "100mi": 7}

# Easy weeks after the race before workouts return (reverse taper)
RECOVERY_WEEKS = {"5k": 1, "10k": 1, "half": 1, "marathon": 2, "50k": 2, "50mi": 3, "100k": 3, "100mi": 4}

# Volume multipliers vs. current training volume, for taper weeks counted
# from the furthest-out taper week to the week before race week.
TAPER_VOLUME = {1: [], 2: [0.75], 3: [0.8, 0.65]}
RACE_WEEK_VOLUME = 0.55  # race week, excluding the race itself
RECOVERY_VOLUME = [0.45, 0.6, 0.7, 0.8]  # post-race week 1, 2, 3, 4

# Ultra fueling target (g carbs/hr) practiced on long runs, by phase
FUELING_G_PER_HR = {"base": 45, "build": 60, "peak": 75, "taper": 75}

# Longest single long run (minutes) by ultra distance — docs/ultra-training-science.md §2.5
ULTRA_LONG_RUN_CAP_MIN = {"50k": 225, "50mi": 330, "100k": 360, "100mi": 390}
# Long run share of weekly volume for ultras (bigger than road plans)
ULTRA_LONG_RUN_SHARE = {"50k": 0.32, "50mi": 0.34, "100k": 0.35, "100mi": 0.35}


@dataclass
class WeekPhase:
    phase: str  # general | base | build | peak | taper | race_week | recovery
    weeks_to_race: int | None = None  # 0 = race week
    volume_multiplier: float | None = None  # None = normal ramp
    max_workouts: int | None = None  # cap on quality sessions this week
    race_date: date | None = None  # set on race week
    back_to_back: bool = False  # ultra B2B long-run weekend
    fueling_g_per_hr: int | None = None
    label: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "label": self.label,
            "weeks_to_race": self.weeks_to_race,
            "back_to_back": self.back_to_back,
            "fueling_g_per_hr": self.fueling_g_per_hr,
            "notes": self.notes,
        }


def is_ultra(distance: str | None) -> bool:
    return distance in ULTRA_DISTANCES


def week_phase(
    week_start: date,
    goal_type: str,
    distance: str | None,
    race_date: date | None,
) -> WeekPhase:
    """Phase for the Monday-start week beginning `week_start`."""
    if goal_type != "race" or not distance or not race_date:
        return WeekPhase(phase="general", label="General build")

    week_end = week_start + timedelta(days=6)

    # After the race: reverse taper
    if week_start > race_date:
        weeks_after = (week_start - race_date).days // 7  # 0 = first full week after
        n_recovery = RECOVERY_WEEKS.get(distance, 1)
        if weeks_after < n_recovery:
            mult = RECOVERY_VOLUME[min(weeks_after, len(RECOVERY_VOLUME) - 1)]
            return WeekPhase(
                phase="recovery",
                volume_multiplier=mult,
                max_workouts=0,
                label=f"Post-race recovery (week {weeks_after + 1} of {n_recovery})",
                notes=["Recovery after racing: easy running only. Workouts return once your legs feel normal again."],
            )
        return WeekPhase(phase="general", label="General build", notes=["Race is done — set your next goal."])

    # Race week
    if week_start <= race_date <= week_end:
        return WeekPhase(
            phase="race_week",
            weeks_to_race=0,
            volume_multiplier=RACE_WEEK_VOLUME,
            max_workouts=1,
            race_date=race_date,
            fueling_g_per_hr=FUELING_G_PER_HR["taper"] if is_ultra(distance) else None,
            label="Race week",
            notes=["Race week: short, sharp, and rested. Nothing you do this week makes you fitter — it only makes you fresher."],
        )

    weeks_to_race = (race_date - week_start).days // 7  # ≥ 1 here
    taper_weeks = max(1, round(TAPER_DAYS.get(distance, 7) / 7))
    pre_race_taper = TAPER_VOLUME.get(taper_weeks, [0.8, 0.65])  # weeks before race week

    if weeks_to_race <= len(pre_race_taper):
        idx = len(pre_race_taper) - weeks_to_race
        return WeekPhase(
            phase="taper",
            weeks_to_race=weeks_to_race,
            volume_multiplier=pre_race_taper[idx],
            max_workouts=2 if weeks_to_race >= 2 else 1,
            fueling_g_per_hr=FUELING_G_PER_HR["taper"] if is_ultra(distance) else None,
            label=f"Taper — {weeks_to_race} week{'s' if weeks_to_race > 1 else ''} to race",
            notes=["Taper: volume comes down, intensity stays. Keep the legs sharp, let fatigue drain."],
        )

    weeks_before_taper = weeks_to_race - len(pre_race_taper)  # 1 = last week before taper
    peak = PEAK_WEEKS.get(distance, 4)
    build = BUILD_WEEKS.get(distance, 4)

    if weeks_before_taper <= peak:
        phase = "peak"
    elif weeks_before_taper <= peak + build:
        phase = "build"
    else:
        phase = "base"

    wp = WeekPhase(
        phase=phase,
        weeks_to_race=weeks_to_race,
        label=f"{phase.title()} — {weeks_to_race} week{'s' if weeks_to_race != 1 else ''} to race",
    )
    if is_ultra(distance):
        wp.fueling_g_per_hr = FUELING_G_PER_HR[phase]
        # Back-to-back weekends every other week in build/peak, never in the last peak week
        wp.back_to_back = phase in ("build", "peak") and weeks_before_taper > 1 and weeks_to_race % 2 == 0
    if phase == "base":
        wp.notes.append("Base phase: build the aerobic engine. Mostly easy miles, one or two controlled quality days.")
    elif phase == "build":
        wp.notes.append("Build phase: raise the ceiling — threshold and VO2 work while volume climbs.")
    else:
        wp.notes.append("Peak phase: race-specific work. Sessions look more and more like race day.")
    return wp


def plan_phases(
    start_date: date,
    num_weeks: int,
    goal_type: str,
    distance: str | None,
    race_date: date | None,
) -> list[WeekPhase]:
    return [
        week_phase(start_date + timedelta(days=7 * w), goal_type, distance, race_date)
        for w in range(num_weeks)
    ]


# ── Readiness gates ─────────────────────────────────────────────

# (min longest run ever, min current weekly miles, min weeks to race)
READINESS = {
    "50k": (13.1, 25, 10),
    "50mi": (20.0, 30, 14),
    "100k": (26.2, 35, 16),
}


def check_readiness(
    distance: str | None,
    race_date: date | None,
    longest_run_miles: float,
    current_weekly_miles: float,
    today: date | None = None,
) -> dict:
    """Is this race goal realistic and safe? Fail safe: suggest a stepping stone instead.

    Returns {"ready": bool, "reasons": [...], "suggestion": str | None}.
    """
    today = today or date.today()
    reasons: list[str] = []
    suggestion = None
    weeks = (race_date - today).days / 7 if race_date else None

    if race_date and race_date < today:
        return {"ready": False, "reasons": ["Race date is in the past."], "suggestion": None}

    if distance == "100mi":
        ran_ultra = longest_run_miles >= 49
        if ran_ultra:
            if weeks is not None and weeks < 20:
                reasons.append(f"Only {weeks:.0f} weeks to race — a 100-mile build needs at least 20.")
        else:
            if current_weekly_miles < 40:
                reasons.append(f"Current volume is {current_weekly_miles:.0f} mpw — first 100s need a 40+ mpw base.")
            if weeks is not None and weeks < 24:
                reasons.append(
                    f"Only {weeks:.0f} weeks to race without a prior 50 mi/100K — needs 24+ weeks."
                )
            if reasons:
                suggestion = "Run a 50-mile or 100K first (or pick a race 6+ months out). It's the standard stepping stone to 100."
    elif distance in READINESS:
        min_long, min_mpw, min_weeks = READINESS[distance]
        if longest_run_miles < min_long:
            reasons.append(f"Longest run so far is {longest_run_miles:.1f} mi — aim for {min_long:g}+ before a {distance}.")
        if current_weekly_miles < min_mpw:
            reasons.append(f"Current volume is {current_weekly_miles:.0f} mpw — {distance} training starts from {min_mpw}+ mpw.")
        if weeks is not None and weeks < min_weeks:
            reasons.append(f"Only {weeks:.0f} weeks to race — a {distance} build needs {min_weeks}+.")
        if reasons:
            step_down = {"50k": "marathon", "50mi": "50K", "100k": "50-miler"}[distance]
            suggestion = f"Build up with a {step_down} first, or choose a later race."
    elif distance and weeks is not None:
        min_weeks = {"5k": 4, "10k": 6, "half": 8, "marathon": 12}.get(distance, 4)
        if weeks < min_weeks:
            reasons.append(f"Only {weeks:.0f} weeks to race — tight for a full {distance} build; the plan will be mostly taper.")

    return {"ready": not reasons, "reasons": reasons, "suggestion": suggestion}
