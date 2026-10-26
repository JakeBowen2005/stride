from app.models.operations import ProviderCredential
from app.athlete_clock import today as athlete_today
"""Pull daily Garmin wellness data: sleep, HRV, resting HR, body battery, stress.

Uses the Personal API's range endpoints: three requests (daily summaries, sleep,
HRV) cover the whole window, so a 28-day backfill costs 3 calls instead of ~170.
Training readiness / status, VO2max and Garmin race predictions are not exposed
by the Personal API; those columns keep whatever older rows already hold and the
UI hides them when absent. Today is refreshed at most every WELLNESS_REFRESH_MINUTES.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.wellness import DailyWellness
from app.services.garmin import garmin_io_lock, io_lock_for
from app.services.garmin_api import GarminAuthError, GarminRateLimited, get_client

logger = logging.getLogger("stride.wellness")

BACKFILL_DAYS = 28
WELLNESS_REFRESH_MINUTES = 20
_lock = threading.Lock()
_last_today_refresh: dict[int, float] = {}


def _safe(fn, *args):
    """One endpoint failing shouldn't drop the rest — but a rejected key or rate
    limit must stop the whole sync."""
    try:
        return fn(*args)
    except (GarminAuthError, GarminRateLimited):
        raise
    except Exception as e:
        logger.warning("Garmin wellness call %s failed (%s)", getattr(fn, "__name__", fn), type(e).__name__)
        return None


def _first_device_value(mapping: dict | None) -> dict:
    """Garmin keys some payloads by device id — take the primary/first device."""
    if not mapping:
        return {}
    values = list(mapping.values())
    primary = [v for v in values if isinstance(v, dict) and v.get("primaryTrainingDevice")]
    return (primary or values)[0] or {}


def flatten_summary(v2: dict | None) -> dict | None:
    """Map a Personal API v2 daily summary onto the legacy flat keys parse_day reads."""
    if not v2:
        return None
    hr, stress, bb = v2.get("heartRate") or {}, v2.get("stress") or {}, v2.get("bodyBattery") or {}
    steps = ((v2.get("movement") or {}).get("steps")) or {}
    return {
        "restingHeartRate": hr.get("restingValue"),
        "bodyBatteryMostRecentValue": bb.get("latestValue"),
        "bodyBatteryHighestValue": bb.get("maxValue"),
        "bodyBatteryLowestValue": bb.get("minValue"),
        "averageStressLevel": stress.get("avgLevel"),
        "totalSteps": steps.get("value"),
        "dailyStepGoal": steps.get("goal"),
        "averageSpo2": (v2.get("pulseOx") or {}).get("avgValue"),
        "avgWakingRespirationValue": (v2.get("respiration") or {}).get("avgValue"),
    }


def parse_day(summary, sleep, hrv, readiness, status, predictions) -> dict:
    """Map raw Garmin payloads to DailyWellness fields. Pure — unit tested."""
    out: dict = {}
    if summary:
        out.update(
            resting_hr=summary.get("restingHeartRate"),
            resting_hr_7d_avg=summary.get("lastSevenDaysAvgRestingHeartRate"),
            body_battery_now=summary.get("bodyBatteryMostRecentValue"),
            body_battery_wake=summary.get("bodyBatteryAtWakeTime"),
            body_battery_high=summary.get("bodyBatteryHighestValue"),
            body_battery_low=summary.get("bodyBatteryLowestValue"),
            stress_avg=summary.get("averageStressLevel") if (summary.get("averageStressLevel") or -1) >= 0 else None,
            steps=summary.get("totalSteps"),
            step_goal=summary.get("dailyStepGoal"),
            spo2_avg=summary.get("averageSpo2"),
            respiration_avg=summary.get("avgWakingRespirationValue"),
        )
    dto = (sleep or {}).get("dailySleepDTO") or sleep or {}  # range rows are the DTO itself
    if dto.get("sleepTimeSeconds"):
        overall = ((dto.get("sleepScores") or {}).get("overall")) or {}
        out.update(
            sleep_seconds=dto.get("sleepTimeSeconds"),
            sleep_score=overall.get("value"),
            sleep_quality=overall.get("qualifierKey"),
            deep_sleep_seconds=dto.get("deepSleepSeconds"),
            light_sleep_seconds=dto.get("lightSleepSeconds"),
            rem_sleep_seconds=dto.get("remSleepSeconds"),
            awake_sleep_seconds=dto.get("awakeSleepSeconds"),
        )
    hs = (hrv or {}).get("hrvSummary") or (hrv if (hrv or {}).get("calendarDate") else {})
    if hs:
        base = hs.get("baseline") or {}
        out.update(
            hrv_last_night=hs.get("lastNightAvg"),
            hrv_weekly_avg=hs.get("weeklyAvg"),
            hrv_status=hs.get("status"),
            hrv_baseline_low=base.get("balancedLow"),
            hrv_baseline_high=base.get("balancedUpper"),
        )
    if readiness:
        tr = readiness[0] if isinstance(readiness, list) else readiness
        if tr:
            out.update(
                readiness_score=tr.get("score"),
                readiness_level=tr.get("level"),
                readiness_feedback=tr.get("feedbackShort"),
                recovery_time_min=tr.get("recoveryTime"),
            )
            if not out.get("sleep_score") and tr.get("sleepScore"):
                out["sleep_score"] = tr.get("sleepScore")
    if status:
        ts = _first_device_value(((status.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")))
        acute = ts.get("acuteTrainingLoadDTO") or {}
        lb = _first_device_value(((status.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap")))
        vo2 = (((status.get("mostRecentVO2Max") or {}).get("generic")) or {})
        out.update(
            training_status=ts.get("trainingStatusFeedbackPhrase"),
            acute_load=acute.get("dailyTrainingLoadAcute"),
            chronic_load=acute.get("dailyTrainingLoadChronic"),
            acwr=acute.get("dailyAcuteChronicWorkloadRatio"),
            load_balance_feedback=lb.get("trainingBalanceFeedbackPhrase"),
            vo2max=vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue"),
        )
    if predictions:
        out.update(
            predicted_5k=predictions.get("time5K"),
            predicted_10k=predictions.get("time10K"),
            predicted_half=predictions.get("timeHalfMarathon"),
            predicted_marathon=predictions.get("timeMarathon"),
        )
    return {k: v for k, v in out.items() if v is not None}


def fetch_range(client, start: date, end: date, *, user_id=None, db=None) -> dict[str, dict]:
    """Three independently recorded streams. Failure never means a checked empty day."""
    from app.services.history_evidence import coverage, encoded
    from app.models.history import WellnessRevision
    import hashlib
    by_day, complete = {}, True
    for stream, fn, key in [('daily_summary', client.daily_summaries, 'summary'),
                             ('sleep', client.sleep_range, 'sleep'), ('hrv', client.hrv_range, 'hrv')]:
        rows = _safe(fn, start, end)
        complete = complete and rows is not None
        if db is not None:
            coverage(user_id, stream, start, end, 'checked' if rows is not None else 'failed', db)
            if rows is not None:
                payload = encoded(rows)
                digest = hashlib.sha256(payload.encode()).hexdigest()
                if not db.query(WellnessRevision.id).filter_by(user_id=user_id, stream=stream,
                        start_date=start.isoformat(), end_date=end.isoformat(), content_hash=digest).first():
                    db.add(WellnessRevision(user_id=user_id, stream=stream, start_date=start.isoformat(),
                        end_date=end.isoformat(), content_hash=digest, payload=payload))
        for row in rows or []:
            day = row.get('calendarDate')
            if day and start.isoformat() <= day <= end.isoformat():
                by_day.setdefault(day, {})[key] = flatten_summary(row) if key == 'summary' else row
    if db is not None:
        coverage(user_id, 'wellness', start, end, 'checked' if complete else 'failed', db)
        db.info['wellness_range_complete'] = complete
    return {day: parse_day(parts.get('summary'), parts.get('sleep'), parts.get('hrv'), None, None, None)
            for day, parts in by_day.items()}


def _upsert(user_id: int, day: date, fields: dict, db: Session):
    row = db.query(DailyWellness).filter(DailyWellness.user_id == user_id, DailyWellness.date == day.isoformat()).first()
    if row is None:
        row = DailyWellness(user_id=user_id, date=day.isoformat())
        db.add(row)
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)
    row.updated_at = datetime.now()


def sync_wellness(user_id: int, db: Session, force: bool = False) -> dict:
    """Refresh today (+ yesterday, which Garmin finalizes overnight); backfill on first run."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    # A full import can hold the Garmin lock for minutes; skip rather than block a request
    io_lock=io_lock_for(user_id)
    if not io_lock.acquire(blocking=False):
        _lock.release()
        return {"status": "busy"}
    try:
        return _sync_wellness(user_id, db, force)
    except GarminRateLimited as e:
        from app.services.garmin import _record_failure, get_connection
        db.rollback()
        _record_failure(get_connection(user_id, db), e)
        db.commit()
        _last_today_refresh[user_id] = time.monotonic()
        return {"status": "backoff"}
    finally:
        io_lock.release()
        _lock.release()


def _sync_wellness(user_id: int, db: Session, force: bool) -> dict:
    now = time.monotonic()
    if not force and now - _last_today_refresh.get(user_id, -1e9) < WELLNESS_REFRESH_MINUTES * 60:
        return {"status": "fresh"}
    from app.config import settings
    if settings.accounts_enabled or db.get(ProviderCredential,user_id):
        from app.services.provider_connections import client_for
        client=client_for(user_id)
    else:
        client=get_client()
    today = athlete_today()
    have = db.query(DailyWellness).filter(DailyWellness.user_id == user_id).count()
    # Repair the gap after downtime as well as yesterday's overnight corrections.
    latest = db.query(DailyWellness.date).filter_by(user_id=user_id).order_by(DailyWellness.date.desc()).first()
    gap = (today - date.fromisoformat(latest[0])).days + 1 if latest else BACKFILL_DAYS
    window = BACKFILL_DAYS if have < 7 else min(BACKFILL_DAYS, max(2, gap))
    start = today - timedelta(days=window - 1)
    days = fetch_range(client, start, today, user_id=user_id, db=db)
    recent_complete = db.info.get('wellness_range_complete', False)
    written = 0
    for iso, fields in days.items():
        if fields:
            _upsert(user_id, date.fromisoformat(iso), fields, db)
            written += 1
    db.flush()
    # One bounded historical chunk per sync. Failed chunks do not advance coverage.
    if have >= 7:
        from app.models.activity import Activity
        from app.models.history import HistoryCoverage
        from sqlalchemy import func
        oldest = db.query(func.min(Activity.date)).filter_by(user_id=user_id).scalar()
        checked = db.query(func.min(HistoryCoverage.start_date)).filter_by(user_id=user_id, stream='wellness', status='checked').scalar()
        end = date.fromisoformat(checked) - timedelta(days=1) if checked else today
        if oldest and end >= oldest.date():
            history_start = max(oldest.date(), end - timedelta(days=BACKFILL_DAYS-1))
            db.commit()  # recent metrics are durable; no SQLite writer held across historical I/O
            older = fetch_range(client, history_start, end, user_id=user_id, db=db)
            for iso, fields in older.items():
                if fields:
                    _upsert(user_id, date.fromisoformat(iso), fields, db)
                    written += 1
            days.update(older)
    db.flush()
    _fill_resting_hr_average(user_id, sorted(days), db)
    db.commit()
    if recent_complete:
        _last_today_refresh[user_id] = now
    return {"status": "ok" if recent_complete else "partial", "days_written": written}


def _fill_resting_hr_average(user_id: int, isos: list[str], db: Session):
    """A corrected day also invalidates the next seven days' resting-HR baseline."""
    if not isos:
        return
    first, last = date.fromisoformat(min(isos)), date.fromisoformat(max(isos))
    rows = db.query(DailyWellness).filter(DailyWellness.user_id == user_id,
        DailyWellness.date >= (first-timedelta(days=7)).isoformat(),
        DailyWellness.date <= (last+timedelta(days=7)).isoformat()).all()
    by_day = {date.fromisoformat(r.date): r for r in rows}
    for day, row in by_day.items():
        if first <= day <= last+timedelta(days=7):
            values = [by_day[d].resting_hr for i in range(1, 8)
                      if (d := day-timedelta(days=i)) in by_day and by_day[d].resting_hr is not None]
            row.resting_hr_7d_avg = round(sum(values)/len(values), 1) if len(values) >= 4 else None


def wellness_to_dict(row: DailyWellness | None) -> dict | None:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in ("id", "user_id", "updated_at")} | {
        "updated_at": row.updated_at.isoformat() if row.updated_at else None
    }
