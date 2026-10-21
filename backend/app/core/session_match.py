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
# Stride matching heuristic: without explicit substitution, materially reduced work
# remains an incomplete attempt. This is an intent/evidence guard, not a safety limit.
MIN_SUBSTITUTION_WORK_SHARE = 0.80


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
    """Sum every segment's work, preserving mixed lengths and rep counts."""
    total = 0.0
    known = bool(prescription)
    for seg in (prescription or {}).get("segments", []):
        if seg.get("category") == "strides":
            continue
        seconds = seg.get("duration_seconds")
        if seconds is None:
            pace = seg.get("pace_range_sec_per_mile") or {}
            if seg.get("distance_meters") and pace.get("fast") and pace.get("slow"):
                seconds = seg["distance_meters"] / METERS_PER_MILE * statistics.mean(pace.values())
            else:
                known = False
                continue
        total += (seg.get("reps") or 0) * seconds
    planned = round(total / 60, 1) if known and total > 0 else None
    done = round(sum(r["duration_s"] for r in executed["reps"]) / 60, 1) if executed else None
    return planned, done


def session_relationship(prescription: dict | None, executed: dict | None, *, substitution_confirmed=False) -> dict:
    """Separate changed shape from incomplete work; do not infer athlete intent.

    A coherent different shape with comparable work can be logged separately without
    advancing the prescribed ladder. Reduced work remains a partial attempt unless
    the athlete explicitly says it was a substitution. Ambiguous/no laps stay unknown.
    """
    planned, done = work_minutes(prescription, executed)
    result = {"status": "unknown", "intent": "confirmed_substitution" if substitution_confirmed else "unknown",
              "planned_work_minutes": planned, "actual_work_minutes": done}
    if not prescription or not executed or prescription.get("category") not in QUALITY:
        return result
    if not executed.get("reps"):
        return result
    if substitution_confirmed:
        return result | {"status": "substituted"}
    reps, rep_seconds = _prescribed_rep_seconds(prescription)
    done_seconds = statistics.median(r["duration_s"] for r in executed["reps"])
    different_length = bool(rep_seconds and abs(done_seconds - rep_seconds) / rep_seconds > REP_LENGTH_TOLERANCE)
    different_count = len(executed["reps"]) != reps
    if planned and done is not None and done < planned * MIN_SUBSTITUTION_WORK_SHARE:
        return result | {"status": "partial"}
    if executed["kind"] != "reps" and prescription.get("format") == "continuous":
        return result | {"status": "matched"}
    if executed["category"] not in QUALITY:
        changed = executed["kind"] == "reps" and different_length and different_count
    else:
        different_kind = executed["category"] != prescription["category"]
        changed = different_length or (different_kind and different_count)
    return result | {"status": "different_session" if changed else "matched"}


def off_plan(prescription: dict | None, executed: dict | None, *, substitution_confirmed=False) -> bool:
    """A separate session, not an automatic exemption for truncated repetitions."""
    return session_relationship(prescription, executed, substitution_confirmed=substitution_confirmed)["status"] in {
        "substituted", "different_session"}


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
            "new_pace_sec": None, "feel": None, "policy_version": "off-plan-v2", "substitution_intent": "unknown",
            "executed": {k: executed[k] for k in ("kind", "category", "label", "reps", "recovery_seconds", "work_miles")}}
