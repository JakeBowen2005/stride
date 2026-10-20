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
from app.models.activity import Activity
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
VERSION = 'openai-coach-v2'


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


def _run(a):
    raw_laps = loads_json(a.splits) or []
    laps = [{k: lap[k] for k in ('intensity', 'distance_m', 'duration_s', 'average_hr') if k in lap}
            for lap in raw_laps[:80] if isinstance(lap, dict)] if isinstance(raw_laps, list) else []
    return {'id': a.id, 'date': a.date.date().isoformat(), 'miles': round(a.distance_meters / 1609.34, 2),
            'seconds': a.duration_seconds, 'category': a.workout_type, 'laps': laps,
            'average_hr': a.average_heartrate, 'max_hr': a.max_heartrate,
            'feel': a.feel_rating, 'notes': (a.feel_notes or '')[:700],
            'work_detail': (a.description or '')[:900],
            'aerobic_training_effect': a.aerobic_training_effect,
            'anaerobic_training_effect': a.anaerobic_training_effect}


def build_context(user_id, db, activity_id=None, plan_id=None):
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
    runs = db.query(Activity).filter(Activity.user_id == user_id,
        Activity.date >= datetime.combine(today-timedelta(days=56), datetime.min.time()),
        Activity.date < datetime.combine(today+timedelta(days=1), datetime.min.time())).order_by(Activity.date, Activity.id).all()
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date, PlannedWorkout.id).all() if plan else []
    row_data = [{**snapshot(r), 'id': r.id, 'date': r.date, 'status': r.session_status,
                 'moved_to': r.moved_to, 'moved_from': r.moved_from, 'activity_id': r.activity_id,
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
    wellness = db.query(DailyWellness).filter(DailyWellness.user_id == user_id,
        DailyWellness.date >= (today-timedelta(days=6)).isoformat(), DailyWellness.date <= today.isoformat()).order_by(DailyWellness.date).all()
    wellness_data = [{key: getattr(w, key) for key in ('date','sleep_seconds','sleep_score','hrv_last_night',
        'hrv_baseline_low','hrv_baseline_high','resting_hr','readiness_score','acwr')} for w in wellness]
    options = build_options(plan, db) if plan and plan.is_active else []
    goal_data = {key: getattr(goal, key) for key in ('id','goal_type','race_distance','race_date','target_time_seconds','target_weekly_mileage','terrain')} if goal else None
    context = {'version': VERSION, 'today': today.isoformat(), 'model': settings.openai_coach_model,
        'athlete': {key: getattr(user, key) for key in ('age','experience_level','days_per_week','rest_days','long_run_day','workout_format','units')},
        'goal': goal_data, 'run': _run(activity) if activity else None,
        'recent_runs': [_run(a) for a in runs[-80:]],
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
            'summary': result.get('summary', 'Review in progress. Check again shortly.'),
            'plan_fit': result.get('plan_fit', 'insufficient_evidence'),
            'observations': result.get('observations', []), 'uncertainties': result.get('uncertainties', []),
            'research': result.get('research', []),
            'suggestions': [{**c, 'reason': chosen[c['id']]} for c in candidates if c['id'] in chosen]}


def review_training(user_id, db, activity_id=None, plan_id=None):
    from app.api.plans import _begin_schedule_write
    # Reserve before calling OpenAI: concurrent retries reuse the same review;
    # quota checks and reservations share a SQLite write lock.
    _begin_schedule_write(db)
    context, sources, fingerprint, plan = build_context(user_id, db, activity_id, plan_id)
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
        candidates=json.dumps(context['candidates']))
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
        current_hash = build_context(user_id, db, activity_id, plan_id)[2]
    except HTTPException:
        current_hash = None
    return serialize_review(row, stale=current_hash != row.context_hash)
