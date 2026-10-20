"""What the athlete actually ran versus what was prescribed.

Athletes sometimes run a different quality session than the plan (3x8min threshold on a
3x1200m interval day). Judging that run against the prescription reads it as a failed
workout, which wrongly blocks progression and every hard-session option for two weeks.
This module recognizes a coherent, different session so callers can log it as off-plan:
no ladder change, no failure, and the calendar/coach describe what was really run.
"""
import json
import statistics

from app.services.lap_analyzer import METERS_PER_MILE, analyze_laps

QUALITY = {"threshold", "intervals"}
# A rep this far from the prescribed rep length is a different session, not noise.
# Lap-matching elsewhere tolerates 8-10% (GPS / lap button); 25% is clearly another workout.
REP_LENGTH_TOLERANCE = 0.25


def executed_session(activities, easy_pace_sec: float | None) -> dict | None:
    """Structured lap analysis of the day's quality work (the activity holding the reps)."""
    best = None
    for activity in activities or []:
        try:
            laps = json.loads(activity.splits or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(laps, list) or not all(isinstance(lap, dict) for lap in laps):
            continue
        analysis = analyze_laps(laps, easy_pace_sec)
        if analysis and (best is None or analysis["work_miles"] > best["work_miles"]):
            best = {**analysis, "activity_id": activity.id}
    return best


def _prescribed_rep_seconds(prescription: dict) -> tuple[int, float | None]:
    """(total reps, median rep duration in seconds) of the prescription's work."""
    reps, lengths = 0, []
    for seg in prescription.get("segments", []):
        if seg.get("category") == "strides":
            continue
        reps += seg.get("reps") or 0
        pace = seg.get("pace_range_sec_per_mile") or {}
        target = (pace.get("fast", 0) + pace.get("slow", 0)) / 2 if pace else None
        if seg.get("duration_seconds"):
            lengths.append(seg["duration_seconds"])
        elif seg.get("distance_meters") and target:
            lengths.append(seg["distance_meters"] / METERS_PER_MILE * target)
    return reps, statistics.median(lengths) if lengths else None


def work_minutes(prescription: dict | None, executed: dict | None) -> tuple[float | None, float | None]:
    """(prescribed, executed) minutes of work, for telling the coach whether the dose grew."""
    planned = None
    if prescription:
        reps, rep_seconds = _prescribed_rep_seconds(prescription)
        planned = round(reps * rep_seconds / 60, 1) if reps and rep_seconds else None
    done = round(sum(r["duration_s"] for r in executed["reps"]) / 60, 1) if executed else None
    return planned, done


def off_plan(prescription: dict | None, executed: dict | None) -> bool:
    """True when a confident quality session clearly differs from the prescribed one."""
    if not prescription or not executed or prescription.get("category") not in QUALITY:
        return False
    if executed["kind"] != "reps" and prescription.get("format") == "continuous":
        return False  # a tempo on a tempo day is the planned session
    reps, rep_seconds = _prescribed_rep_seconds(prescription)
    done_seconds = statistics.median(r["duration_s"] for r in executed["reps"])
    different_length = rep_seconds and abs(done_seconds - rep_seconds) / rep_seconds > REP_LENGTH_TOLERANCE
    different_count = len(executed["reps"]) != reps
    if executed["category"] not in QUALITY:
        # A mixed/fartlek read is low confidence: only off-plan when both shape and count differ.
        return bool(executed["kind"] == "reps" and different_length and different_count)
    different_kind = executed["category"] != prescription["category"]
    return bool(different_length or (different_kind and different_count))


def fmt_pace(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def session_title(executed: dict) -> str:
    """Calendar-style title for what was run, e.g. "3x8min Threshold"."""
    kind = {"threshold": "Threshold", "intervals": "Intervals", "speed": "Speed", "fartlek": "Fartlek"}[executed["category"]]
    if executed["kind"] == "tempo":
        return f"{executed['label'].replace(' tempo', '')} Tempo"
    return f"{executed['label']} {kind}" if kind not in executed["label"].title() else executed["label"]


def off_plan_evaluation(prescribed_title: str, executed: dict) -> dict:
    """Stored in PlannedWorkout.evaluation. 'off_plan' moves no ladder and is never a failure."""
    paces = ", ".join(fmt_pace(r["pace_sec_per_mile"]) for r in executed["reps"])
    return {"decision": "off_plan",
            "reason": (f"You ran {session_title(executed)} ({paces}/mi) instead of {prescribed_title}. "
                       f"Logged as {executed['category']} work; the {prescribed_title} progression holds."),
            "evidence": "garmin_laps", "completion": None,
            "reps_completed": len(executed["reps"]), "reps_prescribed": None,
            "pace_diff_sec": 0.0, "fade_sec": 0.0,
            "actual_pace_sec": round(statistics.mean(r["pace_sec_per_mile"] for r in executed["reps"])),
            "new_pace_sec": None, "feel": None, "policy_version": "off-plan-v1",
            "executed": {k: executed[k] for k in ("kind", "category", "label", "reps", "recovery_seconds", "work_miles")}}
