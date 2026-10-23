"""Observed training history, with current state separated from historical capacity."""
import json
from datetime import date, datetime, timedelta
from collections import defaultdict

from app.models.activity import Activity, is_walk
from app.models.history import DailyFact, DirtyDay, ActivitySource, HistoryCoverage
from app.services.history_cache import cached

VERSION = 'history-facts-v1'
MI = 1609.34


def _day_payload(rows):
    runs = [a for a in rows if not is_walk(a)]
    return {'activity_ids': [a.id for a in runs], 'miles': round(sum(a.distance_meters or 0 for a in runs) / MI, 4),
            'seconds': sum(a.duration_seconds or 0 for a in runs), 'runs': len(runs),
            'longest_miles': round(max([0] + [(a.distance_meters or 0) / MI for a in runs]), 2),
            'quality_ids': [a.id for a in runs if a.workout_type == 'workout'],
            'race_ids': [a.id for a in runs if a.event_type == 'race' or a.workout_type == 'race'],
            'feel': [a.feel_rating for a in runs if a.feel_rating is not None]}


def daily_facts(user_id, db, *, persist=True):
    if persist:
        db.flush()
    existing = db.query(DailyFact).filter_by(user_id=user_id).all()
    dirty = db.query(DirtyDay).filter_by(user_id=user_id).all()
    rebuild = not existing or any(row.version != VERSION for row in existing)
    dates = {row.date for row in dirty}
    if rebuild:
        acts = db.query(Activity).filter_by(user_id=user_id).all()
        dates.update(a.date.date().isoformat() for a in acts)
        dates.update(row.date for row in existing)  # remove obsolete days too
    elif dates:
        acts = db.query(Activity).filter(Activity.user_id == user_id,
            Activity.date >= datetime.fromisoformat(min(dates)),
            Activity.date < datetime.fromisoformat(max(dates)) + timedelta(days=1)).all()
    else:
        acts = []
    groups = defaultdict(list)
    for a in acts:
        if a.date.date().isoformat() in dates:
            groups[a.date.date().isoformat()].append(a)
    if not persist:
        payloads = {row.date: json.loads(row.payload) for row in existing}
        for day in dates:
            payloads[day] = _day_payload(groups[day])
        return [{'date': day, **payload} for day, payload in sorted(payloads.items())]
    by_day = {row.date: row for row in existing}
    for day in dates:
        row = by_day.get(day)
        if row is None:
            row = DailyFact(user_id=user_id, date=day)
            db.add(row); by_day[day] = row
        row.version, row.payload = VERSION, json.dumps(_day_payload(groups[day]))
    for row in dirty:
        db.delete(row)
    db.flush()
    return [{'date': day, **json.loads(row.payload)} for day, row in sorted(by_day.items())]


def _profile(user_id, db, today, persist=True):
    days = [d for d in daily_facts(user_id, db, persist=persist) if d['date'] <= today.isoformat() and d['runs']]
    weeks = defaultdict(lambda: {'miles': 0, 'runs': 0, 'run_days': 0, 'activity_ids': [], 'quality_ids': [], 'race_ids': [], 'longest_miles': 0})
    for day in days:
        d = date.fromisoformat(day['date']); monday = (d - timedelta(days=d.weekday())).isoformat()
        w = weeks[monday]
        for key in ('miles', 'runs'):
            w[key] += day[key]
        w['run_days'] += 1
        for key in ('activity_ids', 'quality_ids', 'race_ids'):
            w[key].extend(day[key])
        w['longest_miles'] = max(w['longest_miles'], day['longest_miles'])
    weekly = [{'week_start': w, **v, 'miles': round(v['miles'], 1)} for w, v in sorted(weeks.items())]
    monday = today - timedelta(days=today.weekday())
    recent = []
    for back in range(12, 0, -1):
        key = (monday - timedelta(weeks=back)).isoformat()
        recent.append({'week_start': key, **weeks[key], 'miles': round(weeks[key]['miles'], 1),
                       'recording_status': 'observed' if weeks[key]['runs'] else 'unknown'})
    # Rank sustained 4-week blocks, never one isolated high week. Missing weeks
    # contribute zero *recorded* mileage; absence is explicitly not proven rest.
    blocks = []
    for w in weekly:
        end = date.fromisoformat(w['week_start'])
        if end >= monday:
            continue
        keys = [(end - timedelta(weeks=i)).isoformat() for i in range(3, -1, -1)]
        span = [weeks[k] for k in keys]
        if all(s['runs'] for s in span):
            blocks.append({'start': keys[0], 'end': (end+timedelta(days=6)).isoformat(),
                'average_mpw': round(sum(s['miles'] for s in span)/4, 1),
                'run_days_per_week': round(sum(s['run_days'] for s in span)/4, 1),
                'activity_ids': [a for s in span for a in s['activity_ids']]})
    ranked = []
    for block in sorted(blocks, key=lambda b: b['average_mpw'], reverse=True):
        if all(block['end'] < other['start'] or block['start'] > other['end'] for other in ranked):
            ranked.append(block)
        if len(ranked) == 3:
            break
    sources = db.query(ActivitySource).filter_by(user_id=user_id, provider='garmin').all()
    statuses = defaultdict(int)
    for source in sources:
        statuses[source.enrichment_status] += 1
    intervals = db.query(HistoryCoverage).filter_by(user_id=user_id).order_by(HistoryCoverage.checked_at.desc()).limit(20).all()
    gaps = []
    for first, second in zip(days, days[1:]):
        gap = (date.fromisoformat(second['date']) - date.fromisoformat(first['date'])).days - 1
        if gap >= 7:
            gaps.append({'after': first['date'], 'before': second['date'], 'unrecorded_days': gap,
                         'interpretation': 'No recorded runs; rest, missing uploads and watchless training cannot be distinguished.'})
    return {'version': VERSION, 'as_of': today.isoformat(),
        'coverage': {'first_recorded_run': days[0]['date'] if days else None,
            'last_recorded_run': days[-1]['date'] if days else None,
            'recorded_runs': sum(d['runs'] for d in days), 'fit_status': dict(statuses),
            'checked_intervals': [{'stream': r.stream, 'start': r.start_date, 'end': r.end_date, 'status': r.status} for r in intervals],
            'limitation': 'Checked dates establish API access, not continuous device wear or complete training.'},
        'current': {'last_12_completed_weeks': recent,
                    'recorded_mpw_last_4_weeks': round(sum(w['miles'] for w in recent[-4:])/4, 1)},
        'historical_capacity': {'sustained_blocks': ranked, 'longest_runs': sorted(
            [{'date': d['date'], 'miles': d['longest_miles'], 'activity_ids': d['activity_ids']} for d in days],
            key=lambda r: r['miles'], reverse=True)[:5], 'meaning': 'Previously observed capacity, not a current fitness prescription.'},
        'recording_gaps': gaps[-10:], 'weekly_history': weekly}


def historical_profile(user_id, db, today=None, *, persist=True):
    today = today or date.today()
    return cached(user_id, 'history-profile', f'{VERSION}:{today}', db, lambda: _profile(user_id, db, today, persist=persist), persist=persist)
