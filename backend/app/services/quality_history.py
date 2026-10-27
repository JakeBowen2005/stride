from app.athlete_clock import today as athlete_today
"""Completed quality/recovery evidence for staging. Preview count never earns promotion."""
import json

from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.core.session_match import executed_session, off_plan
from app.core.workout_data import execution_from_activities, loads
from app.models.activity import Activity, runs_only
from app.models.plan import Plan, PlannedWorkout


def quality_history(user_id, db, today=None):
    today = today or athlete_today()
    cutoff = today - timedelta(days=56)
    calendar_monday = today - timedelta(days=today.weekday())
    acts = db.query(Activity).filter(Activity.user_id == user_id, runs_only(),
        Activity.date >= datetime.combine(calendar_monday-timedelta(weeks=8), datetime.min.time()),
        Activity.date < datetime.combine(today+timedelta(days=1), datetime.min.time())).all()
    by_date = {}
    for act in acts:
        by_date.setdefault(act.date.date().isoformat(), []).append(act)
    rows = db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == user_id,
        Plan.preview_state.is_(None), PlannedWorkout.date >= cutoff.isoformat(),
        PlannedWorkout.date <= today.isoformat(),
        PlannedWorkout.date >= func.coalesce(Plan.prescribed_from, Plan.start_date)
    ).order_by(PlannedWorkout.id.desc()).all()
    cache = {}

    def easy_reference():
        if 'easy' not in cache:
            from app.services.garmin import recent_easy_pace
            cache['easy'] = recent_easy_pace(user_id, db)
        return cache['easy']
    latest = {}
    for row in rows:
        latest.setdefault(row.date, row)
    successful = {'primary': set(), 'support': set(), 'long_run': set()}
    hard_by_week = {}
    failures = set()
    latest_long = None
    development_dates = set()
    for day, row in latest.items():
        activities = by_date.get(day, [])
        if not activities or row.swapped or row.session_status == 'skipped' or row.moved_to is not None:
            continue
        feels = [a.effective_feel for a in activities if a.effective_feel is not None]
        if row.feel_rating is not None:
            feels.append(row.feel_rating)
        feel = min(feels) if feels else None
        spec = loads(row.prescription)
        evaluation = json.loads(row.evaluation) if row.evaluation else {}
        if spec and off_plan(spec, executed_session(activities, spec.get('easy_pace_sec_per_mile') or easy_reference())):
            # A different, coherent quality session is neither a failed nor a successful step of
            # this ladder. A poor feel rating is still a recovery signal.
            if feel is not None and feel <= 4:
                failures.add(day)
            continue
        execution = execution_from_activities(activities, spec) if spec else None
        category = (spec or {}).get('category')
        if category == 'development':
            development_dates.add(day)
            from app.core.workout_evaluator import evaluate_workout
            checked = evaluate_workout(None, None, None, 'workout', None, row.title, feel, spec, execution)
            if checked.decision == 'regress' or (feel is not None and feel <= 4):
                failures.add(day)
        if category in {'threshold','intervals'} and execution:
            from app.core.workout_evaluator import evaluate_workout
            checked = evaluate_workout(None,None,None,'workout',None,row.title,feel,spec,execution)
            # Re-evaluate deterministic work evidence, including fade and target pace.
            evaluation = checked.to_dict()
            targets = execution.get('target_paces_sec_per_mile',[])
            controlled = (bool(targets) and all(t is not None for t in targets)
                          and checked.pace_diff_sec<=5 and checked.fade_sec<10)
        else:
            controlled = False
        if category in {'threshold', 'intervals', 'speed_support', 'hills'}:
            completion = (execution or {}).get('completion')
            complete = (execution or {}).get('confidence') in {'high', 'medium'} and completion is not None and completion >= 1
            if (feel is not None and feel <= 4) or evaluation.get('decision') == 'regress' or (completion is not None and completion < .8):
                failures.add(day)
            # A feel rating or matching mileage cannot prove the work reps were completed.
            if complete and feel is not None and feel >= 6 and (category in {'speed_support','hills'} or (controlled and evaluation.get('decision')!='regress')):
                key = 'support' if category == 'speed_support' else 'primary'
                successful[key].add(day)
                if key == 'primary':
                    d = date.fromisoformat(day)
                    monday = (d - timedelta(days=d.weekday())).isoformat()
                    hard_by_week.setdefault(monday, set()).add(day)
        if row.type == 'long_run' and (latest_long is None or day>latest_long[0]):
            latest_long=(day,feel)
        if row.type == 'long_run' and day >= (today-timedelta(days=28)).isoformat() and feel is not None and feel >= 6:
            miles = sum(a.distance_meters for a in activities) / 1609.34
            if miles >= row.distance_miles * .9:
                successful['long_run'].add(day)
    ratings = [(day, a.effective_feel) for day, items in by_date.items() for a in items if a.effective_feel is not None]
    # Planned-day feedback also counts as recovery evidence, once per date.
    ratings += [(day, row.feel_rating) for day, row in latest.items() if day in by_date and row.feel_rating is not None]
    rated_days = {}
    for day, feel in ratings:
        rated_days[day] = min(feel, rated_days.get(day, feel))
    recent = {d:f for d,f in rated_days.items() if d >= (today-timedelta(days=14)).isoformat()}
    monday = today - timedelta(days=today.weekday())
    full_week_run_days = [len({a.date.date() for a in acts if monday-timedelta(weeks=i) <= a.date.date() < monday-timedelta(weeks=i-1)}) for i in range(8,0,-1)]
    return {'primary_successes': len(successful['primary']), 'support_successes': len(successful['support']),
            'recent_primary_successes':sum(d>=(today-timedelta(days=21)).isoformat() for d in successful['primary']),
            'recent_support_successes':sum(d>=(today-timedelta(days=21)).isoformat() for d in successful['support']),
            'long_run_successes': len(successful['long_run']),
            'latest_long_run_feel':latest_long[1] if latest_long else None,
            'dual_weeks': sum(len(days)>=2 for week,days in hard_by_week.items()
                              if (monday-timedelta(weeks=4)).isoformat() <= week < monday.isoformat()),
            'recovery_days': len(recent), 'recovery_average': sum(recent.values())/len(recent) if recent else None,
            'recent_failure': any(d >= (today-timedelta(days=14)).isoformat() for d in failures),
            'recent_low_feel': any(f<=4 for f in recent.values()),
            'weekly_run_days': full_week_run_days,
            'evidence_window_days': 56,
            'development_dates': sorted(development_dates),
            'matched_quality_dates': sorted(successful['primary'] | successful['support'])}
