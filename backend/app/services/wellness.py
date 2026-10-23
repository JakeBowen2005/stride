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
from app.services.garmin import garmin_io_lock
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
        logger.debug("Garmin wellness call %s failed: %s", getattr(fn, "__name__", fn), e)
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


def fetch_range(client, start: date, end: date) -> dict[str, dict]:
    """Three range requests → parsed fields per ISO date."""
    by_day: dict[str, dict] = {}
    for row in _safe(client.daily_summaries, start, end) or []:
        by_day.setdefault(row.get("calendarDate"), {})["summary"] = flatten_summary(row)
    for row in _safe(client.sleep_range, start, end) or []:
        by_day.setdefault(row.get("calendarDate"), {})["sleep"] = row
    for row in _safe(client.hrv_range, start, end) or []:
        by_day.setdefault(row.get("calendarDate"), {})["hrv"] = row
    return {
        day: parse_day(parts.get("summary"), parts.get("sleep"), parts.get("hrv"), None, None, None)
        for day, parts in by_day.items() if day
    }


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
    if not garmin_io_lock.acquire(blocking=False):
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
        garmin_io_lock.release()
        _lock.release()


def _sync_wellness(user_id: int, db: Session, force: bool) -> dict:
    now = time.monotonic()
    if not force and now - _last_today_refresh.get(user_id, -1e9) < WELLNESS_REFRESH_MINUTES * 60:
        return {"status": "fresh"}
    client = get_client()
    today = date.today()
    have = db.query(DailyWellness).filter(DailyWellness.user_id == user_id).count()
    # Yesterday is finalized overnight, so the routine refresh covers it too
    start = today - timedelta(days=(BACKFILL_DAYS if have < 7 else 2) - 1)
    days = fetch_range(client, start, today)
    written = 0
    for iso, fields in days.items():
        if fields:
            _upsert(user_id, date.fromisoformat(iso), fields, db)
            written += 1
    db.flush()
    _fill_resting_hr_average(user_id, sorted(days), db)
    db.commit()
    _last_today_refresh[user_id] = now
    return {"status": "ok", "days_written": written}


def _fill_resting_hr_average(user_id: int, isos: list[str], db: Session):
    """The Personal API has no 7-day resting HR average; derive it from stored days."""
    for iso in isos:
        day = date.fromisoformat(iso)
        rows = db.query(DailyWellness.resting_hr).filter(
            DailyWellness.user_id == user_id,
            DailyWellness.date >= (day - timedelta(days=7)).isoformat(),
            DailyWellness.date < iso,
            DailyWellness.resting_hr.isnot(None),
        ).all()
        row = db.query(DailyWellness).filter(DailyWellness.user_id == user_id, DailyWellness.date == iso).first()
        if row and len(rows) >= 4:
            row.resting_hr_7d_avg = round(sum(r[0] for r in rows) / len(rows), 1)


def wellness_to_dict(row: DailyWellness | None) -> dict | None:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in ("id", "user_id", "updated_at")} | {
        "updated_at": row.updated_at.isoformat() if row.updated_at else None
    }
