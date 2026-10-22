"""Weekly training-load policy: how many miles each week of a block should hold.

Three separate quantities (they were previously blurred together):

- **baseline** — demonstrated recent training: the last four completed calendar weeks from
  completed runs, divided over the whole window (rest/interrupted days count),
  so a few big days after a break can't inflate it.
- **budget** — the permitted load for each week of the next block.
- **destination** — the long-term target (e.g. a mileage goal of 75 mpw). It sets
  direction and a cap; it is never prescribed immediately.

Historical peak changes *how fast* load may return (an athlete rebuilding toward
a previous peak may ramp faster than one in new territory) but is not a ceiling.

The ramp rates below are Stride policy drawn from docs/training-principles.md and
CLAUDE.md (≤10% for beginners and comebacks, faster only while well below a
previous peak). They are conservative defaults, not universal science.
"""

from app.core.experience import experienced, experience_policy
from dataclasses import dataclass, field
import math

# Per-block growth (applied as half in week 1, full in week 2 of a 2-week block)
RATE_BEGINNER = 0.10
RATE_INTERMEDIATE = 0.12
RATE_COMEBACK = 0.10
RATE_ADVANCED_FAR_BELOW_PEAK = 0.20  # baseline < 50% of a previous peak
RATE_ADVANCED_BELOW_PEAK = 0.15  # 50-75% of peak
RATE_ADVANCED_NEAR_PEAK = 0.10  # ≥75% of peak, or beyond it (new territory)

START_MILES_NO_HISTORY = 10.0  # first block for someone with no usable history
MIN_HISTORY_MILES = 5.0  # below this, history isn't a usable baseline
GENERAL_FITNESS_DESTINATION = 30.0  # general-fitness goals stop growing here
REDUCE_STEP = 0.10  # when the destination is below current load, come down 10%/week
DELOAD_FACTOR = 0.75
HOLD_FACTOR = 1.0
REDUCE_FACTOR = 0.85
RECOVERY_FACTOR = 0.70


@dataclass
class LoadPlan:
    baseline: float
    destination: float | None
    mode: str  # start | build | hold | reduce | deload | recovery
    weekly_budgets: list[float]
    rate: float
    reasons: list[str] = field(default_factory=list)
    recent_week_miles: float | None = None
    planning_anchor: float | None = None
    training_level: float | None = None

    def to_dict(self) -> dict:
        return {
            "baseline": self.baseline,
            "destination": self.destination,
            "mode": self.mode,
            "weekly_budgets": self.weekly_budgets,
            "rate": self.rate,
            "reasons": self.reasons,
            "recent_week_miles": self.recent_week_miles,
            "planning_anchor": self.planning_anchor,
            "training_level": self.training_level,
        }


def _finite(x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) and x > 0 else 0.0


def ramp_rate(baseline: float, peak: float, experience: str, goal_type: str) -> float:
    if goal_type == "comeback":
        return RATE_COMEBACK
    if experienced(experience) and peak > 0:
        headroom = baseline / peak
        if headroom < 0.5:
            return RATE_ADVANCED_FAR_BELOW_PEAK
        if headroom < 0.75:
            return .18 if experience == "expert" else RATE_ADVANCED_BELOW_PEAK
        return .12 if experience == "expert" else RATE_ADVANCED_NEAR_PEAK
    if experience == "intermediate":
        return RATE_INTERMEDIATE
    return RATE_BEGINNER


LEVEL_CAP = 1.35  # the training level never runs more than 35% ahead of the 4-week average
SPIKE_RATIO = 1.20  # a latest week this far above the one before it is a spike, not a level


def training_level(baseline: float, completed_weeks: list[float] | None) -> tuple[float, bool]:
    """Where the athlete is actually training now, and whether last week was a down week.

    The 4-week average includes any deload week, so building from it after every deload
    nets to zero growth (a beginner deloads every third week). When the last four weeks
    contain a down week, the level is the average of the full-volume weeks instead.
    Everything else keeps the 4-week average: a missed (zero) week is a break, not a
    deload, and a latest week far above the one before it is a spike, not a level.
    """
    weeks = [_finite(w) for w in (completed_weeks or [])][-4:]
    if len(weeks) < 4 or any(w <= 0 for w in weeks):
        return baseline, False
    down = []
    for i, miles in enumerate(weeks):
        history = [_finite(w) for w in (completed_weeks or [])][:-4] + weeks[:i]
        reference = max(history[-3:], default=0)
        down.append(reference > 0 and miles <= reference * DOWN_WEEK_RATIO)
    if not any(down):
        return baseline, False
    loaded = [w for w, is_down in zip(weeks, down) if not is_down]
    if len(loaded) >= 2 and loaded[-1] > loaded[-2] * SPIKE_RATIO:
        loaded = loaded[:-1]
    level = sum(loaded) / len(loaded) if loaded else baseline
    return round(min(max(baseline, level), baseline * LEVEL_CAP), 1), down[-1]


def default_destination(goal_type: str, target_weekly_mileage: float | None) -> float | None:
    if goal_type == "mileage" and _finite(target_weekly_mileage):
        return round(_finite(target_weekly_mileage), 1)
    if goal_type == "general":
        return GENERAL_FITNESS_DESTINATION
    return None  # race goals: growth is limited by demonstrated training each block


# Consecutive loaded weeks before considering a deload. Novice defaults retained;
# advanced uses the longer end of the existing 5-7-week guidance, per athlete preference.
DELOAD_AFTER_WEEKS = {level: experience_policy(level).deload_after for level in ("beginner","intermediate","advanced","expert")}
DOWN_WEEK_RATIO = 0.85  # a lighter week versus the recent high resets accumulated load


def deload_due(weekly_miles: list[float], experience: str) -> tuple[bool, str]:
    """From completed weekly mileage (oldest → newest, full weeks only), is a deload due?
    Counts consecutive loaded weeks since the last naturally lighter week, so plan
    regeneration can't skip or invent a deload."""
    limit = DELOAD_AFTER_WEEKS.get(experience, 3)
    streak = 0
    for i, miles in enumerate(weekly_miles):
        prev = weekly_miles[max(0, i - 3):i]
        reference = max(prev, default=0)
        if miles <= 0 or (reference > 0 and miles <= reference * DOWN_WEEK_RATIO):
            streak = 0
        else:
            streak += 1
    if streak >= limit:
        return True, f"{streak} sustained loaded weeks without a meaningful lighter week: including a recovery week."
    return False, f"{streak} loaded week{'s' if streak != 1 else ''} since your last meaningful lighter week; no automatic deload needed."


def plan_load(
    baseline: float,
    peak: float,
    experience: str,
    goal_type: str,
    num_weeks: int,
    target_weekly_mileage: float | None = None,
    assessment: str | None = None,  # build | hold | reduce | recovery (from block assessment)
    deload_week: int | None = None,  # 0-based week index to deload, if a deload is due
    reported_mileage: float | None = None,  # athlete's own estimate when history is missing
    completed_weeks: list[float] | None = None,  # oldest -> newest, full calendar weeks incl zero
) -> LoadPlan:
    baseline = round(_finite(baseline), 1)
    peak = _finite(peak)
    destination = default_destination(goal_type, target_weekly_mileage)
    rate = ramp_rate(baseline, peak, experience, goal_type)
    reasons: list[str] = []

    if baseline < MIN_HISTORY_MILES:
        reported = _finite(reported_mileage)
        start = max(reported, START_MILES_NO_HISTORY) if reported else START_MILES_NO_HISTORY
        if destination:
            start = min(start, destination)
        reasons.append(
            f"Not enough recent running to measure a baseline ({baseline:g} mi/week over 4 weeks); "
            f"starting at {start:g} mi/week."
        )
        return LoadPlan(baseline, destination, "start", [round(start, 1)] * num_weeks, rate, reasons)

    mode = "build"
    level, after_down_week = training_level(baseline, completed_weeks)
    # +½rate, +rate, then hold. Straight after a down week, first return to the pre-deload
    # level, then grow: the week after a deload never jumps ahead of where training was.
    growth = [rate * min(w + (0 if after_down_week else 1), 2) / 2 for w in range(num_weeks)]
    budgets = [level * (1 + g) for g in growth]
    recent = _finite(completed_weeks[-1]) if completed_weeks else None
    anchor = baseline
    recent_build = False
    # For an experienced mileage builder, a repeatable recent high is evidence
    # that the rolling average can lag current training. Do not chase one spike.
    history = (completed_weeks or [])[-4:]
    repeatable = sum(_finite(w) >= (recent or 0) * .8 for w in history) >= 2
    if (experienced(experience) and goal_type == "mileage" and assessment not in {"hold", "reduce", "recovery"}
            and deload_week is None and recent and len(history) == 4 and all(_finite(w) > 0 for w in history)
            and baseline < recent <= baseline * 1.35 and repeatable):
        anchor = recent
        next_miles = round((recent + min(2.0, recent * .05)) * 2) / 2
        budgets = [next_miles] * num_weeks  # repeat, don't staircase on unobserved recovery
        rate = next_miles / recent - 1
        recent_build = True
    reasons.append(f"Baseline {baseline:g} mi/week (4-week average of completed runs).")
    if level > baseline and not recent_build:
        reasons.append(f"Training level {level:g} mi/week (your last two full-volume weeks; down weeks don't reset it).")

    if recent_build:
        reasons.append(f"Last full week {recent:g} mi, supported by another comparable recent week. "
                       f"Plan {budgets[0]:g} mi/week, then repeat it while your run feedback guides adjustments.")

    if assessment in ("hold", "reduce", "recovery"):
        factor = {"hold": HOLD_FACTOR, "reduce": REDUCE_FACTOR, "recovery": RECOVERY_FACTOR}[assessment]
        # Holding keeps the current training level; reducing or recovering after fatigue
        # starts from the more conservative 4-week average (fail safe).
        budgets = [(level if assessment == "hold" else baseline) * factor] * num_weeks
        mode = assessment
        reasons.append(
            {"hold": "Last block's assessment says consolidate: holding volume steady.",
             "reduce": "Last block's assessment says ease off: volume reduced ~15%.",
             "recovery": "Recovery block: volume reduced ~30%."}[assessment]
        )

    if destination is not None:
        if level > destination * 1.05:
            # Destination below current load: come down gradually, never below destination
            budgets = [max(destination, level * (1 - REDUCE_STEP) ** (w + 1)) for w in range(num_weeks)]
            mode = "reduce"
            reasons.append(f"Your goal of {destination:g} mi/week is below current volume; easing down toward it.")
        elif level >= destination * 0.97:
            budgets = [min(b, destination) for b in budgets] if mode != "build" else [destination] * num_weeks
            mode = "hold" if mode == "build" else mode
            reasons.append(f"At your {destination:g} mi/week goal: holding there.")
        elif any(b > destination for b in budgets):
            budgets = [min(b, destination) for b in budgets]
            reasons.append(f"Capped at your {destination:g} mi/week goal.")
        else:
            reasons.append(f"Working toward your {destination:g} mi/week goal; not prescribed all at once.")

    if deload_week is not None and 0 <= deload_week < num_weeks:
        budgets[deload_week] = level * DELOAD_FACTOR
        # The week after a deload returns to the training level rather than jumping ahead
        for w in range(deload_week + 1, num_weeks):
            budgets[w] = min(budgets[w], level)
        mode = "deload" if mode == "build" else mode
        reasons.append(f"Deload in week {deload_week + 1}: ~{1 - DELOAD_FACTOR:.0%} less volume to absorb training.")

    if mode == "build" and not recent_build:
        reasons.insert(1, f"Building up to {rate:.0%} over the block ({budgets[0]:.0f} → {budgets[-1]:.0f} mi/week).")
    return LoadPlan(baseline, destination, mode, [round(b, 1) for b in budgets], rate, reasons, recent, anchor, level)
