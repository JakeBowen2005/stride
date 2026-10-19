"""Pace calibration from real Strava workout descriptions.

Parses workout descriptions to extract actual interval times, tempo paces,
and threshold paces. Uses these to set training paces grounded in real data
instead of theoretical calculations from goal time.
"""

import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.activity import Activity


# Distance in miles for common intervals
INTERVAL_DISTANCES = {
    "200": 0.12427,   # 200m in miles
    "400": 0.24855,   # 400m
    "800": 0.49710,   # 800m
    "1k": 0.62137,    # 1000m
    "1000": 0.62137,
    "mile": 1.0,
    "1 mile": 1.0,
}


def calibrate_paces(user_id: int, db: Session, weeks_back: int = 12) -> dict:
    """Parse recent workout descriptions and return calibrated training paces.

    Returns dict with keys matching what plan_engine._build_current_paces() expects:
        interval_pace, tempo_pace, threshold_pace, race_pace, steady_pace, strides_pace
    All values in seconds per mile.
    """
    cutoff = datetime.now() - timedelta(weeks=weeks_back)

    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.has_workout_description == True,
            Activity.date >= cutoff,
        )
        .order_by(Activity.date.desc())
        .all()
    )

    all_800_paces = []
    all_400_paces = []
    all_200_paces = []
    all_1k_paces = []
    all_mile_paces = []
    all_tempo_paces = []
    all_threshold_paces = []

    for act in activities:
        if not act.description:
            continue

        desc = act.description.lower()

        # Extract 800m splits
        splits_800 = _extract_splits(desc, "800")
        for time_sec in splits_800:
            pace_per_mile = time_sec / INTERVAL_DISTANCES["800"]
            all_800_paces.append(pace_per_mile)

        # Extract 400m splits
        splits_400 = _extract_splits(desc, "400")
        for time_sec in splits_400:
            pace_per_mile = time_sec / INTERVAL_DISTANCES["400"]
            all_400_paces.append(pace_per_mile)

        # Extract 200m splits
        splits_200 = _extract_splits(desc, "200")
        for time_sec in splits_200:
            pace_per_mile = time_sec / INTERVAL_DISTANCES["200"]
            all_200_paces.append(pace_per_mile)

        # Extract 1K splits
        splits_1k = _extract_splits(desc, "1k")
        for time_sec in splits_1k:
            pace_per_mile = time_sec / INTERVAL_DISTANCES["1k"]
            all_1k_paces.append(pace_per_mile)

        # Extract mile repeat splits
        splits_mile = _extract_mile_splits(desc)
        for time_sec in splits_mile:
            all_mile_paces.append(time_sec)  # already per mile

        # Extract tempo/threshold paces
        tempo_paces = _extract_tempo_paces(desc)
        threshold_paces = _extract_threshold_paces(desc)
        all_tempo_paces.extend(tempo_paces)
        all_threshold_paces.extend(threshold_paces)

    result = {"source": "calibrated", "data_points": {}}

    # Interval pace: prefer 800m data (most common), fall back to 1K, 400m
    interval_paces = all_800_paces or all_1k_paces or all_400_paces
    if interval_paces:
        # Use median of recent intervals
        interval_paces.sort()
        median_idx = len(interval_paces) // 2
        result["interval_pace"] = interval_paces[median_idx]
        result["data_points"]["interval"] = len(interval_paces)

    # Tempo pace
    if all_tempo_paces:
        all_tempo_paces.sort()
        median_idx = len(all_tempo_paces) // 2
        result["tempo_pace"] = all_tempo_paces[median_idx]
        result["data_points"]["tempo"] = len(all_tempo_paces)

    # Threshold pace
    if all_threshold_paces:
        all_threshold_paces.sort()
        median_idx = len(all_threshold_paces) // 2
        result["threshold_pace"] = all_threshold_paces[median_idx]
        result["data_points"]["threshold"] = len(all_threshold_paces)
    elif all_tempo_paces:
        # Threshold is slightly slower than tempo
        result["threshold_pace"] = result.get("tempo_pace", 420) * 1.04
        result["data_points"]["threshold"] = 0

    # Mile repeat pace
    if all_mile_paces:
        all_mile_paces.sort()
        median_idx = len(all_mile_paces) // 2
        result["mile_repeat_pace"] = all_mile_paces[median_idx]
        result["data_points"]["mile_repeats"] = len(all_mile_paces)

    # Strides pace from 200m data
    if all_200_paces:
        all_200_paces.sort()
        result["strides_pace"] = all_200_paces[len(all_200_paces) // 2]
        result["data_points"]["strides"] = len(all_200_paces)

    # Race pace: estimate from interval pace (slightly slower)
    if "interval_pace" in result:
        result["race_pace"] = result["interval_pace"] * 1.05

    # Steady pace: between tempo and easy
    if "tempo_pace" in result:
        result["steady_pace"] = result["tempo_pace"] * 1.08

    # Build the detailed breakdown for the frontend
    result["breakdown"] = {
        "800m_splits": [
            {"time": _format_interval_time(p * INTERVAL_DISTANCES["800"]), "pace_per_mile": _format_pace(p)}
            for p in sorted(all_800_paces)
        ] if all_800_paces else [],
        "1k_splits": [
            {"time": _format_interval_time(p * INTERVAL_DISTANCES["1k"]), "pace_per_mile": _format_pace(p)}
            for p in sorted(all_1k_paces)
        ] if all_1k_paces else [],
        "200m_splits": [
            {"time": str(round(p * INTERVAL_DISTANCES["200"])), "pace_per_mile": _format_pace(p)}
            for p in sorted(all_200_paces)
        ] if all_200_paces else [],
        "mile_splits": [
            {"time": _format_pace(p), "pace_per_mile": _format_pace(p)}
            for p in sorted(all_mile_paces)
        ] if all_mile_paces else [],
        "tempo_paces": [_format_pace(p) for p in sorted(all_tempo_paces)] if all_tempo_paces else [],
        "threshold_paces": [_format_pace(p) for p in sorted(all_threshold_paces)] if all_threshold_paces else [],
    }

    return result


def _extract_splits(desc: str, distance: str) -> list[float]:
    """Extract split times for a given distance from description text.

    Handles formats like:
        800 splits (2:49,2:55,2:54)
        800 (3:04,3:03,3:04)
        6x800 ... (2:49, 2:55, 2:54)
        200 splits (38,35,34,32)
        200 (39,38,37)
    """
    times = []

    # Pattern: look for the distance keyword, then find parenthesized times
    # Match "800" or "800m" or "x800" followed eventually by parenthesized splits
    dist_pattern = rf'(?:\d+x)?{distance}m?\b'

    # Find all sections that reference this distance
    for match in re.finditer(dist_pattern, desc):
        # Look for parenthesized times after the distance reference
        after = desc[match.end():]
        paren_match = re.search(r'\(([^)]+)\)', after[:200])  # look within 200 chars
        if paren_match:
            raw = paren_match.group(1)
            times.extend(_parse_time_list(raw, distance))

    return times


def _extract_mile_splits(desc: str) -> list[float]:
    """Extract mile repeat paces from descriptions.

    Handles formats like:
        4x1 mile (6:24,6:19,6:25,6:11)
        Main set 4x1 mile (6:24,6:19,6:25,6:11) 3 min walk rest
    """
    times = []

    # Pattern for mile repeats
    for match in re.finditer(r'\d+x1\s*mile', desc):
        after = desc[match.end():]
        paren_match = re.search(r'\(([^)]+)\)', after[:200])
        if paren_match:
            raw = paren_match.group(1)
            times.extend(_parse_time_list(raw, "mile"))

    return times


def _extract_tempo_paces(desc: str) -> list[float]:
    """Extract tempo run paces from descriptions.

    Handles formats like:
        2x2 miles threshold ... (7:02,6:56) avgs
        3x2 miles @ 6:30
    """
    paces = []

    # Pattern: "Nx2 miles @ pace" or "Nx2 miles threshold ... (paces)"
    # Look for pace values in context of tempo/threshold workout
    if "tempo" in desc or "threshold" in desc or "@ " in desc:
        # Find all parenthesized pace groups
        for match in re.finditer(r'\(([^)]+)\)', desc):
            raw = match.group(1)
            if re.search(r'\d+:\d{2}', raw):
                parsed = _parse_time_list(raw, "mile")
                paces.extend(parsed)

        # Also try "@ pace" format: "3x2 miles @ 6:30"
        at_match = re.search(r'@\s*(\d+:\d{2})', desc)
        if at_match:
            paces.append(_parse_single_time(at_match.group(1)))

    return paces


def _extract_threshold_paces(desc: str) -> list[float]:
    """Extract threshold-specific paces.

    Handles:
        2x2 miles threshold (7:02,6:56)
        Main set 2x3 miles (6:47,6:45) 1 mile float
    """
    paces = []

    if "threshold" in desc:
        for match in re.finditer(r'\(([^)]+)\)', desc):
            raw = match.group(1)
            if re.search(r'\d+:\d{2}', raw):
                parsed = _parse_time_list(raw, "mile")
                paces.extend(parsed)

    # "Main set NxN miles (paces)" pattern — likely threshold/tempo work
    main_match = re.search(r'main set\s+\d+x\d+\s*miles?\s*\(([^)]+)\)', desc)
    if main_match:
        raw = main_match.group(1)
        if re.search(r'\d+:\d{2}', raw):
            paces.extend(_parse_time_list(raw, "mile"))

    return paces


def _parse_time_list(raw: str, distance: str) -> list[float]:
    """Parse a comma-separated list of times into seconds.

    For short distances (200, 400): times are in seconds only (e.g., "38,35,34,32")
    For longer distances (800, 1k, mile): times are in M:SS format (e.g., "2:49,2:55")
    For tempo paces: times are in M:SS format (e.g., "7:02,6:56")
    """
    parts = [p.strip() for p in raw.split(",")]
    times = []

    for part in parts:
        # Remove non-numeric/colon chars (like "uh oh" in "32) uh oh")
        part = re.sub(r'[^0-9:]', '', part.strip())
        if not part:
            continue

        t = _parse_single_time(part)
        if t > 0:
            # Sanity checks
            if distance in ("200", "200m") and 20 < t < 120:
                times.append(t)
            elif distance in ("400", "400m") and 50 < t < 240:
                times.append(t)
            elif distance in ("800", "800m") and 100 < t < 600:
                times.append(t)
            elif distance in ("1k", "1000", "1000m") and 150 < t < 600:
                times.append(t)
            elif distance in ("mile", "1 mile") and 240 < t < 720:
                times.append(t)

    return times


def _parse_single_time(s: str) -> float:
    """Parse a time string to seconds. Handles "M:SS" and plain seconds."""
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return 0
    else:
        try:
            return float(s)
        except ValueError:
            return 0


def _format_pace(seconds_per_mile: float) -> str:
    """Format seconds per mile as M:SS."""
    if seconds_per_mile <= 0:
        return "0:00"
    minutes = int(seconds_per_mile // 60)
    secs = int(seconds_per_mile % 60)
    return f"{minutes}:{secs:02d}"


def _format_interval_time(seconds: float) -> str:
    """Format interval time as M:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"
