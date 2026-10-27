from app.models.operations import ProviderCredential
from app.config import settings
from app.athlete_clock import today as athlete_today
"""Garmin Connect integration (official Personal API).

Stride reads the athlete's own Garmin data with a Garmin Connect Personal API key
(`GARMIN_API_KEY`, created at connect.garmin.com/app/settings/personalApiToken).
See `services/garmin_api.py` for the client and what the API does not expose.

Sync modes:
- incremental: one date-windowed request for runs since the newest stored run
  (minus a 2-day overlap so renamed/late-uploaded runs come through). Garmin
  filters non-runs server-side; only new runs cost a FIT download (for laps).
- full: walks the entire running history (first connect / repair). Resumable.

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
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.activity import Activity, runs_only
from app.models.garmin import GarminConnection
from app.models.history import ActivitySource
from app.services.history_evidence import PARSER_VERSION, REPAIR_BATCH, capture, coverage, pending, source_for
from app.services.descriptions import is_workout_description
from app.services.garmin_api import (
    GarminAuthError, GarminNotConnected, GarminRateLimited, get_client, has_api_key, laps_from_fit, reset_client,
)
from app.services.lap_analyzer import summarize_workout

logger = logging.getLogger("stride.garmin")

METERS_PER_MILE = 1609.34
PAGE_SIZE = 100
OVERLAP_DAYS = 2  # incremental window reaches back past the newest stored run
FULL_SYNC_DELAY = 0.4  # seconds between FIT downloads during a full import
RATE_LIMIT_BACKOFF = timedelta(minutes=30)  # after a Garmin 429, stop calling for this long
ERROR_BACKOFF = timedelta(minutes=10)  # network / 5xx: don't hammer Garmin every minute
AUTH_BACKOFF = timedelta(hours=12)  # rejected key: needs a new key (and restart) anyway

_sync_lock = threading.Lock()
_athlete_sync_locks = {}
_athlete_io_locks = {}
_lock_registry = threading.Lock()


def sync_lock_for(user_id):
    if not settings.accounts_enabled:return _sync_lock
    with _lock_registry:return _athlete_sync_locks.setdefault(user_id,threading.Lock())


def io_lock_for(user_id):
    if not settings.accounts_enabled:return garmin_io_lock
    with _lock_registry:return _athlete_io_locks.setdefault(user_id,threading.RLock())

# Serializes every network call through the shared Garmin client (activity + wellness sync)
garmin_io_lock = threading.RLock()

__all__ = ["GarminNotConnected", "has_api_key", "laps_from_fit", "poll_due", "sync_garmin", "garmin_io_lock"]


def _in_quiet_hours(hour: int, spec: str) -> bool:
    try:
        start, end = (int(x) for x in spec.split("-"))
    except ValueError:
        return False
    return start <= hour or hour < end if start > end else start <= hour < end


def clear_backoff(user_id: int):
    """On startup: the process may have a new key, so give it a fresh chance."""
    from app.database import SessionLocal
    with SessionLocal() as db:
        conn = db.query(GarminConnection).filter(GarminConnection.user_id == user_id).first()
        if conn and conn.backoff_until:
            conn.backoff_until = None
            db.commit()


def poll_due(user_id: int, now: datetime | None = None) -> bool:
    """Is a background check due? Any sync (including the app-open one) resets the clock,
    and overnight checks drop to hourly."""
    from app.config import settings
    from app.database import SessionLocal

    if settings.garmin_poll_minutes <= 0:
        return False
    now = now or datetime.now()
    interval = timedelta(minutes=settings.garmin_poll_minutes)
    if _in_quiet_hours(now.hour, settings.garmin_quiet_hours):
        interval = max(interval, timedelta(hours=1))
    with SessionLocal() as db:
        conn = db.query(GarminConnection).filter(GarminConnection.user_id == user_id).first()
        if conn and conn.backoff_until and conn.backoff_until > now:
            return False
        last = conn.last_sync_at if conn else None
    return last is None or now - last >= interval


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
    started = _parse_local_time(raw.get("startTimeLocal"))
    if started is None:
        raise ValueError("Garmin activity has no valid local start time")

    distance = raw.get("distance") or 0.0
    moving = raw.get("movingDuration") or raw.get("duration") or 0.0
    cadence_spm = raw.get("averageRunningCadenceInStepsPerMinute")
    event = ((raw.get("eventType") or {}).get("typeKey") or "").lower() or None

    return {
        "external_id": str(raw["activityId"]),
        "source": "garmin",
        "name": raw.get("activityName") or "Run",
        "date": started,
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


def build_description(user_desc: str | None, laps: list[dict], easy_pace_sec: float | None,
                      comment: str | None = None) -> str | None:
    """User notes win if they already describe the workout; otherwise add a lap summary."""
    if user_desc and is_workout_description(user_desc):
        return user_desc
    summary = summarize_workout(laps, easy_pace_sec, comment)
    if user_desc and summary:
        return f"{user_desc}\n\n{summary}"
    return summary or user_desc


def refresh_activity_lap_summary(activity: Activity, db: Session) -> bool:
    """Re-read one run's "Garmin laps: ..." text, e.g. after the athlete's comment named the
    structure ("2x12min"). Same rules as refresh_lap_summaries; the caller commits."""
    if activity.source != "garmin" or "Garmin laps:" not in (activity.description or ""):
        return False
    try:
        laps = json.loads(activity.splits or "[]")
    except (ValueError, TypeError):
        return False
    if not isinstance(laps, list) or not all(isinstance(lap, dict) for lap in laps):
        return False
    easy = EasyPaceIndex(activity.user_id, db).at(activity.date)
    summary = summarize_workout(laps, easy, activity.feel_notes) if easy else None
    if not summary:
        return False
    head = activity.description.split("Garmin laps:")[0].rstrip()
    updated = f"{head}\n\n{summary}" if head else summary
    if updated == activity.description:
        return False
    activity.description = updated
    return True


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
        summary = summarize_workout(laps, easy, activity.feel_notes) if easy else None
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
            runs_only(),
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
    """Find a non-Garmin activity (e.g. Strava import) that is the same run.

    Manual noon placeholders require one plausible same-day distance match.
    Ambiguous doubles remain separate; successful merges keep feedback and plan links."""
    start = parsed["date"]
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    imports = db.query(Activity).filter(Activity.user_id==user_id,Activity.source=='manual',
        Activity.external_id.like('fit-%'),Activity.date>=start-timedelta(seconds=10),Activity.date<=start+timedelta(seconds=10)).all()
    imports = [a for a in imports if abs(a.distance_meters-parsed['distance_meters'])/max(parsed['distance_meters'],1)<=.005
               and abs(a.duration_seconds-parsed['duration_seconds'])/max(parsed['duration_seconds'],1)<=.02]
    if len(imports)==1:return imports[0]
    manual = db.query(Activity).filter(
        Activity.user_id == user_id, Activity.source == "manual", Activity.external_id.like("manual-%"),
        Activity.date >= day, Activity.date < day + timedelta(days=1),
    ).first()
    if manual and manual.distance_meters and parsed["distance_meters"]:
        # Noon is a placeholder, so compare distance and all uploads on the date.
        # Never let an unrelated shakeout inherit the main workout's feedback.
        diff = abs(manual.distance_meters - parsed["distance_meters"]) / parsed["distance_meters"]
        candidates_today = db.info.get('garmin_day_candidates', {}).get(day.date(), [])
        matches = [r for r in candidates_today if r.get('distance') and
                   abs(manual.distance_meters - r['distance']) / r['distance'] <= .05]
        if diff <= .05 and len(matches) == 1 and day.date() not in db.info.get('garmin_ambiguous_days', set()):
            return manual
    window = timedelta(minutes=10)
    candidates = db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.source.notin_(["garmin", "manual"]),
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

    if outcome == 'merged':
        alias = source_for(activity, activity.source, activity.external_id or f'activity-{activity.id}', db)
        capture(alias, 'legacy', db, payload={c.name: getattr(activity, c.name) for c in Activity.__table__.columns})
        alias.enrichment_status = 'complete'
    _apply(activity, parsed)
    source = source_for(activity, 'garmin', parsed['external_id'], db)
    capture(source, 'summary', db, payload=raw)
    _enrich(client, activity, source, db, easy_pace)
    from app.services.coaching_jobs import enqueue_synced_run
    enqueue_synced_run(activity, db)
    return outcome


def watch_rating(detail: dict | None) -> tuple[int | None, int | None]:
    """Garmin's post-run self-evaluation (feel 0-100, perceived effort 10-100) from the
    activity detail. The run list doesn't carry it; the detail summary does."""
    summary = (detail or {}).get("summaryDTO") or {}
    feel, rpe = summary.get("directWorkoutFeel"), summary.get("directWorkoutRpe")
    return (int(feel) if isinstance(feel, (int, float)) else None,
            int(rpe) if isinstance(rpe, (int, float)) and rpe > 0 else None)


def _watch_rating_due(activity) -> bool:
    if activity.garmin_rating_checked_at is None:
        return True
    # Watch feedback may arrive after the FIT/summary. Refresh recent evidence,
    # with a bounded window so old history never becomes a detail-request crawl.
    if activity.date.date() < athlete_today() - timedelta(days=7):
        return False
    delay = timedelta(minutes=15) if activity.garmin_feel is None and activity.garmin_rpe is None else timedelta(hours=6)
    return activity.garmin_rating_checked_at < datetime.now() - delay


def _fetch_watch_rating(client, activity, db=None) -> bool:
    """One detail request per run. Caller has committed, so no SQLite writer is held
    across network I/O. Rate limits and a rejected key propagate; anything else is
    treated as "no rating" (it's optional evidence)."""
    if not hasattr(client, "get_activity"):
        return False
    try:
        detail = client.get_activity(activity.external_id)
        feel, rpe = watch_rating(detail)
        if db is not None:
            capture(source_for(activity, 'garmin', activity.external_id, db), 'detail', db, payload=detail or {})
    except (GarminAuthError, GarminRateLimited):
        raise
    except Exception as exc:
        logger.info("Watch rating fetch failed for %s: %s", activity.external_id, type(exc).__name__)
        return False
    activity.garmin_rating_checked_at = datetime.now()
    changed = (feel, rpe) != (activity.garmin_feel, activity.garmin_rpe)
    activity.garmin_feel, activity.garmin_rpe = feel, rpe
    return changed


def _enrich(client, activity, source, db, easy_pace):
    """Persist original evidence before parsing; retry failures independently of dates."""
    db.commit()  # summary + pending enrichment are durable; release writer before FIT I/O
    from app.services.sync_jobs import heartbeat
    heartbeat(activity.user_id,db)
    if _watch_rating_due(activity):
        _fetch_watch_rating(client, activity, db)
        db.commit()  # detail evidence is durable; release writer before FIT I/O
    try:
        if hasattr(client, 'get_fit'):
            blob = client.get_fit(source.external_id)
            if not blob:
                pending(source, 'FIT not yet available')
                return False
            capture(source, 'fit', db, blob=blob)
            laps = laps_from_fit(blob)
        else:  # narrow adapter for legacy clients/test doubles
            laps = client.get_laps(source.external_id)
        if not laps:
            pending(source, 'No lap evidence')
            return False
    except (GarminAuthError, GarminRateLimited):
        raise
    except Exception as exc:
        pending(source, type(exc).__name__)
        return False
    activity.splits = json.dumps(laps)
    activity.description = build_description(_strip_lap_summary(activity.description), laps, easy_pace,
                                             activity.feel_notes)
    activity.has_workout_description = is_workout_description(activity.description)
    source.fit_checked_at = datetime.now()
    source.enrichment_status, source.parser_version = 'complete', PARSER_VERSION
    source.last_error, source.next_retry_at, source.attempts = None, None, 0
    return True


def _retry_enrichment(client, user_id, db, easy_paces, attempted):
    rows = db.query(ActivitySource).filter(ActivitySource.user_id == user_id,
        ActivitySource.provider == 'garmin', ActivitySource.enrichment_status.in_(['pending', 'retry']),
        or_(ActivitySource.next_retry_at.is_(None), ActivitySource.next_retry_at <= datetime.now())).order_by(ActivitySource.id).limit(REPAIR_BATCH).all()
    changed = 0
    for source in rows:
        if source.external_id in attempted:
            continue
        activity = db.get(Activity, source.activity_id)
        if activity and _enrich(client, activity, source, db, easy_paces.at(activity.date)):
            changed += 1
            from app.services.coaching_jobs import enqueue_synced_run
            enqueue_synced_run(activity, db)
    return changed


def sync_garmin(user_id: int, db: Session, full: bool = False) -> dict:
    """Pull running activities from Garmin into the DB. Thread-safe; one sync at a time."""
    lock=sync_lock_for(user_id)
    if not lock.acquire(blocking=False):
        return {"status": "busy", "message": "A Garmin sync is already running."}
    db.info.pop("garmin_day_candidates", None)
    db.info.pop("garmin_ambiguous_days", None)
    try:
        db.info.pop("garmin_day_candidates", None)
        db.info.pop("garmin_ambiguous_days", None)
        conn = get_connection(user_id, db)
        if conn.backoff_until and conn.backoff_until > datetime.now():
            return {"status": "backoff", "message": f"Garmin rate-limited us; retrying after {conn.backoff_until:%H:%M}."}
        db.commit()  # connection creation must not hold SQLite's writer across network calls
        with io_lock_for(user_id):
            return _sync(user_id, db, full)
    finally:
        lock.release()


def _pages(client, start_date: date | None = None, end_date: date | None = None):
    """Yield pages of runs (newest first) until Garmin returns a short page."""
    start = 0
    while True:
        batch = client.search_runs(start, PAGE_SIZE, start_date, end_date)
        if batch:
            yield batch
        if len(batch) < PAGE_SIZE:
            return
        start += PAGE_SIZE


def _client(user_id: int, db: Session):
    if settings.accounts_enabled or db.get(ProviderCredential, user_id):
        from app.services.provider_connections import client_for
        return client_for(user_id)
    return get_client()


def refresh_watch_rating(user_id: int, activity: Activity | None, db: Session) -> bool:
    """The athlete is commenting on this run now: read the watch's post-run rating first
    so the review sees it. Garmin may not have had it when the run first synced, and the
    next sync may be minutes away. Call before taking the schedule write lock (network
    I/O). Optional evidence: never raises, and skips when a sync already holds Garmin I/O."""
    if activity is None or activity.source != "garmin" or not activity.external_id:
        return False
    if activity.date.date() < athlete_today() - timedelta(days=7):
        return False
    lock = io_lock_for(user_id)
    if not lock.acquire(timeout=5):
        return False  # a running sync reads the rating itself
    try:
        changed = _fetch_watch_rating(_client(user_id, db), activity, db)
        db.commit()
        return changed
    except Exception as exc:
        db.rollback()
        logger.info("Watch rating refresh skipped for %s: %s", activity.external_id, type(exc).__name__)
        return False
    finally:
        lock.release()


def _sync(user_id: int, db: Session, full: bool) -> dict:
    conn = get_connection(user_id, db)
    try:
        client = _client(user_id, db)
    except GarminNotConnected as e:
        conn.connected = False
        conn.last_error = str(e)
        db.commit()
        raise
    except Exception as e:
        _record_failure(conn, e)
        db.commit()
        raise

    if not conn.display_name:
        try:
            conn.display_name = client.display_name()
        except (GarminAuthError, GarminRateLimited):
            pass  # the activity request below reports these properly
        except Exception:
            pass  # cosmetic; never fail a sync over the profile name
    known, lapless = set(), set()
    attempted = set()
    for ext, splits in db.query(Activity.external_id, Activity.splits).filter(
            Activity.user_id == user_id, Activity.source == "garmin"):
        known.add(ext)
        if not splits or splits == "[]":
            lapless.add(ext)
    # An explicit repair has a durable generation. Resume it after a rate limit
    # without downloading every already-checked FIT again from the newest page.
    if full and conn.full_repair_started_at is None:
        conn.full_repair_started_at = datetime.now()
    repair_started = conn.full_repair_started_at
    full = full or repair_started is not None
    db.commit()
    # Until one full import has completed (it may have been interrupted), keep walking the
    # whole history — but skip runs already stored, so a resume doesn't redo finished work.
    if conn.full_sync_done and conn.last_reconciled_at is None:
        conn.last_reconciled_at = datetime.now() - timedelta(days=6)
    backfill = not full and not conn.full_sync_done
    reconcile = bool(conn.full_sync_done and (conn.last_reconciled_at is not None and conn.last_reconciled_at < datetime.now() - timedelta(days=7)))
    explicit_full = full
    full = full or backfill or reconcile
    easy_paces = EasyPaceIndex(user_id, db)
    counts = {"new": 0, "merged": 0, "updated": 0, "seen": 0, "requests": 0}

    if full:
        pages = _pages(client)
    else:
        newest = db.query(func.max(Activity.date)).filter(
            Activity.user_id == user_id, Activity.source == "garmin").scalar()
        since = min((newest or datetime.now()).date(), (conn.last_sync_at or datetime.now()).date()) - timedelta(days=OVERLAP_DAYS)
        pages = _pages(client, since, athlete_today() + timedelta(days=1))

    try:
        for batch in pages:
            if settings.accounts_enabled:
                from app.services.provider_connections import configured
                if not configured(user_id,db):
                    raise GarminNotConnected('Provider connection was removed during sync.')
            counts["requests"] += 1
            # Manual placeholders must have exactly one plausible Garmin counterpart.
            candidates = db.info.setdefault('garmin_day_candidates', {})
            for candidate in batch:
                dt = _parse_local_time(candidate.get('startTimeLocal'))
                if dt:
                    candidates.setdefault(dt.date(), []).append(candidate)
            if len(batch) == PAGE_SIZE:
                boundary = _parse_local_time(batch[-1].get('startTimeLocal'))
                if boundary:
                    db.info.setdefault('garmin_ambiguous_days', set()).add(boundary.date())
            for raw in batch:
                counts["seen"] += 1
                parsed = parse_activity(raw)
                if parsed is None:
                    continue
                if parsed["external_id"] in known:
                    if not backfill:
                        updated = _refresh_summary(user_id, parsed, db, raw)
                        rated = db.query(Activity).filter_by(user_id=user_id, source='garmin', external_id=parsed['external_id']).one()
                        if _watch_rating_due(rated) and not full:
                            # Runs synced before watch ratings were read: check once, inside the
                            # incremental window only (never a full-history crawl).
                            db.commit()
                            counts["requests"] += 1
                            rating_changed = _fetch_watch_rating(client, rated, db)
                            updated = rating_changed or updated
                            if rating_changed:
                                from app.services.coaching_jobs import enqueue_synced_run
                                enqueue_synced_run(rated, db)
                        source = db.query(ActivitySource).filter_by(user_id=user_id, provider='garmin', external_id=parsed['external_id']).one()
                        repair_due = explicit_full and (source.fit_checked_at is None or source.fit_checked_at < repair_started)
                        if repair_due or (source.enrichment_status in {'pending', 'retry'} and (source.next_retry_at is None or source.next_retry_at <= datetime.now())):
                            attempted.add(parsed['external_id'])
                            activity = db.get(Activity, source.activity_id)
                            if _enrich(client, activity, source, db, easy_paces.at(parsed['date'])):
                                updated = True
                                from app.services.coaching_jobs import enqueue_synced_run
                                enqueue_synced_run(activity, db)
                            if explicit_full:
                                time.sleep(FULL_SYNC_DELAY)
                        counts['updated'] += int(updated)
                    continue
                attempted.add(parsed['external_id'])
                outcome = _store_activity(client, user_id, raw, parsed, db, easy_paces.at(parsed["date"]))
                counts["requests"] += 1
                counts[outcome] += 1
                known.add(parsed["external_id"])
                if full:
                    time.sleep(FULL_SYNC_DELAY)
                    if (counts["new"] + counts["merged"]) % 25 == 0:
                        db.commit()
            db.commit()
    except Exception as e:
        db.rollback()
        conn = get_connection(user_id, db)
        _record_failure(conn, e)
        db.commit()
        raise

    if not backfill:
        try:
            counts['updated'] += _retry_enrichment(client, user_id, db, easy_paces, attempted)
        except Exception as exc:
            db.rollback()
            _record_failure(get_connection(user_id, db), exc)
            db.commit()
            raise
    # A checked discovery interval records access, not proof that every day was worn.
    earliest = db.query(func.min(Activity.date)).filter_by(user_id=user_id, source='garmin').scalar()
    coverage(user_id, 'activities', (earliest.date() if earliest else athlete_today()) if full else since,
             athlete_today(), 'checked', db)
    changed = counts["new"] + counts["merged"] + counts['updated']
    if changed or full:
        reanalyze_laps(user_id, db)

    conn = get_connection(user_id, db)
    conn.connected = True
    conn.last_error = None
    conn.last_sync_at = datetime.now()
    if counts["new"] + counts["merged"]:
        conn.last_new_activity_at = datetime.now()
    if full:
        conn.full_sync_done = True
        conn.last_reconciled_at = datetime.now()
        conn.full_repair_started_at = None
    db.commit()

    counts["mode"] = "full" if full else "incremental"
    counts["status"] = "ok"
    counts["message"] = (
        f"Garmin sync complete: {counts['new']} new, {counts['merged']} matched to existing runs."
        if changed else "Garmin sync complete: you're up to date."
    )
    return counts


def _record_failure(conn: GarminConnection, e: Exception):
    """Classify a Garmin failure: rejected key (needs a new one), rate limit (back off)."""
    if isinstance(e, GarminAuthError):
        reset_client()
        conn.connected = False
        conn.backoff_until = datetime.now() + AUTH_BACKOFF  # a restart with a new key clears it
        conn.last_error = ("Garmin rejected the API key (expired or deleted). Create a new Personal API key "
                           "at connect.garmin.com/app/settings/personalApiToken and update GARMIN_API_KEY.")
    elif isinstance(e, GarminRateLimited):
        conn.backoff_until = datetime.now() + RATE_LIMIT_BACKOFF
        conn.last_error = "Garmin rate limit hit; pausing sync for 30 minutes."
    else:
        conn.backoff_until = datetime.now() + ERROR_BACKOFF
        conn.last_error = f"Sync error: {type(e).__name__}"
    logger.warning("Garmin sync failed for user %s: %s", conn.user_id, e)


def _refresh_summary(user_id: int, parsed: dict, db: Session, raw: dict) -> bool:
    activity = db.query(Activity).filter_by(user_id=user_id, source='garmin', external_id=parsed['external_id']).one()
    before = {key: getattr(activity, key) for key in parsed}
    # Provider metrics may become null after correction. Athlete overrides and notes live separately.
    for key, value in parsed.items():
        if key != 'workout_type':
            setattr(activity, key, value)
    source = source_for(activity, 'garmin', parsed['external_id'], db)
    if source.parser_version is None and activity.splits and activity.splits != '[]':
        source.enrichment_status = 'complete'  # existing normalized laps; explicit full sync refreshes FIT
    if any(before[key] is not None and getattr(activity, key) != before[key] for key in ('distance_meters', 'duration_seconds', 'elapsed_seconds', 'activity_subtype')):
        source.enrichment_status, source.next_retry_at = 'pending', None
    capture(source, 'summary', db, payload=raw)
    changed = any(getattr(activity, key) != value for key, value in before.items())
    if changed:
        from app.services.coaching_jobs import enqueue_synced_run
        enqueue_synced_run(activity, db)
    return changed


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
        Activity.user_id == user_id, Activity.source == "garmin", Activity.splits.isnot(None), runs_only()
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
        new_desc = build_description(_strip_lap_summary(a.description), laps, easy_paces.at(a.date), a.feel_notes)
        if new_desc != a.description:
            a.description = new_desc
            a.has_workout_description = is_workout_description(new_desc)
            changed += 1
    db.commit()
    counts = classify_activities(user_id, db)
    detect_prs(user_id, db)
    return {"reanalyzed": len(acts), "changed": changed, "classification": counts}
