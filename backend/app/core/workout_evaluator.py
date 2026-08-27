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

    return result


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

    # Interval patterns
    if re.search(r'\d+x\d+', desc):
        return "intervals"

    # Threshold/tempo keywords
    if any(kw in desc for kw in ["threshold", "tempo", "cruise"]):
        return "threshold"

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
    elif actual_avg_pace_sec and prescribed_pace_sec:
        # No splits parsed — use overall average pace
        pace_diff = actual_avg_pace_sec - prescribed_pace_sec

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

    if type_mismatch:
        # Runner swapped hard day for easy — don't regress, just hold
        return WorkoutEvaluation(
            decision="hold",
            reason="Swapped workout for easy run. Holding current level.",
            pace_diff_sec=0,
            fade_sec=0,
            reps_completed=0,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=None,
        )

    # No data to evaluate (no splits, no pace, no feel)
    if not primary_splits and not actual_avg_pace_sec and not feel_rating:
        return WorkoutEvaluation(
            decision="hold",
            reason="Insufficient data to evaluate. Holding current level.",
            pace_diff_sec=0,
            fade_sec=0,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=None,
        )

    # RECALIBRATE: beaten paces by 10+ sec/mi AND felt good
    if pace_diff < -10 and feel >= 7:
        # Suggest new pace: 5 sec/mi bump (conservative)
        new_pace = (prescribed_pace_sec - 5) if prescribed_pace_sec else None
        return WorkoutEvaluation(
            decision="recalibrate",
            reason=f"Beat prescribed pace by {abs(pace_diff):.0f} sec/mi with feel {feel}/10. Recalibrating training paces.",
            pace_diff_sec=pace_diff,
            fade_sec=fade,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=new_pace,
        )

    # ADVANCE+: hit paces AND feel 9-10 AND low fade
    if pace_diff <= 5 and feel >= 9 and fade < 3:
        new_pace = (prescribed_pace_sec - 5) if prescribed_pace_sec else None
        return WorkoutEvaluation(
            decision="advance",
            reason=f"Crushed it — paces on target, feel {feel}/10, minimal fade. Advancing and bumping pace.",
            pace_diff_sec=pace_diff,
            fade_sec=fade,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=new_pace,
        )

    # ADVANCE: hit paces AND feel 7-8 AND fade < 5sec
    if pace_diff <= 5 and feel >= 7 and fade < 5:
        return WorkoutEvaluation(
            decision="advance",
            reason=f"Good execution — paces on target, feel {feel}/10, controlled fade. Advancing to next level.",
            pace_diff_sec=pace_diff,
            fade_sec=fade,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=None,
        )

    # REGRESS: missed paces badly OR feel <= 4 OR big fade
    if (pace_diff > 10 and feel <= 5) or feel <= 4 or fade > 10:
        return WorkoutEvaluation(
            decision="regress",
            reason=f"Struggled — pace off by {pace_diff:.0f}s, feel {feel}/10, fade {fade:.0f}s. Stepping back one level.",
            pace_diff_sec=pace_diff,
            fade_sec=fade,
            reps_completed=reps_completed,
            reps_prescribed=reps_prescribed,
            actual_pace_sec=actual_pace,
            new_pace_sec=None,
        )

    # HOLD: everything else (mediocre execution, moderate fade, etc.)
    return WorkoutEvaluation(
        decision="hold",
        reason=f"Solid effort — feel {feel}/10, fade {fade:.0f}s. Repeating current level to consolidate.",
        pace_diff_sec=pace_diff,
        fade_sec=fade,
        reps_completed=reps_completed,
        reps_prescribed=reps_prescribed,
        actual_pace_sec=actual_pace,
        new_pace_sec=None,
    )


def determine_starting_level(
    category: str,
    recent_workout_descriptions: list[str],
    calibrated_pace_sec: float | None,
) -> int:
    """Determine starting ladder level from recent Strava history.

    Looks at the most challenging workout the runner has completed recently
    and maps it to a ladder position.
    """
    if not recent_workout_descriptions:
        return 1

    max_reps_800 = 0
    max_reps_1k = 0
    max_reps_mile = 0
    has_tempo = False
    max_tempo_minutes = 0

    for desc in recent_workout_descriptions:
        if not desc:
            continue
        d = desc.lower()

        # Count 800m reps
        match_800 = re.search(r'(\d+)x800', d)
        if match_800:
            max_reps_800 = max(max_reps_800, int(match_800.group(1)))

        # Count 1K reps
        match_1k = re.search(r'(\d+)x1k', d)
        if match_1k:
            max_reps_1k = max(max_reps_1k, int(match_1k.group(1)))

        # Count mile reps
        match_mile = re.search(r'(\d+)x1\s*mile', d)
        if match_mile:
            max_reps_mile = max(max_reps_mile, int(match_mile.group(1)))

        # Check for tempo/threshold
        if "tempo" in d or "threshold" in d:
            has_tempo = True
            # Try to extract duration
            min_match = re.search(r'(\d+)\s*min', d)
            if min_match:
                max_tempo_minutes = max(max_tempo_minutes, int(min_match.group(1)))

    if category == "intervals":
        if max_reps_mile >= 4:
            return 8  # 4x1mi level
        if max_reps_800 >= 8:
            return 7  # 8x800 level
        if max_reps_800 >= 6:
            return 5  # 6x800 level
        if max_reps_1k >= 5:
            return 4  # 5x1K level
        if max_reps_800 >= 5:
            return 3  # 5x800 level
        if max_reps_800 >= 4:
            return 1  # 4x800 level
        return 1

    elif category == "threshold":
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
