"""Pacing calculations based on goal times and current fitness."""


def goal_paces(distance: str, target_time_seconds: float) -> dict:
    """Calculate training paces from a goal race time.

    Returns paces in seconds per mile for different workout types.
    """
    if distance == "5k":
        race_pace = target_time_seconds / 3.10686  # sec per mile
        return {
            "race_pace": race_pace,
            "interval_pace": race_pace * 0.95,  # slightly faster than race pace
            "tempo_pace": race_pace * 1.08,  # ~8% slower than race pace
            "easy_pace_low": race_pace * 1.5,  # easy range low
            "easy_pace_high": race_pace * 1.7,  # easy range high
            "long_run_pace": race_pace * 1.55,
            "strides_pace": race_pace * 0.85,
        }
    elif distance == "10k":
        race_pace = target_time_seconds / 6.21371
        return {
            "race_pace": race_pace,
            "interval_pace": race_pace * 0.93,
            "tempo_pace": race_pace * 1.05,
            "easy_pace_low": race_pace * 1.4,
            "easy_pace_high": race_pace * 1.6,
            "long_run_pace": race_pace * 1.45,
            "strides_pace": race_pace * 0.82,
        }
    elif distance == "half":
        race_pace = target_time_seconds / 13.1094
        return {
            "race_pace": race_pace,
            "interval_pace": race_pace * 0.88,
            "tempo_pace": race_pace * 0.97,
            "easy_pace_low": race_pace * 1.3,
            "easy_pace_high": race_pace * 1.5,
            "long_run_pace": race_pace * 1.35,
            "strides_pace": race_pace * 0.78,
        }
    elif distance == "marathon":
        race_pace = target_time_seconds / 26.2188
        return {
            "race_pace": race_pace,
            "interval_pace": race_pace * 0.85,
            "tempo_pace": race_pace * 0.93,
            "threshold_pace": race_pace * 0.90,
            "easy_pace_low": race_pace * 1.25,
            "easy_pace_high": race_pace * 1.45,
            "long_run_pace": race_pace * 1.3,
            "mp_long_run_pace": race_pace * 1.0,
            "strides_pace": race_pace * 0.75,
        }
    return {}


def format_pace(seconds_per_mile: float) -> str:
    """Format seconds per mile as M:SS string."""
    minutes = int(seconds_per_mile // 60)
    secs = int(seconds_per_mile % 60)
    return f"{minutes}:{secs:02d}"


def pace_range(low_sec: float, high_sec: float) -> str:
    """Format a pace range like '8:30-9:15'."""
    return f"{format_pace(low_sec)}-{format_pace(high_sec)}"


def time_from_pace_and_distance(pace_sec_per_mile: float, distance_miles: float) -> str:
    """Calculate total time from pace and distance."""
    total_seconds = pace_sec_per_mile * distance_miles
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = int(total_seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
