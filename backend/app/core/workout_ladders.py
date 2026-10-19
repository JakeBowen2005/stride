"""Workout progression ladders.

Defines 12-level ladders for threshold and interval workouts.
The plan engine reads the athlete's current level and picks the right workout.
Paces are injected at generation time — ladders define structure only.

Key design:
- Each level defines a workout template (reps, duration, rest, format)
- Paces come from the athlete's current calibrated paces, not the ladder
- Levels alternate format (time-based, continuous, distance-based) for variety
- The ladder progresses volume first, then pace, then rest reduction
"""

import re
import math

from app.core.pacing import format_pace


# ── Threshold Ladder (5K/10K) ─────────────────────────────────────

THRESHOLD_LADDER_5K = [
    # Level 1: Intro time-based intervals
    {
        "level": 1,
        "name": "2x10min Hard",
        "format": "time_intervals",
        "structure_template": "2x10min at {tp_fast}/mi with 2min jog rest.",
        "purpose": "Intro threshold work. Builds lactate clearance. Broken format — slightly faster than continuous tempo.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 5.5,
        "quality_minutes": 20,
    },
    # Level 2: Continuous tempo
    {
        "level": 2,
        "name": "20min Continuous Tempo",
        "format": "continuous",
        "structure_template": "20min at {tp}/mi. One continuous effort — no rest, so pace is slightly easier than broken intervals.",
        "purpose": "Teaches sustained effort without rest crutch. Mental toughness.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 5.5,
        "quality_minutes": 20,
    },
    # Level 3: Volume bump (time-based)
    {
        "level": 3,
        "name": "2x12min Hard",
        "format": "time_intervals",
        "structure_template": "2x12min at {tp_fast}/mi with 2min jog rest.",
        "purpose": "Extends threshold stimulus — 4 more minutes of quality. Broken format allows slightly faster pace.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.0,
        "quality_minutes": 24,
    },
    # Level 4: More reps (time-based)
    {
        "level": 4,
        "name": "3x10min Hard",
        "format": "time_intervals",
        "structure_template": "3x10min at {tp_fast}/mi with 2min jog rest.",
        "purpose": "Builds lactate threshold — 30min total quality. Broken format allows slightly faster pace.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_minutes": 30,
    },
    # Level 5: Longer continuous
    {
        "level": 5,
        "name": "25min Continuous Tempo",
        "format": "continuous",
        "structure_template": "25min at {tp}/mi. One continuous effort — lock into rhythm.",
        "purpose": "Extended threshold stimulus. Teaches the body to clear lactate at a sustained pace.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_minutes": 25,
    },
    # Level 6: Longer reps
    {
        "level": 6,
        "name": "2x15min Hard",
        "format": "time_intervals",
        "structure_template": "2x15min at {tp_fast}/mi with 2min jog rest.",
        "purpose": "30min quality in two big chunks. Broken format — slightly faster than continuous tempo.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0,
        "quality_minutes": 30,
    },
    # Level 7: High volume time-based
    {
        "level": 7,
        "name": "3x12min Hard",
        "format": "time_intervals",
        "structure_template": "3x12min at {tp_fast}/mi with 2min jog rest.",
        "purpose": "36min total threshold — approaching peak time-based volume. Broken format allows faster pace.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.5,
        "quality_minutes": 36,
    },
    # Level 8: Peak continuous
    {
        "level": 8,
        "name": "30min Continuous Tempo",
        "format": "continuous",
        "structure_template": "30min at {tp}/mi. Peak continuous threshold. Lock in and hold.",
        "purpose": "Peak continuous threshold volume. 30 minutes of sustained hard effort.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.5,
        "quality_minutes": 30,
    },
    # Level 9: Switch to distance-based
    {
        "level": 9,
        "name": "2x2mi Threshold",
        "format": "distance_intervals",
        "structure_template": "2x2mi at {tp_fast}/mi with 0.5mi easy jog rest.",
        "purpose": "Distance-based threshold. Pace discipline over measured distance.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.5,
        "quality_minutes": 28,
    },
    # Level 10: More distance reps
    {
        "level": 10,
        "name": "3x2mi Threshold",
        "format": "distance_intervals",
        "structure_template": "3x2mi at {tp_fast}/mi with 0.5mi easy jog rest.",
        "purpose": "6 miles at threshold. The staple distance-based threshold workout.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_minutes": 42,
    },
    # Level 11: Longer reps
    {
        "level": 11,
        "name": "2x3mi Threshold",
        "format": "distance_intervals",
        "structure_template": "2x3mi at {tp_fast}/mi with 1mi easy float between.",
        "purpose": "Longer reps build ability to hold threshold for extended periods.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_minutes": 42,
    },
    # Level 12: Peak threshold (combo format)
    {
        "level": 12,
        "name": "20-30-20 Sandwich",
        "format": "continuous",
        "structure_template": "20min easy, 30min hard at {tp}/mi, 20min easy.",
        "purpose": "Sustained threshold with built-in warmup/cooldown. Peak threshold session.",
        "warmup": "Built into workout", "cooldown": "Built into workout",
        "total_miles": 8.0,
        "quality_minutes": 30,
    },
]


# ── Interval Ladder (5K/10K) ──────────────────────────────────────

INTERVAL_LADDER_5K = [
    # Level 1: Intro VO2max
    {
        "level": 1,
        "name": "4x800m",
        "format": "track_intervals",
        "structure_template": "4x800m at {ip_range}/mi with 2min jog rest.",
        "purpose": "Intro VO2max work. Short enough to maintain form with generous rest.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 5.0,
        "quality_miles": 2.0,
    },
    # Level 2: Speed variety
    {
        "level": 2,
        "name": "6x400m Fast",
        "format": "speed",
        "structure_template": "6x400m at {sp}/mi with 200m jog rest.",
        "purpose": "Pure speed development. Improves running economy and neuromuscular coordination.",
        "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy",
        "total_miles": 5.0,
        "quality_miles": 1.5,
    },
    # Level 3: +1 rep
    {
        "level": 3,
        "name": "5x800m",
        "format": "track_intervals",
        "structure_template": "5x800m at {ip_range}/mi with 90sec jog rest.",
        "purpose": "Building VO2max volume. One more rep, slightly tighter rest.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 5.5,
        "quality_miles": 2.5,
    },
    # Level 4: Longer reps
    {
        "level": 4,
        "name": "5x1K",
        "format": "track_intervals",
        "structure_template": "5x1K at {ip_range}/mi with 200m jog rest.",
        "purpose": "Kilometer repeats — longer time at VO2max per rep. Builds speed endurance.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.1,
    },
    # Level 5: 6x800 (volume)
    {
        "level": 5,
        "name": "6x800m",
        "format": "track_intervals",
        "structure_template": "6x800m at {ip_range}/mi with 90sec jog rest.",
        "purpose": "Develops VO2max. 3 miles of quality — hard but controlled.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.0,
    },
    # Level 6: Combo session (VO2max + speed kicker)
    {
        "level": 6,
        "name": "6x800m + 4x200m",
        "format": "combo",
        "structure_template": "6x800m at {ip_range}/mi with 90sec jog rest, then 4x200m at {sp}/mi with full recovery.",
        "purpose": "VO2max stimulus with speed kicker. Develops economy on tired legs.",
        "warmup": "1.5mi easy", "cooldown": "1mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.5,
    },
    # Level 7: Peak 800m volume
    {
        "level": 7,
        "name": "8x800m",
        "format": "track_intervals",
        "structure_template": "8x800m at {ip_range}/mi with 90sec jog rest.",
        "purpose": "High-volume VO2max. 4 miles of quality — peak 800m session.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.5,
        "quality_miles": 4.0,
    },
    # Level 8: Mile repeats
    {
        "level": 8,
        "name": "4x1mi",
        "format": "track_intervals",
        "structure_template": "4x1mi at {ip_range}/mi with 3min jog rest.",
        "purpose": "Mile repeats — sustained VO2max effort. Race-pace confidence builder.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 8.0,
        "quality_miles": 4.0,
    },
    # Level 9: Race-pace specific (shift from IP to RP)
    {
        "level": 9,
        "name": "5x1K at Race Pace",
        "format": "race_specific",
        "structure_template": "5x1K at {rp_range}/mi with 200m jog rest. Exactly goal 5K pace.",
        "purpose": "Race-pace practice. Teaches the body exactly what 5K effort feels like.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.1,
    },
    # Level 10: Longer race-pace reps
    {
        "level": 10,
        "name": "5x1200m at Race Pace",
        "format": "race_specific",
        "structure_template": "5x1200m at {rp_range}/mi with 2min jog rest.",
        "purpose": "Extends time at race pace per rep. Builds sustained speed endurance.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0,
        "quality_miles": 3.7,
    },
    # Level 11: Peak race-pace volume
    {
        "level": 11,
        "name": "6x1K at Race Pace",
        "format": "race_specific",
        "structure_template": "6x1K at {rp_range}/mi with 90sec jog rest. Tighter rest, more volume.",
        "purpose": "Peak race-pace volume. 6K at 5K pace — the ultimate 5K workout.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0,
        "quality_miles": 3.7,
    },
    # Level 12: Confidence builder
    {
        "level": 12,
        "name": "4x1mi at Race Pace",
        "format": "race_specific",
        "structure_template": "4x1mi at {rp_range}/mi with 3min jog rest. If you can hold 5K pace for 4 separate miles, you can hold it for 3.1.",
        "purpose": "The ultimate 5K confidence builder. Race-pace mile repeats.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 8.0,
        "quality_miles": 4.0,
    },
]


def program_key(distance: str | None = "5k") -> str:
    """Levels are comparable only inside the same versioned distance program."""
    return f"ladder-v2:{distance or 'general'}"


def get_ladder(category: str, distance: str = "5k", phase: str = "build") -> list[dict]:
    """Stride templates, not validated physiological dose equivalences.

    Level orders the local program's work volume. Phase reduces that envelope or
    changes rep length; it never changes the athlete's stored level or pace.
    """
    if category not in ("threshold", "intervals"):
        return []
    if distance == "5k" and phase in ("build", "general"):
        return THRESHOLD_LADDER_5K if category == "threshold" else INTERVAL_LADDER_5K
    # Threshold duration grows more gradually for mileage/general/ultra programs.
    aerobic = distance in ("mileage", "general", "comeback", "50k", "50mi", "100k", "100mi")
    duration = 6 if aerobic else 8 if distance in ("10k", "5k") else 10
    result = []
    for level in range(1, 13):
        reps = 2 + (level - 1) // 4
        rep_minutes = duration + (level - 1) % 4
        if phase == "base":
            reps, rep_minutes = 2, max(5, rep_minutes - 3)
        elif phase in ("taper", "race_week", "recovery"):
            reps, rep_minutes = 2, 4 if phase == "taper" else 3
        if category == "threshold":
            name = f"{reps}x{rep_minutes}min Threshold"
            structure = f"{reps}x{rep_minutes}min at {{tp_fast}}/mi with 2min jog rest."
            quality_minutes = reps * rep_minutes
            total = round((3 + quality_minutes / 7 + (reps - 1) * 0.2) * 2) / 2
        else:
            # Longer-race intervals emphasize controlled aerobic repetitions;
            # never substitute an aspirational goal race pace for demonstrated pace.
            meters = 400 if phase in ("base", "taper", "race_week", "recovery") else (800 if distance == "5k" else 1200 if phase == "peak" else 1000 if distance == "10k" else 1200)
            reps = (4 if phase == "base" else 3) if phase in ("base", "taper", "race_week", "recovery") else 3 + (level - 1) // 3
            pace = "{ip_range}"
            name = f"{reps}x{meters}m Intervals"
            structure = f"{reps}x{meters}m at {pace}/mi with 2min jog rest."
            quality_minutes = 0
            total = round((3 + reps * meters / 1609.34 + (reps - 1) * 0.2) * 2) / 2
        # Peak half/marathon sessions sustain the same minutes in fewer pieces.
        if category == "threshold" and phase == "peak" and distance in ("half", "marathon"):
            reps, rep_minutes = 2, quality_minutes // 2
            name = f"2x{rep_minutes}min Threshold"
            structure = f"2x{rep_minutes}min at {{tp_fast}}/mi with 2min jog rest."
        result.append({"level": level, "name": name, "format": "time_intervals" if category == "threshold" else "track_intervals",
                       "structure_template": structure, "purpose": f"{distance} {phase}: controlled {category} work within the weekly budget.",
                       "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": total,
                       "work_spec": {"reps": reps, "seconds": rep_minutes * 60 if category == "threshold" else None, "meters": meters if category == "intervals" else None}})
    return result


REP_MILES = {"200m": 0.124274, "400m": 0.248548, "600m": 0.372823, "800m": 0.497097,
             "1K": 0.621371, "1k": 0.621371, "1200m": 0.745645, "1mi": 1.0, "1.5mi": 1.5}
_REP_RE = re.compile(r"(\d+x)(200m|400m|600m|800m|1K|1k|1200m|1\.5mi|1mi) at (\d+:\d{2})(?:-(\d+:\d{2}))?/mi")


def _sec(p: str) -> int:
    m, s = p.split(":")
    return int(m) * 60 + int(s)


def with_rep_times(structure: str) -> str:
    """Write reps the way runners talk: "6x800m in 2:55-3:00 (5:50-6:00/mi)".

    Per-mile paces stay in parentheses (that's what the watch shows), but the
    rep split is what you actually look at on the track.
    """
    def repl(m: re.Match) -> str:
        reps, dist, fast, slow = m.group(1), m.group(2), m.group(3), m.group(4)
        miles = REP_MILES[dist]
        t1 = format_pace(round(_sec(fast) * miles))
        rng = f"{fast}-{slow}" if slow else fast
        times = f"{t1}-{format_pace(round(_sec(slow) * miles))}" if slow else t1
        return f"{reps}{dist} in {times} ({rng}/mi)"

    return _REP_RE.sub(repl, structure)


def get_workout_at_level(
    category: str,
    level: int,
    paces: dict,
    distance: str = "5k",
    phase: str = "build",
) -> dict:
    """Build a concrete workout from a ladder level with injected paces.

    Returns a dict compatible with what plan_engine expects from the old
    workout library (name, structure, purpose, warmup, cooldown, total_miles).
    """
    ladder = get_ladder(category, distance, phase)
    if not ladder:
        return _fallback_workout(category, paces)

    # Clamp level to valid range
    level = max(1, min(level, len(ladder)))
    template = ladder[level - 1]

    tp_sec = paces.get("tempo_pace", paces.get("threshold_pace", 420))
    broken = paces.get("broken_threshold_pace", tp_sec - 10)
    ip = paces.get("interval_pace", 370)
    ipf = paces.get("interval_pace_fast", ip - 10)
    rp = paces.get("race_pace", ip)

    from app.core.workout_data import prescription, render, segment
    if distance == "5k" and phase in ("build", "general"):
        if category == "threshold":
            specs = [(2, 600, None), (1, 1200, None), (2, 720, None), (3, 600, None),
                     (1, 1500, None), (2, 900, None), (3, 720, None), (1, 1800, None),
                     (2, None, 2 * 1609.34), (3, None, 2 * 1609.34), (2, None, 3 * 1609.34), (1, 1800, None)]
            reps, seconds, meters = specs[level - 1]
            pace = tp_sec if reps == 1 else broken
            segments = [segment(reps, meters=meters, seconds=seconds, fast=pace, slow=pace,
                                recovery_seconds=120 if reps > 1 and not meters else None,
                                recovery_meters=(1609.34 if level == 11 else 804.67) if meters else None)]
        else:
            specs = [(4, 800), (6, 400), (5, 800), (5, 1000), (6, 800), (6, 800),
                     (8, 800), (4, 1609.34), (5, 1000), (5, 1200), (6, 1000), (4, 1609.34)]
            reps, meters = specs[level - 1]
            fast, slow = (paces.get("strides_pace", 300),) * 2 if level == 2 else ((rp - 5, rp) if level >= 9 else (ipf, ip))
            rest = [120, None, 90, None, 90, 90, 90, 180, None, 120, 90, 180][level - 1]
            segments = [segment(reps, meters=meters, fast=fast, slow=slow, recovery_seconds=rest, recovery_meters=200 if rest is None else None, category="strides" if level == 2 else "intervals")]
            if level == 6:
                segments.append(segment(4, meters=200, fast=paces.get("strides_pace", 300), slow=paces.get("strides_pace", 300), category="strides"))
    else:
        # These values are authored by the numeric program builder above.
        spec = template["work_spec"]
        if category == "threshold":
            segments = [segment(spec["reps"], seconds=spec["seconds"], fast=broken, slow=broken, recovery_seconds=120)]
        else:
            fast, slow = ipf, ip
            segments = [segment(spec["reps"], meters=spec["meters"], fast=fast, slow=slow, recovery_seconds=120)]
    data = prescription(category, template["format"], segments, program=program_key(distance), phase=phase, level=level)
    data["easy_pace_sec_per_mile"] = paces.get("long_run_pace")
    data["base_pace_sec_per_mile"] = tp_sec if category == "threshold" else ip
    # Full numeric session distance includes easy bookends and jog recoveries.
    # Time-based work uses the faster bound, avoiding budget underestimation.
    easy = paces.get("long_run_pace", 540)
    warmup = template.get("warmup", "1.5mi easy")
    cooldown = template.get("cooldown", "1.5mi easy")
    def bookend(text):
        m = re.match(r"([\d.]+)mi", text)
        return float(m.group(1)) * 1609.34 if m else 1200 / easy * 1609.34
    data['warmup'] = segment(meters=bookend(warmup))
    data['cooldown'] = segment(meters=bookend(cooldown))
    if warmup == "Built into workout":
        warmup = cooldown = "20min easy"
    total_meters = data['warmup']['distance_meters'] + data['cooldown']['distance_meters']
    for spec in segments:
        work = spec['distance_meters'] or spec['duration_seconds'] / spec['pace_range_sec_per_mile']['fast'] * 1609.34
        recovery = spec.get('recovery_meters') or (spec.get('recovery_seconds') or 0) / easy * 1609.34
        total_meters += spec['reps'] * work + max(0, spec['reps'] - 1) * recovery
    total_miles = math.ceil(total_meters / 1609.34 * 2) / 2
    data['total_distance_meters'] = round(total_meters, 2)
    structure = render(data)

    return {
        "name": template["name"],
        "structure": structure,
        "prescription": data,
        "purpose": template["purpose"],
        "program_key": program_key(distance),
        "category": category,
        "phase": phase,
        "level": level,
        "warmup": warmup,
        "cooldown": cooldown,
        "total_miles": total_miles,
    }


def get_deload_workout(
    category: str,
    current_level: int,
    paces: dict,
    distance: str = "5k",
    phase: str = "build",
) -> dict:
    """Pick a deload workout: lower half of current level, reduced volume."""
    # Drop to roughly level/2, minimum level 1
    deload_level = max(1, current_level // 2)
    return get_workout_at_level(category, deload_level, paces, distance, phase)


def get_week2_variant(
    category: str,
    level: int,
    paces: dict,
    distance: str = "5k",
    phase: str = "build",
) -> dict:
    """Return a week-2 variant for within-block micro-progression.

    Strategy: if current level is time-based, week 2 uses the next level
    (which is often a format change). If current level is at the top,
    stay at the same level.
    """
    ladder = get_ladder(category, distance, phase)
    if not ladder or level >= len(ladder):
        return get_workout_at_level(category, level, paces, distance, phase)

    # Week 2 gets the next level as a "taste" of what's coming
    return get_workout_at_level(category, level + 1, paces, distance, phase)


def _fallback_workout(category: str, paces: dict) -> dict:
    """Fallback if no ladder exists for this category."""
    tp = format_pace(paces.get("tempo_pace", 420))
    return {
        "name": "Tempo Run",
        "structure": f"25min at {tp}/mi.",
        "purpose": "Builds lactate threshold.",
        "warmup": "1.5mi easy",
        "cooldown": "1.5mi easy",
        "total_miles": 6.5,
    }
