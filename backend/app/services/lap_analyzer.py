"""Turn Garmin laps into a workout summary the rest of Stride understands.

The pace calibrator and workout evaluator parse workout text like
"6x800 (3:01, 3:04, 3:02)" or "3x2 miles threshold (6:50, 6:48)". With Strava,
that text came from hand-written descriptions. With Garmin we have real lap
data, so we build the same text from the laps — no typing required.

Detection order:
1. Structured Garmin workouts mark laps as WARMUP / ACTIVE / RECOVERY / REST /
   COOLDOWN — use those labels directly.
2. Otherwise, work laps are laps clearly faster than easy pace. Reps are
   grouped by consistent distance (800s, miles) or duration (10min reps);
   contiguous fast auto-laps are a continuous tempo.
"""

import statistics

METERS_PER_MILE = 1609.34

WORK_INTENSITIES = {"ACTIVE", "INTERVAL"}
NON_WORK_INTENSITIES = {"REST", "RECOVERY", "WARMUP", "COOLDOWN"}

# (meters, label) — labels match the patterns pace_calibrator/workout_evaluator parse
STANDARD_REPS = [
    (200, "200"),
    (300, "300"),
    (400, "400"),
    (600, "600"),
    (800, "800"),
    (1000, "1k"),
    (1200, "1200"),
    (METERS_PER_MILE, "1 mile"),
    (2000, "2k"),
    (2 * METERS_PER_MILE, "2 miles"),
    (3 * METERS_PER_MILE, "3 miles"),
]

# Laps at least this much faster than easy pace count as work (0.82 = 18% faster).
# Tuned on real data: at 0.90, moderate "steady" miles (e.g. 8:38 vs a 9:48 easy pace)
# were counted as tempo, which would drag calibrated workout paces slower.
WORK_PACE_RATIO = 0.82


def lap_pace_per_mile(lap: dict) -> float | None:
    dist = lap.get("distance_m") or 0
    dur = lap.get("duration_s") or 0
    if dist < 50 or dur <= 0:
        return None
    return dur / (dist / METERS_PER_MILE)


def _fmt_time(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _fmt_rest(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 120:
        return f"{seconds}s"
    mins, secs = divmod(seconds, 60)
    return f"{mins}min" if secs < 15 else f"{mins}:{secs:02d}"


def _cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    return statistics.pstdev(values) / mean if mean else 1.0


def _nearest_standard(distance_m: float) -> str | None:
    for meters, label in STANDARD_REPS:
        if abs(distance_m - meters) / meters <= 0.08:
            return label
    return None


def _find_work_laps(laps: list[dict], easy_pace_sec: float | None) -> list[int]:
    """Return indices of work laps."""
    intensities = {(lap.get("intensity") or "").upper() for lap in laps}
    if intensities & NON_WORK_INTENSITIES and intensities & WORK_INTENSITIES:
        work = [i for i, lap in enumerate(laps) if (lap.get("intensity") or "").upper() in WORK_INTENSITIES]
        # Structured workouts with a single "ACTIVE" block are just a run
        if len(work) >= 2 or (len(work) == 1 and (laps[work[0]].get("duration_s") or 0) >= 900):
            return work

    paces = [lap_pace_per_mile(lap) for lap in laps]
    valid = [p for p in paces if p]
    if len(valid) < 2:
        return []

    if easy_pace_sec:
        reference = easy_pace_sec
    else:
        # No easy pace known — fall back to this run's median lap pace. (Not the slower
        # laps: on a slow, hilly run that makes ordinary miles look like reps.)
        reference = statistics.median(valid)

    cutoff = reference * WORK_PACE_RATIO
    return [
        i for i, p in enumerate(paces)
        if p and p <= cutoff and (laps[i].get("distance_m") or 0) >= 150
    ]


def summarize_workout(laps: list[dict], easy_pace_sec: float | None = None) -> str | None:
    """Build a workout summary string from laps, or None if it looks like a steady run.

    `easy_pace_sec` is the athlete's typical easy pace (sec/mile); it makes
    detection much more reliable than comparing laps within one run.
    """
    if not laps or len(laps) < 2:
        return None

    work_idx = _find_work_laps(laps, easy_pace_sec)
    if len(work_idx) < 2 and not (
        len(work_idx) == 1 and (laps[work_idx[0]].get("duration_s") or 0) >= 900
    ):
        return None

    work = [laps[i] for i in work_idx]
    contiguous = all(b - a == 1 for a, b in zip(work_idx, work_idx[1:]))

    # Recovery between reps = laps sitting between consecutive work laps
    rest_durations = []
    for a, b in zip(work_idx, work_idx[1:]):
        between = laps[a + 1 : b]
        if between:
            rest_durations.append(sum(lap.get("duration_s") or 0 for lap in between))
    rest_note = f" w/ {_fmt_rest(statistics.median(rest_durations))} recovery" if rest_durations else ""

    distances = [lap.get("distance_m") or 0 for lap in work]
    durations = [lap.get("duration_s") or 0 for lap in work]
    paces = [lap_pace_per_mile(lap) or 0 for lap in work]
    n = len(work)
    total_work_miles = sum(distances) / METERS_PER_MILE

    # Continuous tempo: fast laps back-to-back (usually 1mi auto-laps) with no recovery
    if contiguous and not rest_durations:
        if total_work_miles < 1.5:
            return None  # a couple of quick auto-laps isn't a tempo
        if work_idx[0] == 0:
            return None  # fast from the first lap with no warmup = steady run or race, not a tempo
        pace_list = ", ".join(_fmt_time(p) for p in paces)
        miles = round(total_work_miles * 2) / 2
        return f"Garmin laps: tempo {miles:g} miles ({pace_list}) avg {_fmt_time(sum(durations) / total_work_miles)}/mi"

    distance_label = _nearest_standard(statistics.median(distances)) if _cv(distances) <= 0.10 else None

    # Distance-based reps (e.g. 800s, miles)
    if distance_label:
        label = distance_label
        if label in ("200", "300", "400"):
            times = ", ".join(str(round(d)) for d in durations)
            return f"Garmin laps: {n}x{label} ({times}){rest_note}"
        if label in ("600", "800", "1k", "1200", "2k"):
            times = ", ".join(_fmt_time(d) for d in durations)
            return f"Garmin laps: {n}x{label} ({times}){rest_note}"
        if label == "1 mile":
            times = ", ".join(_fmt_time(d) for d in durations)
            return f"Garmin laps: {n}x1 mile ({times}){rest_note}"
        pace_list = ", ".join(_fmt_time(p) for p in paces)
        return f"Garmin laps: {n}x{label} threshold ({pace_list}){rest_note}"

    # Time-based reps (e.g. 4x10min, 6x3min)
    if _cv(durations) <= 0.10:
        minutes = round(statistics.median(durations) / 60)
        pace_list = ", ".join(_fmt_time(p) for p in paces)
        kind = "threshold" if minutes >= 5 else "fartlek"
        return f"Garmin laps: {n}x{minutes}min {kind} ({pace_list}/mi){rest_note}"

    # Consistent but non-standard distance (e.g. 500m reps)
    if _cv(distances) <= 0.10:
        meters = round(statistics.median(distances) / 10) * 10
        times = ", ".join(_fmt_time(d) for d in durations)
        return f"Garmin laps: {n}x{meters}m ({times}){rest_note}"

    # Mixed reps (ladder / fartlek) — list each rep
    reps = ", ".join(f"{lap.get('distance_m', 0) / METERS_PER_MILE:.2f}mi @ {_fmt_time(p)}" for lap, p in zip(work, paces))
    return f"Garmin laps: {n} reps fartlek ({reps}){rest_note}"
