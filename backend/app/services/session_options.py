"""Personalized, deterministic replacement menus. The athlete (or the AI review)
selects one concrete option; nothing here is authored by a model.

Each menu holds at most three sessions in different shapes at a dose that fits
the athlete's experience, current volume and phase (see core/session_catalog.py
for sources and the dose band). Every proposed session, including any easy-day
cuts it needs, is dry-run through the same budget and schedule validator used
when the athlete applies it.
"""
import copy
import hashlib
import json
import math
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.goal_pace import step_note
from app.core.session_catalog import (
    MAX_OPTIONS,
    build_workout,
    dose_band,
    ranked_templates,
    specific_bands,
)
from app.core.workout_data import MI, day_prescription, loads
from app.models.activity import Activity, runs_only
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.services.coaching_options import snapshot

VERSION = 'session-menu-v3'
QUALITY_ACTIVITY_TYPES = {'workout', 'threshold', 'intervals', 'tempo', 'fartlek', 'hill_repeats', 'race'}
ULTRA_PROGRAMS = {'50k', '50mi', '100k', '100mi'}


def _json(raw, fallback=None):
    try:
        return json.loads(raw) if raw else fallback
    except (ValueError, TypeError):
        return fallback


def _approved_category_paces(rows, stored, calibrated, paces):
    """No new category evidence: keep the approved numeric pace. Never infer a
    faster threshold from a label change or an easy-run estimate."""
    for category, key in (('threshold', 'threshold_pace'), ('intervals', 'interval_pace')):
        if key in calibrated:
            continue
        targets = [seg['pace_range_sec_per_mile'] for r in rows
                   for data in [loads(r.prescription) or {}] if data.get('category') == category
                   for seg in data['segments'] if seg.get('pace_range_sec_per_mile')]
        if category == 'threshold' and targets:
            paces['broken_threshold_pace'] = max(t['slow'] for t in targets)
            paces['tempo_pace'] = paces['broken_threshold_pace'] + 10
        elif category == 'intervals' and targets:
            paces['interval_pace'] = max(t['slow'] for t in targets)
            paces['interval_pace_fast'] = max(t['fast'] for t in targets)
        elif stored:
            keys = (('threshold_pace', 'tempo_pace', 'broken_threshold_pace') if category == 'threshold'
                    else ('interval_pace', 'interval_pace_fast'))
            paces.update({name: stored[name] for name in keys if name in stored})
    return paces


def context_for(plan, db):
    """Everything a menu depends on, plus a token that changes when any of it does."""
    from app.api.plans import _parse_pace
    from app.core.goal_pace import with_specific_pace
    from app.core.pacing import goal_paces
    from app.core.plan_engine import _build_current_paces, effective_paces
    from app.core.quality_policy import select_quality_policy
    from app.core.workout_ladders import program_key
    from app.services.analyzer import analyze_athlete, compute_weekly_mileage
    from app.services.pace_calibrator import calibrate_paces
    from app.services.quality_history import quality_history

    user = db.get(User, plan.user_id)
    goal = db.query(Goal).filter_by(user_id=plan.user_id, active=True).first()
    analysis = analyze_athlete(plan.user_id, db)
    experience = user.experience_level or analysis.get('overview', {}).get('experience_level', 'beginner')
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    weeks = {w['week_start']: w['actual'] for w in compute_weekly_mileage(plan.user_id, db, 10)}
    full_weeks = [weeks.get((monday - timedelta(weeks=i)).isoformat(), 0) for i in range(8, 0, -1)]
    evidence = quality_history(plan.user_id, db)
    acts = db.query(Activity).filter(
        Activity.user_id == plan.user_id,
        Activity.date >= datetime.combine(today - timedelta(days=56), datetime.min.time()),
        Activity.date < datetime.combine(today + timedelta(days=1), datetime.min.time()),
        runs_only(),
    ).order_by(Activity.id).all()
    recent_long = max((a.distance_meters / MI for a in acts if a.date.date() >= today - timedelta(days=28)), default=0)
    assessment = (_json(plan.assessment, {}) or {}).get('decision')
    quality = select_quality_policy(goal.goal_type if goal else 'general', experience, user.days_per_week,
                                    full_weeks, evidence['weekly_run_days'], recent_long,
                                    assessment=assessment, evidence=evidence)

    recent_pace = analysis.get('paces', {}).get('recent_easy_pace') or analysis.get('paces', {}).get('easy_pace')
    easy = _parse_pace(recent_pace) if recent_pace else 0
    calibrated = calibrate_paces(plan.user_id, db)
    stored = _json(plan.training_paces, {}) or {}
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
    paces = _build_current_paces(easy or stored.get('long_run_pace', 570), calibrated)
    paces = _approved_category_paces(rows, stored, calibrated, paces)
    program = (goal.race_distance or goal.goal_type) if goal else 'general'
    progression = db.query(WorkoutProgression).filter_by(
        user_id=plan.user_id, program_key=program_key(program)).order_by(WorkoutProgression.id).all()
    paces = effective_paces(paces, {p.category: {'current_pace_sec': p.current_pace_sec}
                                    for p in progression if p.current_pace_sec})
    # Goal pace is a target only: specific_pace steps toward it from demonstrated pace.
    goal_pace = (goal_paces(goal.race_distance, goal.target_time_seconds) or {}).get('race_pace') \
        if goal and goal.goal_type == 'race' and goal.race_distance and goal.target_time_seconds else None
    paces['goal_race_pace'] = round(goal_pace) if goal_pace else None
    paces = with_specific_pace(paces, program)

    completed_dates = {a.date.date().isoformat() for a in acts}
    fingerprint = {
        'version': VERSION, 'today': today.isoformat(), 'plan_id': plan.id, 'active': plan.is_active,
        'load': plan.load, 'snapshot': plan.athlete_snapshot, 'phases': plan.phases, 'goal_snapshot': plan.goal_snapshot,
        'athlete': {k: getattr(user, k) for k in ('experience_level', 'rest_days', 'days_per_week', 'long_run_day', 'workout_format')},
        'goal': {k: getattr(goal, k) for k in ('id', 'goal_type', 'race_distance', 'target_time_seconds', 'race_date', 'terrain')} if goal else None,
        'sessions': [{**snapshot(r), 'id': r.id, 'date': r.date,
                      'status': 'completed' if r.date in completed_dates else r.session_status,
                      'moved_to': r.moved_to, 'moved_from': r.moved_from, 'feedback': r.feel_rating,
                      'notes': r.feel_notes, 'original': r.original_prescription} for r in rows],
        'activities': [{k: getattr(a, k) for k in ('id', 'date', 'distance_meters', 'duration_seconds', 'feel_rating',
                                                   'feel_notes', 'description', 'splits')} for a in acts],
        'quality': quality.to_dict(), 'paces': paces,
        'levels': [(p.category, p.current_level, p.current_pace_sec) for p in progression],
    }
    token = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()
    return {'user': user, 'goal': goal, 'experience': experience, 'baseline': sum(full_weeks[-4:]) / 4,
            'recent_long': recent_long, 'evidence': evidence, 'quality': quality, 'paces': paces,
            'rows': rows, 'token': token, 'program': program}


def _as_patch(workout):
    return {'type': 'workout', 'title': workout['name'], 'description': workout['structure'],
            'purpose': workout['purpose'], 'distance_miles': workout['total_miles'],
            'warmup': workout.get('warmup'), 'cooldown': workout.get('cooldown'),
            'prescription': json.dumps(workout['prescription']), 'b2b': False}


class _Week:
    """Phase, capacity and load facts for the week that holds the session."""

    def __init__(self, plan, row, ctx, db):
        from app.api.plans import _get_activities_for_date
        phases = _json(plan.phases, []) or []
        self.info = phases[row.week_number - 1] if row.week_number <= len(phases) else {}
        self.phase = self.info.get('phase', 'general')
        self.others = [r for r in ctx['rows'] if r.week_number == row.week_number and r.id != row.id]
        load = _json(plan.load, {}) or {}
        budgets = load.get('weekly_budgets', [])
        self.budget = (budgets[row.week_number - 1] if row.week_number <= len(budgets)
                       else sum(r.distance_miles for r in self.others) + row.distance_miles)
        self.deload = bool(plan.is_deload) and ('deload_week' not in load or load['deload_week'] == row.week_number - 1)
        week_rows = [r for r in ctx['rows'] if r.week_number == row.week_number]
        self.back_to_back = bool(self.info.get('back_to_back')) or sum(bool(r.b2b) and r.type == 'long_run' for r in week_rows) >= 2

        def substantial(r):
            return r.type == 'workout' and (loads(r.prescription) or {}).get('category') != 'speed_support'

        def hard_long(r):
            return r.type == 'long_run' and any(t in r.title.lower() for t in ('mp ', 'race-effort', 'steady', 'sandwich'))

        def ran_quality(r):
            return any(a.workout_type in QUALITY_ACTIVITY_TYPES for a in _get_activities_for_date(r.date, plan.user_id, db))

        self.hard_count = sum(substantial(r) or hard_long(r) or ran_quality(r) for r in self.others)
        # Swapping a hard session for another keeps the week's hard-day count unchanged.
        self.row_is_hard = substantial(row) or hard_long(row)
        self.has_light_support = any(r.type == 'workout' and not substantial(r) for r in self.others)
        self.phase_cap = self.info.get('max_workouts')
        if self.phase_cap is None and self.phase == 'taper':
            self.phase_cap = 1
        if self.phase == 'recovery':
            self.phase_cap = 0
        if self.phase == 'base' and ctx['experience'] not in {'advanced', 'expert'}:
            self.phase_cap = 1
        capacity = 2 if ctx['quality'].stage == 'dual' else 1
        if self.phase_cap is not None:
            capacity = min(capacity, self.phase_cap)
        if self.deload or self.back_to_back:
            capacity = min(capacity, 1)
        self.capacity = capacity


def _quality_candidates(category, row, week, ctx, poor):
    """Full-dose threshold/interval (or hill) sessions from the catalog."""
    if poor or week.phase in {'race_week', 'recovery'}:
        return [], ['Recent recovery or a race/recovery week calls for easy running or rest instead of another hard session.']
    if week.hard_count >= week.capacity and not week.row_is_hard:
        return [], ['This week already has its hard sessions. Swap one of those instead, or keep this day easy.']
    pace = ctx['paces']['broken_threshold_pace' if category == 'threshold' else 'interval_pace']
    volume = max(ctx['baseline'], week.budget or 0)
    band = dose_band(category, ctx['experience'], volume, pace, week.phase, week.deload)
    terrain = ctx['goal'].terrain if ctx['goal'] else None
    specific = specific_bands(ctx['program'], ctx['experience'], volume, ctx['paces'], week.phase,
                              deload=week.deload, terrain=terrain)
    week_index = date.fromisoformat(row.date).isocalendar()[1]
    templates = ranked_templates(category, band, ctx['paces'], phase=week.phase, terrain=terrain,
                                 prefer_time=ctx['user'].workout_format == 'time', week_index=week_index,
                                 program=ctx['program'], specific=specific, weekly_miles=volume)
    from app.core.quality_policy import format_bookends
    from app.core.workout_ladders import program_key
    why = step_note(ctx['program'], ctx['paces'])
    candidates = []
    for template in templates:
        workout = build_workout(template, ctx['paces'], program=program_key(ctx['program']), phase=week.phase,
                                why=why if template.pace_key == 'specific_pace' else '')
        candidates.append((template.family, _as_patch(format_bookends(workout, ctx['paces'], ctx['user'].workout_format))))
    reason = (f"{ctx['experience'].title()} runner, {volume:.0f} mi/week, {week.phase} phase: "
              f"{band.low:.0f}-{band.high:.0f} min of {'threshold' if category == 'threshold' else 'hard'} work, "
              'in three different shapes.')
    reasons = [reason]
    if any(t.specific for t in templates):
        reasons.append('Goal-specific options come first. ' + (why or 'Race-specific work for this phase of your goal.'))
    return candidates, reasons


def _support_candidates(row, week, ctx, poor):
    """A light second stimulus while the athlete earns two substantial sessions."""
    eligible = (not poor and week.phase not in {'taper', 'race_week', 'recovery'} and not week.deload
                and not week.back_to_back and (week.phase_cap is None or week.phase_cap >= 2)
                and ctx['quality'].stage == 'support' and week.hard_count == 1 and not week.has_light_support)
    if not eligible:
        return [], []
    from app.core.quality_policy import light_speed_support
    candidates, families = [], set()
    start = date.fromisoformat(row.date)
    for i in range(12):
        workout = light_speed_support(ctx['paces'], ctx['user'].workout_format, week_start=start + timedelta(weeks=i),
                                      terrain=ctx['goal'].terrain if ctx['goal'] else None)
        family = workout['prescription']['stimulus']
        if family not in families:
            families.add(family)
            candidates.append((family, _as_patch(workout)))
    return candidates, ['Full intervals open up once you reach the two-workout stage. These light sessions fit alongside this week’s main workout.']


def _long_run_candidates(row, week, ctx, poor):
    from app.core.plan_engine import _long_run_structure
    if poor:
        return [], ['Recovery feedback does not support prescribing a long run right now. Choose easy running or rest.']
    if row.b2b or any(r.type == 'long_run' for r in week.others):
        return [], ['Keep one main long run per week. Planned ultra back-to-backs need their coordinated structure.']
    cap = min(week.budget * .35, max(6, ctx['recent_long'] * 1.1))
    if week.phase == 'taper':
        cap = min(cap, 10)
    if week.phase in {'recovery', 'race_week'}:
        cap = min(cap, 6)
    top = math.floor(cap * 2) / 2
    lengths = [m for m in (top, top - 2, top - 4) if m >= max(2, cap * .5)]
    steady_ok = (ctx['program'] in {'marathon', 'half'} and week.phase in {'build', 'peak'} and ctx['quality'].stage == 'dual'
                 and week.hard_count < 1 and ctx['baseline'] >= 40 and not poor)
    from app.core.goal_pace import allows_goal_pace
    # Marathon-pace long runs share the steady-finish readiness gate and the goal-pace phase gate.
    mp_ok = (steady_ok and ctx['program'] == 'marathon' and ctx['paces'].get('specific_pace')
             and allows_goal_pace('marathon', week.phase, deload=week.deload))
    candidates = []
    for miles in lengths:
        patch = {'type': 'long_run', 'distance_miles': miles, 'warmup': None, 'cooldown': None, 'b2b': False,
                 **_long_run_structure(miles, 'easy', ctx['paces'])}
        if ctx['program'] in ULTRA_PROGRAMS:
            from app.core.periodization import week_phase
            from app.core.special_weeks import ultra_long_run
            race_date = date.fromisoformat(ctx['goal'].race_date) if ctx['goal'].race_date else None
            info = week_phase(date.fromisoformat(row.date), 'race', ctx['program'], race_date)
            ultra = ultra_long_run(date.fromisoformat(row.date), ctx['program'], miles / .35, info, ctx['paces'], ctx['goal'].terrain)
            patch.update({k: v for k, v in ultra.items() if k in patch})
        if patch['distance_miles'] > cap + .001:
            continue  # a helper's minimum duration must not override the athlete's dose cap
        patch['prescription'] = json.dumps(day_prescription(patch))
        candidates.append((f'easy-{miles}', patch))
        if mp_ok and miles >= 12 and not any(f.startswith('mp-') for f, _ in candidates):
            for run_type in ('mp_finish', 'mp_block') if week.phase == 'peak' and miles >= 14 else ('mp_finish',):
                mp = copy.deepcopy(patch)
                mp.update(_long_run_structure(miles, run_type, ctx['paces']))
                mp['purpose'] = f"{mp['purpose']} {step_note('marathon', ctx['paces'])}".strip()
                mp['prescription'] = json.dumps(day_prescription(mp))
                candidates.append((f'mp-{run_type}-{miles}', mp))
        if steady_ok and miles >= 12 and not any(f.startswith('steady') for f, _ in candidates):
            steady = copy.deepcopy(patch)
            steady.update(_long_run_structure(miles, 'steady_finish', ctx['paces']))
            steady['prescription'] = json.dumps(day_prescription(steady))
            # Marathon-pace options lead for marathoners; steady stays the half-marathon choice.
            candidates.insert(len(candidates) if mp_ok else 1, (f'steady-{miles}', steady))
    return candidates, ['Long-run length is bounded by your recent longest run, the phase and 35% of this week’s budget (a Stride heuristic).']


@contextmanager
def read_only_trial(plan, db):
    """Validate proposed ORM edits without a savepoint, flush or database write.

    The separate identity map shares the caller's connection/snapshot. Queries
    in the real budget and schedule validators see its edited objects, while
    autoflush is disabled. Closing this rollback-only session leaves the caller's
    transaction and objects untouched, including an acceptance write lock.
    """
    with Session(bind=db.connection(), autoflush=False,
                 join_transaction_mode='rollback_only') as trial:
        trial_plan = trial.get(Plan, plan.id)
        rows = trial.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
        yield trial_plan, rows, trial


def _dry_run(plan, row, ctx, candidates, db):
    """Keep the first valid candidate per family, up to MAX_OPTIONS."""
    from app.api.plans import _fits_week_budget, _validate_schedule
    before = {r.id: snapshot(r) for r in ctx['rows']}
    options, families, seen = [], set(), set()
    for family, patch in candidates:
        if len(options) >= MAX_OPTIONS:
            break
        signature = json.dumps(patch, sort_keys=True)
        if family in families or signature in seen:
            continue
        seen.add(signature)
        with read_only_trial(plan, db) as (trial_plan, trial_rows, trial):
            trial_row = next(r for r in trial_rows if r.id == row.id)
            try:
                if not _fits_week_budget(trial_plan, trial_row, patch['distance_miles'], trial):
                    continue
                for key, value in patch.items():
                    setattr(trial_row, key, value)
                _validate_schedule(trial_plan, trial)
                changes = [{'session_id': r.id, 'date': r.date, 'before': before[r.id], 'replacement': snapshot(r)}
                           for r in trial_rows if snapshot(r) != before[r.id]]
                if not changes:
                    continue
                option_id = hashlib.sha256((ctx['token'] + json.dumps(changes, sort_keys=True)).encode()).hexdigest()
                prescription = _json(patch['prescription'])
                options.append({'id': option_id, 'date': row.date, 'title': patch['title'],
                                'description': patch['description'], 'purpose': patch.get('purpose'),
                                'distance_miles': patch['distance_miles'], 'warmup': patch['warmup'],
                                'cooldown': patch['cooldown'], 'prescription': prescription,
                                'shape': family, 'changes': changes})
                families.add(family)
            except HTTPException:
                pass
    return options


def build_session_options(plan, row, category, db, context=None):
    from app.api.plans import _get_activities_for_date
    locked = (not plan.is_active or row.date < max(date.today().isoformat(), plan.prescribed_from or plan.start_date)
              or row.type == 'race' or row.activity_id or row.moved_to or row.session_status == 'skipped'
              or _get_activities_for_date(row.date, plan.user_id, db))
    if locked:
        raise HTTPException(409, 'Only an unrun current or future session in the approved plan can be changed')
    ctx = context or context_for(plan, db)
    saved_goal = _json(plan.goal_snapshot, {}) or {}
    if ctx['goal'] and saved_goal and (saved_goal.get('type') != ctx['goal'].goal_type
                                       or saved_goal.get('distance') != ctx['goal'].race_distance):
        raise HTTPException(409, 'Your goal changed. Review a revised block before selecting workouts for the new goal.')
    week = _Week(plan, row, ctx, db)
    poor = ctx['evidence']['recent_low_feel'] or ctx['evidence']['recent_failure']
    if category in {'threshold', 'intervals'}:
        candidates, reasons = _quality_candidates(category, row, week, ctx, poor)
        if category == 'intervals' and not candidates:
            support, support_reasons = _support_candidates(row, week, ctx, poor)
            if support:
                candidates, reasons = support, support_reasons
    else:
        candidates, reasons = _long_run_candidates(row, week, ctx, poor)
    options = _dry_run(plan, row, ctx, candidates, db)
    if candidates and not options:
        reasons.append('No option fits the remaining budget, rest preferences and hard-day spacing. Try another day or an easier session.')
    return {'category': category, 'options': options, 'reasons': reasons,
            'quality_stage': ctx['quality'].stage, 'context': ctx['token']}


def apply_option(plan, row, category, option_id, reason, db):
    from app.api.plans import _mark_changed, _validate_schedule
    menu = build_session_options(plan, row, category, db)
    choice = next((o for o in menu['options'] if o['id'] == option_id), None)
    if not choice:
        raise HTTPException(409, 'This option is no longer available. Reload the options using your latest training.')
    for change in choice['changes']:
        target = db.get(PlannedWorkout, change['session_id'])
        if target.id == row.id:
            _mark_changed(target, f'{reason}: chose {choice["title"]}.')
        else:
            _mark_changed(target, f'Shortened to fit {choice["title"]} on {row.date} within this week’s budget.')
        for key, value in change['replacement'].items():
            setattr(target, key, value)
        if target.id == row.id:
            target.session_status = 'replaced'
    db.flush()
    _validate_schedule(plan, db)
    return choice

