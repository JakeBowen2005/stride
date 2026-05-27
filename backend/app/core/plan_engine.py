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


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DEFAULT_WORKOUT_DAYS = [1, 3]
DEFAULT_LONG_RUN_DAY = 5
DEFAULT_REST_DAY = 6


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
    block_number: int = 1,
) -> dict:
    if start_date is None:
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start_date = today + timedelta(days=days_until_monday)

    # Check if this block should be a deload
    is_deload = _is_deload_block(block_number, experience_level)

    week1_target, week2_target = _calculate_target_mileage(
        current_weekly_mileage, peak_weekly_mileage, experience_level, goal_type
    )

    if is_deload:
        # Week 1 = deload (reduced ~25%), Week 2 = back to building
        deload_mileage = round(current_weekly_mileage * 0.75, 1)
        week1_target = deload_mileage
        # Week 2 resumes normal progression from current mileage
        week2_target = round(current_weekly_mileage * (1 + 0.05), 1)  # slight bump back

    goal_pace_data = None
    if goal_type == "race" and goal_distance and target_time_seconds:
        goal_pace_data = goal_paces(goal_distance, target_time_seconds)

    # Build paces with progression toward goal
    current_paces = _build_current_paces(
        easy_pace_seconds, current_workout_paces,
        goal_pace_data=goal_pace_data,
        current_mileage=current_weekly_mileage,
    )

    workout_lib = get_workout_library(current_paces, goal_distance or "5k", current_weekly_mileage)

    include_workouts = _should_include_workouts(
        current_weekly_mileage, goal_type, experience_level
    )
    workouts_per_week = _workouts_per_week(current_weekly_mileage, experience_level)

    rest_indices = [DAY_NAMES.index(d) for d in rest_days if d in DAY_NAMES]
    long_run_idx = DAY_NAMES.index(long_run_day)

    week1 = _build_week(
        week_num=1, start_date=start_date, block_start=start_date,
        target_mileage=week1_target, days_per_week=days_per_week,
        rest_indices=rest_indices, long_run_idx=long_run_idx,
        easy_pace=easy_pace_seconds, current_paces=current_paces,
        workout_lib=workout_lib, include_workouts=include_workouts,
        num_workouts=min(workouts_per_week, 1) if is_deload else workouts_per_week,
        goal_distance=goal_distance,
        current_mileage=current_weekly_mileage, is_deload=is_deload,
    )
    week2 = _build_week(
        week_num=2, start_date=start_date + timedelta(days=7),
        block_start=start_date, target_mileage=week2_target,
        days_per_week=days_per_week, rest_indices=rest_indices,
        long_run_idx=long_run_idx, easy_pace=easy_pace_seconds,
        current_paces=current_paces, workout_lib=workout_lib,
        include_workouts=include_workouts, num_workouts=workouts_per_week,
        goal_distance=goal_distance, current_mileage=current_weekly_mileage,
        is_deload=False,  # week 2 is back to normal
    )

    easy_range = pace_range(easy_pace_seconds * 0.95, easy_pace_seconds * 1.05)
    week1_actual = round(sum(d["distance_miles"] for d in week1), 1)
    week2_actual = round(sum(d["distance_miles"] for d in week2), 1)

    # Week 2 must always be >= week 1. If not, bump the long run.
    if week2_actual < week1_actual:
        deficit = week1_actual - week2_actual + 0.5
        for d in week2:
            if d["type"] == "long_run":
                d["distance_miles"] = _round_half(d["distance_miles"] + deficit)
                # Regenerate the description with updated distance
                long_wo = _pick_long_run(workout_lib, include_workouts, 2, current_weekly_mileage, start_date + timedelta(days=7))
                run_type = long_wo["run_type"] if long_wo and long_wo.get("run_type") else "easy"
                lr = _long_run_structure(d["distance_miles"], run_type, current_paces)
                d["title"] = lr["title"]
                d["description"] = lr["description"]
                d["purpose"] = lr["purpose"]
                break
        week2_actual = round(sum(d["distance_miles"] for d in week2), 1)

    plan = {
        "start_date": start_date.isoformat(),
        "end_date": (start_date + timedelta(days=13)).isoformat(),
        "block_number": block_number,
        "is_deload": is_deload,
        "week1": {"target_mileage": week1_actual, "days": week1},
        "week2": {"target_mileage": week2_actual, "days": week2},
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

    if is_deload:
        plan["notes"].append(
            "Deload week — reduced volume so your body can absorb the training. "
            "Keep 1 quality workout, stay sharp, but let the fatigue dissipate. "
            "You'll come back stronger next block."
        )

    if not include_workouts:
        plan["notes"].append(
            f"Building base mileage first. Currently at {current_weekly_mileage:.0f} mpw — "
            f"focus on easy miles and gradually increasing distance."
        )

    return plan


def _build_current_paces(
    easy_pace: float,
    workout_paces: dict | None,
    goal_pace_data: dict | None = None,
    current_mileage: float = 0,
) -> dict:
    """Build training paces with progression toward goal.

    Threshold starts conservative (easy * 0.77 = ~7:00 from 9:06 easy).
    As mileage builds (30-60 mpw), threshold blends toward goal target
    (goal MP - 25sec/mi). This mirrors real training progression.
    """
    # Base paces from easy pace
    base_threshold = easy_pace * 0.77

    # Progress threshold toward goal as fitness builds
    threshold = base_threshold
    if goal_pace_data and current_mileage >= 30:
        goal_mp = goal_pace_data.get("race_pace")
        if goal_mp:
            # Target threshold = 25 sec/mi faster than goal MP
            goal_threshold = goal_mp - 25
            # Blend: 0% at 30mpw, 100% at 60mpw
            progress = min((current_mileage - 30) / 30, 1.0)
            threshold = base_threshold * (1 - progress) + goal_threshold * progress

    # Derive other paces from threshold
    tempo = threshold * 0.96          # slightly faster than threshold
    steady = threshold + 25           # ~25sec slower than threshold, near MP range

    # Interval pace progresses toward goal as mileage builds
    base_interval = easy_pace * 0.67
    interval = base_interval
    if goal_pace_data and current_mileage >= 30:
        goal_interval = goal_pace_data.get("interval_pace", base_interval)
        progress = min((current_mileage - 30) / 30, 1.0)
        interval = base_interval * (1 - progress) + goal_interval * progress

    # Round all paces to nearest 5 seconds
    threshold = _round_pace(threshold)
    tempo = _round_pace(tempo)
    interval = _round_pace(interval)
    interval_fast = _round_pace(interval - 10)  # feeling-good end of range
    steady = _round_pace(steady)

    # Goal race pace for MP workouts and long runs (None if no goal set)
    grp = _round_pace(goal_pace_data["race_pace"]) if goal_pace_data and goal_pace_data.get("race_pace") else None

    if workout_paces:
        return {
            "race_pace": _round_pace(workout_paces.get("race_pace", interval)),
            "interval_pace": _round_pace(workout_paces.get("interval_pace", interval)),
            "interval_pace_fast": _round_pace(workout_paces.get("interval_pace", interval) - 10),
            "tempo_pace": _round_pace(workout_paces.get("tempo_pace", tempo)),
            "threshold_pace": _round_pace(workout_paces.get("threshold_pace", threshold)),
            "steady_pace": _round_pace(workout_paces.get("steady_pace", steady)),
            "easy_pace_low": _round_pace(easy_pace * 0.95),
            "easy_pace_high": _round_pace(easy_pace * 1.05),
            "long_run_pace": _round_pace(easy_pace),
            "strides_pace": _round_pace(workout_paces.get("strides_pace", easy_pace * 0.55)),
            "goal_race_pace": grp,
        }

    return {
        "race_pace": interval,
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
    }


def _calculate_target_mileage(
    current: float, peak: float, experience: str, goal_type: str
) -> tuple[float, float]:
    """Headroom-based mileage ramp."""
    base = max(current, 10)

    if goal_type == "comeback":
        max_increase = 0.10
    elif experience == "advanced" and peak > 0:
        headroom = current / peak if peak > 0 else 1.0
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

    if goal_type == "comeback":
        ceiling = current * 1.3
    else:
        ceiling = min(peak * 0.9, current * 1.5)

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


def _should_include_workouts(current_mileage: float, goal_type: str, experience: str) -> bool:
    if goal_type == "comeback":
        return False
    if experience == "beginner" and current_mileage < 15:
        return False
    if current_mileage < 20:
        return False
    return True


def _workouts_per_week(current_mileage: float, experience: str) -> int:
    if current_mileage < 20:
        return 1
    return 2


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
    if include_workouts:
        preferred_workout_days = [1, 3]
        placed = 0
        for wd in preferred_workout_days:
            if placed >= num_workouts:
                break
            if wd in run_days and day_assignments.get(wd) == "easy":
                placed += 1
                if placed == 1:
                    day_assignments[wd] = "workout_threshold"
                    workout1 = _pick_workout(workout_lib, "threshold", week_num, block_start, deload=is_deload)
                else:
                    day_assignments[wd] = "workout_speed"
                    workout2 = _pick_workout(workout_lib, "intervals", week_num, block_start, deload=is_deload)

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

        if assignment == "rest":
            days.append(_rest_day(day_date, day_name))

        elif assignment == "long":
            distance = _round_half(mileage_dist.get("long", target_mileage * 0.28))
            long_wo = _pick_long_run(workout_lib, include_workouts, week_num, current_mileage, block_start)

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

        elif assignment == "workout_threshold":
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

        elif assignment == "workout_speed":
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

            if not strides_placed and include_workouts:
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

    wo_keys = [k for k, v in assignments.items() if v.startswith("workout")]
    wo_totals = [wo1_miles, wo2_miles]
    total_workout_miles = 0
    for idx, k in enumerate(wo_keys):
        wo_dist = wo_totals[idx] if idx < len(wo_totals) else 0
        distribution[f"workout{idx + 1}"] = wo_dist
        total_workout_miles += wo_dist

    distribution["long"] = _round_half(target * long_pct)

    remaining = target - total_workout_miles - distribution["long"]
    easy_days = [k for k, v in assignments.items() if v == "easy"]

    if easy_days:
        per_easy = remaining / len(easy_days) if remaining > 0 else 3.0
        for d in easy_days:
            distribution[f"easy_{d}"] = max(per_easy, 3.0)

    return distribution


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


def _pick_long_run(
    workout_lib: dict | None, include_workouts: bool,
    week_num: int, current_mileage: float,
    start_date: date = None,
) -> dict | None:
    """Pick long run type. Week 1 = easy, Week 2 = quality (rotated)."""
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
    if not quality:
        return options[0]

    if start_date:
        block_seed = start_date.toordinal() // 7
    else:
        block_seed = 0
    idx = block_seed % len(quality)
    return quality[idx]
