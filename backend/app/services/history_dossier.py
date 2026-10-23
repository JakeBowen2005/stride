"""Small, evidence-linked facts for the model. No causal/physiological guesses."""
from datetime import date, datetime, timedelta
from sqlalchemy import or_

from app.models.activity import Activity, runs_only
from app.models.history import ActivitySource, HistoryCoverage
from app.models.wellness import DailyWellness
from app.services.history_facts import historical_profile, VERSION
from app.services.history_cache import revision


def dossier(user_id, db, today=None, *, persist=False):
    today = today or date.today()
    profile = historical_profile(user_id, db, today, persist=persist)
    insights = []
    blocks = profile['historical_capacity']['sustained_blocks']
    if blocks:
        block = blocks[0]
        insights.append({'id': 'sustained-volume', 'kind': 'observed',
            'text': f"Recorded {block['average_mpw']:g} mi/week over {block['start']} through {block['end']}. This describes past capacity, not current fitness.",
            'activity_ids': block['activity_ids'], 'dates': [block['start'], block['end']]})
    longest = profile['historical_capacity']['longest_runs']
    if longest:
        run = longest[0]
        insights.append({'id': 'historical-long-run', 'kind': 'observed',
            'text': f"Longest recorded run is a {run['miles']:g}-mile run on {run['date']}; it does not establish current long-run tolerance.",
            'activity_ids': run['activity_ids'], 'dates': [run['date']]})
    if profile['recording_gaps']:
        gap = profile['recording_gaps'][-1]
        insights.append({'id': 'recording-gap', 'kind': 'coverage',
            'text': f"No runs recorded between {gap['after']} and {gap['before']} ({gap['unrecorded_days']} unrecorded days). The reason is unknown.",
            'activity_ids': [], 'dates': [gap['after'], gap['before']]})
    races = db.query(Activity).filter(Activity.user_id == user_id, runs_only(), Activity.date < datetime.combine(today + timedelta(days=1), datetime.min.time()),
        or_(Activity.event_type == 'race', Activity.workout_type == 'race')).order_by(Activity.date.desc()).limit(5).all()
    weekly = profile['weekly_history']
    race_blocks = []
    for race in races:
        race_day = race.date.date()
        end = race_day - timedelta(days=race_day.weekday())
        start = end - timedelta(weeks=6)
        preceding = [w for w in weekly if start.isoformat() <= w['week_start'] < end.isoformat()]
        race_blocks.append({'race_activity_id': race.id, 'date': race_day.isoformat(),
            'race_miles': round(race.distance_meters/1609.34, 2), 'duration_seconds': race.duration_seconds,
            'preceding_6_week_recorded_mpw': round(sum(w['miles'] for w in preceding)/6, 1),
            'observed_weeks': len(preceding),
            'activity_ids': [race.id] + [a for w in preceding for a in w['activity_ids']],
            'interpretation': 'Observed buildup and result; missing weeks may be missing data, and association does not establish causation.'})
    recent_wellness = db.query(DailyWellness).filter(DailyWellness.user_id == user_id,
        DailyWellness.date >= (today-timedelta(days=34)).isoformat(), DailyWellness.date <= today.isoformat()).order_by(DailyWellness.date).all()
    recovery = {}
    for metric in ('resting_hr', 'hrv_last_night', 'sleep_seconds'):
        recent = [r for r in recent_wellness if r.date >= (today-timedelta(days=6)).isoformat() and getattr(r, metric) is not None]
        earlier = [r for r in recent_wellness if r.date < (today-timedelta(days=6)).isoformat() and getattr(r, metric) is not None]
        if len(recent) >= 4 and len(earlier) >= 14:
            recovery[metric] = {'recent_mean': round(sum(getattr(r, metric) for r in recent)/len(recent), 1),
                'prior_mean': round(sum(getattr(r, metric) for r in earlier)/len(earlier), 1),
                'recent_days': len(recent), 'prior_days': len(earlier), 'dates': [r.date for r in recent],
                'interpretation': 'Descriptive comparison only; not a readiness diagnosis or proof of workout response.'}
    coverage = db.query(HistoryCoverage).filter_by(user_id=user_id).order_by(HistoryCoverage.checked_at.desc()).limit(20).all()
    return {'version': VERSION, 'as_of': today.isoformat(), 'input_revision': revision(user_id, db, flush=persist),
        'coverage': profile['coverage'], 'current': profile['current'],
        'historical_capacity': profile['historical_capacity'], 'race_buildups': race_blocks,
        'recovery_comparisons': recovery, 'insights': insights,
        'stream_freshness': [{'stream': r.stream, 'start': r.start_date, 'end': r.end_date,
                              'status': r.status, 'checked_at': r.checked_at.isoformat()} for r in coverage]}


def evidence_manifest(user_id, db, activity_ids):
    rows = db.query(ActivitySource).filter(ActivitySource.user_id == user_id, ActivitySource.activity_id.in_(activity_ids)).order_by(ActivitySource.id.desc()).limit(120).all() if activity_ids else []
    return [{'activity_id': r.activity_id, 'provider': r.provider, 'summary_hash': r.summary_hash,
             'fit_status': r.enrichment_status, 'parser_version': r.parser_version} for r in rows]
