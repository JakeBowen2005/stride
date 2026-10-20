"""Garmin Connect integration.

Garmin's official Activity API is enterprise-only, so Stride uses the
`garminconnect` library, which talks to Garmin Connect as you. Login happens
once via `python garmin_login.py` (email, password, MFA code if enabled);
the resulting tokens are saved to `settings.garmin_tokenstore` and reused
here — your password is never stored.

Sync modes:
- incremental: newest activities first, stops at the first one already stored.
  Cheap enough to run every few minutes (auto-sync loop in main.py).
- full: walks the entire Garmin history (first connect / repair).

Activities previously imported from Strava are matched by start time + distance
and upgraded in place (keeping their descriptions, feel ratings and plan links)
instead of being duplicated.
"""

import bisect
import json
import logging
import statistics
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.activity import Activity
from app.models.garmin import GarminConnection
from app.services.descriptions import is_workout_description
from app.services.lap_analyzer import lap_pace_per_mile, summarize_workout

logger = logging.getLogger("stride.garmin")

METERS_PER_MILE = 1609.34
METERS_TO_FEET = 3.28084
TOKEN_FILE = "garmin_tokens.json"
PAGE_SIZE_INCREMENTAL = 20
PAGE_SIZE_FULL = 100
FULL_SYNC_DELAY = 0.4  # seconds between per-activity requests during full sync
RATE_LIMIT_BACKOFF = timedelta(minutes=30)  # after a Garmin 429, stop calling for this long

_client = None
_client_lock = threading.Lock()
_sync_lock = threading.Lock()
# Serializes every network call through the shared Garmin client (activity + wellness sync)
garmin_io_lock = threading.RLock()


class GarminNotConnected(Exception):
    pass


# ── Auth ────────────────────────────────────────────────────────

def token_dir() -> Path:
    return Path(settings.garmin_tokenstore).expanduser()


def has_tokens() -> bool:
    return (token_dir() / TOKEN_FILE).exists()


def get_client():
    """Return a logged-in Garmin client, built from saved tokens."""
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        if not has_tokens():
            raise GarminNotConnected("No Garmin tokens. Run `python garmin_login.py` in backend/.")
        from garminconnect import Garmin

        client = Garmin()
        client.login(str(token_dir()))
        _client = client
        return client


def reset_client():
    global _client
    with _client_lock:
        _client = None


def get_connection(user_id: int, db: Session) -> GarminConnection:
    conn = db.query(GarminConnection).filter(GarminConnection.user_id == user_id).first()
    if not conn:
        conn = GarminConnection(user_id=user_id, connected=False)
        db.add(conn)
        db.flush()
    return conn


# ── Parsing ─────────────────────────────────────────────────────

def is_run(raw: dict) -> bool:
    type_key = ((raw.get("activityType") or {}).get("typeKey") or "").lower()
    return "run" in type_key  # running, trail_running, treadmill_running, track_running, ultra_run...


def _parse_local_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_activity(raw: dict) -> dict | None:
    """Map a Garmin activity summary to Activity fields. Returns None for non-runs."""
    if not is_run(raw):
        return None

    distance = raw.get("distance") or 0.0
    moving = raw.get("movingDuration") or raw.get("duration") or 0.0
    cadence_spm = raw.get("averageRunningCadenceInStepsPerMinute")
    event = ((raw.get("eventType") or {}).get("typeKey") or "").lower() or None

    return {
        "external_id": str(raw["activityId"]),
        "source": "garmin",
        "name": raw.get("activityName") or "Run",
        "date": _parse_local_time(raw.get("startTimeLocal")) or datetime.now(),
        "distance_meters": distance,
        "duration_seconds": moving,
        "elapsed_seconds": raw.get("elapsedDuration") or raw.get("duration"),
        "average_pace_per_km": (moving / distance) * 1000 if distance > 0 and moving > 0 else None,
        "average_heartrate": raw.get("averageHR"),
        "max_heartrate": raw.get("maxHR"),
        "elevation_gain": raw.get("elevationGain"),
        # Stored per-leg (half of steps/min) to match the legacy Strava convention;
        # the API doubles it back for display.
        "average_cadence": cadence_spm / 2 if cadence_spm else None,
        "event_type": event,
        "activity_subtype": ((raw.get("activityType") or {}).get("typeKey") or None),
        "aerobic_training_effect": raw.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": raw.get("anaerobicTrainingEffect"),
        "training_effect_label": raw.get("trainingEffectLabel"),
        "training_load": raw.get("activityTrainingLoad"),
        "vo2max": raw.get("vO2MaxValue"),
        "avg_ground_contact_time": raw.get("avgGroundContactTime"),
        "avg_vertical_oscillation": raw.get("avgVerticalOscillation"),
        "calories": raw.get("calories"),
        "workout_type": "race" if event == "race" else None,
    }


def parse_laps(splits_response: dict | None) -> list[dict]:
    """Normalize Garmin lapDTOs into Stride's split format."""
    laps = []
    for i, lap in enumerate((splits_response or {}).get("lapDTOs") or [], 1):
        distance = lap.get("distance") or 0.0
        duration = lap.get("movingDuration") or lap.get("duration") or 0.0
        entry = {
            "mile": i,  # lap number (kept as "mile" for frontend compatibility)
            "distance_m": round(distance, 1),
            "distance_miles": round(distance / METERS_PER_MILE, 2),
            "duration_s": round(duration, 1),
            "duration_seconds": round(duration, 1),
            "heart_rate": round(lap["averageHR"]) if lap.get("averageHR") else None,
            "elevation_diff_ft": round(((lap.get("elevationGain") or 0) - (lap.get("elevationLoss") or 0)) * METERS_TO_FEET, 1),
            "intensity": lap.get("intensityType"),
        }
        pace = lap_pace_per_mile(entry)
        entry["pace_seconds"] = round(pace, 1) if pace else None
        entry["pace"] = f"{int(pace // 60)}:{int(pace % 60):02d}/mi" if pace else "—"
        laps.append(entry)
    return laps


def build_description(user_desc: str | None, laps: list[dict], easy_pace_sec: float | None) -> str | None:
    """User notes win if they already describe the workout; otherwise add a lap summary."""
    if user_desc and is_workout_description(user_desc):
        return user_desc
    summary = summarize_workout(laps, easy_pace_sec)
    if user_desc and summary:
        return f"{user_desc}\n\n{summary}"
    return summary or user_desc


def refresh_lap_summaries(db: Session) -> int:
    """Rewrite stored "Garmin laps: ..." text with the current lap analyzer.

    The pace calibrator and evaluator read this text, so when lap detection improves (e.g.
    merging auto-lap remainders into reps) old runs must be re-read too. Only the generated
    summary is replaced; the athlete's own notes before it are kept. Idempotent.
    """
    changed = 0
    indexes: dict[int, EasyPaceIndex] = {}
    rows = db.query(Activity).filter(Activity.source == "garmin", Activity.description.like("%Garmin laps:%")).all()
    for activity in rows:
        try:
            laps = json.loads(activity.splits or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(laps, list) or not all(isinstance(lap, dict) for lap in laps):
            continue
        index = indexes.setdefault(activity.user_id, EasyPaceIndex(activity.user_id, db))
        easy = index.at(activity.date)
        summary = summarize_workout(laps, easy) if easy else None
        if not summary:
            continue  # never delete a summary; without an easy-pace reference keep what's stored
        head = activity.description.split("Garmin laps:")[0].rstrip()
        updated = f"{head}\n\n{summary}" if head else summary
        if updated != activity.description:
            activity.description = updated
            changed += 1
    if changed:
        db.commit()
    return changed


# ── Sync ────────────────────────────────────────────────────────

class EasyPaceIndex:
    """Typical easy pace (sec/mi) as of any date — the reference for lap analysis.

    Loads the athlete's run paces once, then answers per-activity lookups from
    memory (a full import asks ~600 times; querying the DB each time was O(n^2)).
    Uses the 60th percentile of 3-10 mile runs in the 90 days before the date,
    falling back to all earlier history when that window is thin.
    """

    def __init__(self, user_id: int, db: Session):
        rows = db.query(Activity.date, Activity.distance_meters, Activity.duration_seconds).filter(
            Activity.user_id == user_id,
            Activity.distance_meters >= 4800,
            Activity.distance_meters <= 16000,
            Activity.duration_seconds > 0,
        ).order_by(Activity.date).all()
        self.dates = [r[0] for r in rows]
        self.paces = [r[2] / (r[1] / METERS_PER_MILE) for r in rows]

    @staticmethod
    def _pct60(paces: list[float]) -> float | None:
        if len(paces) < 5:
            return None
        return statistics.quantiles(paces, n=10)[5]

    def at(self, as_of: datetime | None = None) -> float | None:
        as_of = as_of or datetime.now()
        end = bisect.bisect_left(self.dates, as_of)
        start = bisect.bisect_left(self.dates, as_of - timedelta(days=90))
        return self._pct60(self.paces[start:end]) or self._pct60(self.paces[:end])


def recent_easy_pace(user_id: int, db: Session, as_of: datetime | None = None) -> float | None:
    return EasyPaceIndex(user_id, db).at(as_of)


def _find_legacy_match(user_id: int, parsed: dict, db: Session) -> Activity | None:
    """Find a non-Garmin activity (e.g. Strava import) that is the same run."""
    start = parsed["date"]
    window = timedelta(minutes=10)
    candidates = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.source != "garmin",
        Activity.date >= start - window,
        Activity.date <= start + window,
    ).all()
    best, best_diff = None, None
    for c in candidates:
        if not c.distance_meters or not parsed["distance_meters"]:
            continue
        diff = abs(c.distance_meters - parsed["distance_meters"]) / parsed["distance_meters"]
        if diff <= 0.05 and (best_diff is None or diff < best_diff):
            best, best_diff = c, diff
    return best


def _apply(activity: Activity, parsed: dict):
    for key, val in parsed.items():
        if val is None:
            continue
        if key == "workout_type" and activity.workout_type:
            continue  # don't clobber classification
        setattr(activity, key, val)


def _store_activity(client, user_id: int, raw: dict, parsed: dict, db: Session, easy_pace: float | None) -> str:
    """Insert/merge one activity. Returns 'new', 'merged' or 'updated'."""
    activity = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.source == "garmin",
        Activity.external_id == parsed["external_id"],
    ).first()
    outcome = "updated"
    if activity is None:
        activity = _find_legacy_match(user_id, parsed, db)
        outcome = "merged" if activity else "new"
    if activity is None:
        activity = Activity(user_id=user_id)
        db.add(activity)

    legacy_desc = activity.description
    _apply(activity, parsed)

    try:
        laps = parse_laps(client.get_activity_splits(parsed["external_id"]))
    except Exception as e:  # laps are a bonus; never fail the sync over them
        logger.warning("Lap fetch failed for %s: %s", parsed["external_id"], e)
        laps = []
    if laps:
        activity.splits = json.dumps(laps)

    user_desc = raw.get("description")
    if user_desc is None and outcome == "new":
        try:
            detail = client.get_activity(parsed["external_id"]) or {}
            user_desc = detail.get("description")
        except Exception:
            pass
    # Keep hand-written Strava descriptions on merged runs
    base_desc = user_desc or (legacy_desc if outcome != "new" else None)
    if base_desc and base_desc.startswith("Garmin laps:"):
        base_desc = None  # regenerate our own summary rather than nesting it
    activity.description = build_description(base_desc, laps, easy_pace)
    activity.has_workout_description = is_workout_description(activity.description)
    if outcome in {'new', 'merged'}:
        from app.services.coaching_jobs import enqueue_synced_run
        enqueue_synced_run(activity, db)
    return outcome


def sync_garmin(user_id: int, db: Session, full: bool = False) -> dict:
    """Pull running activities from Garmin into the DB. Thread-safe; one sync at a time."""
    if not _sync_lock.acquire(blocking=False):
        return {"status": "busy", "message": "A Garmin sync is already running."}
    conn = get_connection(user_id, db)
    if conn.backoff_until and conn.backoff_until > datetime.now():
        _sync_lock.release()
        return {"status": "backoff", "message": f"Garmin rate-limited us; retrying after {conn.backoff_until:%H:%M}."}
    try:
        with garmin_io_lock:
            return _sync(user_id, db, full)
    finally:
        _sync_lock.release()


def _sync(user_id: int, db: Session, full: bool) -> dict:
    conn = get_connection(user_id, db)
    try:
        client = get_client()
    except GarminNotConnected as e:
        conn.connected = False
        conn.last_error = str(e)
        db.commit()
        raise
    except Exception as e:
        reset_client()
        _record_failure(conn, e)
        db.commit()
        raise

    if not conn.display_name:
        try:
            conn.display_name = client.get_full_name()
        except Exception:
            pass

    known = {
        ext for (ext,) in db.query(Activity.external_id).filter(
            Activity.user_id == user_id, Activity.source == "garmin"
        )
    }
    # Until one full import has completed (it may have been interrupted), keep walking the
    # whole history — but skip runs already stored, so a resume doesn't redo finished work.
    backfill = not full and not conn.full_sync_done
    full = full or backfill
    page_size = PAGE_SIZE_FULL if full else PAGE_SIZE_INCREMENTAL
    easy_paces = EasyPaceIndex(user_id, db)
    counts = {"new": 0, "merged": 0, "updated": 0, "skipped_non_runs": 0, "seen": 0}
    refresh_cutoff = datetime.now() - timedelta(hours=48)

    start = 0
    try:
        while True:
            batch = client.get_activities(start, page_size) or []
            if not batch:
                break
            reached_known = False
            for raw in batch:
                counts["seen"] += 1
                parsed = parse_activity(raw)
                if parsed is None:
                    counts["skipped_non_runs"] += 1
                    continue
                if parsed["external_id"] in known and backfill:
                    continue
                if parsed["external_id"] in known and not full:
                    # Re-check the last 48h so renamed runs / added notes come through
                    if parsed["date"] >= refresh_cutoff:
                        _refresh_summary(user_id, raw, parsed, db)
                        continue
                    reached_known = True
                    break
                outcome = _store_activity(client, user_id, raw, parsed, db, easy_paces.at(parsed["date"]))
                counts[outcome] += 1
                if full:
                    time.sleep(FULL_SYNC_DELAY)
                    if (counts["new"] + counts["merged"] + counts["updated"]) % 25 == 0:
                        db.commit()
            db.commit()
            if reached_known or len(batch) < page_size:
                break
            start += page_size
    except Exception as e:
        db.rollback()
        conn = get_connection(user_id, db)
        _record_failure(conn, e)
        db.commit()
        raise

    changed = counts["new"] + counts["merged"]
    if changed or full:
        from app.services.analyzer import classify_activities, detect_prs

        classify_activities(user_id, db)
        detect_prs(user_id, db)

    conn = get_connection(user_id, db)
    conn.connected = True
    conn.last_error = None
    conn.last_sync_at = datetime.now()
    if changed:
        conn.last_new_activity_at = datetime.now()
    if full:
        conn.full_sync_done = True
    db.commit()

    counts["mode"] = "full" if full else "incremental"
    counts["status"] = "ok"
    counts["message"] = (
        f"Garmin sync complete: {counts['new']} new, {counts['merged']} matched to existing runs."
        if changed else "Garmin sync complete: you're up to date."
    )
    return counts


def _record_failure(conn: GarminConnection, e: Exception):
    """Classify a Garmin failure: expired session (rebuild client), rate limit (back off)."""
    from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

    if isinstance(e, GarminConnectAuthenticationError):
        reset_client()
        conn.connected = False
        conn.last_error = "Garmin session expired. Re-run `python garmin_login.py` in backend/."
    elif isinstance(e, GarminConnectTooManyRequestsError):
        conn.backoff_until = datetime.now() + RATE_LIMIT_BACKOFF
        conn.last_error = "Garmin rate limit hit; pausing sync for 30 minutes."
    else:
        conn.last_error = f"Sync error: {type(e).__name__}"
    logger.warning("Garmin sync failed for user %s: %s", conn.user_id, e)


def _refresh_summary(user_id: int, raw: dict, parsed: dict, db: Session):
    activity = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.source == "garmin",
        Activity.external_id == parsed["external_id"],
    ).first()
    if not activity:
        return
    activity.name = parsed["name"]
    user_desc = raw.get("description")
    if user_desc and user_desc not in (activity.description or ""):
        laps = json.loads(activity.splits) if activity.splits else []
        activity.description = build_description(user_desc, laps, recent_easy_pace(user_id, db, activity.date))  # rare path
        activity.has_workout_description = is_workout_description(activity.description)


def _strip_lap_summary(description: str | None) -> str | None:
    if not description:
        return None
    idx = description.find("Garmin laps:")
    if idx == -1:
        return description
    return description[:idx].strip() or None


def reanalyze_laps(user_id: int, db: Session) -> dict:
    """Rebuild lap-based workout summaries from stored laps (no Garmin API calls),
    then re-classify and re-detect PRs. Use after improving lap_analyzer."""
    from app.services.analyzer import classify_activities, detect_prs

    acts = db.query(Activity).filter(
        Activity.user_id == user_id, Activity.source == "garmin", Activity.splits.isnot(None)
    ).all()
    easy_paces = EasyPaceIndex(user_id, db)
    changed = 0
    for a in acts:
        try:
            laps = json.loads(a.splits)
        except (json.JSONDecodeError, TypeError):
            continue
        if not laps or "distance_m" not in laps[0]:
            continue  # legacy Strava mile splits, not Garmin laps
        new_desc = build_description(_strip_lap_summary(a.description), laps, easy_paces.at(a.date))
        if new_desc != a.description:
            a.description = new_desc
            a.has_workout_description = is_workout_description(new_desc)
            changed += 1
    db.commit()
    counts = classify_activities(user_id, db)
    detect_prs(user_id, db)
    return {"reanalyzed": len(acts), "changed": changed, "classification": counts}
