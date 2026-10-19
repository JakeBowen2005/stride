"""Pace calibration from real Strava workout descriptions.

Parses workout descriptions to extract actual interval times, tempo paces,
and threshold paces. Uses these to set training paces grounded in real data
instead of theoretical calculations from goal time.
"""

import re
import statistics
import math
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.plan import PlannedWorkout, Plan
from app.core.workout_data import loads


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
    """Independent per-category calibration, weighted by workout recency.

    Two distinct workouts in 84 days, including one in 28 days, are required.
    Each workout contributes one median so many reps cannot swamp other days.
    Numeric matched work is preferred; old logged splits remain a fallback.
    """
    window = min(max(weeks_back * 7, 1), 84)
    cutoff = datetime.now() - timedelta(days=window)
    samples = {key: [] for key in ("interval_pace", "tempo_pace", "threshold_pace", "strides_pace")}
    seen = set()
    rows = db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == user_id, PlannedWorkout.execution.isnot(None), PlannedWorkout.date >= cutoff.date().isoformat()).order_by(PlannedWorkout.id.desc()).all()
    for row in rows:
        execution, prescribed = loads(row.execution), loads(row.prescription)
        if not execution or not prescribed:
            continue
        ids = execution.get("matched_activity_ids", [])
        if not ids or seen.intersection(ids):
            continue
        # An incomplete/uncertain structured execution must not bypass its gates
        # through the same activity's generated prose or an older plan match.
        seen.update(ids)
        if execution.get("confidence") not in ("high", "medium") or (execution.get("completion") or 0) < 1:
            continue
        age = (datetime.now().date() - datetime.fromisoformat(row.date).date()).days
        by_category = {}
        index = 0
        for spec in prescribed['segments']:
            category = spec.get('category') or prescribed['category']
            # Continuous threshold is the program's tempo field; broken reps
            # store threshold independently. No synthetic cross-category paces.
            key = 'tempo_pace' if category == 'threshold' and prescribed['format'] == 'continuous' else {'threshold': 'threshold_pace', 'intervals': 'interval_pace', 'strides': 'strides_pace'}.get(category)
            paces = execution.get('rep_paces_sec_per_mile', [])[index:index + spec['reps']]
            index += spec['reps']
            if key and paces:
                by_category.setdefault(key, []).extend(paces)
        for key, paces in by_category.items():
            samples[key].append((age, statistics.median(paces), ids))

    activities = db.query(Activity).filter(Activity.user_id == user_id, Activity.date >= cutoff).order_by(Activity.date.desc()).all()
    for act in activities:
        if act.id in seen or not act.description:
            continue
        age = (datetime.now().date() - act.date.date()).days
        desc = act.description.lower()
        # Explicit words win: a threshold workout cannot also become tempo or VO2.
        if 'threshold' in desc:
            parsed = {'threshold_pace': _extract_threshold_paces(desc)}
        elif 'tempo' in desc:
            parsed = {'tempo_pace': _extract_tempo_paces(desc)}
        else:
            interval = [t / INTERVAL_DISTANCES[dist] for dist in ('800', '1k') for t in _extract_splits(desc, dist)]
            interval += _extract_mile_splits(desc)
            parsed = {'interval_pace': interval, 'strides_pace': [t / INTERVAL_DISTANCES['200'] for t in _extract_splits(desc, '200')]}
        for key, paces in parsed.items():
            valid = [v for v in paces if math.isfinite(v) and 180 <= v <= 900]
            if valid:
                samples[key].append((age, statistics.median(valid), [act.id]))

    result = {'source': 'calibrated', 'policy_version': 'calibration-v2', 'data_points': {}, 'evidence': {}, 'breakdown': {}}
    for key, values in samples.items():
        values = [v for v in values if 0 <= v[0] <= window]
        # Multiple activities on one day are one training exposure.
        days = {}
        for age, pace, ids in values:
            day = days.setdefault(age, {'paces': [], 'ids': []})
            day['paces'].append(pace)
            day['ids'].extend(ids)
        values = [(age, statistics.median(day['paces']), day['ids']) for age, day in days.items()]
        result['data_points'][key] = len(values)
        eligible = len(values) >= 2 and any(age <= 28 for age, _, _ in values)
        result['evidence'][key] = {'workout_count': len(values), 'eligible': eligible,
                                   'matched_activity_ids': sorted({i for _, _, ids in values for i in ids}),
                                   'reason': 'Two distinct workout days, one within 28 days, required in the 84-day window.'}
        if not eligible:
            continue
        weighted = sorted((pace, max(.1, 1 - age / 84)) for age, pace, _ in values)
        halfway = sum(weight for _, weight in weighted) / 2
        cumulative = 0
        for pace, weight in weighted:
            cumulative += weight
            if cumulative >= halfway:
                result[key] = pace
                break
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
