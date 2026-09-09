"""2-week rolling plan generator.

Key principles:
- Progression in BOTH mileage and intensity across blocks
- Mileage ramp rate accounts for headroom (current vs peak)
- Threshold pace PROGRESSES toward goal (starts conservative, builds)
- Workout variety via date-seeded rotation
- Long runs have specific mile breakdowns (not just "steady finish")
- Marathon-first design: everything builds toward race day
"""

from datetime import date, timedelta

from app.core.pacing import format_pace, goal_paces, pace_range
from app.core.workouts import get_workout_library
from app.core.periodization import (
    PHASE_RACE_WEEK,
    PHASE_TAPER,
    determine_phase,
    parse_race_date,
    phase_note,
    race_week_volume_factor,
    taper_factors,
    weeks_until_race,
)
from app.core.workout_ladders import (
    get_workout_at_level,
    get_deload_workout,
    get_week2_variant,
    get_taper_workout,
    highest_non_mp_level,
    level_requires_mp,
)


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DEFAULT_WORKOUT_DAYS = [1, 3]
DEFAULT_LONG_RUN_DAY = 5
DEFAULT_REST_DAY = 6


def calculate_plan_params() -> dict:
    """Calculate start_date, end_date, and num_weeks for a plan.

    ALL plans start from Monday of the current week:
      - Mon-Wed (weekday <= 2): 2 weeks (rest of this week + 1 full week)
      - Thu-Sun (weekday >= 3): 3 weeks (rest of this week + 2 full weeks)
    Days before today in the current week show as non-prescribed.
    """
    today = date.today()
    weekday = today.weekday()  # 0=Mon, 6=Sun

    # Start from Monday of current week
    start_date = today - timedelta(days=weekday)
    if weekday <= 2:  # Mon-Wed
        num_weeks = 2  # rest of this week + 1 full week
    else:  # Thu-Sun
        num_weeks = 3  # rest of this week + 2 full weeks
    end_date = start_date + timedelta(days=num_weeks * 7 - 1)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "num_weeks": num_weeks,
        "first_prescribe_date": today,
    }


def _round_half(d: float) -> float:
    """Round distance to nearest 0.5 mile."""
    return round(d * 2) / 2


def _round_pace(seconds: float) -> float:
    """Round pace to nearest 5 seconds."""
    return round(seconds / 5) * 5


def generate_plan(
    goal_type: str,
    goal_distance: str | None,
    target_time_seconds: float | None,
    current_weekly_mileage: float,
    peak_weekly_mileage: float,
    experience_level: str,
    days_per_week: int,
    rest_days: list[str],
    long_run_day: str,
    easy_pace_seconds: float,
    current_workout_paces: dict | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    num_weeks: int = 2,
    first_prescribe_date: date | None = None,
    block_number: int = 1,
    progression_state: dict | None = None,
    race_date: str | None = None,
) -> dict:
    if start_date is None:
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start_date = today + timedelta(days=days_until_monday)

    if end_date is None:
        end_date = start_date + timedelta(days=num_weeks * 7 - 1)

    # Check if this block should be a deload
    is_deload = _is_deload_block(block_number, experience_level)

    week1_target, week2_target = _calculate_target_mileage(
        current_weekly_mileage, peak_weekly_mileage, experience_level, goal_type
    )

    # Pick which week inside this block gets deloaded. Never deload a week
    # that is already underway -- pushing a deload onto a week the athlete
    # has half-run just shortens the remaining days for no benefit.
    fpd_for_deload = first_prescribe_date or date.today()
    deload_week_idx = None
    if is_deload:
        for wk in range(num_weeks):
            wk_start_d = start_date + timedelta(days=wk * 7)
            if not (wk_start_d <= fpd_for_deload <= wk_start_d + timedelta(days=6)):
                deload_week_idx = wk
                break
        if deload_week_idx is None:
            is_deload = False

    goal_pace_data = None
    if goal_type == "race" and goal_distance and target_time_seconds:
        goal_pace_data = goal_paces(goal_distance, target_time_seconds)

    current_paces = _build_current_paces(
        easy_pace_seconds, current_workout_paces,
        goal_pace_data=goal_pace_data,
        current_mileage=current_weekly_mileage,
        goal_distance=goal_distance,
    )

    workout_lib = get_workout_library(current_paces, goal_distance or "5k", current_weekly_mileage)

    include_workouts = _should_include_workouts(
        current_weekly_mileage, goal_type, experience_level, goal_distance
    )
    workouts_per_week = _workouts_per_week(current_weekly_mileage, experience_level, goal_distance)

    # Strides keep leg speed and running economy alive during base building.
    # They are not a workout and cost nothing aerobically -- an experienced
    # athlete rebuilding volume should be doing them from week one.
    allow_strides = experience_level in ("advanced", "intermediate") and current_weekly_mileage >= 8

    rest_indices = [DAY_NAMES.index(d) for d in rest_days if d in DAY_NAMES]
    long_run_idx = DAY_NAMES.index(long_run_day)

    easy_range = pace_range(easy_pace_seconds * 0.95, easy_pace_seconds * 1.05)

    # Build all weeks
    weeks = []
    # For mileage targets beyond week 2, interpolate
    targets = [week1_target, week2_target]
    for extra in range(2, num_weeks):
        targets.append(round(week2_target * (1 + 0.03 * (extra - 1)), 1))

    # Deload cuts ~25% for one week only. The week after resumes from the
    # pre-deload mileage with a small bump -- it does not restart the ramp.
    if deload_week_idx is not None:
        pre_deload = targets[deload_week_idx]
        targets[deload_week_idx] = round(current_weekly_mileage * 0.75, 1)
        for i in range(deload_week_idx + 1, len(targets)):
            targets[i] = round(pre_deload * (1 + 0.05 * (i - deload_week_idx)), 1)

    race_day = parse_race_date(race_date)
    phases_seen: list[tuple[str, int | None]] = []

    for wk in range(num_weeks):
        wk_num = wk + 1
        wk_start = start_date + timedelta(days=wk * 7)
        wk_target = targets[wk] if wk < len(targets) else targets[-1]
        wk_is_deload = deload_week_idx is not None and wk == deload_week_idx

        # Race-date-aware overrides. These take precedence over the normal
        # ramp and over any scheduled deload: you do not deload into a taper,
        # and you certainly do not ramp into one.
        weeks_out = weeks_until_race(race_day, wk_start)
        wk_phase = determine_phase(weeks_out, goal_distance, current_weekly_mileage, include_workouts)
        phases_seen.append((wk_phase, weeks_out))

        long_run_factor = None
        wk_workouts = min(workouts_per_week, 1) if wk_is_deload else workouts_per_week

        if wk_phase == PHASE_RACE_WEEK:
            wk_target = round(current_weekly_mileage * race_week_volume_factor(goal_distance), 1)
            long_run_factor = 0.0
            wk_workouts = 1
            wk_is_deload = False
        elif wk_phase == PHASE_TAPER:
            vol_factor, lr_factor = taper_factors(weeks_out, goal_distance)
            if vol_factor:
                wk_target = round(current_weekly_mileage * vol_factor, 1)
                long_run_factor = lr_factor
                # Intensity and frequency are maintained through a taper --
                # only volume comes down. Keep both quality slots.
                wk_is_deload = False

        week_days = _build_week(
            week_num=wk_num, start_date=wk_start, block_start=start_date,
            target_mileage=wk_target,
            days_per_week=_effective_days_per_week(wk_target, days_per_week),
            rest_indices=rest_indices, long_run_idx=long_run_idx,
            easy_pace=easy_pace_seconds, current_paces=current_paces,
            workout_lib=workout_lib, include_workouts=include_workouts,
            num_workouts=wk_workouts,
            goal_distance=goal_distance,
            long_run_factor=long_run_factor,
            race_day=race_day,
            phase=wk_phase,
            weeks_out=weeks_out,
            current_mileage=current_weekly_mileage, is_deload=wk_is_deload,
            progression_state=progression_state,
            allow_strides=allow_strides,
        )

        wk_actual = round(sum(d["distance_miles"] for d in week_days), 1)

        # Each week should be >= previous week. Bump long run if not.
        # Skipped on a deload week (the whole point is to go down) and the
        # bump is capped so a rounding shortfall can't produce a 24mi long run.
        prev_was_deload = deload_week_idx is not None and wk - 1 == deload_week_idx
        tapering = wk_phase in (PHASE_TAPER, PHASE_RACE_WEEK)
        if weeks and not wk_is_deload and not prev_was_deload and not tapering:
            prev_mileage = weeks[-1]["target_mileage"]
            if wk_actual < prev_mileage:
                deficit = min(prev_mileage - wk_actual + 0.5, 2.0)
                for d in week_days:
                    if d["type"] == "long_run":
                        d["distance_miles"] = _round_half(d["distance_miles"] + deficit)
                        long_wo = _pick_long_run(
                            workout_lib, include_workouts, wk_num, current_weekly_mileage, wk_start,
                            mp_ready=current_paces.get("mp_ready", True),
                            max_long_miles=d["distance_miles"],
                            is_deload=wk_is_deload,
                        )
                        run_type = long_wo["run_type"] if long_wo and long_wo.get("run_type") else "easy"
                        lr = _long_run_structure(d["distance_miles"], run_type, current_paces)
                        d["title"] = lr["title"]
                        d["description"] = lr["description"]
                        d["purpose"] = lr["purpose"]
                        break
                wk_actual = round(sum(d["distance_miles"] for d in week_days), 1)

        # For first plan's current week, mark pre-today days as prescribe=False
        if first_prescribe_date:
            for d in week_days:
                d_date = date.fromisoformat(d["date"])
                if d_date < first_prescribe_date and d["type"] != "rest":
                    d["prescribed"] = False
                else:
                    d["prescribed"] = True
        else:
            for d in week_days:
                d["prescribed"] = True

        weeks.append({
            "week_number": wk_num,
            "target_mileage": wk_actual,
            "days": week_days,
        })

    plan = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "block_number": block_number,
        "is_deload": is_deload,
        "weeks": weeks,
        "pacing_guide": {
            "easy": easy_range,
            "steady": format_pace(current_paces["steady_pace"]),
            "current_threshold": format_pace(current_paces["threshold_pace"]),
            "current_tempo": format_pace(current_paces["tempo_pace"]),
            "current_interval": f"{format_pace(current_paces['interval_pace_fast'])}-{format_pace(current_paces['interval_pace'])}",
        },
        "notes": [],
    }

    if goal_pace_data:
        plan["pacing_guide"]["goal_race_pace"] = format_pace(goal_pace_data["race_pace"])
        plan["notes"].append(
            f"Workouts are paced off CURRENT fitness, progressing toward goal. "
            f"Goal race pace ({format_pace(goal_pace_data['race_pace'])}/mi) is the target."
        )

    # Lead with the phase note — where you are in the cycle frames everything else.
    if phases_seen:
        first_phase, first_weeks_out = phases_seen[0]
        note = phase_note(first_phase, first_weeks_out, goal_distance)
        if note:
            plan["notes"].insert(0, note)
        plan["phase"] = first_phase
        plan["weeks_to_race"] = first_weeks_out

    if goal_pace_data and not current_paces.get("mp_ready", True):
        plan["notes"].append(
            f"Goal race pace ({format_pace(goal_pace_data['race_pace'])}/mi) is still at or "
            f"faster than your current threshold ({format_pace(current_paces['threshold_pace'])}/mi). "
            f"Race-pace workouts are on hold until threshold comes down — that gap closes with "
            f"mileage and threshold work, not by forcing goal pace early."
        )

    if is_deload:
        plan["notes"].append(
            "Deload week — reduced volume so your body can absorb the training. "
            "Keep 1 quality workout, stay sharp, but let the fatigue dissipate. "
            "You'll come back stronger next block."
        )

    if not include_workouts:
        if current_weekly_mileage < RETURN_THRESHOLD_MPW and peak_weekly_mileage >= 40:
            plan["notes"].append(
                f"Return-to-running phase. You're at {current_weekly_mileage:.0f} mpw against a "
                f"{peak_weekly_mileage:.0f} mpw peak — the aerobic engine is still there, but "
                f"tendons, ligaments and bone detrain faster than lungs do. All easy running plus "
                f"strides until volume is back around 18-20 mpw, then quality comes back in. "
                f"Rushing this is the single most reliable way to get hurt."
            )
        else:
            plan["notes"].append(
                f"Building base mileage first. Currently at {current_weekly_mileage:.0f} mpw — "
                f"focus on easy miles and gradually increasing distance."
            )

    return plan


# How far threshold and VO2max pace sit from goal race pace, per distance.
# Positive = slower than race pace, negative = faster. Seconds per mile.
# Sources: Daniels VDOT tables, Pfitzinger (threshold = 15K-HM effort).
GOAL_PACE_OFFSETS = {
    #            threshold        interval (VO2max / 5K effort)
    "5k":       {"threshold": +30, "interval": -8},
    "10k":      {"threshold": +15, "interval": -25},
    "half":     {"threshold": -5,  "interval": -40},
    "marathon": {"threshold": -27, "interval": -55},
}


def _goal_derived_paces(goal_distance: str | None, race_pace: float) -> dict:
    """Threshold and interval targets implied by a goal race pace."""
    offsets = GOAL_PACE_OFFSETS.get((goal_distance or "").lower())
    if not offsets:
        offsets = GOAL_PACE_OFFSETS["5k"]
    return {
        "threshold": race_pace + offsets["threshold"],
        "interval": race_pace + offsets["interval"],
    }


def _mp_is_realistic(goal_race_pace: float | None, threshold_pace: float) -> bool:
    """Is goal race pace slow enough, relative to current threshold, to train at?

    Marathon pace has to sit comfortably BELOW threshold. If the goal pace is
    at or faster than the athlete's current threshold, race-pace workouts
    would be harder than their threshold session -- physiologically backwards
    and a good way to get hurt. In that state we withhold MP-specific work and
    keep building the threshold that has to come down first.
    """
    if not goal_race_pace:
        return False
    return goal_race_pace >= threshold_pace + 15


def _build_current_paces(
    easy_pace: float,
    workout_paces: dict | None,
    goal_pace_data: dict | None = None,
    current_mileage: float = 0,
    goal_distance: str | None = None,
) -> dict:
    """Build training paces with progression toward goal.

    Two pace families, and the distinction matters:
      threshold_pace  broken reps with float/jog rest (2x2mi, 3x2mi, 2x10min)
      tempo_pace      continuous, no rest -- always 10 sec/mi EASIER

    Threshold starts conservative (easy * 0.77 = ~7:00 from 9:06 easy) and
    blends toward the goal-implied target as weekly mileage builds from
    30 to 60 mpw. The goal-implied target is distance-aware: threshold is
    27 sec/mi faster than marathon pace, but 30 sec/mi SLOWER than 5K pace.
    """
    # Base paces from easy pace (used until there is enough volume to trust
    # the goal-derived numbers)
    base_threshold = easy_pace * 0.77
    base_interval = easy_pace * 0.67

    threshold = base_threshold
    interval = base_interval

    grp_raw = goal_pace_data.get("race_pace") if goal_pace_data else None
    if grp_raw and current_mileage >= 30:
        targets = _goal_derived_paces(goal_distance, grp_raw)
        # Blend: 0% at 30mpw, 100% at 60mpw
        progress = min((current_mileage - 30) / 30, 1.0)
        threshold = base_threshold * (1 - progress) + targets["threshold"] * progress
        interval = base_interval * (1 - progress) + targets["interval"] * progress

        # Weekly mileage is a weak proxy for fitness, and an ambitious goal can
        # drag these targets well past anything the athlete has actually run.
        # Cap the jump at 20 sec/mi faster than the effort-derived baseline in
        # any single block. Real Strava splits (current_workout_paces) override
        # this entirely -- measured beats inferred.
        threshold = max(threshold, base_threshold - 20)
        interval = max(interval, base_interval - 20)

    # Continuous tempo is 10 sec/mi EASIER than broken threshold reps.
    # Rest between reps is what lets you hold the faster pace.
    tempo = threshold + 10

    # Steady sits within a minute of goal race pace for marathon-type goals,
    # otherwise ~25 sec/mi off threshold.
    steady = (grp_raw + 30) if grp_raw and (goal_distance or "").lower() in ("marathon", "half") else threshold + 25

    threshold = _round_pace(threshold)
    tempo = _round_pace(tempo)
    interval = _round_pace(interval)
    interval_fast = _round_pace(interval - 10)  # feeling-good end of range
    steady = _round_pace(steady)

    # Goal race pace for MP workouts and long runs (None if no goal set)
    grp = _round_pace(grp_raw) if grp_raw else None

    if workout_paces:
        # Calibrated from real Strava splits. Trust the measured numbers for
        # threshold and intervals, but race_pace must stay the GOAL pace --
        # the calibrator estimates it from 800m splits, which is nonsense for
        # a marathon goal (that number is 5K effort, not race effort).
        cal_threshold = _round_pace(
            workout_paces.get("threshold_pace") or workout_paces.get("tempo_pace") or threshold
        )
        cal_interval = _round_pace(workout_paces.get("interval_pace", interval))
        cal_steady = grp + 30 if grp and (goal_distance or "").lower() in ("marathon", "half") else _round_pace(
            workout_paces.get("steady_pace", cal_threshold + 25)
        )
        return {
            "race_pace": grp or _round_pace(workout_paces.get("race_pace", interval)),
            "interval_pace": cal_interval,
            "interval_pace_fast": _round_pace(cal_interval - 10),
            "tempo_pace": _round_pace(cal_threshold + 10),
            "threshold_pace": cal_threshold,
            "steady_pace": _round_pace(cal_steady),
            "easy_pace_low": _round_pace(easy_pace * 0.95),
            "easy_pace_high": _round_pace(easy_pace * 1.05),
            "long_run_pace": _round_pace(easy_pace),
            "strides_pace": _round_pace(workout_paces.get("strides_pace", easy_pace * 0.55)),
            "goal_race_pace": grp,
            "mp_ready": _mp_is_realistic(grp, cal_threshold),
        }

    return {
        "race_pace": grp or interval,
        "interval_pace": interval,
        "interval_pace_fast": interval_fast,
        "tempo_pace": tempo,
        "threshold_pace": threshold,
        "steady_pace": steady,
        "easy_pace_low": _round_pace(easy_pace * 0.95),
        "easy_pace_high": _round_pace(easy_pace * 1.05),
        "long_run_pace": _round_pace(easy_pace),
        "strides_pace": _round_pace(easy_pace * 0.55),
        "goal_race_pace": grp,
        "mp_ready": _mp_is_realistic(grp, threshold),
    }


# Below this weekly volume, percentage ramps stop meaning anything: 10% of
# 2 mpw is a fifth of a mile. Returning runners get an absolute-step ramp.
RETURN_THRESHOLD_MPW = 12.0


def _return_to_running_targets(
    current: float, peak: float, experience: str
) -> tuple[float, float]:
    """Absolute-step ramp for someone coming back from a break.

    Anchored on training history rather than on recent (near-zero) mileage.
    A 2:58 marathoner with a 70 mpw peak who has not run in six weeks is not
    a beginner -- but their connective tissue has detrained even if their
    aerobic system has not, so the first weeks are capped in absolute terms
    and the ceiling for the whole return phase is ~30% of established peak.

    The step size shrinks as volume returns, handing off smoothly to the
    percentage ramp at RETURN_THRESHOLD_MPW instead of jumping at the seam.
    """
    if experience == "advanced" and peak >= 40:
        first_week_step = 12.0
        phase_ceiling = peak * 0.30
    elif peak >= 20:
        first_week_step = 8.0
        phase_ceiling = max(peak * 0.35, 10.0)
    else:
        first_week_step = 5.0
        phase_ceiling = 10.0

    blend = min(current / RETURN_THRESHOLD_MPW, 1.0)
    step = first_week_step * (1 - blend) + (current * 0.15) * blend

    week1 = max(3.0, min(current + step, phase_ceiling))
    week2 = min(week1 + max(week1 * 0.12, 2.0), phase_ceiling)
    return round(week1, 1), round(week2, 1)


def _calculate_target_mileage(
    current: float, peak: float, experience: str, goal_type: str
) -> tuple[float, float]:
    """Headroom-based mileage ramp."""
    # Returning from a break (or genuinely just starting). The old code
    # computed `ceiling = current * 1.5`, which collapses to nothing near
    # zero -- an athlete at 0 mpw was handed a 0-mile week, and one at
    # 1.5 mpw got 2.2 miles.
    if current < RETURN_THRESHOLD_MPW or goal_type == "comeback":
        return _return_to_running_targets(current, peak, experience)

    base = current

    if experience == "advanced" and peak > 0:
        headroom = current / peak
        if headroom < 0.5:
            max_increase = 0.20
        elif headroom < 0.75:
            max_increase = 0.15
        else:
            max_increase = 0.10
    elif experience == "intermediate":
        max_increase = 0.12
    else:
        max_increase = 0.10

    week1 = round(base * (1 + max_increase * 0.5), 1)
    week2 = round(base * (1 + max_increase), 1)

    # Never exceed 90% of established peak in a rolling block, and never add
    # more than 50% (or 8 miles, whichever is larger) over current volume.
    ceiling = min(peak * 0.9, max(current * 1.5, current + 8)) if peak > 0 else current + 8
    week1 = min(week1, ceiling)
    week2 = min(week2, ceiling)
    return week1, week2


def _is_deload_block(block_number: int, experience: str) -> bool:
    """Determine if this block should be a deload.

    First deload comes after the initial adaptation phase:
      Advanced: first deload at block 4, then every 3rd block after (7, 10, 13...)
      Intermediate: first deload at block 3, then every 2nd block after (5, 7, 9...)
      Beginner: first deload at block 3, then every 2nd block after (5, 7, 9...)

    Push through initial soreness, then deload once in a groove.
    """
    if block_number <= 2:
        return False

    if experience == "advanced":
        # First deload at block 4, then every 3rd block after
        if block_number == 4:
            return True
        return block_number > 4 and (block_number - 4) % 3 == 0
    else:
        # First deload at block 3, then every 2nd block after
        if block_number == 3:
            return True
        return block_number > 3 and (block_number - 3) % 2 == 0


MIN_EASY_RUN_MILES = 3.0
# Shortest run worth prescribing at higher volume — a genuine recovery run.
RECOVERY_RUN_MILES = 2.5


def _effective_days_per_week(target_mileage: float, requested_days: int) -> int:
    """Cap running days so a low-volume week isn't spread into token 1-mile runs.

    _distribute_mileage() floors every easy day at MIN_EASY_RUN_MILES. Six run
    days against a 12-mile week therefore produced 5x3mi + a long run = 18.5mi,
    overshooting the target by 54%. Fewer, longer runs is also better training
    at low volume.
    """
    if target_mileage <= 0:
        return max(1, min(requested_days, 3))
    # Reserve the long run (~28% of the week), then see how many easy days of
    # at least MIN_EASY_RUN_MILES the rest of the budget supports.
    easy_budget = target_mileage * 0.72
    supported_easy_days = int(easy_budget // MIN_EASY_RUN_MILES)
    return max(3, min(requested_days, supported_easy_days + 1))


# Weekly mileage required before structured quality work is prescribed.
# Endurance goals need more base than 5K/10K goals do, because their workouts
# are physically bigger: the smallest rung of the marathon threshold ladder is
# 7.5 miles, against 5.5 for the 5K ladder.
QUALITY_MILEAGE_FLOOR = {
    #             advanced  other
    "marathon":  (28.0,     34.0),
    "half":      (26.0,     32.0),
    "10k":       (18.0,     22.0),
    "5k":        (18.0,     20.0),
}


def _should_include_workouts(
    current_mileage: float,
    goal_type: str,
    experience: str,
    goal_distance: str | None = None,
) -> bool:
    """Structured quality work requires a mileage base underneath it.

    Principle 1: build mileage BEFORE adding intensity. An experienced runner
    coming back needs a few weeks of easy running first; a beginner needs
    considerably more.
    """
    if goal_type == "comeback":
        return current_mileage >= 30
    advanced_floor, other_floor = QUALITY_MILEAGE_FLOOR.get(
        (goal_distance or "5k").lower(), (20.0, 24.0)
    )
    # Established athletes can reintroduce quality a little earlier -- the
    # aerobic machinery is intact, it just needs reactivating.
    floor = advanced_floor if experience == "advanced" else other_floor
    return current_mileage >= floor


def _workouts_per_week(current_mileage: float, experience: str, goal_distance: str | None = None) -> int:
    """Two quality sessions a week is the target, but only once volume
    supports them. Below that, one hard day plus a long run is already two
    stressful days in a small week.
    """
    # Marathon quality sessions are big (a 3x2mi day is 11 miles all-in), so
    # two of them need more weekly volume underneath than two 5K sessions do.
    second_workout_floor = 40.0 if (goal_distance or "").lower() in ("marathon", "half") else 28.0
    return 2 if current_mileage >= second_workout_floor else 1


# ── Long run structure generator ────────────────────────────────

def _long_run_structure(total_miles: float, run_type: str, paces: dict) -> dict:
    """Generate specific mile breakdown for long runs.

    Returns title + description with exact mile splits, not vague percentages.
    """
    easy_range = pace_range(paces["easy_pace_low"], paces["easy_pace_high"])
    steady = format_pace(paces["steady_pace"])
    grp = paces.get("goal_race_pace")
    mp_label = f"goal MP ({format_pace(grp)}/mi)" if grp else f"steady ({steady}/mi)"
    mp_pace = format_pace(grp) if grp else steady
    total = _round_half(total_miles)

    if run_type == "easy":
        return {
            "title": "Easy Long Run",
            "description": f"{total}mi easy at {easy_range}/mi. Conversational the entire time.",
            "purpose": "Builds aerobic endurance, capillary density, and fat-burning efficiency.",
        }

    elif run_type == "steady_finish":
        # Steady portion: 2mi at 10-11mi, 3mi at 12-14mi, 4mi at 15+
        if total <= 11:
            hard = 2.0
        elif total <= 14:
            hard = 3.0
        else:
            hard = 4.0
        easy_mi = _round_half(total - hard)
        return {
            "title": "Steady Finish Long Run",
            "description": f"{easy_mi}mi easy at {easy_range}/mi, then {hard}mi at steady effort ({steady}/mi).",
            "purpose": "Teaches finishing strong on tired legs. Controlled — not a workout.",
        }

    elif run_type == "mp_finish":
        # MP finish: 3mi at 12-14mi, 4mi at 15-16mi, 5mi at 17+
        if total <= 14:
            hard = 3.0
        elif total <= 16:
            hard = 4.0
        else:
            hard = 5.0
        easy_mi = _round_half(total - hard)
        return {
            "title": "MP Finish Long Run",
            "description": f"{easy_mi}mi easy at {easy_range}/mi, then {hard}mi at {mp_label}. Controlled — don't force it.",
            "purpose": "Marathon-specific endurance. Running race effort on tired legs — the key long run workout.",
        }

    elif run_type == "sandwich":
        # Easy / steady / easy — roughly equal thirds
        third = _round_half(total / 3)
        middle = _round_half(total - third * 2)
        return {
            "title": "Steady Sandwich Long Run",
            "description": f"{third}mi easy at {easy_range}/mi, {middle}mi at steady ({steady}/mi), {third}mi easy to finish.",
            "purpose": "Sustained steady effort sandwiched between easy. Builds pacing discipline over distance.",
        }

    elif run_type == "mp_block":
        # Sets of 3mi at MP with 1mi float between
        sets = max(int(total // 4), 2)
        mp_total = sets * 3
        float_total = sets - 1
        wu = _round_half((total - mp_total - float_total) / 2)
        cd = _round_half(total - mp_total - float_total - wu)
        return {
            "title": "MP Block Long Run",
            "description": f"{wu}mi easy, then {sets}x3mi at {mp_label} with 1mi float ({easy_range}/mi) between sets, {cd}mi easy.",
            "purpose": "Accumulates massive marathon pace volume. Peak long run workout.",
        }

    # Fallback
    return {
        "title": "Easy Long Run",
        "description": f"{total}mi easy at {easy_range}/mi.",
        "purpose": "Aerobic endurance.",
    }


# ── Week builder ────────────────────────────────────────────────

def _build_week(
    week_num: int, start_date: date, block_start: date,
    target_mileage: float, days_per_week: int, rest_indices: list[int],
    long_run_idx: int, easy_pace: float, current_paces: dict,
    workout_lib: dict, include_workouts: bool, num_workouts: int,
    goal_distance: str | None, current_mileage: float,
    is_deload: bool = False,
    progression_state: dict | None = None,
    allow_strides: bool = False,
    long_run_factor: float | None = None,
    race_day: date | None = None,
    phase: str | None = None,
    weeks_out: int | None = None,
) -> list[dict]:
    run_days = [i for i in range(7) if i not in rest_indices]

    while len(run_days) > days_per_week:
        protected = {long_run_idx, 1, 3}
        for candidate in reversed(run_days):
            if candidate not in protected:
                run_days.remove(candidate)
                break
        else:
            for candidate in reversed(run_days):
                if candidate != long_run_idx:
                    run_days.remove(candidate)
                    break

    day_assignments = {}
    for i in range(7):
        if i not in run_days:
            day_assignments[i] = "rest"
        elif i == long_run_idx:
            day_assignments[i] = "long"
        else:
            day_assignments[i] = "easy"

    workout1 = None
    workout2 = None

    # A single quality session should not exceed ~30% of the week, and must
    # never be longer than the long run. Compute the budget before picking,
    # because ladder levels have fixed distances.
    long_pct = 0.30 if goal_distance in ("marathon", "half") else 0.28
    long_estimate = target_mileage * long_pct
    max_workout_miles = max(min(target_mileage * 0.30, long_estimate - 0.5), 4.0)

    if include_workouts:
        preferred_workout_days = [1, 3]  # Tue, Thu

        # When the week only supports ONE quality session, pick the one that
        # matters most for the goal. For the marathon and half that is
        # threshold/MP work — it raises the pace the whole race sits under.
        # For 5K/10K it is VO2max. On a deload it is always the controlled
        # aerobic session; speed work is the opposite of absorbing training.
        single_is_threshold = num_workouts <= 1 and (
            is_deload or (goal_distance or "").lower() in ("marathon", "half")
        )
        if single_is_threshold:
            preferred_workout_days = [3, 1]
        placed = 0
        for wd in preferred_workout_days:
            if placed >= num_workouts:
                break
            if wd in run_days and day_assignments.get(wd) == "easy":
                placed += 1
                # In a taper, ladder workouts are the wrong shape: their
                # total_miles is fixed, so a level-8 threshold session is 12.5
                # miles whether you are 12 weeks out or 6 days out.
                tapering = phase in (PHASE_TAPER, PHASE_RACE_WEEK) and weeks_out is not None

                if placed == 1 and not single_is_threshold:
                    # Intervals (hard speed work) early in the week
                    day_assignments[wd] = "workout_speed"  # reverted below if nothing fits
                    taper_wo = get_taper_workout(
                        max(weeks_out, 1), current_paces, goal_distance or "marathon",
                        category="intervals",
                    ) if tapering else None
                    workout1 = taper_wo or _pick_workout_progressive(
                        workout_lib, "intervals", week_num, block_start,
                        current_paces, goal_distance or "5k",
                        is_deload, progression_state,
                        max_miles=max_workout_miles,
                    )
                else:
                    # Threshold later in the week
                    day_assignments[wd] = "workout_threshold"
                    taper_wo = get_taper_workout(
                        max(weeks_out, 1), current_paces, goal_distance or "marathon",
                        category="threshold",
                    ) if tapering else None
                    workout2 = taper_wo or _pick_workout_progressive(
                        workout_lib, "threshold", week_num, block_start,
                        current_paces, goal_distance or "5k",
                        is_deload, progression_state,
                        max_miles=max_workout_miles,
                    )

    # A workout the week cannot afford comes back as None -- put the day back
    # to easy rather than leaving a hard slot with nothing in it.
    for idx, wo in ((1, workout1), (2, workout2)):
        if wo is not None:
            continue
        marker = "workout_speed" if idx == 1 else "workout_threshold"
        for day_idx, assignment in list(day_assignments.items()):
            if assignment == marker:
                day_assignments[day_idx] = "easy"

    wo1_miles = _round_half(workout1["total_miles"]) if workout1 and workout1.get("total_miles") else 0
    wo2_miles = _round_half(workout2["total_miles"]) if workout2 and workout2.get("total_miles") else 0

    mileage_dist = _distribute_mileage(
        target_mileage, day_assignments, goal_distance,
        wo1_miles=wo1_miles, wo2_miles=wo2_miles,
    )

    easy_range = pace_range(easy_pace * 0.95, easy_pace * 1.05)
    strides_placed = False
    days = []

    for i in range(7):
        day_date = start_date + timedelta(days=i)
        assignment = day_assignments[i]
        day_name = DAY_NAMES[i]

        if race_day is not None and day_date == race_day:
            days.append(_race_day(day_date, day_name, goal_distance, current_paces))
            continue

        if race_day is not None and (race_day - day_date).days == 1:
            days.append(_shakeout_day(day_date, day_name, easy_range))
            continue

        if race_day is not None and (race_day - day_date).days == 2:
            days.append(_rest_day(day_date, day_name))
            continue

        if assignment == "rest":
            days.append(_rest_day(day_date, day_name))

        elif assignment == "long":
            distance = _round_half(mileage_dist.get("long", target_mileage * 0.28))
            if long_run_factor is not None:
                distance = _round_half(distance * long_run_factor)
                if distance < 3.0:
                    # Race week: no long run at all, just an easy shakeout.
                    days.append(_easy_day(day_date, day_name, 4.0, easy_range))
                    continue
            if phase in (PHASE_TAPER, PHASE_RACE_WEEK):
                # Taper long runs shed distance and quality both. A long run
                # with race-pace blocks two weeks out is a workout you cannot
                # recover from in time to use.
                lr = _long_run_structure(
                    distance,
                    "steady_finish" if (weeks_out or 0) >= 3 and distance >= 10 else "easy",
                    current_paces,
                )
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": lr["title"], "description": lr["description"],
                    "purpose": lr["purpose"], "distance_miles": distance,
                    "warmup": None, "cooldown": None,
                })
                continue

            long_wo = _pick_long_run(
                workout_lib, include_workouts, week_num, current_mileage, block_start,
                mp_ready=current_paces.get("mp_ready", True),
                max_long_miles=distance,
                is_deload=is_deload,
            )

            if long_wo and long_wo.get("structure"):
                # Peak fixed-structure long runs — use as-is
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": long_wo["name"],
                    "description": long_wo["structure"],
                    "purpose": long_wo["purpose"],
                    "distance_miles": long_wo.get("total_miles", distance),
                    "warmup": None, "cooldown": None,
                })
            elif long_wo and long_wo.get("run_type"):
                lr = _long_run_structure(distance, long_wo["run_type"], current_paces)
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": lr["title"],
                    "description": lr["description"],
                    "purpose": lr["purpose"],
                    "distance_miles": distance,
                    "warmup": None, "cooldown": None,
                })
            else:
                lr = _long_run_structure(distance, "easy", current_paces)
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": lr["title"],
                    "description": lr["description"],
                    "purpose": lr["purpose"],
                    "distance_miles": distance,
                    "warmup": None, "cooldown": None,
                })

        elif assignment == "workout_speed":
            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "workout",
                "title": workout1["name"],
                "description": workout1["structure"],
                "purpose": workout1["purpose"],
                "distance_miles": wo1_miles,
                "warmup": workout1.get("warmup", "1.5mi easy"),
                "cooldown": workout1.get("cooldown", "1.5mi easy"),
            })

        elif assignment == "workout_threshold":
            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "workout",
                "title": workout2["name"],
                "description": workout2["structure"],
                "purpose": workout2["purpose"],
                "distance_miles": wo2_miles,
                "warmup": workout2.get("warmup", "1.5mi easy"),
                "cooldown": workout2.get("cooldown", "1.5mi easy"),
            })

        else:  # easy
            distance = _round_half(mileage_dist.get(f"easy_{i}", target_mileage * 0.12))
            title = "Easy Run"
            desc = f"Conversational effort the entire time. Should be able to hold a full conversation — if you can't, slow down. ({easy_range}/mi or slower)"
            purpose = "Aerobic base building and recovery between hard efforts."

            if not strides_placed and (include_workouts or allow_strides):
                strides_placed = True
                title = "Easy Run + Strides"
                sp = format_pace(current_paces["strides_pace"])
                desc = f"Conversational effort the whole run — easy means easy. After the run: 4-6x20sec strides at {sp}/mi with full recovery walk between. ({easy_range}/mi or slower)"
                purpose = "Aerobic base + maintain leg speed and neuromuscular coordination."

            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "easy", "title": title,
                "description": desc, "purpose": purpose,
                "distance_miles": distance,
                "warmup": None, "cooldown": None,
            })

    return days


RACE_LABELS = {"5k": "5K", "10k": "10K", "half": "Half Marathon", "marathon": "Marathon"}
RACE_MILES = {"5k": 3.1, "10k": 6.2, "half": 13.1, "marathon": 26.2}


def _race_day(day_date: date, day_name: str, goal_distance: str | None, paces: dict) -> dict:
    """Race day. Everything in the block has been pointing here."""
    label = RACE_LABELS.get((goal_distance or "").lower(), "Race")
    miles = RACE_MILES.get((goal_distance or "").lower(), 0)
    grp = paces.get("goal_race_pace")
    pace_str = f" Goal pace {format_pace(grp)}/mi." if grp else ""
    return {
        "date": day_date.isoformat(), "day": day_name,
        "type": "race",
        "title": f"RACE DAY — {label}",
        "description": (
            f"This is the one.{pace_str} Go out at goal pace, not faster — the first "
            f"few miles will feel too easy and that is exactly right. Warm up as you "
            f"would for a workout."
        ),
        "purpose": "Everything in this block has been pointing at today.",
        "distance_miles": miles,
        "warmup": "1-2mi easy + strides", "cooldown": "Easy jog if you can face it",
    }


def _shakeout_day(day_date: date, day_name: str, easy_range: str) -> dict:
    """The day before a race. Shorter than feels right, and that is the point."""
    return {
        "date": day_date.isoformat(), "day": day_name,
        "type": "easy", "title": "Shakeout + Strides",
        "description": (
            f"2mi very easy at {easy_range}/mi or slower, then 4x100m strides. "
            f"You will want to do more. Don't."
        ),
        "purpose": "Keeps the legs open without touching tomorrow's energy.",
        "distance_miles": 2.0,
        "warmup": None, "cooldown": None,
    }


def _easy_day(day_date: date, day_name: str, miles: float, easy_range: str) -> dict:
    return {
        "date": day_date.isoformat(), "day": day_name,
        "type": "easy", "title": "Easy Run",
        "description": f"Conversational effort the entire time. ({easy_range}/mi or slower)",
        "purpose": "Aerobic maintenance without adding fatigue.",
        "distance_miles": miles,
        "warmup": None, "cooldown": None,
    }


def _rest_day(day_date: date, day_name: str) -> dict:
    return {
        "date": day_date.isoformat(), "day": day_name,
        "type": "rest", "title": "Rest Day",
        "description": "Full rest. Recovery is when your body adapts and gets stronger.",
        "purpose": "Physical and mental recovery.",
        "distance_miles": 0, "warmup": None, "cooldown": None,
    }


def _distribute_mileage(
    target: float, assignments: dict, goal_distance: str | None,
    wo1_miles: float = 0, wo2_miles: float = 0,
) -> dict:
    if goal_distance in ("marathon", "half"):
        long_pct = 0.30
    else:
        long_pct = 0.28

    distribution = {}

    # Workout mileage is whatever was actually placed. The old version mapped
    # workout days to [wo1, wo2] positionally, so a week that placed only the
    # THRESHOLD session (deload weeks do exactly this) read wo1_miles == 0 and
    # left the whole workout allocation to be re-spent on easy days -- a
    # "deload" week came out barely smaller than the build week before it.
    distribution["workout1"] = wo1_miles
    distribution["workout2"] = wo2_miles
    total_workout_miles = wo1_miles + wo2_miles

    distribution["long"] = _round_half(target * long_pct)

    remaining = target - total_workout_miles - distribution["long"]
    easy_days = [k for k, v in assignments.items() if v == "easy"]

    # Every easy day is floored at MIN_EASY_RUN_MILES, so if the budget will
    # not stretch that far the week inflates past its target. Convert the
    # surplus days to rest instead -- fewer, real runs beats more token ones.
    # Above ~30 mpw a short recovery day is legitimate training, so the floor
    # relaxes rather than costing a running day. Jake runs 6-7 days a week at
    # volume; dropping frequency to protect a 3-mile minimum is the wrong trade.
    easy_floor = MIN_EASY_RUN_MILES if target < 30 else RECOVERY_RUN_MILES
    if easy_days and remaining < len(easy_days) * easy_floor:
        supported = max(1, int(remaining // easy_floor))
        for day_idx in sorted(easy_days, reverse=True)[: len(easy_days) - supported]:
            assignments[day_idx] = "rest"
            easy_days.remove(day_idx)

    if easy_days:
        per_easy = remaining / len(easy_days) if remaining > 0 else easy_floor
        for d in easy_days:
            distribution[f"easy_{d}"] = max(per_easy, easy_floor)

        # Principle 9: the long run is the longest run of the week. At low
        # volume the percentage split plus the easy-day floor could otherwise
        # produce a 3.5mi "long run" alongside 4mi easy days.
        longest_easy = max(distribution[f"easy_{d}"] for d in easy_days)
        if distribution["long"] < longest_easy + 0.5:
            distribution["long"] = _round_half(longest_easy + 1.0)

    return distribution


def _fit_workout_to_week(
    workout: dict, category: str, level: int, paces: dict,
    goal_distance: str, max_miles: float | None,
) -> dict | None:
    """Step down the ladder until the session fits the week's mileage budget.

    Ladder levels carry a fixed total_miles, so a level appropriate to the
    athlete's ABILITY can still be wrong for their current VOLUME. An 11-mile
    3x2mi threshold session inside a 20-mile week is 55% of the week in one
    day and longer than the long run.
    """
    if not max_miles or max_miles <= 0:
        return workout
    if workout.get("total_miles", 0) <= max_miles:
        return workout

    for lower in range(level - 1, 0, -1):
        candidate = get_workout_at_level(category, lower, paces, goal_distance)
        if candidate.get("total_miles", 0) <= max_miles:
            return candidate

    # Even the smallest rung is too big for this week. Prescribing it anyway
    # would put a third of the week's mileage into one hard day, so the
    # honest answer is no workout at all.
    return None


def _pick_workout_progressive(
    workout_lib: dict, category: str, week_num: int, block_start: date,
    current_paces: dict, goal_distance: str,
    is_deload: bool, progression_state: dict | None,
    max_miles: float | None = None,
) -> dict | None:
    """Pick a workout using the progression ladder if state exists,
    falling back to the old rotation system if not.
    """
    # If no progression state, fall back to old system
    if not progression_state or category not in progression_state:
        return _pick_workout(workout_lib, category, week_num, block_start, deload=is_deload)

    state = progression_state[category]
    level = state.get("current_level", 1)

    # Apply pace override from recalibration
    paces = dict(current_paces)
    if state.get("current_pace_sec"):
        if category == "intervals":
            paces["interval_pace"] = state["current_pace_sec"]
            paces["interval_pace_fast"] = state["current_pace_sec"] - 10
        elif category == "threshold":
            paces["tempo_pace"] = state["current_pace_sec"]
            paces["threshold_pace"] = state["current_pace_sec"]

    # Withhold goal-pace sessions until goal pace is actually trainable.
    if not paces.get("mp_ready", True) and level_requires_mp(category, level, goal_distance):
        level = highest_non_mp_level(category, level, goal_distance)

    if is_deload:
        wo = get_deload_workout(category, level, paces, goal_distance)
        return _fit_workout_to_week(wo, category, max(1, level // 2), paces, goal_distance, max_miles)

    # Week 1 = current level, Week 2 = variant (next level preview)
    effective_level = level
    if week_num % 2 == 0:
        wk2_level = level + 1
        if paces.get("mp_ready", True) or not level_requires_mp(category, wk2_level, goal_distance):
            effective_level = wk2_level
            wo = get_week2_variant(category, level, paces, goal_distance)
        else:
            wo = get_workout_at_level(category, level, paces, goal_distance)
    else:
        wo = get_workout_at_level(category, level, paces, goal_distance)

    return _fit_workout_to_week(wo, category, effective_level, paces, goal_distance, max_miles)


def _pick_workout(workout_lib: dict, category: str, week_num: int,
                   start_date: date = None, deload: bool = False) -> dict:
    """Pick a workout, rotating across blocks via start_date seed.

    Week 1 and week 2 within the same block always get different workouts.
    The block_seed shifts each 2-week block so workouts rotate over time.
    On deload: pick from the lighter workouts (lower total_miles).
    """
    options = workout_lib.get(category, [])

    if not options:
        options = workout_lib.get("threshold", []) or workout_lib.get("tempo", [])

    if not options:
        return {
            "name": "Tempo Run",
            "structure": "25min at threshold effort.",
            "purpose": "Builds lactate threshold.",
            "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
            "total_miles": 6.5,
        }

    if deload:
        # Pick from shorter workouts only — keep it under 9mi total
        light = [w for w in options if w.get("total_miles", 6) <= 8.5]
        if light:
            options = light
        else:
            sorted_opts = sorted(options, key=lambda w: w.get("total_miles", 6))
            options = sorted_opts[:2]

    if start_date:
        block_seed = start_date.toordinal() // 14  # seed per 2-week block
    else:
        block_seed = 0

    # Week 1 gets index N, week 2 gets index N+1 — always different
    idx = (block_seed + week_num - 1) % len(options)
    return options[idx]


MP_LONG_RUN_TYPES = {"mp_finish", "peak_fixed"}


def _pick_long_run(
    workout_lib: dict | None, include_workouts: bool,
    week_num: int, current_mileage: float,
    start_date: date = None,
    mp_ready: bool = True,
    max_long_miles: float | None = None,
    is_deload: bool = False,
) -> dict | None:
    """Pick long run type. Week 1 = easy, Week 2 = quality (rotated).

    `max_long_miles` is the distance the week's mileage budget actually
    allows. Peak long runs ("10 + 10 MP", "Sandwich MP") carry a FIXED
    total_miles that overrides the budget, so a 19mi race-simulation run
    could land in a deload week and blow the target by 12 miles. Anything
    meaningfully longer than the budget is filtered out here.
    """
    if not workout_lib or not include_workouts:
        return None

    options = workout_lib.get("long_run", [])
    if not options:
        return None

    # Week 1 = always easy long run
    if week_num % 2 == 1:
        return options[0]

    # Week 2 = rotate through quality options (skip the easy one at index 0)
    quality = [o for o in options[1:] if current_mileage >= o.get("min_mpw", 0)]

    if is_deload:
        # A deload keeps quality but sheds volume. Fixed-structure peak long
        # runs are the opposite of that.
        quality = [o for o in quality if o.get("run_type") != "peak_fixed"]
    elif max_long_miles is not None:
        quality = [
            o for o in quality
            if o.get("run_type") != "peak_fixed"
            or o.get("total_miles", 0) <= max_long_miles + 1.5
        ]

    if not mp_ready:
        # Goal pace is not yet slower than threshold — a "10mi easy + 8mi at
        # goal MP" long run right now is a race, not a workout. Steady-effort
        # long runs give the same specificity without the hole.
        quality = [o for o in quality if o.get("run_type") not in MP_LONG_RUN_TYPES]
    if not quality:
        return options[0]

    if start_date:
        block_seed = start_date.toordinal() // 7
    else:
        block_seed = 0
    idx = block_seed % len(quality)
    return quality[idx]
