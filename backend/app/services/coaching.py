"""Grounded advice with durable deduplication, bounded spend and explicit acceptance."""
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func

from app.config import settings
from app.core.workout_data import execution_from_activities, loads
from app.models.activity import Activity, runs_only
from app.models.coaching import CoachingReview
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.models.wellness import DailyWellness
from app.services.coaching_options import build_options, snapshot
from app.services.openai_coach import INSTRUCTIONS, request_advice
from app.services.quality_history import quality_history

logger = logging.getLogger('stride.coaching')
DOCS = Path(__file__).resolve().parents[3] / 'docs'
VERSION = 'openai-coach-v3'


def research_context(goal):
    from app.services.coach import SCIENCE_DOCS
    paths = [
        ('quality-policy', 'research/quality-stage-progression.md', 8500),
        ('personal-dossier', 'research/the-long-game-coaching-dossier.md', 5000),
        ('personal-decisions', 'research/the-long-game-decision-engine.md', 6000),
        ('training-principles', 'training-principles.md', 6000),
        ('support-variety', 'research/secondary-session-variety.md', 4000),
    ]
    if goal and goal.race_distance in SCIENCE_DOCS:
        paths.append(('goal-science', SCIENCE_DOCS[goal.race_distance], 5000))
    result = []
    for source_id, relative, limit in paths:
        path = DOCS / relative
        if path.exists():
            text = path.read_text()
            # Include later recovery/adjustment material in long retrospectives too.
            excerpt = text if len(text) <= limit else text[:limit//2] + '\n[excerpt gap]\n' + text[-limit//2:]
            result.append({'id': source_id, 'path': relative, 'excerpt': excerpt})
    return result


def _pace(seconds_per_mile):
    if not seconds_per_mile:
        return None
    seconds = round(seconds_per_mile)
    return f"{seconds // 60}:{seconds % 60:02d}/mi"


def _brief_run(a, executed=None):
    """One line of history: enough for trends without spending tokens on every lap."""
    miles = a.distance_meters / 1609.34
    return {'date': a.date.date().isoformat(), 'miles': round(miles, 1),
            'pace': _pace(a.duration_seconds / miles) if miles and a.duration_seconds else None,
            'avg_hr': round(a.average_heartrate) if a.average_heartrate else None,
            'session': executed['label'] + f" {executed['category']}" if executed else None,
            'feel': a.feel_rating}


def _run(a, executed=None, planned=None):
    """Everything Garmin and the athlete told us about the run under review."""
    raw_laps = loads_json(a.splits) or []
    laps = []
    for lap in raw_laps[:60] if isinstance(raw_laps, list) else []:
        if not isinstance(lap, dict) or not lap.get('distance_m') or not lap.get('duration_s'):
            continue
        hr = lap.get('average_hr', lap.get('heart_rate'))
        laps.append({'miles': round(lap['distance_m'] / 1609.34, 2), 'time_s': round(lap['duration_s']),
                     'pace': _pace(lap['duration_s'] / (lap['distance_m'] / 1609.34)),
                     'hr': round(hr) if isinstance(hr, (int, float)) else None,
                     'intensity': lap.get('intensity'), 'elev_ft': lap.get('elevation_diff_ft')})
    miles = a.distance_meters / 1609.34
    run = {'id': a.id, 'date': a.date.date().isoformat(), 'miles': round(miles, 2),
           'duration': f"{int(a.duration_seconds // 60)}:{int(a.duration_seconds % 60):02d}" if a.duration_seconds else None,
           'avg_pace': _pace(a.duration_seconds / miles) if miles and a.duration_seconds else None,
           'average_hr': a.average_heartrate, 'max_hr': a.max_heartrate,
           'elevation_gain_ft': round(a.elevation_gain * 3.281) if a.elevation_gain else None,
           'aerobic_training_effect': a.aerobic_training_effect,
           'anaerobic_training_effect': a.anaerobic_training_effect,
           'laps': laps,
           'detected_session': None,
           'athlete_feedback': {'feel_1_to_10': planned.feel_rating if planned and planned.feel_rating is not None else a.feel_rating,
                                'notes': ((planned.feel_notes if planned else None) or a.feel_notes or '')[:700] or None,
                                'pace_vs_target': planned.pace_assessment if planned else None,
                                'said_swapped': bool(planned.swapped) if planned else False}}
    if executed:
        run['detected_session'] = {'title': executed.get('title'), 'category': executed['category'],
            'reps': [{'miles': round(r['distance_m'] / 1609.34, 2), 'time_s': round(r['duration_s']),
                      'pace': _pace(r['pace_sec_per_mile']), 'avg_hr': r['average_hr']} for r in executed['reps']],
            'recovery_s': executed['recovery_seconds'], 'work_miles': executed['work_miles']}
    return run


def _training_summary(user_id, runs, executed_by_id, today, plan_rows, goal):
    """Deterministic athlete snapshot the coach reads first on every call."""
    monday = today - timedelta(days=today.weekday())
    weeks = []
    for i in range(6, 0, -1):
        start, end = monday - timedelta(weeks=i), monday - timedelta(weeks=i - 1)
        week_runs = [r for r in runs if start <= r.date.date() < end]
        weeks.append({'week_of': start.isoformat(), 'miles': round(sum(r.distance_meters for r in week_runs) / 1609.34, 1),
                      'runs': len(week_runs), 'longest': round(max((r.distance_meters for r in week_runs), default=0) / 1609.34, 1)})
    this_week = [r for r in runs if r.date.date() >= monday]
    planned_week = [r for r in plan_rows if monday.isoformat() <= r.date < (monday + timedelta(days=7)).isoformat()]
    quality = [{'date': r.date.date().isoformat(), 'session': executed_by_id[r.id].get('title'),
                'paces': [_pace(x['pace_sec_per_mile']) for x in executed_by_id[r.id]['reps']]}
               for r in runs if r.id in executed_by_id][-6:]
    return {'goal': goal, 'last_6_weeks': weeks,
            'this_week': {'done_miles': round(sum(r.distance_meters for r in this_week) / 1609.34, 1),
                          'planned_miles': round(sum(r.distance_miles for r in planned_week), 1) if planned_week else None},
            'recent_quality_sessions': quality}


def build_context(user_id, db, activity_id=None, plan_id=None, concern=None):
    from app.api.plans import _get_activities_for_date
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'Athlete not found')
    goal = db.query(Goal).filter_by(user_id=user_id, active=True).first()
    activity = db.query(Activity).filter_by(user_id=user_id, id=activity_id).first() if activity_id else None
    if activity_id and not activity:
        raise HTTPException(404, 'Run not found')
    if activity and activity.date.date() > date.today():
        raise HTTPException(409, 'Future activities cannot be reviewed as completed runs')
    plan = db.query(Plan).filter_by(user_id=user_id, id=plan_id).first() if plan_id else db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    if plan_id and (not plan or plan.preview_state in {'discarded', 'superseded'}):
        raise HTTPException(404, 'Plan not available')
    if not activity and not plan:
        raise HTTPException(404, 'No run or plan to review')
    today = date.today()
    # Eight weeks establish quality/recovery context. Exclude future activities.
    runs = db.query(Activity).filter(Activity.user_id == user_id, runs_only(),
        Activity.date >= datetime.combine(today-timedelta(days=56), datetime.min.time()),
        Activity.date < datetime.combine(today+timedelta(days=1), datetime.min.time())).order_by(Activity.date, Activity.id).all()
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date, PlannedWorkout.id).all() if plan else []
    from app.api.plans import easy_pace_for
    from app.core.session_match import executed_session, off_plan, off_plan_evaluation, session_title, work_minutes
    easy = easy_pace_for(None, user_id, db) or next(
        (spec['easy_pace_sec_per_mile'] for r in rows if (spec := loads(r.prescription)) and spec.get('easy_pace_sec_per_mile')), None)
    executed_by_id = {}
    for run in runs:
        found = executed_session([run], easy)
        if found:
            executed_by_id[run.id] = found | {'title': session_title(found)}
    actuals_by_day = {}
    for run in runs:actuals_by_day.setdefault(run.date.date().isoformat(),[]).append(run)
    row_data = [{**snapshot(r), 'id': r.id, 'date': r.date, 'weekday': date.fromisoformat(r.date).strftime('%a'),
                 'days_from_today': (date.fromisoformat(r.date) - today).days,
                 'status': 'completed' if actuals_by_day.get(r.date) else r.session_status,
                 'moved_to': r.moved_to, 'moved_from': r.moved_from, 'activity_id': max(actuals_by_day[r.date],key=lambda a:a.distance_meters).id if actuals_by_day.get(r.date) else r.activity_id,
                 'feel': r.feel_rating, 'notes': r.feel_notes, 'evaluation': loads_json(r.evaluation)} for r in rows]
    matched = None
    if activity:
        # Latest approved genuine prescription, not synthetic history or a draft.
        matched = db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == user_id,
            Plan.preview_state.is_(None), PlannedWorkout.date == activity.date.date().isoformat(),
            PlannedWorkout.date >= func.coalesce(Plan.prescribed_from, Plan.start_date)).order_by(Plan.id.desc()).first()
    execution = None
    evaluation = None
    if matched:
        contract = loads(matched.prescription)
        evaluation = loads_json(matched.evaluation)
        if contract:
            execution = execution_from_activities(_get_activities_for_date(matched.date, user_id, db), contract)
            if evaluation is None and contract['category'] in {'threshold', 'intervals'}:
                from app.core.workout_evaluator import evaluate_workout
                evaluation = evaluate_workout(None, None, None, matched.type, None, matched.title,
                    matched.feel_rating if matched.feel_rating is not None else activity.feel_rating, contract, execution).to_dict()
                evaluation['provisional'] = True  # explanation only; no progression or feedback effects applied
    wellness = db.query(DailyWellness).filter(DailyWellness.user_id == user_id,
        DailyWellness.date >= (today-timedelta(days=6)).isoformat(), DailyWellness.date <= today.isoformat()).order_by(DailyWellness.date).all()
    wellness_data = [{key: getattr(w, key) for key in ('date','sleep_seconds','sleep_score','hrv_last_night',
        'hrv_baseline_low','hrv_baseline_high','resting_hr','readiness_score','acwr')} for w in wellness]
    options = build_options(plan, db) if plan and plan.is_active else []
    goal_data = {key: getattr(goal, key) for key in ('id','goal_type','race_distance','race_date','target_time_seconds','target_weekly_mileage','terrain','description')} if goal else None
    executed_run = None
    off_plan_note = None
    if activity:
        spec = loads(matched.prescription) if matched else None
        executed_run = executed_session(_get_activities_for_date(activity.date.date().isoformat(), user_id, db),
                                        easy_pace_for(spec, user_id, db))
        if executed_run:
            executed_run = executed_run | {'title': session_title(executed_run)}
        if matched and matched.type == 'workout' and off_plan(spec, executed_run):
            # Judge the run on what was actually run, never against the session it replaced.
            evaluation = off_plan_evaluation(matched.title, executed_run)
            execution = None
            planned_min, done_min = work_minutes(spec, executed_run)
            # Minutes at threshold and at interval pace are different loads; only compare like with like.
            same_kind = executed_run['category'] == spec.get('category')
            dose = ("DOSE ABOVE PLAN" if same_kind and planned_min and done_min and done_min >= 1.5 * planned_min
                    else "similar dose" if same_kind else "different intensity, compare effort not minutes")
            off_plan_note = (f"OFF-PLAN: prescribed {matched.title}, but laps show {executed_run['title']}. "
                             "It REPLACED that day's planned quality session; it is not an extra session. "
                             f"Work: {done_min} min of {executed_run['category']} run vs {planned_min} min of "
                             f"{spec.get('category')} planned ({dose}).")
    context = {'version': VERSION, 'today': today.isoformat(), 'model': settings.openai_coach_model,
        'athlete': {key: getattr(user, key) for key in ('age','experience_level','days_per_week','rest_days','long_run_day','workout_format','units')},
        'goal': goal_data,
        # Stride's calibrated paces for the athlete's CURRENT fitness: judge reps against these, not PRs.
        'current_paces': {k: _pace(v) for k, v in (loads_json(plan.training_paces) or {}).items()
                          if isinstance(v, (int, float)) and v} if plan else None,
        'training_summary': _training_summary(user_id, runs, executed_by_id, today, rows, goal_data),
        'run': _run(activity, executed_run, matched) if activity else None,
        'run_vs_plan': off_plan_note or ('Matches the prescribed session.' if matched and execution and execution.get('confidence') in {'high', 'medium'} else None),
        'recent_runs': [_brief_run(a, executed_by_id.get(a.id)) for a in runs[-60:]],
        'quality_evidence': quality_history(user_id, db), 'recovery': wellness_data,
        'matched_prescription': snapshot(matched) if matched else None,
        'execution': execution, 'deterministic_evaluation': evaluation,
        'plan': {'id': plan.id, 'active': plan.is_active, 'start': plan.start_date, 'end': plan.end_date,
                 'goal': loads_json(plan.goal_snapshot), 'load': loads_json(plan.load),
                 'athlete': {k: v for k, v in (loads_json(plan.athlete_snapshot) or {}).items() if k != 'name'}, 'phases': loads_json(plan.phases),
                 'assessment': loads_json(plan.assessment), 'sessions': row_data} if plan else None,
        'progression': [{key: getattr(p, key) for key in ('category','program_key','current_level','current_pace_sec')}
                        for p in db.query(WorkoutProgression).filter_by(user_id=user_id).order_by(WorkoutProgression.id).all()],
        'candidates': options}
    if concern:
        context['athlete_request'] = concern
    if plan:
        snapshot_data = loads_json(plan.athlete_snapshot) or {}
        quality = snapshot_data.get('quality_policy') or {'stage': 'single', 'sessions': 1}
        context['plan']['quality_authority'] = quality
        context['plan']['weekly_structure'] = [
            {'week_number': week, 'quality_days': [
                {'date': r.date, 'category': (loads(r.prescription) or {}).get('category', 'legacy_workout'), 'title': r.title}
                for r in rows if r.week_number == week and r.type == 'workout' and not r.moved_to],
             'long_runs': [{'date': r.date, 'title': r.title} for r in rows if r.week_number == week and r.type == 'long_run']}
            for week in sorted({r.week_number for r in rows})]
        context['policy_interpretation'] = {
            'initial_quality': 'One controlled primary workout PER WEEK is permitted even without prior verified quality success. Missing evidence blocks progression and a second substantial weekly workout, not all introductory quality.',
            'week_boundaries': 'Count quality separately for each week_number. Two sessions in DIFFERENT weeks are not two weekly workouts.',
            'heart_rate': 'No athlete HR zones/threshold are supplied. An average HR alone cannot establish excessive easy effort.',
            'risk': 'The injury-risk label is a heuristic. Compare prescribed load with actual recent full weeks and recovery; it is not a diagnosis or automatic veto.',
            'matching': 'matched_prescription null means there is no genuine prescription to judge this run against. Never infer missed strides or incomplete work from a synthetic historical day.'}
    sources = research_context(goal)
    fingerprint = hashlib.sha256(json.dumps({'context': context, 'research': sources, 'instructions': INSTRUCTIONS, 'key_version': hashlib.sha256(settings.openai_api_key.encode()).hexdigest()}, sort_keys=True, default=str).encode()).hexdigest()
    return context, sources, fingerprint, plan


def normalize_concern(concern):
    """The athlete's own words, whitespace-collapsed; blank means no concern."""
    return ' '.join((concern or '').split()) or None


def loads_json(raw):
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


def serialize_review(row, *, stale=False):
    result = loads_json(row.result) or {}
    candidates = loads_json(row.candidates) or []
    chosen = {s['candidate_id']: s['reason'] for s in result.get('suggestions', [])}
    return {'id': row.id, 'status': row.status, 'model': row.model, 'created_at': row.created_at.isoformat(),
            'stale': stale, 'applied_candidate_id': row.applied_candidate_id,
            'athlete_concern': row.athlete_concern,
            'summary': result.get('summary', 'Review in progress. Check again shortly.'),
            'plan_fit': result.get('plan_fit', 'insufficient_evidence'),
            'observations': result.get('observations', []), 'uncertainties': result.get('uncertainties', []),
            'research': result.get('research', []),
            'suggestions': [{**c, 'reason': chosen[c['id']]} for c in candidates if c['id'] in chosen]}


def review_training(user_id, db, activity_id=None, plan_id=None, concern=None):
    from app.api.plans import _begin_schedule_write
    # Reserve before calling OpenAI: concurrent retries reuse the same review;
    # quota checks and reservations share a SQLite write lock.
    _begin_schedule_write(db)
    concern = normalize_concern(concern)
    context, sources, fingerprint, plan = build_context(user_id, db, activity_id, plan_id, concern)
    cached = db.query(CoachingReview).filter_by(user_id=user_id, context_hash=fingerprint).first()
    if cached and cached.status == 'pending' and cached.created_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2):
        cached.status = 'fallback'
        cached.result = json.dumps({'summary': 'The previous review was interrupted. No AI training changes were applied.', 'suggestions': []})
    retry = cached and cached.status == 'fallback' and cached.created_at < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    if cached and not retry:
        db.commit()
        return serialize_review(cached)
    configured = bool(settings.openai_api_key)
    utc_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.query(func.coalesce(func.sum(CoachingReview.attempts), 0)).filter(CoachingReview.user_id == user_id,
        CoachingReview.created_at >= utc_day, CoachingReview.model.is_not(None)).scalar()
    if configured and used >= settings.openai_coach_daily_limit:
        raise HTTPException(429, 'Daily AI review limit reached. Existing reviews and training rules still work; try tomorrow.')
    row = cached or CoachingReview(user_id=user_id, activity_id=activity_id, plan_id=plan.id if plan else None,
        context_hash=fingerprint, status='pending', model=settings.openai_coach_model if configured else None,
        candidates=json.dumps(context['candidates']), athlete_concern=concern)
    if retry:
        row.status = 'pending'
        row.attempts += 1
        row.created_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()  # No write lock held across network I/O.
    review_id = row.id
    db.rollback()  # release the read transaction opened by expire-on-commit access
    try:
        if not configured:
            raise RuntimeError('not_configured')
        advice, usage = request_advice(context, sources)
        # Defense in depth beyond JSON schema: IDs must exist, at most one per date.
        available = {c['id']: c for c in context['candidates']}
        dates = set()
        for suggestion in advice.suggestions:
            if suggestion.candidate_id not in available:
                raise ValueError('Unknown candidate')
            day = available[suggestion.candidate_id]['date']
            if day in dates:
                raise ValueError('Conflicting suggestions')
            dates.add(day)
        known_sources = {s['id']: s for s in sources}
        if any(s not in known_sources for s in advice.research_ids):
            raise ValueError('Unknown research reference')
        result = advice.model_dump()
        result['research'] = [{'id': s, 'path': known_sources[s]['path']} for s in advice.research_ids]
        status = 'ready'
    except Exception as exc:
        # Deliberately avoid str(exc) or traceback: provider errors can echo inputs.
        logger.warning('AI review unavailable (%s); deterministic coaching remains active', type(exc).__name__)
        result = {'summary': 'AI review is unavailable. Your run feedback and deterministic training decisions are saved; no AI changes were applied.',
                  'plan_fit': 'insufficient_evidence', 'observations': [],
                  'uncertainties': ['OpenAI is not configured.' if not configured else 'The provider did not return a valid review.'],
                  'suggestions': [], 'research': []}
        usage = {}
        status = 'fallback'
    row = db.get(CoachingReview, review_id)
    row.result, row.status = json.dumps(result), status
    row.input_tokens, row.output_tokens = usage.get('input_tokens', 0), usage.get('output_tokens', 0)
    db.commit()
    try:
        current_hash = build_context(user_id, db, activity_id, plan_id, concern)[2]
    except HTTPException:
        current_hash = None
    return serialize_review(row, stale=current_hash != row.context_hash)
