"""Pull daily Garmin wellness data: sleep, HRV, resting HR, body battery, stress,
training readiness / status, VO2max and race predictions.

Each Garmin endpoint is fetched independently — if one fails (or the watch
doesn't support it) the rest still land. Today is refreshed at most every
WELLNESS_REFRESH_MINUTES; the first sync backfills BACKFILL_DAYS for trends.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.wellness import DailyWellness
from app.services.garmin import garmin_io_lock, get_client

logger = logging.getLogger("stride.wellness")

BACKFILL_DAYS = 28
WELLNESS_REFRESH_MINUTES = 20
_lock = threading.Lock()
_last_today_refresh: dict[int, float] = {}


def _safe(fn, *args):
    """One endpoint failing (or unsupported on this watch) shouldn't drop the rest —
    but an expired session or rate limit must stop the whole sync."""
    from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

    try:
        return fn(*args)
    except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError):
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
    dto = (sleep or {}).get("dailySleepDTO") or {}
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
    hs = (hrv or {}).get("hrvSummary") or {}
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


def _fetch_day(client, day: date, include_predictions: bool) -> dict:
    d = day.isoformat()
    return parse_day(
        _safe(client.get_user_summary, d),
        _safe(client.get_sleep_data, d),
        _safe(client.get_hrv_data, d),
        _safe(client.get_training_readiness, d),
        _safe(client.get_training_status, d),
        _safe(client.get_race_predictions) if include_predictions else None,
    )


def _upsert(user_id: int, day: date, fields: dict, db: Session):
    row = db.query(DailyWellness).filter(DailyWellness.user_id == user_id, DailyWellness.date == day.isoformat()).first()
    if row is None:
        row = DailyWellness(user_id=user_id, date=day.isoformat())
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_at = datetime.now()


def sync_wellness(user_id: int, db: Session, force: bool = False) -> dict:
    """Refresh today (+ yesterday, which Garmin finalizes overnight); backfill on first run."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    try:
        with garmin_io_lock:
            return _sync_wellness(user_id, db, force)
    finally:
        _lock.release()


def _sync_wellness(user_id: int, db: Session, force: bool) -> dict:
    now = time.monotonic()
    if not force and now - _last_today_refresh.get(user_id, -1e9) < WELLNESS_REFRESH_MINUTES * 60:
        return {"status": "fresh"}
    client = get_client()
    today = date.today()
    have = db.query(DailyWellness).filter(DailyWellness.user_id == user_id).count()
    days = [today - timedelta(days=i) for i in range(BACKFILL_DAYS if have < 7 else 2)]
    written = 0
    for i, day in enumerate(days):
        fields = _fetch_day(client, day, include_predictions=(i == 0))
        if fields:
            _upsert(user_id, day, fields, db)
            written += 1
        if len(days) > 2:
            time.sleep(0.3)  # gentle on Garmin during backfill
    db.commit()
    _last_today_refresh[user_id] = now
    return {"status": "ok", "days_written": written}


def wellness_to_dict(row: DailyWellness | None) -> dict | None:
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in ("id", "user_id", "updated_at")} | {
        "updated_at": row.updated_at.isoformat() if row.updated_at else None
    }
