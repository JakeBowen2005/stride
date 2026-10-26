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


def lap_split(number: int, distance_m: float, duration_s: float, heart_rate: float | None = None,
              intensity: str | None = None, elevation_diff_ft: float = 0.0) -> dict:
    """One lap in Stride's stored split format (what the API returns and SplitsTable renders)."""
    entry = {
        "mile": number,  # lap number (kept as "mile" for frontend compatibility)
        "distance_m": round(distance_m, 1),
        "distance_miles": round(distance_m / METERS_PER_MILE, 2),
        "duration_s": round(duration_s, 1),
        "duration_seconds": round(duration_s, 1),
        "heart_rate": round(heart_rate) if heart_rate else None,
        "elevation_diff_ft": elevation_diff_ft,
        "intensity": str(intensity).upper() if intensity else None,
    }
    pace = lap_pace_per_mile(entry)
    entry["pace_seconds"] = round(pace, 1) if pace else None
    entry["pace"] = f"{int(pace // 60)}:{int(pace % 60):02d}/mi" if pace else "—"
    return entry


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


def _lap_hr(lap: dict) -> float | None:
    hr = lap.get("average_hr", lap.get("heart_rate"))
    return float(hr) if isinstance(hr, (int, float)) and hr > 0 else None


def _merge(group: list[dict]) -> dict:
    """One rep from back-to-back work laps (e.g. a 1.00mi auto-lap plus its 0.10mi remainder)."""
    distance = sum(lap.get("distance_m") or 0 for lap in group)
    duration = sum(lap.get("duration_s") or 0 for lap in group)
    timed = [(hr, lap.get("duration_s") or 0) for lap in group if (hr := _lap_hr(lap))]
    hr = sum(h * d for h, d in timed) / sum(d for _, d in timed) if timed and sum(d for _, d in timed) else None
    return {"distance_m": distance, "duration_s": duration, "average_hr": hr, "laps": len(group)}


def _auto_lap(lap: dict) -> bool:
    """Garmin auto-lap length: 1.00 mi or 1.00 km (±1%)."""
    d = lap.get("distance_m") or 0
    return any(abs(d - m) / m <= 0.01 for m in (METERS_PER_MILE, 1000.0))


def _similar_pace(rep: dict, lap: dict) -> bool:
    """Same effort: within 5%, or 12% for a short remainder lap (GPS pace is noisy over 0.1 mi)."""
    a, b = lap_pace_per_mile(rep), lap_pace_per_mile(lap)
    short = (lap.get("distance_m") or 0) < 0.35 * METERS_PER_MILE
    return bool(a and b and abs(a - b) / a <= (0.12 if short else 0.05))


def _groups(indices: list[int]) -> list[list[int]]:
    """Split work-lap indices into runs of consecutive laps."""
    groups: list[list[int]] = []
    for i in indices:
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _category(kind: str, minutes: float) -> str:
    if kind == "tempo" or minutes >= 5:
        return "threshold"
    return "intervals" if minutes >= 1.5 else "speed"


def analyze_laps(laps: list[dict], easy_pace_sec: float | None = None) -> dict | None:
    """Structured read of a quality session from its laps, or None for a steady run.

    Returns {kind, category, label, text, reps: [{distance_m, duration_s, pace_sec_per_mile,
    average_hr}], recovery_seconds, work_miles}. `text` is the "Garmin laps: ..." summary the
    pace calibrator and evaluator parse. Garmin auto-laps split a rep that crosses a mile
    marker (an 8-minute rep becomes 1.00mi + 0.10mi), so when a session has recoveries,
    back-to-back work laps are merged into one rep.
    """
    if not laps or len(laps) < 2:
        return None

    work_idx = _find_work_laps(laps, easy_pace_sec)
    if len(work_idx) < 2 and not (
        len(work_idx) == 1 and (laps[work_idx[0]].get("duration_s") or 0) >= 900
    ):
        return None

    groups = _groups(work_idx)
    # Laps between efforts that are still near work pace are not recovery: one continuous effort.
    paces_all = [lap_pace_per_mile(lap) for lap in laps]
    valid_paces = [x for x in paces_all if x]
    reference = easy_pace_sec or (statistics.median(valid_paces) if valid_paces else None)
    gaps = [laps[a[-1] + 1: b[0]] for a, b in zip(groups, groups[1:])]
    if len(groups) > 1 and reference and all(
            all((lap_pace_per_mile(lap) or reference) <= reference * 0.90 for lap in gap) for gap in gaps):
        work_idx = list(range(groups[0][0], groups[-1][-1] + 1))
        groups = [work_idx]
    total_work_miles = sum(laps[i].get("distance_m") or 0 for i in work_idx) / METERS_PER_MILE

    # Continuous tempo: fast laps back-to-back (usually 1mi auto-laps) with no recovery
    if len(groups) == 1:
        if total_work_miles < 1.5:
            return None  # a couple of quick auto-laps isn't a tempo
        if work_idx[0] == 0:
            return None  # fast from the first lap with no warmup = steady run or race, not a tempo
        work = [laps[i] for i in work_idx]
        paces = [lap_pace_per_mile(lap) or 0 for lap in work]
        durations = [lap.get("duration_s") or 0 for lap in work]
        miles = round(total_work_miles * 2) / 2
        avg = sum(durations) / total_work_miles
        merged = _merge(work)
        return {"kind": "tempo", "category": "threshold", "label": f"{miles:g} mi tempo",
                "text": f"Garmin laps: tempo {miles:g} miles ({', '.join(_fmt_time(p) for p in paces)}) avg {_fmt_time(avg)}/mi",
                "reps": [{"distance_m": merged["distance_m"], "duration_s": merged["duration_s"],
                          "pace_sec_per_mile": round(avg), "average_hr": merged["average_hr"]}],
                "recovery_seconds": None, "work_miles": round(total_work_miles, 2)}

    # A back-to-back work lap continues the current rep only when the previous lap ended on a
    # Garmin auto-lap marker (exactly 1.00 mi or 1.00 km) at a similar pace: the watch split
    # the rep, the runner didn't. Laps the runner pressed (other lengths) stay separate reps.
    reps_idx: list[list[int]] = []
    for g in groups:
        for i in g:
            current = reps_idx[-1] if reps_idx and reps_idx[-1][-1] == i - 1 else None
            if current and _auto_lap(laps[current[-1]]) and _similar_pace(_merge([laps[j] for j in current]), laps[i]):
                current.append(i)
            else:
                reps_idx.append([i])
    work = [_merge([laps[i] for i in rep]) for rep in reps_idx]
    if any(rep["distance_m"] < 50 for rep in work):
        return None  # e.g. treadmill laps with no distance: no paces to report or evaluate
    rest_durations = [sum(lap.get("duration_s") or 0 for lap in laps[a[-1] + 1: b[0]])
                      for a, b in zip(reps_idx, reps_idx[1:]) if b[0] > a[-1] + 1]
    rest = statistics.median(rest_durations) if rest_durations else None
    rest_note = f" w/ {_fmt_rest(rest)} recovery" if rest else ""

    distances = [rep["distance_m"] for rep in work]
    durations = [rep["duration_s"] for rep in work]
    paces = [lap_pace_per_mile(rep) or 0 for rep in work]
    n = len(work)
    minutes = statistics.median(durations) / 60
    reps = [{"distance_m": round(rep["distance_m"], 1), "duration_s": round(rep["duration_s"], 1),
             "pace_sec_per_mile": round(p), "average_hr": round(rep["average_hr"]) if rep["average_hr"] else None}
            for rep, p in zip(work, paces)]

    def out(label: str, text: str) -> dict:
        return {"kind": "reps", "category": _category("reps", minutes), "label": label, "text": text, "reps": reps,
                "recovery_seconds": round(rest) if rest else None, "work_miles": round(total_work_miles, 2)}

    distance_label = _nearest_standard(statistics.median(distances)) if _cv(distances) <= 0.10 else None
    if distance_label:
        # Every rep must actually be that distance, or printed rep TIMES would read as slow splits.
        meters = next(m for m, lab in STANDARD_REPS if lab == distance_label)
        if any(abs(d - meters) / meters > 0.05 for d in distances):
            distance_label = None
    # Reps run by the clock (every rep 8:00 give or take a few seconds) are time reps even
    # when the distance happens to land near a standard one (8:00 at 6:45/mi is ~1.9 km).
    on_the_minute = minutes >= 3 and _cv(durations) <= 0.02 and abs(statistics.median(durations) - round(minutes) * 60) <= 5
    if distance_label and on_the_minute:
        meters = next(m for m, lab in STANDARD_REPS if lab == distance_label)
        if abs(statistics.median(distances) - meters) / meters > 0.02:
            distance_label = None

    # Distance-based reps (e.g. 800s, miles)
    if distance_label:
        label = distance_label
        if label in ("200", "300", "400"):
            times = ", ".join(str(round(d)) for d in durations)
            return out(f"{n}x{label}m", f"Garmin laps: {n}x{label} ({times}){rest_note}")
        if label in ("600", "800", "1k", "1200", "2k"):
            times = ", ".join(_fmt_time(d) for d in durations)
            return out(f"{n}x{label}" + ("" if label.endswith("k") else "m"), f"Garmin laps: {n}x{label} ({times}){rest_note}")
        if label == "1 mile":
            times = ", ".join(_fmt_time(d) for d in durations)
            return out(f"{n}x1 mile", f"Garmin laps: {n}x1 mile ({times}){rest_note}")
        pace_list = ", ".join(_fmt_time(p) for p in paces)
        return out(f"{n}x{label}", f"Garmin laps: {n}x{label} threshold ({pace_list}){rest_note}")

    # Time-based reps (e.g. 4x10min, 6x3min)
    if _cv(durations) <= 0.10:
        whole = round(minutes)
        pace_list = ", ".join(_fmt_time(p) for p in paces)
        kind = "threshold" if whole >= 5 else "fartlek"
        return out(f"{n}x{whole}min", f"Garmin laps: {n}x{whole}min {kind} ({pace_list}/mi){rest_note}")

    # Consistent but non-standard distance (e.g. 500m reps)
    if _cv(distances) <= 0.10:
        meters = round(statistics.median(distances) / 10) * 10
        times = ", ".join(_fmt_time(d) for d in durations)
        return out(f"{n}x{meters}m", f"Garmin laps: {n}x{meters}m ({times}){rest_note}")

    # Mixed reps (ladder / fartlek) — list each rep
    listed = ", ".join(f"{rep['distance_m'] / METERS_PER_MILE:.2f}mi @ {_fmt_time(p)}" for rep, p in zip(work, paces))
    result = out(f"{n}-rep fartlek", f"Garmin laps: {n} reps fartlek ({listed}){rest_note}")
    result["category"] = "fartlek"
    return result


def summarize_workout(laps: list[dict], easy_pace_sec: float | None = None) -> str | None:
    """Build a workout summary string from laps, or None if it looks like a steady run.

    `easy_pace_sec` is the athlete's typical easy pace (sec/mile); it makes
    detection much more reliable than comparing laps within one run.
    """
    analysis = analyze_laps(laps, easy_pace_sec)
    return analysis["text"] if analysis else None
