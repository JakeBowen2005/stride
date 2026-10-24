"""Grounded advice with durable deduplication, bounded spend and explicit acceptance."""
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func

from app.config import settings
from app.core.workout_data import execution_from_activities, loads
from app.models.activity import Activity, runs_only, is_walk, activity_classification
from app.models.coaching import CoachingReview, CoachingAttempt
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.models.wellness import DailyWellness
from app.services.coaching_options import build_options, snapshot
from app.services.openai_coach import INSTRUCTIONS, request_advice
from app.services.quality_history import quality_history

logger = logging.getLogger('stride.coaching')
DOCS = Path(__file__).resolve().parents[3] / 'docs'
VERSION = 'openai-coach-v9-measured-scopes'


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
            'feel': a.effective_feel}


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
    feedback_matches = bool(planned and planned.feedback_activity_id == a.id)
    app_feel = planned.feel_rating if feedback_matches and planned.feel_rating is not None else a.feel_rating
    app_effort = planned.effort_rating if feedback_matches else a.effort_rating
    lap_summary = next((line.strip() for line in (a.description or '').splitlines() if line.strip().startswith('Garmin laps:')), None)
    run = {'id': a.id, 'date': a.date.date().isoformat(), 'miles': round(miles, 2),
           'duration': f"{int(a.duration_seconds // 60)}:{int(a.duration_seconds % 60):02d}" if a.duration_seconds else None,
           'avg_pace': _pace(a.duration_seconds / miles) if miles and a.duration_seconds else None,
           'average_hr': a.average_heartrate, 'max_hr': a.max_heartrate,
           'elevation_gain_ft': round(a.elevation_gain * 3.281) if a.elevation_gain else None,
           'classification': activity_classification(a),
           'aerobic_training_effect': a.aerobic_training_effect,
           'anaerobic_training_effect': a.anaerobic_training_effect,
           'laps': laps,
           # Measured from the watch's laps: the authority on what was actually run
           'measured_lap_summary': lap_summary,
           'detected_session': None,
           'watch_self_evaluation': {'feel_1_to_10': a.watch_feel, 'effort_1_to_10': a.watch_effort,
                                     'provenance': 'garmin_watch_prompt_after_the_run'}
                                    if a.garmin_feel is not None or a.garmin_rpe else None,
           'athlete_feedback': {'feel_1_to_10': app_feel if app_feel is not None else a.watch_feel,
                                'feel_source': 'app' if app_feel is not None else ('watch' if a.watch_feel is not None else None),
                                'notes': ((planned.feel_notes if feedback_matches else None) or a.feel_notes or '')[:700] or None,
                                'pace_vs_target': planned.pace_assessment if feedback_matches else None,
                                'said_swapped': bool(planned.swapped) if feedback_matches else False,
                                'effort_1_to_10': app_effort if app_effort is not None else a.watch_effort,
                                'reported_completion': loads_json(planned.reported_completion) if feedback_matches else None,
                                'provenance': 'athlete_report',
                                'evidence_note': 'Reported completion/effort is subjective; it is not measured lap verification.'}}
    if executed:
        run['detected_session'] = {'title': executed.get('title'), 'category': executed['category'],
            'matched_activity_ids': [executed['activity_id']],
            'reps': [{'meters': round(r['distance_m']), 'time_s': round(r['duration_s']),
                      'pace': _pace(r['pace_sec_per_mile']), 'avg_hr': r['average_hr']} for r in executed['reps']],
            # What was run between reps (measured), next to what the plan asked for
            'measured_recovery_s': executed['recovery_seconds'],
            'planned_recovery_s': _planned_recovery(planned),
            'work_miles': executed['work_miles']}
    return run


def _planned_recovery(planned):
    data = loads_json(planned.prescription) if planned and planned.prescription else None
    if not isinstance(data, dict):
        return None
    return next((s.get('recovery_seconds') for s in data.get('segments') or [] if s.get('recovery_seconds')), None)


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


def _week_view(rows, runs, today):
    """This calendar week and next, day by day: the frame the coach talks about first."""
    monday = today - timedelta(days=today.weekday())
    done_by_day = {}
    for r in runs:
        done_by_day.setdefault(r.date.date().isoformat(), []).append(r)
    weeks = {}
    for label, start in (('this_week', monday), ('next_week', monday + timedelta(days=7))):
        days, planned_total, done_total = [], 0.0, 0.0
        for offset in range(7):
            day = start + timedelta(days=offset)
            iso = day.isoformat()
            planned = next((r for r in rows if r.date == iso and not r.moved_to), None)
            done = done_by_day.get(iso, [])
            done_miles = round(sum(a.distance_meters for a in done) / 1609.34, 1)
            planned_total += (planned.distance_miles or 0) if planned else 0
            done_total += done_miles
            days.append({'date': iso, 'weekday': day.strftime('%a'), 'days_from_today': (day - today).days,
                         'planned': {'type': planned.type, 'title': planned.title, 'miles': planned.distance_miles} if planned else None,
                         'done_miles': done_miles or None,
                         'feel': planned.feel_rating if planned else None})
        quality = [d for d in days if d['planned'] and d['planned']['type'] in {'workout', 'long_run', 'race'}]
        weeks[label] = {'week_of': start.isoformat(), 'planned_miles': round(planned_total, 1),
                        'done_miles': round(done_total, 1) if label == 'this_week' else None,
                        'remaining_planned_miles': round(sum((d['planned'] or {}).get('miles') or 0 for d in days
                                                             if d['days_from_today'] >= 0 and not d['done_miles']), 1),
                        'key_sessions': [{'weekday': d['weekday'], 'title': d['planned']['title']} for d in quality],
                        'days': days}
    return weeks


MEMORY_DAYS = 14
MEMORY_LIMIT = 6


def prior_reviews(user_id, db, activity_id=None, plan_id=None):
    """The coach's own completed notes from the last two weeks, newest first.

    Only the latest note per subject (a run, or a plan's weekly review) is kept, and the
    subject under review is left out so a refresh does not just echo itself. A run review
    sees only earlier run reviews; the weekly review sees both, to synthesize the trend.
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=MEMORY_DAYS)
    rows = db.query(CoachingReview).filter(CoachingReview.user_id == user_id, CoachingReview.status == 'ready',
        CoachingReview.created_at >= since).order_by(CoachingReview.created_at.desc(), CoachingReview.id.desc()).all()
    current = ('run', activity_id) if activity_id else ('week', plan_id)
    seen, notes = {current}, []
    for row in rows:
        subject = ('run', row.activity_id) if row.activity_id else ('week', row.plan_id)
        result = loads_json(row.result) or {}
        if subject in seen or not result.get('summary'):
            continue
        if current[0] == 'run' and subject[0] == 'week':
            continue  # a run review stays about its run; week notes made the two converge
        seen.add(subject)
        run = db.get(Activity, row.activity_id) if row.activity_id else None
        notes.append({'written': row.created_at.date().isoformat(), 'scope': subject[0],
                      'run_date': run.date.date().isoformat() if run else None,
                      'summary': result['summary'], 'plan_fit': result.get('plan_fit'),
                      'observations': result.get('observations', [])[:3],
                      'athlete_concern': row.athlete_concern,
                      'athlete_accepted_a_suggestion': bool(row.applied_candidate_id)})
        if len(notes) == MEMORY_LIMIT:
            break
    return notes


def build_context(user_id, db, activity_id=None, plan_id=None, concern=None):
    """Cache expensive facts/menu building, while keeping prior coach notes fresh."""
    from app.services.history_cache import cached
    goal = db.query(Goal).filter_by(user_id=user_id, active=True).first()
    sources = research_context(goal)
    selected_plan = db.query(Plan).filter_by(user_id=user_id, id=plan_id).first() if plan_id else db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    resolved_plan_id = selected_plan.id if selected_plan else plan_id
    key = hashlib.sha256(json.dumps({'version': VERSION, 'today': date.today().isoformat(),
        'activity': activity_id, 'plan': resolved_plan_id, 'concern': normalize_concern(concern),
        'model': settings.openai_coach_model, 'instructions': INSTRUCTIONS, 'research': sources,
        'credential_version': hashlib.sha256(settings.openai_api_key.encode()).hexdigest()}, sort_keys=True).encode()).hexdigest()
    def build():
        context, docs, fingerprint, plan = _build_context(user_id, db, activity_id, plan_id, concern)
        context.pop('prior_reviews', None)
        return {'context': context, 'sources': docs, 'fingerprint': fingerprint, 'plan_id': plan.id if plan else None}
    result = cached(user_id, 'coach-context', key, db, build, persist=db.info.get('history_cache_write', False))
    context = result['context']
    context['prior_reviews'] = prior_reviews(user_id, db, activity_id, result['plan_id'])
    plan = db.get(Plan, result['plan_id']) if result['plan_id'] else None
    return context, result['sources'], result['fingerprint'], plan


def _build_context(user_id, db, activity_id=None, plan_id=None, concern=None):
    from app.api.plans import _get_activities_for_date
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'Athlete not found')
    goal = db.query(Goal).filter_by(user_id=user_id, active=True).first()
    activity = db.query(Activity).filter_by(user_id=user_id, id=activity_id).first() if activity_id else None
    if activity_id and not activity:
        raise HTTPException(404, 'Run not found')
    if activity and is_walk(activity):
        raise HTTPException(409, 'This is a walking activity; select the running session to review it.')
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
                 'feel': r.feel_rating, 'effort_1_to_10': r.effort_rating, 'reported_completion': loads_json(r.reported_completion), 'notes': r.feel_notes, 'evaluation': loads_json(r.evaluation)} for r in rows]
    matched = None
    if activity:
        # Latest approved genuine prescription, not synthetic history or a draft.
        matched = db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == user_id,
            Plan.preview_state.is_(None), PlannedWorkout.date == activity.date.date().isoformat(),
            PlannedWorkout.date >= func.coalesce(Plan.prescribed_from, Plan.start_date)).order_by(Plan.id.desc()).first()
    execution = None
    evaluation = None
    if matched:
        from app.api.plans import _work_evidence_activity
        primary = _work_evidence_activity(_get_activities_for_date(matched.date, user_id, db))
        if not primary or primary.id != activity.id:
            matched = None  # a double/shakeout is not the primary workout's execution
    if matched:
        contract = loads(matched.prescription)
        evaluation = loads_json(matched.evaluation)
        if evaluation and activity.id not in evaluation.get('activity_ids', []):
            evaluation = None
        if contract:
            execution = execution_from_activities([activity], contract)
            if (evaluation is None or evaluation.get('decision') == 'off_plan') and contract['category'] in {'threshold', 'intervals'}:
                from app.core.workout_evaluator import evaluate_workout, gate_progression
                from app.api.plans import _plan_program
                state = db.query(WorkoutProgression).filter_by(user_id=user_id, category=contract["category"], program_key=_plan_program(plan)).first()
                provisional = evaluate_workout(None, None, None, matched.type, None, matched.title,
                    matched.feel_rating if matched.feedback_activity_id == activity.id and matched.feel_rating is not None else activity.effective_feel, contract, execution)
                evaluation = gate_progression(provisional, contract, state.current_level if state else None).to_dict()
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
        executed_run = executed_session([activity], easy_pace_for(spec, user_id, db))
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
    from app.services.load_history import completed_week_load
    context = {'workload': completed_week_load(user_id, db), 'version': VERSION, 'today': today.isoformat(), 'model': settings.openai_coach_model,
        'athlete': {key: getattr(user, key) for key in ('age','experience_level','days_per_week','rest_days','long_run_day','workout_format','units')},
        'goal': goal_data,
        # Stride's calibrated paces for the athlete's CURRENT fitness: judge reps against these, not PRs.
        'current_paces': {k: _pace(v) for k, v in (loads_json(plan.training_paces) or {}).items()
                          if isinstance(v, (int, float)) and v} if plan else None,
        'review_scope': 'run' if activity else 'week',
        'week_view': _week_view(rows, runs, today),
        'training_summary': _training_summary(user_id, runs, executed_by_id, today, rows, goal_data),
        'run': _run(activity, executed_run, matched) if activity else None,
        'run_vs_plan': off_plan_note or ('Matches the prescribed session.' if matched and execution and execution.get('confidence') in {'high', 'medium'} else None),
        # Four weeks of single-line history; older trends are already in training_summary.last_6_weeks.
        'recent_runs': [_brief_run(a, executed_by_id.get(a.id)) for a in runs if a.date.date() >= today - timedelta(days=28)],
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
    from app.services.history_dossier import dossier, evidence_manifest
    context['historical_profile'] = dossier(user_id, db, today, persist=db.info.get('history_cache_write', False))
    ids = {r.id for r in runs}
    if activity:
        ids.add(activity.id)
    for block in context['historical_profile']['historical_capacity']['sustained_blocks']:
        ids.update(block['activity_ids'])
    for race in context['historical_profile']['race_buildups']:
        ids.update(race['activity_ids'])
    for run in context['historical_profile']['historical_capacity']['longest_runs']:
        ids.update(run['activity_ids'])
    context['evidence_manifest'] = evidence_manifest(user_id, db, ids)
    sources = research_context(goal)
    fingerprint = hashlib.sha256(json.dumps({'context': context, 'research': sources, 'instructions': INSTRUCTIONS, 'key_version': hashlib.sha256(settings.openai_api_key.encode()).hexdigest()}, sort_keys=True, default=str).encode()).hexdigest()
    # Memory is added after hashing: it is the coach's own earlier opinion, not training data,
    # so a new note elsewhere must not mark this review (or its suggestions) stale.
    context['prior_reviews'] = prior_reviews(user_id, db, activity_id, plan.id if plan and not activity_id else plan_id)
    return context, sources, fingerprint, plan


def normalize_concern(concern):
    """The athlete's own words, whitespace-collapsed; blank means no concern."""
    return ' '.join((concern or '').split()) or None


def loads_json(raw):
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None


SENTENCE_END = re.compile(r'[.!?][)"\'’”]*(?=\s|$)')


def finish_sentences(text):
    """Never show a sentence the model was cut off in the middle of.

    Drops a trailing fragment after the last complete sentence; text with no complete
    sentence at all keeps its words and gets an ellipsis instead.
    """
    text = (text or '').strip()
    if not text or text.rstrip('"\'’”)').endswith(('.', '!', '?')):
        return text
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    if ends:
        return text[:ends[-1]].strip()
    return text.rstrip(' ,;:—–-') + '…'


def serialize_review(row, *, stale=False):
    result = loads_json(row.result) or {}
    candidates = loads_json(row.candidates) or []
    chosen = {s['candidate_id']: finish_sentences(s['reason']) for s in result.get('suggestions', [])}
    return {'id': row.id, 'status': row.status, 'model': row.model, 'created_at': row.created_at.isoformat(),
            'stale': stale, 'applied_candidate_id': row.applied_candidate_id,
            'athlete_concern': row.athlete_concern,
            'policy_version': row.policy_version or 'legacy', 'context_as_of': row.created_at.isoformat(),
            'summary': finish_sentences(result.get('summary', 'Review in progress. Check again shortly.')),
            'plan_fit': result.get('plan_fit', 'insufficient_evidence'),
            # Bullets have no length cap, so the provider never cuts them off; leave them as written.
            'observations': result.get('observations', []), 'uncertainties': result.get('uncertainties', []),
            'research': result.get('research', []),
            'history_insights': result.get('history_insights', []),
            'input_revision': row.input_revision,
            'suggestions': [{**c, 'reason': chosen[c['id']]} for c in candidates if c['id'] in chosen]}


def review_training(user_id, db, activity_id=None, plan_id=None, concern=None):
    from app.api.plans import _begin_schedule_write
    # Reserve before calling OpenAI: concurrent retries reuse the same review;
    # quota checks and reservations share a SQLite write lock.
    _begin_schedule_write(db)
    db.info['history_cache_write'] = True
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
        candidates=json.dumps(context['candidates']), athlete_concern=concern, policy_version=VERSION)
    if retry:
        row.status = 'pending'
        row.attempts += 1
        row.created_at = datetime.now(timezone.utc)
    from app.services.openai_coach import model_payload
    row.input_snapshot = json.dumps({'instructions': INSTRUCTIONS, **model_payload(context, sources)}, default=str)
    row.input_revision = context['historical_profile']['input_revision']
    db.add(row)
    db.flush()
    attempt = CoachingAttempt(review_id=row.id, number=row.attempts, input_snapshot=row.input_snapshot,
        input_revision=row.input_revision, model=row.model, policy_version=VERSION, status='pending')
    db.add(attempt)
    db.commit()  # No write lock held across network I/O.
    review_id, attempt_id = row.id, attempt.id
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
        known_insights = {item['id']: item for item in context['historical_profile']['insights']}
        if any(item not in known_insights for item in advice.history_insight_ids):
            raise ValueError('Unknown historical evidence')
        result = advice.model_dump()
        result['history_insights'] = [known_insights[item] for item in dict.fromkeys(advice.history_insight_ids)]
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
    attempt = db.get(CoachingAttempt, attempt_id)
    attempt.status, attempt.result = status, row.result
    attempt.input_tokens, attempt.output_tokens = row.input_tokens, row.output_tokens
    db.commit()
    try:
        current_hash = build_context(user_id, db, activity_id, plan_id, concern)[2]
    except HTTPException:
        current_hash = None
    return serialize_review(row, stale=current_hash != row.context_hash)
