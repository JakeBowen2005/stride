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

from app.core.pacing import format_pace, pace_range


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
        "rep_adjust_sec": 0,
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
        "rep_adjust_sec": 0,
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
        "rep_adjust_sec": 5,
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
        "rep_adjust_sec": 0,
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
        "rep_adjust_sec": 0,
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
        "rep_adjust_sec": 0,
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
        "rep_adjust_sec": 12,
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
        "rep_adjust_sec": 8,
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


# -- Threshold Ladder (Marathon / Half) ----------------------------
#
# Marathon threshold work is distance-based cruise intervals, not short
# time-based reps. The progression mirrors what actually built the 2:58:
# 2x2mi -> 3x2mi -> 2x3mi -> 4x2mi, with MP-specific work layered in as
# the ladder climbs. Float/jog rest, never standing rest.

THRESHOLD_LADDER_MARATHON = [
    {
        "level": 1,
        "name": "2x2mi Threshold",
        "format": "distance_intervals",
        "structure_template": "2x2mi at {tp_fast}/mi with 0.5mi easy jog float.",
        "purpose": "Intro cruise intervals. 4mi at threshold - the base unit of marathon threshold work.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.5,
        "quality_miles": 4.0,
    },
    {
        "level": 2,
        "name": "20min Continuous Tempo",
        "format": "continuous",
        "structure_template": "20min continuous at {tp}/mi. No rest, so pace is slightly easier than broken reps.",
        "purpose": "Sustained threshold without the rest crutch. Builds the mental side of marathon pacing.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.0,
    },
    {
        "level": 3,
        "name": "MP Pace Run - 4mi",
        "format": "mp_continuous",
        "structure_template": "4mi continuous at goal MP ({mp}/mi). Controlled - can push if it feels good, but do not force it.",
        "purpose": "First taste of sustained race pace. Everything in a marathon block revolves around this number.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 8.0,
        "quality_miles": 4.0,
    },
    {
        "level": 4,
        "name": "3x2mi Threshold",
        "format": "distance_intervals",
        "structure_template": "3x2mi at {tp_fast}/mi with 0.5mi easy jog float.",
        "purpose": "The staple. 6mi at threshold - the most important non-long-run workout for the marathon.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_miles": 6.0,
    },
    {
        "level": 5,
        "name": "25min Continuous Tempo",
        "format": "continuous",
        "structure_template": "25min continuous at {tp}/mi. Lock into rhythm and hold.",
        "purpose": "Extended continuous threshold. Raises the ceiling that marathon pace sits under.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0,
        "quality_miles": 3.7,
    },
    {
        "level": 6,
        "name": "MP Pace Run - 6mi",
        "format": "mp_continuous",
        "structure_template": "6mi continuous at goal MP ({mp}/mi). Demanding but not a race - stay disciplined.",
        "purpose": "Sustained MP block. Trains glycogen use and pacing automaticity at race effort.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 10.0,
        "quality_miles": 6.0,
    },
    {
        "level": 7,
        "name": "2x3mi Threshold",
        "format": "distance_intervals",
        "structure_template": "2x3mi at {tp_fast}/mi with 1mi easy float between.",
        "purpose": "Longer reps. Teaches holding threshold effort for extended stretches - marathon specific.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_miles": 6.0,
    },
    {
        "level": 8,
        "name": "4x2mi Threshold",
        "format": "distance_intervals",
        "structure_template": "4x2mi at {tp_fast}/mi with 0.5mi jog float. Negative split it.",
        "purpose": "Peak threshold volume - 8mi at threshold. This is the engine builder.",
        "warmup": "2mi easy", "cooldown": "1mi easy",
        "total_miles": 12.5,
        "quality_miles": 8.0,
    },
    {
        "level": 9,
        "name": "2x2mi Threshold + 2x10min Tempo",
        "format": "combo",
        "structure_template": "2x2mi at {tp_fast}/mi with 0.5mi jog, then 2x10min at {tp}/mi with 2min jog.",
        "purpose": "Threshold volume with a tempo kicker. Quality work on already-tired legs.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 10.5,
        "quality_miles": 8.0,
    },
    {
        "level": 10,
        "name": "3x3mi Threshold",
        "format": "distance_intervals",
        "structure_template": "3x3mi at {tp_fast}/mi with 1mi easy float between.",
        "purpose": "9mi at threshold across three long reps. Late-block specific endurance.",
        "warmup": "2mi easy", "cooldown": "1mi easy",
        "total_miles": 15.0,
        "quality_miles": 9.0,
    },
    {
        "level": 11,
        "name": "2mi Threshold + 6mi MP",
        "format": "combo",
        "structure_template": "2mi at {tp_fast}/mi, 0.5mi float, then 6mi at goal MP ({mp}/mi).",
        "purpose": "Threshold primer into a long MP block. Simulates racing on pre-fatigued legs.",
        "warmup": "2mi easy", "cooldown": "1.5mi easy",
        "total_miles": 13.0,
        "quality_miles": 8.0,
    },
    {
        "level": 12,
        "name": "3x3mi at MP",
        "format": "mp_block",
        "structure_template": "3x3mi at goal MP ({mp}/mi) with 0.5mi jog float. 9 miles at race pace - this is a hard day.",
        "purpose": "Peak marathon-specific volume. Only earned after holding MP for 5-6mi in workouts and long runs.",
        "warmup": "2mi easy", "cooldown": "1mi easy",
        "total_miles": 13.0,
        "quality_miles": 9.0,
    },
]


# -- Interval Ladder (Marathon / Half) -----------------------------
#
# For the marathon, VO2max work is maintenance, not the main course.
# Reps skew long (1K, mile, 1.5mi) and the ladder tops out at
# marathon-supporting speed endurance rather than 5K race-pace volume.

INTERVAL_LADDER_MARATHON = [
    {
        "level": 1,
        "name": "4x800m",
        "rep_adjust_sec": 0,
        "format": "track_intervals",
        "structure_template": "4x800m at {ip_range}/mi with 90sec jog rest.",
        "purpose": "Intro VO2max. Short reps, generous rest - reawakens turnover without wrecking the week.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 5.0,
        "quality_miles": 2.0,
    },
    {
        "level": 2,
        "name": "6x400m Fast",
        "format": "speed",
        "structure_template": "6x400m at {sp}/mi with 200m jog rest.",
        "purpose": "Pure speed and economy. Keeps fast-twitch fibers alive during high-volume aerobic work.",
        "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy",
        "total_miles": 5.0,
        "quality_miles": 1.5,
    },
    {
        "level": 3,
        "name": "6x800m",
        "rep_adjust_sec": 0,
        "format": "track_intervals",
        "structure_template": "6x800m at {ip_range}/mi with 90sec jog rest.",
        "purpose": "3mi of quality at VO2max. Hard but repeatable inside a high-mileage week.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.0,
    },
    {
        "level": 4,
        "name": "5x1K",
        "rep_adjust_sec": 5,
        "format": "track_intervals",
        "structure_template": "5x1K at {ip_range}/mi with 200m jog rest.",
        "purpose": "Longer time at VO2max per rep. The marathoner version of interval work.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 6.5,
        "quality_miles": 3.1,
    },
    {
        "level": 5,
        "name": "4x1mi",
        "rep_adjust_sec": 12,
        "format": "track_intervals",
        "structure_template": "4x1mi at {ip_range}/mi with 3min jog rest.",
        "purpose": "Mile repeats. Sustained aerobic power - the ceiling that marathon pace lives under.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 9.0,
        "quality_miles": 4.0,
    },
    {
        "level": 6,
        "name": "5x1K + 2mi Threshold",
        "rep_adjust_sec": 5,
        "format": "combo",
        "structure_template": "5x1K at {ip_range}/mi with 400m jog, then 2mi continuous at {tp_fast}/mi.",
        "purpose": "VO2max stimulus with a threshold finish. Running strong on tired legs.",
        "warmup": "2mi easy", "cooldown": "1mi easy",
        "total_miles": 10.0,
        "quality_miles": 5.1,
    },
    {
        "level": 7,
        "name": "5x1mi",
        "rep_adjust_sec": 12,
        "format": "track_intervals",
        "structure_template": "5x1mi at {ip_range}/mi with 3min jog rest. Negative split.",
        "purpose": "5 miles at interval pace. Serious speed endurance on a marathon base.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 10.0,
        "quality_miles": 5.0,
    },
    {
        "level": 8,
        "name": "4x1.5mi",
        "format": "extended_reps",
        "structure_template": "4x1.5mi at {ext}/mi with 3min jog rest. This is an easier threshold day, not an interval session.",
        "purpose": "Extended reps just under threshold. Marathon-specific endurance at controlled effort.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 10.5,
        "quality_miles": 6.0,
    },
    {
        "level": 9,
        "name": "6x1K",
        "rep_adjust_sec": 5,
        "format": "track_intervals",
        "structure_template": "6x1K at {ip_range}/mi with 200m jog rest.",
        "purpose": "Peak 1K volume. Maintains the aerobic ceiling deep into a heavy block.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0,
        "quality_miles": 3.7,
    },
    {
        "level": 10,
        "name": "3x2mi",
        "format": "extended_reps",
        "structure_template": "3x2mi at {ext}/mi with 0.5mi jog float.",
        "purpose": "Six miles slightly under threshold. Bridges VO2max work into race-specific fitness.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_miles": 6.0,
    },
    {
        "level": 11,
        "name": "6x1mi",
        "rep_adjust_sec": 12,
        "format": "track_intervals",
        "structure_template": "6x1mi at {ip_range}/mi with 3min jog rest.",
        "purpose": "Peak mile-repeat volume. Big aerobic power session - use sparingly.",
        "warmup": "2mi easy", "cooldown": "2mi easy",
        "total_miles": 11.0,
        "quality_miles": 6.0,
    },
    {
        "level": 12,
        "name": "Progressive 8mi",
        "format": "progression",
        "structure_template": "8mi progression: start easy, drop to steady by mile 4, finish the last 2mi at goal MP ({mp}/mi) or faster.",
        "purpose": "Race-rhythm rehearsal under fatigue. Teaches closing hard when it hurts.",
        "warmup": "Built into workout", "cooldown": "1mi very easy",
        "total_miles": 9.0,
        "quality_miles": 8.0,
    },
]


LADDERS = {
    ("threshold", "5k"): THRESHOLD_LADDER_5K,
    ("threshold", "10k"): THRESHOLD_LADDER_5K,
    ("threshold", "half"): THRESHOLD_LADDER_MARATHON,
    ("threshold", "marathon"): THRESHOLD_LADDER_MARATHON,
    ("intervals", "5k"): INTERVAL_LADDER_5K,
    ("intervals", "10k"): INTERVAL_LADDER_5K,
    ("intervals", "half"): INTERVAL_LADDER_MARATHON,
    ("intervals", "marathon"): INTERVAL_LADDER_MARATHON,
}


def get_ladder(category: str, distance: str = "5k") -> list[dict]:
    """Return the progression ladder for a given category and goal distance.

    5K/10K use short time-based threshold reps and track intervals.
    Half/marathon use distance-based cruise intervals and MP-specific work.
    """
    dist = (distance or "5k").lower()
    return LADDERS.get((category, dist)) or LADDERS.get((category, "5k")) or []


def ladder_length(category: str, distance: str = "5k") -> int:
    """Number of levels in a ladder. Used to clamp progression decisions."""
    return len(get_ladder(category, distance)) or 1


def get_workout_at_level(
    category: str,
    level: int,
    paces: dict,
    distance: str = "5k",
) -> dict:
    """Build a concrete workout from a ladder level with injected paces.

    Returns a dict compatible with what plan_engine expects from the old
    workout library (name, structure, purpose, warmup, cooldown, total_miles).
    """
    ladder = get_ladder(category, distance)
    if not ladder:
        return _fallback_workout(category, paces)

    # Clamp level to valid range
    level = max(1, min(level, len(ladder)))
    template = ladder[level - 1]

    # Build pace strings for template substitution.
    #   tp      = continuous tempo (no rest, so ~10 sec/mi easier)
    #   tp_fast = broken threshold reps with float/jog rest
    # _build_current_paces guarantees tempo_pace == threshold_pace + 10,
    # so tp_fast lands exactly on threshold pace.
    thr_sec = paces.get("threshold_pace") or paces.get("tempo_pace") or 420
    tp_sec = paces.get("tempo_pace") or (thr_sec + 10)
    tp = format_pace(tp_sec)
    tp_fast = format_pace(min(thr_sec, tp_sec - 10))
    # interval_pace is anchored on 800m repeats (that is what the calibrator
    # parses most often). Longer reps get an offset -- see rep_adjust_sec.
    rep_adjust = template.get("rep_adjust_sec", 0)
    ip = paces.get("interval_pace", 370) + rep_adjust
    ipf = paces.get("interval_pace_fast", paces.get("interval_pace", 370) - 10) + rep_adjust
    ip_range = f"{format_pace(ipf)}-{format_pace(ip)}"
    sp = format_pace(paces.get("strides_pace", 300))

    # Extended reps (1.5mi / 2mi): just under threshold, never interval pace.
    ext = format_pace(thr_sec - 10)

    # Goal race pace. For 5K/10K ladders this is the goal 5K/10K pace; for
    # marathon/half ladders it is goal MP. Falls back to threshold so a
    # goal-less plan still renders something sane instead of crashing.
    mp_sec = paces.get("goal_race_pace") or paces.get("race_pace") or thr_sec
    mp = format_pace(mp_sec)

    rp = paces.get("race_pace", ip)
    rpf = rp - 5  # slightly faster end
    rp_range = f"{format_pace(rpf)}-{format_pace(rp)}"

    structure = template["structure_template"].format(
        tp=tp,
        tp_fast=tp_fast,
        ip_range=ip_range,
        sp=sp,
        rp_range=rp_range,
        ext=ext,
        mp=mp,
    )

    return {
        "name": template["name"],
        "structure": structure,
        "purpose": template["purpose"],
        "warmup": template.get("warmup", "1.5mi easy"),
        "cooldown": template.get("cooldown", "1.5mi easy"),
        "total_miles": template.get("total_miles", 6.0),
    }


def get_deload_workout(
    category: str,
    current_level: int,
    paces: dict,
    distance: str = "5k",
) -> dict:
    """Pick a deload workout: lower half of current level, reduced volume."""
    # Drop to roughly level/2, minimum level 1
    deload_level = max(1, current_level // 2)
    return get_workout_at_level(category, deload_level, paces, distance)


def get_week2_variant(
    category: str,
    level: int,
    paces: dict,
    distance: str = "5k",
) -> dict:
    """Return a week-2 variant for within-block micro-progression.

    Strategy: if current level is time-based, week 2 uses the next level
    (which is often a format change). If current level is at the top,
    stay at the same level.
    """
    ladder = get_ladder(category, distance)
    if not ladder or level >= len(ladder):
        return get_workout_at_level(category, level, paces, distance)

    # Week 2 gets the next level as a "taste" of what's coming
    return get_workout_at_level(category, level + 1, paces, distance)


def max_level(category: str, distance: str = "5k") -> int:
    """Highest valid level for this ladder (progression clamp)."""
    return ladder_length(category, distance)


def level_requires_mp(category: str, level: int, distance: str = "5k") -> bool:
    """True if this ladder level prescribes work at goal race pace."""
    ladder = get_ladder(category, distance)
    if not ladder:
        return False
    level = max(1, min(level, len(ladder)))
    return "{mp}" in ladder[level - 1].get("structure_template", "")


def highest_non_mp_level(category: str, max_lvl: int, distance: str = "5k") -> int:
    """Highest level at or below max_lvl that does not prescribe goal-pace work.

    Used when goal race pace is still faster than the athlete's current
    threshold pace -- prescribing "6mi at goal MP" in that state asks for a
    workout harder than their threshold session, which is backwards.
    """
    for lvl in range(max(1, max_lvl), 0, -1):
        if not level_requires_mp(category, lvl, distance):
            return lvl
    return 1


# ── Taper workouts ────────────────────────────────────────────────
#
# A taper session is not a scaled-down ladder workout. Ladder levels carry a
# fixed total_miles -- level 8 threshold is 12.5 miles whether you are 12
# weeks out or 6 days out -- and 12.5 miles of quality the week of a marathon
# undoes the taper it is supposed to be part of.
#
# The research (Bosquet meta-analysis; PMC 2021) is specific: keep INTENSITY
# and keep FREQUENCY, shorten the SESSION. These are short, sharp, and
# deliberately easy to finish feeling like you had more in the tank.
#
# Structures follow docs/marathon-training-science.md sample taper.

TAPER_WORKOUTS = {
    "marathon": {
        3: {
            "intervals": {
                "name": "4x800m (taper)",
                "structure_template": "4x800m at {ip_range}/mi with 90sec jog rest. Crisp, controlled, stop while it still feels good.",
                "purpose": "Keeps VO2max and turnover alive on a fraction of the usual volume.",
                "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": 5.0,
            },
            "threshold": {
                "name": "2x2mi Threshold (taper)",
                "structure_template": "2x2mi at {tp_fast}/mi with 0.5mi jog float. A touch-up, not a test.",
                "purpose": "Holds threshold sharpness while volume drops. Finish wanting more.",
                "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": 7.5,
            },
        },
        2: {
            "intervals": {
                "name": "6x400m (taper)",
                "structure_template": "6x400m at {sp}/mi with 400m jog rest. Short and sharp.",
                "purpose": "Neuromuscular sharpener. Costs almost nothing aerobically.",
                "warmup": "1.5mi easy + 4 strides", "cooldown": "1mi easy", "total_miles": 5.0,
            },
            "threshold": {
                "name": "3mi at MP (taper)",
                "structure_template": "3mi continuous at goal MP ({mp}/mi). Locking in race rhythm, nothing more.",
                "purpose": "Rehearses race pace on fresh legs. Confidence, not fitness — the fitness is banked.",
                "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": 6.0,
            },
        },
        1: {
            "intervals": {
                "name": "4x800m at 5K effort (race week)",
                "structure_template": "4x800m at {ip_range}/mi with 2min jog rest. Six days out — wake the legs up, do not tire them.",
                "purpose": "Final VO2max touch. Six days is enough to absorb it and nothing more.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.5,
            },
            "threshold": {
                "name": "2mi at MP (race week)",
                "structure_template": "2mi at goal MP ({mp}/mi), then 4x100m strides. Should feel almost too easy.",
                "purpose": "Last sharpener. Four days out: rehearsal only, zero fatigue cost.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.5,
            },
        },
    },
    "half": {
        2: {
            "intervals": {
                "name": "5x800m (taper)",
                "structure_template": "5x800m at {ip_range}/mi with 90sec jog rest.",
                "purpose": "Keeps turnover sharp while volume drops.",
                "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": 5.5,
            },
            "threshold": {
                "name": "2x2mi Threshold (taper)",
                "structure_template": "2x2mi at {tp_fast}/mi with 0.5mi jog float. Controlled.",
                "purpose": "Holds threshold sharpness while volume drops.",
                "warmup": "1.5mi easy", "cooldown": "1.5mi easy", "total_miles": 7.5,
            },
        },
        1: {
            "intervals": {
                "name": "4x400m (race week)",
                "structure_template": "4x400m at {sp}/mi with 400m jog rest.",
                "purpose": "Neuromuscular sharpener at zero fatigue cost.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.0,
            },
            "threshold": {
                "name": "2mi at Race Pace (race week)",
                "structure_template": "2mi at goal race pace ({mp}/mi), then 4x100m strides.",
                "purpose": "Final sharpener on fresh legs.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.5,
            },
        },
    },
    "10k": {
        1: {
            "intervals": {
                "name": "3x1K at Race Pace (race week)",
                "structure_template": "3x1K at goal race pace ({mp}/mi) with 3min jog rest. Crisp, not exhausting.",
                "purpose": "Race-pace sharpener. Reminds the legs what the effort feels like.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 5.0,
            },
            "threshold": {
                "name": "2mi at Race Pace (race week)",
                "structure_template": "2mi at goal race pace ({mp}/mi), then 4x100m strides.",
                "purpose": "Final rehearsal at goal effort.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.5,
            },
        },
    },
    "5k": {
        1: {
            "intervals": {
                "name": "4x400m at Race Pace (race week)",
                "structure_template": "4x400m at goal race pace ({mp}/mi) with 400m jog rest. Sharp and short.",
                "purpose": "Neuromuscular sharpener. Leaves you fresher, not fitter.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 4.5,
            },
            "threshold": {
                "name": "1mi at Race Pace (race week)",
                "structure_template": "1mi at goal race pace ({mp}/mi), then 4x100m strides.",
                "purpose": "Final rehearsal. Anything more this week costs more than it gives.",
                "warmup": "1.5mi easy", "cooldown": "1mi easy", "total_miles": 3.5,
            },
        },
    },
}


def get_taper_workout(
    weeks_out: int,
    paces: dict,
    distance: str = "marathon",
    category: str = "threshold",
) -> dict | None:
    """Short race-sharpening session for a taper week.

    `category` mirrors the ladder categories so the two weekly quality slots
    get different sessions -- Tuesday sharp and short, Thursday at race pace.
    """
    dist = (distance or "marathon").lower()
    table = TAPER_WORKOUTS.get(dist) or TAPER_WORKOUTS["marathon"]
    if not table:
        return None

    week_entry = table.get(weeks_out)
    if not week_entry:
        # Closer than the table goes (or further out): use the nearest defined
        # week rather than dropping quality entirely.
        nearest = min(table, key=lambda k: abs(k - weeks_out))
        week_entry = table[nearest]

    template = week_entry.get(category) or next(iter(week_entry.values()))

    thr_sec = paces.get("threshold_pace") or paces.get("tempo_pace") or 420
    tp_sec = paces.get("tempo_pace") or (thr_sec + 10)
    mp_sec = paces.get("goal_race_pace") or paces.get("race_pace") or thr_sec
    ip = paces.get("interval_pace", 370)
    ipf = paces.get("interval_pace_fast", ip - 10)

    structure = template["structure_template"].format(
        tp=format_pace(tp_sec),
        tp_fast=format_pace(min(thr_sec, tp_sec - 10)),
        mp=format_pace(mp_sec),
        sp=format_pace(paces.get("strides_pace", 300)),
        ip_range=f"{format_pace(ipf)}-{format_pace(ip)}",
    )
    return {
        "name": template["name"],
        "structure": structure,
        "purpose": template["purpose"],
        "warmup": template.get("warmup", "1.5mi easy"),
        "cooldown": template.get("cooldown", "1mi easy"),
        "total_miles": template.get("total_miles", 6.0),
    }


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
