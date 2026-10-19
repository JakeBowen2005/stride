from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.wellness import DailyWellness
from app.services.wellness import wellness_to_dict

router = APIRouter(prefix="/api/wellness", tags=["wellness"])

TRAINING_STATUS_LABELS = {
    "PRODUCTIVE": "Productive", "MAINTAINING": "Maintaining", "RECOVERY": "Recovery",
    "UNPRODUCTIVE": "Unproductive", "DETRAINING": "Detraining", "OVERREACHING": "Overreaching",
    "PEAKING": "Peaking", "STRAINED": "Strained", "NO_STATUS": "No status",
}


def training_status_label(phrase: str | None) -> str | None:
    if not phrase:
        return None
    for key, label in TRAINING_STATUS_LABELS.items():
        if phrase.upper().startswith(key):
            return label
    return phrase.replace("_", " ").title()


def recovery_signals(today: dict | None) -> list[dict]:
    """Plain-language flags from overnight data. Conservative thresholds (fail safe):
    a flag suggests easing off; it never pushes harder."""
    if not today:
        return []
    signals = []
    hrv, low = today.get("hrv_last_night"), today.get("hrv_baseline_low")
    if hrv and low and hrv < low:
        signals.append({"level": "caution", "metric": "hrv",
                        "message": f"HRV {hrv:.0f}ms is below your normal range (≥{low:.0f}). Body is under strain — keep today easy."})
    rhr, rhr7 = today.get("resting_hr"), today.get("resting_hr_7d_avg")
    if rhr and rhr7 and rhr >= rhr7 + 5:
        signals.append({"level": "caution", "metric": "resting_hr",
                        "message": f"Resting HR {rhr:.0f} is {rhr - rhr7:.0f} bpm above your 7-day average — a classic fatigue/illness sign."})
    sleep = today.get("sleep_seconds")
    if sleep and sleep < 6 * 3600:
        signals.append({"level": "caution", "metric": "sleep",
                        "message": f"Only {sleep / 3600:.1f}h of sleep. Hard sessions on short sleep cost more and give less."})
    if today.get("acwr") and today["acwr"] > 1.5:
        signals.append({"level": "warning", "metric": "acwr",
                        "message": f"Acute:chronic load ratio is {today['acwr']:.2f} — above 1.5 is the injury danger zone."})
    if not signals and today.get("readiness_score") and today["readiness_score"] >= 75:
        signals.append({"level": "good", "metric": "readiness",
                        "message": "Recovered and ready — a good day to hit a quality session."})
    return signals


@router.get("/{user_id}")
def get_wellness(user_id: int, days: int = Query(default=28, le=120), db: Session = Depends(get_db)):
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = (
        db.query(DailyWellness)
        .filter(DailyWellness.user_id == user_id, DailyWellness.date >= since)
        .order_by(DailyWellness.date.asc())
        .all()
    )
    history = [wellness_to_dict(r) for r in rows]
    today_row = next((h for h in reversed(history) if h["date"] == date.today().isoformat()), None)
    latest = history[-1] if history else None
    # Fresh = today's Garmin data. An older row is shown as "as of <date>" but never
    # drives readiness or recovery signals (stale data mustn't imply readiness).
    freshness = "fresh" if today_row else ("stale" if latest else "absent")
    current = today_row or latest
    return {
        "today": today_row,
        "latest": current,
        "freshness": freshness,
        "as_of": current["date"] if current else None,
        "training_status_label": training_status_label((current or {}).get("training_status")),
        "signals": recovery_signals(today_row),
        "history": history,
    }
