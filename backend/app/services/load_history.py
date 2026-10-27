from app.athlete_clock import today as athlete_today
"""One calendar-week mileage definition for planning, dashboard and explanations.

Policy ratio, not an injury predictor: last completed Monday–Sunday divided by
four completed weeks (including that week). Empty weeks count as zero. Never
compare an incomplete current week to completed weeks.
"""
from datetime import date, datetime, timedelta
from app.models.activity import Activity, runs_only

MI = 1609.34


def completed_week_load(user_id, db, today=None):
    today = today or athlete_today()
    monday = today - timedelta(days=today.weekday())
    starts = [monday - timedelta(weeks=i) for i in range(12, 0, -1)]
    totals = dict.fromkeys(starts, 0.0)
    acts = db.query(Activity).filter(Activity.user_id == user_id, runs_only(),
        Activity.date >= datetime.combine(starts[0], datetime.min.time()),
        Activity.date < datetime.combine(monday, datetime.min.time())).all()
    for a in acts:
        day = a.date.date()
        week = day - timedelta(days=day.weekday())
        totals[week] += (a.distance_meters or 0) / MI
    weeks = [totals[s] for s in starts]
    baseline = sum(weeks[-4:]) / 4
    acute = weeks[-1]
    ratio = round(acute / baseline, 2) if baseline > 0 else None
    label = ('UNKNOWN — no completed-week baseline' if ratio is None else
             'HIGH — last completed week is elevated relative to the four-week baseline; review recovery' if ratio > 1.5 else
             'MODERATE — recent mileage increased; review recovery and consistency' if ratio > 1.3 else
             'LOW — recent mileage is below the four-week baseline; this does not establish readiness to increase' if ratio < .8 else
             'BALANCED — recent mileage is close to the four-week baseline')
    return {'as_of': today.isoformat(), 'definition': 'last completed week / four completed weeks (including that week)',
        'acute_week_start': starts[-1].isoformat(), 'acute_week_end': (monday-timedelta(days=1)).isoformat(),
        'acute_miles': round(acute, 1), 'baseline_start': starts[-4].isoformat(),
        'baseline_end': (monday-timedelta(days=1)).isoformat(), 'baseline_miles': round(baseline, 1),
        'eight_week_average': round(sum(weeks[-8:])/8, 1), 'twelve_week_average': round(sum(weeks)/12, 1),
        'weeks': [{'week_start': s.isoformat(), 'miles': round(totals[s], 1)} for s in starts],
        'ratio': ratio, 'label': label, 'policy_version': 'calendar-load-v1',
        'limitation': 'Mileage-only training trend; not a diagnosis or an injury probability.'}
