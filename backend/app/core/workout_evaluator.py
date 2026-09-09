"""Post-workout evaluation engine.

Analyzes Strava workout data against the prescription and produces a
progression decision: ADVANCE, HOLD, REGRESS, or RECALIBRATE.

Uses:
- Parsed splits from Strava descriptions (via pace_calibrator patterns)
- Prescribed workout details (from PlannedWorkout)
- Subjective feel rating (from user feedback)
- Rep-by-rep fade analysis
"""

import re
from dataclasses import dataclass


@dataclass
class WorkoutEvaluation:
    """Result of evaluating a completed workout."""
    decision: str           # "advance", "hold", "regress", "recalibrate"
    reason: str             # human-readable explanation
    pace_diff_sec: float    # avg actual pace - prescribed pace (negative = faster)
    fade_sec: float         # second-half avg - first-half avg (positive = slowed)
    reps_completed: int     # how many reps the runner did
    reps_prescribed: int    # how many were prescribed
    actual_pace_sec: float  # average pace from actual splits (sec/mi)
    new_pace_sec: float | None  # recalibrated pace if decision is recalibrate
    pace_confidence: str = "none"  # "splits" | "none" -- is pace_diff meaningful?
    advance_steps: int = 1  # how many ladder levels to move on an advance


# ── Split Extraction ──────────────────────────────────────────────

# Distance in miles for pace conversion
INTERVAL_MILES = {
    "200": 0.12427,
    "400": 0.24855,
    "600": 0.37282,
    "800": 0.49710,
    "1000": 0.62137,
    "1k": 0.62137,
    "1200": 0.74565,
    "mile": 1.0,
}


def extract_splits_from_description(description: str) -> dict:
    """Parse a Strava description and extract all interval splits.

    Returns dict with keys like "800", "400", "1k", "mile" mapping to
    lists of split times in seconds.
    """
    if not description:
        return {}

    desc = description.lower()
    result = {}

    # Try each distance
    for dist_key in ["200", "400", "600", "800", "1000", "1k", "1200", "mile"]:
        splits = _extract_splits_for_distance(desc, dist_key)
        if splits:
            result[dist_key] = splits

    # Also check for "NxN mile" pattern
    mile_splits = _extract_mile_splits(desc)
    if mile_splits:
        result["mile"] = mile_splits

    # Distance reps longer than a mile -- "3x2 miles (6:36,6:36,6:20)",
    # "2x3mi (6:47,6:45)". These are the staple marathon threshold workouts
    # and the values logged are already per-mile PACES, not rep times, so
    # they slot straight into the "mile" bucket (1.0 mi -> pace == time).
    # Without this the evaluator saw no splits on any threshold session and
    # fell back to effort-only judgement.
    long_rep_paces = _extract_long_rep_paces(desc)
    if long_rep_paces:
        result["mile"] = (result.get("mile") or []) + long_rep_paces

    return result


# Nx2mi / Nx3mi / Nx1.5 mile followed by a parenthesised list of paces.
_LONG_REP_RE = re.compile(
    r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*(?:mi\b|miles?)[^()\n]{0,60}\(([^)]+)\)"
)


def _extract_long_rep_paces(desc: str) -> list[float]:
    """Per-mile paces from multi-mile rep sets."""
    paces: list[float] = []
    for match in _LONG_REP_RE.finditer(desc):
        rep_miles = float(match.group(2))
        if rep_miles < 1.5:
            continue  # 1mi reps are handled by _extract_mile_splits
        paces.extend(_parse_time_list(match.group(3), "mile"))
    return paces


def _extract_splits_for_distance(desc: str, distance: str) -> list[float]:
    """Extract split times for a specific distance from description."""
    times = []
    # Match "800" or "800m" or "x800" followed by parenthesized times
    dist_pattern = rf'(?:\d+x)?{distance}m?\b'

    for match in re.finditer(dist_pattern, desc):
        after = desc[match.end():]
        paren_match = re.search(r'\(([^)]+)\)', after[:200])
        if paren_match:
            raw = paren_match.group(1)
            times.extend(_parse_time_list(raw, distance))

    return times


def _extract_mile_splits(desc: str) -> list[float]:
    """Extract mile repeat paces."""
    times = []
    for match in re.finditer(r'\d+x1\s*mile', desc):
        after = desc[match.end():]
        paren_match = re.search(r'\(([^)]+)\)', after[:200])
        if paren_match:
            times.extend(_parse_time_list(paren_match.group(1), "mile"))
    return times


def _parse_time_list(raw: str, distance: str) -> list[float]:
    """Parse comma-separated times to seconds."""
    parts = [p.strip() for p in raw.split(",")]
    times = []
    for part in parts:
        part = re.sub(r'[^0-9:]', '', part.strip())
        if not part:
            continue
        t = _parse_time(part)
        if t <= 0:
            continue
        # Sanity check ranges
        ranges = {
            "200": (20, 120), "400": (50, 240), "600": (80, 360),
            "800": (100, 600), "1000": (150, 600), "1k": (150, 600),
            "1200": (180, 720), "mile": (240, 720),
        }
        lo, hi = ranges.get(distance, (0, 9999))
        if lo < t < hi:
            times.append(t)
    return times


def _parse_time(s: str) -> float:
    """Parse "M:SS" or plain seconds."""
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return 0
    try:
        return float(s)
    except ValueError:
        return 0


# ── Fade Analysis ─────────────────────────────────────────────────

def calculate_fade(splits: list[float]) -> float:
    """Calculate fade: avg second half - avg first half.

    Positive = slowed down. Negative = got faster (negative split).
    Returns 0 if fewer than 2 splits.
    """
    if len(splits) < 2:
        return 0.0

    mid = len(splits) // 2
    first_half = splits[:mid]
    second_half = splits[mid:]

    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)

    return avg_second - avg_first


# ── Rep Count Extraction ──────────────────────────────────────────

def extract_rep_count(description: str) -> tuple[int, str]:
    """Extract the number of reps and distance from a Strava description.

    Returns (rep_count, distance_key). E.g., "6x800" → (6, "800").
    """
    if not description:
        return 0, ""

    # Match patterns like "6x800", "5x1K", "4x1 mile", "3x1200"
    match = re.search(r'(\d+)x(\d+)\s*(m|k|mi|mile)?', description.lower())
    if match:
        reps = int(match.group(1))
        dist = match.group(2)
        suffix = match.group(3) or ""
        if suffix == "k" or dist == "1" and suffix == "k":
            return reps, "1k"
        if suffix in ("mi", "mile") or dist == "1" and suffix == "mile":
            return reps, "mile"
        return reps, dist

    return 0, ""


# ── Workout Type Detection ────────────────────────────────────────

def identify_workout_type(description: str) -> str | None:
    """Identify what type of workout was actually performed.

    Returns: "intervals", "threshold", "tempo", "easy", "fartlek",
             "progression", or None if can't determine.
    """
    if not description:
        return None

    desc = description.lower()

    # Threshold keywords and multi-mile reps come FIRST: "3x2 miles threshold"
    # matches the generic NxN interval pattern but is threshold work, and
    # misclassifying it sends the wrong ladder the progression signal.
    if any(kw in desc for kw in ["threshold", "tempo", "cruise"]):
        return "threshold"
    if re.search(r'\d+\s*x\s*[2-9](?:\.\d+)?\s*(?:mi\b|miles?)', desc):
        return "threshold"
    if re.search(r'(?:@|at)\s*(?:goal\s*)?(?:mp|marathon pace)', desc):
        return "threshold"

    # Interval patterns
    if re.search(r'\d+x\d+', desc):
        return "intervals"

    # Time-based hard efforts
    if re.search(r'\d+\s*min\s*(hard|fast|at|@)', desc):
        return "threshold"

    # Fartlek
    if "fartlek" in desc:
        return "fartlek"

    # Progression
    if "progression" in desc:
        return "progression"

    # Hill
    if "hill" in desc:
        return "intervals"

    # If none of the above, it's probably an easy run
    return "easy"


# ── Core Evaluation ───────────────────────────────────────────────

def evaluate_workout(
    actual_description: str | None,
    actual_avg_pace_sec: float | None,
    actual_distance_miles: float | None,
    prescribed_type: str,
    prescribed_pace_sec: float | None,
    prescribed_name: str | None,
    feel_rating: int | None,
) -> WorkoutEvaluation:
    """Evaluate a completed workout against its prescription.

    This is the main entry point. Combines split analysis, fade,
    pace comparison, and feel rating into a single progression decision.
    """
    # Default values
    pace_diff = 0.0
    fade = 0.0
    reps_completed = 0
    reps_prescribed = 0
    actual_pace = actual_avg_pace_sec or 0
    feel = feel_rating or 6  # default to neutral if not provided

    # Extract prescribed rep count from workout name
    if prescribed_name:
        reps_prescribed, _ = extract_rep_count(prescribed_name)

    # Parse actual splits from Strava description
    splits_by_dist = extract_splits_from_description(actual_description or "")

    # Find the primary split set (longest list = main workout set)
    primary_splits = []
    primary_dist_key = ""
    for dist_key, splits in splits_by_dist.items():
        if len(splits) > len(primary_splits):
            primary_splits = splits
            primary_dist_key = dist_key

    pace_confidence = "none"

    if primary_splits:
        reps_completed = len(primary_splits)

        # Convert split times to pace per mile
        dist_miles = INTERVAL_MILES.get(primary_dist_key, 0.5)
        split_paces = [s / dist_miles for s in primary_splits]
        actual_pace = sum(split_paces) / len(split_paces)

        # Calculate fade from raw split times
        fade = calculate_fade(primary_splits)

        # Pace difference (negative = faster than prescribed)
        if prescribed_pace_sec:
            pace_diff = actual_pace - prescribed_pace_sec
            pace_confidence = "splits"

    # NOTE: we deliberately do NOT fall back to the activity's overall average
    # pace here. That average includes warmup, cooldown and every recovery jog,
    # so on a 2x10min threshold session it reads ~90 sec/mi "slow" no matter how
    # well the reps were run. Comparing it to the prescribed rep pace made the
    # threshold ladder mathematically unable to ever ADVANCE.

    # Also count reps from description directly
    if reps_completed == 0 and actual_description:
        reps_completed, _ = extract_rep_count(actual_description)

    # Check if the runner did a completely different workout
    actual_type = identify_workout_type(actual_description)
    type_mismatch = (
        prescribed_type == "workout"
        and actual_type == "easy"
    )

    # ── Decision Logic ────────────────────────────────────────

    def _result(decision, reason, new_pace=None, steps=1):
        return WorkoutEvaluation(
            decision=decision,
            reason=reason,
            pace_diff_sec=pace_diff if pace_confidence == "splits" else 0.0,
            fade_sec=fade,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=new_pace,
            pace_confidence=pace_confidence,
            advance_steps=steps,
        )

    if type_mismatch:
        # Runner swapped hard day for easy -- don't regress, just hold
        return _result("hold", "Swapped workout for easy run. Holding current level.")

    # Bailed early on the session: cut short by 2+ reps means the level is
    # not consolidated, regardless of how fast the reps they did were.
    short_session = (
        reps_prescribed > 0
        and reps_completed > 0
        and reps_completed <= reps_prescribed - 2
    )
    if short_session:
        return _result(
            "hold",
            f"Completed {reps_completed} of {reps_prescribed} reps. "
            f"Holding this level until the full session goes down.",
        )

    # ── No trustworthy pace data (time-based reps, continuous tempo, or a
    # description we couldn't parse). Decide on effort + fade alone rather
    # than comparing rep pace against a whole-run average that includes
    # warmup and cooldown.
    if pace_confidence == "none":
        if not feel_rating:
            return _result("hold", "No splits and no feel rating. Holding current level.")
        if feel <= 4:
            return _result(
                "regress",
                f"Felt {feel}/10 on this session. Stepping back one level to rebuild confidence.",
            )
        if feel >= 8:
            return _result(
                "advance",
                f"Session felt strong ({feel}/10) and you completed it. Advancing to the next level.",
            )
        return _result(
            "hold",
            f"Solid effort at {feel}/10. Repeating this level to consolidate before progressing.",
        )

    # ── Pace evidence available (parsed rep splits) ──────────────

    # RECALIBRATE: beaten paces by 10+ sec/mi AND felt good
    if pace_diff < -10 and feel >= 7:
        new_pace = (prescribed_pace_sec - 5) if prescribed_pace_sec else None
        return _result(
            "recalibrate",
            f"Beat prescribed pace by {abs(pace_diff):.0f} sec/mi with feel {feel}/10. "
            f"Recalibrating training paces.",
            new_pace=new_pace,
        )

    # ADVANCE+: hit paces AND feel 9-10 AND low fade.
    # Two levels only when they beat the target AND barely noticed -- this is
    # the "experienced rebuilder" case where fitness is coming back faster
    # than the ladder can climb.
    if pace_diff <= 5 and feel >= 9 and fade < 3:
        new_pace = (prescribed_pace_sec - 5) if prescribed_pace_sec else None
        steps = 2 if pace_diff <= -5 else 1
        suffix = " Jumping two levels." if steps == 2 else ""
        return _result(
            "advance",
            f"Crushed it -- paces on target, feel {feel}/10, minimal fade.{suffix}",
            new_pace=new_pace,
            steps=steps,
        )

    # ADVANCE: hit paces AND feel 7-8 AND fade < 5sec
    if pace_diff <= 5 and feel >= 7 and fade < 5:
        return _result(
            "advance",
            f"Good execution -- paces on target, feel {feel}/10, controlled fade. "
            f"Advancing to next level.",
        )

    # REGRESS: missed paces badly OR feel <= 4 OR big fade
    if (pace_diff > 10 and feel <= 5) or feel <= 4 or fade > 10:
        return _result(
            "regress",
            f"Struggled -- pace off by {pace_diff:.0f}s, feel {feel}/10, fade {fade:.0f}s. "
            f"Stepping back one level.",
        )

    # HOLD: everything else (mediocre execution, moderate fade, etc.)
    return _result(
        "hold",
        f"Solid effort -- feel {feel}/10, fade {fade:.0f}s. Repeating current level to consolidate.",
    )


def determine_starting_level(
    category: str,
    recent_workout_descriptions: list[str],
    calibrated_pace_sec: float | None = None,
    distance: str = "5k",
) -> int:
    """Determine starting ladder level from recent Strava history.

    Looks at the most challenging workout the runner has completed recently
    and maps it to a ladder position. The mapping is ladder-specific: 6x800m
    is level 5 on the 5K interval ladder but level 3 on the marathon one,
    because the marathon ladder reserves its top rungs for longer reps.
    """
    if not recent_workout_descriptions:
        return 1

    dist = (distance or "5k").lower()
    is_endurance = dist in ("marathon", "half")

    max_reps_800 = 0
    max_reps_1k = 0
    max_reps_mile = 0
    max_reps_1_5mi = 0
    max_reps_2mi = 0
    max_reps_3mi = 0
    max_mp_miles = 0
    has_tempo = False
    max_tempo_minutes = 0

    for desc in recent_workout_descriptions:
        if not desc:
            continue
        d = desc.lower()

        match_800 = re.search(r'(\d+)\s*x\s*800', d)
        if match_800:
            max_reps_800 = max(max_reps_800, int(match_800.group(1)))

        match_1k = re.search(r'(\d+)\s*x\s*1\s*k\b', d)
        if match_1k:
            max_reps_1k = max(max_reps_1k, int(match_1k.group(1)))

        match_mile = re.search(r'(\d+)\s*x\s*1\s*(?:mi\b|mile)', d)
        if match_mile:
            max_reps_mile = max(max_reps_mile, int(match_mile.group(1)))

        match_15 = re.search(r'(\d+)\s*x\s*1\.5\s*(?:mi|mile)', d)
        if match_15:
            max_reps_1_5mi = max(max_reps_1_5mi, int(match_15.group(1)))

        match_2mi = re.search(r'(\d+)\s*x\s*2\s*(?:mi\b|mile)', d)
        if match_2mi:
            max_reps_2mi = max(max_reps_2mi, int(match_2mi.group(1)))

        match_3mi = re.search(r'(\d+)\s*x\s*3\s*(?:mi\b|mile)', d)
        if match_3mi:
            max_reps_3mi = max(max_reps_3mi, int(match_3mi.group(1)))

        # Continuous marathon-pace blocks: "6 miles at MP", "5mi at marathon pace"
        match_mp = re.search(r'(\d+)\s*(?:mi\b|miles?)\s*(?:@|at)\s*(?:goal\s*)?(?:mp|marathon pace)', d)
        if match_mp:
            max_mp_miles = max(max_mp_miles, int(match_mp.group(1)))

        if "tempo" in d or "threshold" in d:
            has_tempo = True
            min_match = re.search(r'(\d+)\s*min', d)
            if min_match:
                max_tempo_minutes = max(max_tempo_minutes, int(min_match.group(1)))

    if category == "intervals":
        if is_endurance:
            # INTERVAL_LADDER_MARATHON
            if max_reps_mile >= 6:
                return 11
            # NB: 2mi reps are threshold work, not VO2max -- they seed the
            # threshold ladder, not this one.
            if max_reps_1k >= 6:
                return 9
            if max_reps_1_5mi >= 4:
                return 8
            if max_reps_mile >= 5:
                return 7
            if max_reps_mile >= 4:
                return 5
            if max_reps_1k >= 5:
                return 4
            if max_reps_800 >= 6:
                return 3
            return 1
        # INTERVAL_LADDER_5K
        if max_reps_mile >= 4:
            return 8
        if max_reps_800 >= 8:
            return 7
        if max_reps_800 >= 6:
            return 5
        if max_reps_1k >= 5:
            return 4
        if max_reps_800 >= 5:
            return 3
        return 1

    if category == "threshold":
        if is_endurance:
            # THRESHOLD_LADDER_MARATHON
            if max_reps_3mi >= 3:
                return 10
            if max_mp_miles >= 6:
                return 6
            if max_reps_2mi >= 4:
                return 8
            if max_reps_3mi >= 2:
                return 7
            if max_reps_2mi >= 3:
                return 4
            if max_mp_miles >= 4:
                return 3
            if max_reps_2mi >= 2:
                return 1
            if max_tempo_minutes >= 25:
                return 5
            if max_tempo_minutes >= 20:
                return 2
            return 1
        # THRESHOLD_LADDER_5K
        if max_tempo_minutes >= 30:
            return 8
        if max_tempo_minutes >= 25:
            return 5
        if max_tempo_minutes >= 20:
            return 2
        if has_tempo:
            return 1
        return 1

    return 1
