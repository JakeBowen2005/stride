"""Post-workout evaluation engine.

Analyzes workout evidence (Garmin lap summaries or notes) against the prescription
and produces a progression decision: ADVANCE, HOLD, REGRESS, RECALIBRATE, or
INSUFFICIENT (not enough evidence; treated as hold).

Uses:
- Parsed splits from activity descriptions (via pace_calibrator patterns)
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
    evidence: str = "none"  # splits | average | none | different_session
    completion: float | None = None  # reps done / prescribed
    feel: int | None = None
    policy_version: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "decision", "reason", "evidence", "completion", "reps_completed", "reps_prescribed",
            "pace_diff_sec", "fade_sec", "actual_pace_sec", "new_pace_sec", "feel", "policy_version")}


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

EVAL_POLICY_VERSION = "eval-v2"
FULL_COMPLETION = 1.0  # every prescribed rep needed to advance or recalibrate
INCOMPLETE_BELOW = 0.6  # under 60% of reps = clearly incomplete session
FADE_OK = 5.0  # sec (per rep, or sec/mi for paced reps) — controlled
FADE_BIG = 10.0
RECAL_MARGIN = 10.0  # beat prescribed pace by ≥10 s/mi (with full completion + low fade)


def _extract_paced_reps(desc: str) -> tuple[int, list[float]]:
    """Time-based or continuous threshold work written with per-mile paces, e.g.
    "2x10min threshold (6:45, 6:44/mi)" or "tempo 4 miles (6:45, 6:42)". Returns
    (rep_count, paces_sec_per_mile)."""
    if not desc:
        return 0, []
    d = desc.lower()
    m = re.search(r"(\d+)x(\d+)\s*min[^()]*\(([^)]+)\)", d)
    if m:
        paces = [p for p in (_parse_time(x.strip().split("/")[0]) for x in m.group(3).split(",")) if 240 < p < 720]
        return int(m.group(1)), paces
    m = re.search(r"tempo\s+([\d.]+)\s*miles?\s*\(([^)]+)\)", d)
    if m:
        paces = [p for p in (_parse_time(x.strip().split("/")[0]) for x in m.group(2).split(",")) if 240 < p < 720]
        return 1, paces
    return 0, []


def evaluate_workout(
    actual_description: str | None,
    actual_avg_pace_sec: float | None,
    actual_distance_miles: float | None,
    prescribed_type: str,
    prescribed_pace_sec: float | None,
    prescribed_name: str | None,
    feel_rating: int | None,
    prescription: dict | None = None,
    execution: dict | None = None,
) -> WorkoutEvaluation:
    """Evaluate a completed workout against its prescription.

    Gates, in order (policy eval-v2):
    1. Evidence: per-rep splits are strong evidence. A whole-run average includes
       warmup/cooldown, so it can never advance or recalibrate; no data at all is an
       explained hold. Feel alone never proves execution.
    2. Completion: advancing or recalibrating needs every prescribed rep. A short
       session holds (schedule or fatigue can't be told apart from text alone) —
       it is not treated as a fitness regression unless pace/feel also show a struggle.
    3. Fade before speed: a big fade blocks recalibration even if early reps were fast.
    4. One lever: advance changes the ladder level only; recalibrate changes pace only.
    """
    feel = feel_rating  # None = not rated; never assumed
    reps_prescribed = sum(s["reps"] for s in prescription["segments"]) if prescription else extract_rep_count(prescribed_name)[0] if prescribed_name else 0

    def result(decision: str, reason: str, *, pace_diff=None, fade=None, reps=0, pace=None, new_pace=None,
               evidence="none", completion=None) -> WorkoutEvaluation:
        ev = WorkoutEvaluation(
            decision=decision, reason=reason, pace_diff_sec=pace_diff or 0.0, fade_sec=fade or 0.0,
            reps_completed=reps, reps_prescribed=reps_prescribed, actual_pace_sec=pace or 0.0, new_pace_sec=new_pace,
        )
        ev.evidence = evidence
        ev.completion = completion
        ev.feel = feel
        ev.policy_version = EVAL_POLICY_VERSION
        return ev

    numeric = execution and execution.get("evidence_source") in ("garmin_labeled_laps", "garmin_inferred_work_laps")
    if numeric:
        if execution.get("confidence") not in ("high", "medium"):
            return result("insufficient", "Work laps are ambiguous or include extra work. Holding until the session can be matched confidently.", evidence="ambiguous_laps")
        rep_paces = execution["rep_paces_sec_per_mile"]
        targets = execution["target_paces_sec_per_mile"]
        # Normalize each rep against its own target (combo sessions have multiple paces).
        differences = [p - t for p, t in zip(rep_paces, targets) if t is not None]
        normalized = differences if len(differences) == len(rep_paces) else rep_paces
        fade = calculate_fade(normalized)
        reps_done = len(rep_paces)
        primary_splits = []
        if differences:
            prescribed_pace_sec = sum(targets) / len(targets)
    else:
        # ── Gather work evidence ──
        splits_by_dist = extract_splits_from_description(actual_description or "")
        primary_splits, primary_dist_key = [], ""
        for dist_key, splits in splits_by_dist.items():
            if len(splits) > len(primary_splits):
                primary_splits, primary_dist_key = splits, dist_key

        rep_paces: list[float] = []
        fade = None
        if primary_splits:
            dist_miles = INTERVAL_MILES.get(primary_dist_key, 0.5)
            rep_paces = [t / dist_miles for t in primary_splits]
            fade = calculate_fade(primary_splits)  # same-distance reps: raw seconds compare fairly
        else:
            n, paces = _extract_paced_reps(actual_description or "")
            if paces:
                rep_paces = paces
                fade = calculate_fade(paces)  # already normalized to sec/mi
                if not reps_prescribed:
                    reps_prescribed = n
        reps_done = len(primary_splits) if primary_splits else (len(rep_paces) if rep_paces else 0)
    actual_type = identify_workout_type(actual_description)
    if prescribed_type == "workout" and actual_type == "easy" and not rep_paces and not numeric:
        return result("hold", "Ran easy instead of the workout. Holding your level — no fitness judgement from an easy day.",
                      evidence="different_session")

    if not rep_paces:
        if numeric and execution.get("completion") == 0:
            return result("hold", "Recorded work does not match the prescribed rep distance or duration. Holding your level.", evidence="mismatched_laps", completion=0)
        if actual_avg_pace_sec:
            return result(
                "insufficient",
                "Couldn't find rep-by-rep data (only the whole-run average, which includes warmup and cooldown). "
                "Holding your level until there's real work evidence.",
                pace=actual_avg_pace_sec, evidence="average",
            )
        return result("insufficient", "No workout data to evaluate. Holding your level.", evidence="none")

    pace = sum(rep_paces) / len(rep_paces)
    pace_diff = (pace - prescribed_pace_sec) if prescribed_pace_sec else None
    # Time-based sessions: a single parsed pace per rep; count what was recorded
    completion = execution.get("completion") if numeric else (reps_done / reps_prescribed) if reps_prescribed else None
    common = dict(pace_diff=pace_diff, fade=fade, reps=reps_done, pace=pace, evidence=execution["evidence_source"] if numeric else "splits", completion=completion)
    feel_txt = f", feel {feel}/10" if feel is not None else ""
    diff_txt = f"{abs(pace_diff):.0f}s/mi {'faster' if pace_diff < 0 else 'slower'} than target" if pace_diff is not None else "pace target unknown"

    if prescription and not numeric:
        return result("insufficient", "Legacy text is available, but this structured session needs matching work-lap distance/duration evidence before progression.", **common)

    # ── Completion gate ──
    if completion is not None and completion < FULL_COMPLETION:
        struggled = (pace_diff is not None and pace_diff > 10) or (feel is not None and feel <= 4)
        if completion < INCOMPLETE_BELOW and struggled:
            return result("regress", f"Completed {reps_done} of {reps_prescribed} reps and it was a struggle ({diff_txt}{feel_txt}). Stepping back one level.", **common)
        return result("hold", f"Completed {reps_done} of {reps_prescribed} reps. Repeating this level before advancing.", **common)

    # ── Clear struggle ──
    if (fade is not None and fade > FADE_BIG) or (feel is not None and feel <= 4) or (pace_diff is not None and pace_diff > 10 and (feel is None or feel <= 5)):
        return result("regress", f"Struggled — {diff_txt}{feel_txt}, fade {fade or 0:.0f}s. Stepping back one level.", **common)

    if pace_diff is None:
        return result("hold", "Completed all reps, but there was no target pace to compare against. Holding.", **common)

    # ── Recalibrate (pace lever only): fade checked before speed ──
    if pace_diff < -RECAL_MARGIN and (fade or 0) < FADE_OK and feel is not None and feel >= 7:
        if prescription and (len(prescription['segments']) != 1 or prescription['segments'][0].get('category') == 'strides'):
            return result("hold", "Completed the support-speed or mixed session well. Holding pace: this session does not isolate one training-pace category.", **common)
        return result("recalibrate", f"All reps {diff_txt} with controlled fade{feel_txt}. Updating training paces (level unchanged).",
                      new_pace=prescribed_pace_sec - 5, **common)

    # ── Advance (level lever only) ──
    if pace_diff <= 5 and (fade or 0) < FADE_OK and feel is not None and feel >= 7:
        return result("advance", f"All reps on target ({diff_txt}){feel_txt}, controlled fade. Advancing one level.", **common)

    reason = f"Completed all reps ({diff_txt}{feel_txt}, fade {fade or 0:.0f}s). Repeating this level to consolidate."
    if feel is None:
        reason = f"Completed all reps ({diff_txt}). Rate how it felt to unlock progression; holding for now."
    return result("hold", reason, **common)


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
