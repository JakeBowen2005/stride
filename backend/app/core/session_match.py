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
# A rep length the athlete describes this far from the prescription is a different session (5x1200
# on a 5x1k day). Tighter than REP_LENGTH_TOLERANCE: the comment, not GPS noise, says it changed.
DESCRIBED_LENGTH_TOLERANCE = 0.10


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
        # The athlete's comment ("did 2x12min instead") says which laps were the reps
        analysis = analyze_laps(laps, easy_pace_sec, getattr(activity, "feel_notes", None))
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
    if executed.get("described") and (
            len(executed["reps"]) > reps
            or (rep_seconds and abs(done_seconds - rep_seconds) / rep_seconds > DESCRIBED_LENGTH_TOLERANCE)):
        # The comment names the session the laps show, and it isn't the prescription: the athlete
        # has told us it was a swap. Fewer reps of the prescribed length stays a partial attempt.
        return result | {"status": "substituted", "intent": "described_in_comment"}
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


# A long-run day with a run this short (vs the plan) was an easy day, not a long run.
SHORT_LONG_RUN_SHARE = 0.6
# An easy day this much longer than planned (both conditions) was the week's long run.
LONG_ON_EASY_FACTOR, LONG_ON_EASY_EXTRA_MILES = 1.5, 3.0
# ...and long enough to stand in for that week's planned long run.
LONG_RUN_STAND_IN_SHARE = 0.75
SWAP_WINDOW_DAYS = 2


def ran_session(planned_type: str, planned_title: str, planned_miles: float,
                ran_miles: float, executed: dict | None, executed_off_plan: bool,
                week_long_run_miles: float | None = None) -> dict:
    """One answer to "what did the athlete run on this day", for every place that shows it.

    Quality comes from the laps (executed_session). Without quality reps, a long-run day run
    short was an easy run, and an easy day run much longer was the long run. Distance from the
    watch is the evidence: no question to the athlete, nothing invented."""
    session = {"title": planned_title, "type": planned_type, "off_plan": False,
               "planned_title": planned_title, "planned_type": planned_type, "swapped_with": None}
    if executed:
        return session | {"title": session_title(executed), "type": "workout", "off_plan": executed_off_plan}
    if planned_type == "long_run" and planned_miles and ran_miles < SHORT_LONG_RUN_SHARE * planned_miles:
        return session | {"title": "Easy Run", "type": "easy", "off_plan": True}
    if planned_type in {"easy", "recovery"} and planned_miles and ran_miles >= max(
            LONG_ON_EASY_FACTOR * planned_miles, planned_miles + LONG_ON_EASY_EXTRA_MILES,
            LONG_RUN_STAND_IN_SHARE * (week_long_run_miles or 0)):
        return session | {"title": "Long Run", "type": "long_run", "off_plan": True}
    return session


def pair_swaps(days: list[dict]) -> None:
    """Link a long run run on a nearby easy day with the long-run day run easy (a swap).
    `days`: [{"date": iso, "session": ran_session(...) or None}], mutated in place."""
    from datetime import date
    shortened = [d for d in days if d["session"] and d["session"]["off_plan"]
                 and d["session"]["planned_type"] == "long_run" and d["session"]["type"] == "easy"]
    lengthened = [d for d in days if d["session"] and d["session"]["off_plan"]
                  and d["session"]["type"] == "long_run" and d["session"]["planned_type"] != "long_run"]
    for short in shortened:
        near = [d for d in lengthened if d["session"]["swapped_with"] is None and abs(
            (date.fromisoformat(d["date"]) - date.fromisoformat(short["date"])).days) <= SWAP_WINDOW_DAYS]
        if near:
            other = min(near, key=lambda d: abs((date.fromisoformat(d["date"]) - date.fromisoformat(short["date"])).days))
            short["session"]["swapped_with"], other["session"]["swapped_with"] = other["date"], short["date"]
