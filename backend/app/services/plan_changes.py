"""Plain-language plan changes: request → proposal → athlete approval → audit and undo.

The AI (``plan_change_ai``) only translates the athlete's words into constraints and ops.
Everything that decides is here and in ``core/request_ops``: a deterministic safety screen,
the same schedule validator every other edit uses, the feature's own rules, and a
rules-only solver that works without the AI. See docs/plain-language-plan-changes.md.
"""
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.athlete_clock import day_start_utc, today as athlete_today
from app.config import settings
from app.core.request_ops import (CONTENT, DAY_NAMES, REDUCING, OpError, apply_ops, hard_adjacency,
                                  request_violations, solve)
from app.models.coaching import CoachingReview
from app.models.plan import Plan, PlannedWorkout
from app.models.plan_change import PlanChangeRequest
from app.models.user import User

logger = logging.getLogger('stride.plan_changes')

WINDOW_DAYS = 14
MAX_TEXT = 500
MAX_CLARIFY_ROUNDS = 2

# Deterministic pre-screen, before any model call. The model may only tighten it.
RED_FLAGS = re.compile(r"\b(chest (pain|tight\w*)|faint\w*|passed out|black(ed)? out|short(ness)? of breath|can'?t breathe|"
                       r"heart (racing|palpitation\w*)|palpitation\w*|collaps\w*)\b", re.I)
INJURY = re.compile(r"\b(pain\w*|injur\w*|sprain\w*|strain\w*|stress fracture|fracture\w*|tendon\w*|tendinitis|shin ?splints?|"
                    r"achilles|it ?band|plantar|limp\w*|swollen|swelling|hurt\w*|tweak\w*|niggle\w*)\b", re.I)
ILLNESS = re.compile(r"\b(sick|ill|illness|fever\w*|flu|covid|cold|virus|vomit\w*|nause\w*|stomach bug|food poisoning|"
                     r"sore throat|congest\w*|chills)\b", re.I)
SAFETY_RANK = {'none': 0, 'illness': 1, 'injury': 2, 'red_flag': 3}


def normalize_text(text: str | None) -> str:
    return ' '.join((text or '').split())[:MAX_TEXT]


def screen(text: str) -> str:
    if RED_FLAGS.search(text):
        return 'red_flag'
    if INJURY.search(text):
        return 'injury'
    if ILLNESS.search(text):
        return 'illness'
    return 'none'


def tighten(screened: str, model_safety: str | None) -> str:
    """The model's reading can only make the safety level stricter, never looser."""
    return max(screened, model_safety or 'none', key=lambda s: SAFETY_RANK.get(s, 0))


# ---------------------------------------------------------------- the editable window

def _rows(plan: Plan, db):
    return db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()


def _ran(plan: Plan, db) -> set[str]:
    from app.api.plans import _activities_by_date
    return set(_activities_by_date(plan.user_id, plan.start_date, plan.end_date, db))


def _day(row: PlannedWorkout, editable: bool) -> dict:
    data = {k: getattr(row, k) for k in CONTENT}
    data['prescription'] = json.loads(row.prescription) if row.prescription else None
    data['b2b'] = bool(row.b2b)
    return data | {'date': row.date, 'week_number': row.week_number, 'editable': editable, 'id': row.id}


def window(plan: Plan, db) -> tuple[list[dict], str, str]:
    """Every plan day, with ``editable`` set for unrun, non-race days from today through 13 days ahead."""
    first = max(athlete_today().isoformat(), plan.prescribed_from or plan.start_date)
    last = min(plan.end_date, (athlete_today() + timedelta(days=WINDOW_DAYS - 1)).isoformat())
    ran = _ran(plan, db)
    days = [_day(r, first <= r.date <= last and r.date not in ran and not r.activity_id and r.type != 'race')
            for r in _rows(plan, db)]
    return days, first, last


def _rest_days(plan: Plan, user: User) -> set[str]:
    schedule = json.loads(plan.athlete_snapshot or '{}').get('schedule_preferences')
    rest = schedule['rest_days'] if schedule is not None else (user.rest_days or '').split(',')
    return {d.strip() for d in rest if d.strip() in DAY_NAMES}


def _phases(plan: Plan) -> dict[int, str]:
    phases = json.loads(plan.phases or '[]')
    return {i + 1: (p.get('phase') if isinstance(p, dict) else p) or 'general' for i, p in enumerate(phases)}


def _easy_pace(plan: Plan) -> float:
    return json.loads(plan.athlete_snapshot or '{}').get('easy_pace_seconds') or 600


def _last_long_run(plan: Plan, first_editable: str, db) -> str | None:
    """The latest long run actually run before the editable window (this plan or the previous one)."""
    from app.api.plans import _get_activities_for_date
    rows = (db.query(PlannedWorkout).join(Plan).filter(Plan.user_id == plan.user_id, PlannedWorkout.type == 'long_run',
                                                       PlannedWorkout.date < first_editable,
                                                       PlannedWorkout.date >= (date.fromisoformat(first_editable) - timedelta(days=10)).isoformat())
            .order_by(PlannedWorkout.date.desc()).all())
    for row in rows:
        if row.activity_id or _get_activities_for_date(row.date, plan.user_id, db):
            return row.date
    return None


def _prior_hard(plan: Plan, db) -> set[str]:
    from app.api.plans import _activities_by_date, _is_hard_activity
    from app.services.analyzer import analyze_athlete
    load = json.loads(plan.load or '{}')
    baseline = load.get('baseline') or json.loads(plan.athlete_snapshot or '{}').get('current_weekly_mileage')
    if baseline is None:
        baseline = analyze_athlete(plan.user_id, db).get('current_fitness', {}).get('weekly_mileage_4w_avg', 0)
    before = (date.fromisoformat(plan.start_date) - timedelta(days=1)).isoformat()
    acts = _activities_by_date(plan.user_id, before, plan.start_date, db)
    return {d for d, runs in acts.items() if d < plan.start_date and any(_is_hard_activity(a, baseline) for a in runs)}


def fingerprint(plan: Plan, user: User, db, days: list[dict] | None = None) -> str:
    days = days if days is not None else window(plan, db)[0]
    data = {'today': athlete_today().isoformat(), 'plan': plan.id, 'rest': sorted(_rest_days(plan, user)),
            'limits': user.day_time_budgets,
            'days': [{k: d.get(k) for k in ('date', 'type', 'title', 'distance_miles', 'editable')} for d in days]}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def context(plan: Plan, user: User, db) -> dict:
    days, first, last = window(plan, db)
    return {'days': days, 'first': first, 'last': last, 'rest_days': _rest_days(plan, user), 'phases': _phases(plan),
            'last_long_run': _last_long_run(plan, first, db), 'easy_pace': _easy_pace(plan),
            'prior_hard': _prior_hard(plan, db)}


# ---------------------------------------------------------------- checking a proposal

def valid_constraints(raw: list[dict], ctx: dict) -> list[dict]:
    """Keep constraints inside the editable window, in Stride's own shape."""
    editable = {d['date'] for d in ctx['days'] if d['editable']}
    out = []
    for c in raw or []:
        if c.get('date') in editable and c.get('kind') in {'no_run', 'no_hard', 'max_minutes', 'prefer_rest'}:
            minutes = c.get('minutes')
            if c['kind'] == 'max_minutes' and not (isinstance(minutes, int) and 0 < minutes <= 600):
                continue
            item = {'date': c['date'], 'kind': c['kind'], 'minutes': minutes if c['kind'] == 'max_minutes' else None}
            if item not in out:
                out.append(item)
    return out[:8]


def _validate_in_trial(plan: Plan, after: list[dict], touched: set[str], db) -> list[dict]:
    """Write the result onto a rollback-only copy and run the same validator every edit uses."""
    from app.api.plans import _session_minutes, _validate_schedule
    from app.services.session_options import read_only_trial
    by_date = {d['date']: d for d in after}
    with read_only_trial(plan, db) as (trial_plan, trial_rows, trial):
        changed = {}
        for row in trial_rows:
            if row.date in touched:
                changed[row.id] = _session_minutes(trial_plan, row)
                for key in CONTENT:
                    value = by_date[row.date][key]
                    setattr(row, key, json.dumps(value) if key == 'prescription' and value is not None else value)
        try:
            _validate_schedule(trial_plan, trial, changed=changed)
        except HTTPException as exc:
            return [{'code': 'schedule_rule', 'date': None, 'message': part.strip()} for part in str(exc.detail).split(';')]
    return []


def evaluate(plan: Plan, ctx: dict, ops: list[dict], constraints: list[dict], db, *, reduce_only: bool = False):
    """Apply ``ops`` and run every check. Returns (after_days, reasons); empty reasons means it passes."""
    try:
        after = apply_ops(ctx['days'], ops)
    except OpError as exc:
        return None, [exc.reason]
    if reduce_only and any(o['op'] not in REDUCING for o in ops):
        return None, [{'code': 'reduce_only', 'date': ops[0]['date'],
                       'message': 'While you are unwell or hurt, sessions can only be eased, shortened or skipped.'}]
    touched = {o['date'] for o in ops} | {o['target_date'] for o in ops if o.get('target_date')}
    reasons = request_violations(ctx['days'], after, ops, phases=ctx['phases'], last_long_run=ctx['last_long_run'],
                                 constraints=constraints, easy_pace=ctx['easy_pace'], reduce_only=reduce_only)
    reasons += [r for r in hard_adjacency(after, ctx['prior_hard']) if r['date'] in touched
                or (date.fromisoformat(r['date']) - timedelta(days=1)).isoformat() in touched]
    if not reasons:
        reasons = _validate_in_trial(plan, after, touched, db)
    return after, reasons


def solver_proposal(plan: Plan, ctx: dict, constraints: list[dict], db, *, reduce_only: bool = False):
    """Rules-only path: the first solver candidate that also passes the database validator."""
    if not constraints:
        return None, []
    tried = []
    for ops in solve(ctx['days'], constraints, rest_days=ctx['rest_days'], phases=ctx['phases'],
                     last_long_run=ctx['last_long_run'], prior_hard=ctx['prior_hard'],
                     easy_pace=ctx['easy_pace'], reduce_only=reduce_only):
        after, reasons = evaluate(plan, ctx, ops, constraints, db, reduce_only=reduce_only)
        if not reasons:
            return ops, []
        tried.extend(reasons)
    # Nothing satisfied the request: the safest honest answer may still be "skip those days".
    fallback = [{'op': 'skip', 'date': c['date']} for c in constraints if c['kind'] == 'no_run']
    fallback += [{'op': 'easy', 'date': c['date']} for c in constraints if c['kind'] == 'no_hard'
                 and any(d['date'] == c['date'] and d['type'] in {'workout', 'long_run'} for d in ctx['days'])]
    if fallback:
        after, reasons = evaluate(plan, ctx, fallback, constraints, db, reduce_only=reduce_only)
        if not reasons:
            return fallback, []
        tried.extend(reasons)
    return None, tried


def diff(ctx: dict, after: list[dict]) -> list[dict]:
    before = {d['date']: d for d in ctx['days']}
    out = []
    for d in after:
        old = before[d['date']]
        if any(old.get(k) != d.get(k) for k in ('type', 'title', 'distance_miles')):
            out.append({'date': d['date'], 'day': DAY_NAMES[date.fromisoformat(d['date']).weekday()],
                        'before': {k: old.get(k) for k in ('type', 'title', 'distance_miles')},
                        'after': {k: d.get(k) for k in ('type', 'title', 'distance_miles')}})
    return out


def summary_lines(ctx: dict, after: list[dict]) -> list[str]:
    from app.core.change_guard import summarize_change
    weeks = sorted({d['week_number'] for d in after if d['editable']})

    def shaped(days):
        return [{'week_number': w, 'days': [d for d in days if d['week_number'] == w]} for w in weeks]
    return summarize_change(shaped(ctx['days']), shaped(after))


CHECKS = ['No two hard days in a row', 'Weekly mileage not increased', 'No workout added',
          'Long runs at least 5 days apart', 'Rest days and daily time limits respected']


# ---------------------------------------------------------------- quota

def _check_quota(user_id: int, db) -> None:
    used = db.query(func.coalesce(func.sum(PlanChangeRequest.attempts), 0)).filter(
        PlanChangeRequest.user_id == user_id, PlanChangeRequest.created_at >= day_start_utc(),
        PlanChangeRequest.model.is_not(None)).scalar()
    if used >= settings.openai_plan_change_daily_limit:
        raise HTTPException(429, f'Daily limit for AI plan changes reached ({used} of {settings.openai_plan_change_daily_limit}); '
                                 'it resets at midnight. The quick picker still works.')
    utc_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    shared = (db.query(func.coalesce(func.sum(CoachingReview.attempts), 0)).filter(
                  CoachingReview.created_at >= utc_day, CoachingReview.model.is_not(None)).scalar()
              + db.query(func.coalesce(func.sum(PlanChangeRequest.attempts), 0)).filter(
                  PlanChangeRequest.created_at >= utc_day, PlanChangeRequest.model.is_not(None)).scalar())
    if shared >= settings.openai_coach_global_daily_limit:
        raise HTTPException(429, 'The app AI budget is reached for today. The quick picker still works.')
    from app.services import ai_budget
    ai_budget.check(user_id, db)


def remaining_today(user_id: int, db) -> int:
    used = db.query(func.coalesce(func.sum(PlanChangeRequest.attempts), 0)).filter(
        PlanChangeRequest.user_id == user_id, PlanChangeRequest.created_at >= day_start_utc(),
        PlanChangeRequest.model.is_not(None)).scalar()
    return max(0, settings.openai_plan_change_daily_limit - used)


def ai_available(user: User) -> bool:
    return bool(settings.openai_api_key) and bool(user.ai_consent)


# ---------------------------------------------------------------- the request lifecycle

def serialize(row: PlanChangeRequest, db=None) -> dict:
    proposal = json.loads(row.proposal or '{}')
    return {'id': row.id, 'status': row.status, 'source': row.source, 'safety': row.safety,
            'request_text': row.request_text, 'thread': json.loads(row.thread or '[]'),
            'understood': proposal.get('understood'), 'constraints': proposal.get('constraints', []),
            'ops': proposal.get('ops', []), 'changes': proposal.get('changes', []),
            'summary': proposal.get('summary', []), 'checks': proposal.get('checks', []),
            'explanation': proposal.get('explanation'), 'question': proposal.get('question'),
            'choices': proposal.get('choices', []), 'reasons': proposal.get('reasons', []),
            'note': proposal.get('note'),
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'applied_at': row.applied_at.isoformat() if row.applied_at else None,
            'undone_at': row.undone_at.isoformat() if row.undone_at else None}


def _active(user_id: int, db) -> tuple[User, Plan]:
    user = db.get(User, user_id)
    plan = db.query(Plan).filter_by(user_id=user_id, is_active=True).first()
    if not user or not plan:
        raise HTTPException(404, 'No active plan')
    return user, plan


SAFETY_NOTES = {
    'illness': "Being sick or run down is a reason to back off, never to push through. I can only ease, shorten or skip "
               "sessions while you recover. If it's above the neck and mild, an easy jog is usually fine; with a fever or "
               "anything in your chest, rest.",
    'injury': "Pain that changes how you run is a reason to stop, not adapt. I can only ease, shorten or skip sessions "
              "until it settles. If it's sharp, swelling, or still there when you walk, get it checked.",
    'red_flag': "Chest pain, fainting or breathlessness at rest need a medical check before any running. Please stop and "
                "see a medical professional. I can skip your next few days so nothing is waiting for you.",
}


def _finish(row: PlanChangeRequest, plan: Plan, ctx: dict, *, kind: str, understood: str | None, constraints: list[dict],
            ops: list[dict] | None, explanation: str | None, reasons: list[dict], source: str, db,
            question: str | None = None, choices: list[str] | None = None) -> PlanChangeRequest:
    proposal = {'understood': understood, 'constraints': constraints, 'explanation': explanation,
                'reasons': [r['message'] for r in reasons][:6]}
    if row.safety != 'none':
        proposal['note'] = SAFETY_NOTES[row.safety]
    if kind == 'clarify':
        row.status = 'clarifying'
        proposal.update(question=question, choices=choices or [])
    elif kind in {'out_of_scope', 'no_change'}:
        row.status = kind
    elif ops:
        after, _ = evaluate(plan, ctx, ops, constraints, db, reduce_only=row.safety != 'none')
        row.status, row.source = 'proposed', source
        proposal.update(ops=ops, changes=diff(ctx, after), summary=summary_lines(ctx, after), checks=CHECKS)
    else:
        row.status = 'no_safe_change'
    row.proposal = json.dumps(proposal, default=str)
    return row


def create(user_id: int, text: str, db, *, constraints: list[dict] | None = None, answer_to: int | None = None) -> dict:
    """Make (or continue) a request and return its proposal. ``constraints`` = the no-AI quick picker."""
    from app.services import plan_change_ai
    user, plan = _active(user_id, db)
    text = normalize_text(text)
    if not text and not constraints:
        raise HTTPException(422, 'Tell me what is coming up, or pick days in the quick picker.')
    ctx = context(plan, user, db)
    print_ = fingerprint(plan, user, db, ctx['days'])
    if answer_to:
        row = db.get(PlanChangeRequest, answer_to)
        if not row or row.user_id != user_id or row.status != 'clarifying':
            raise HTTPException(409, 'That question is no longer open.')
        thread = json.loads(row.thread or '[]')
        thread.append({'q': json.loads(row.proposal or '{}').get('question'), 'a': text})
        row.thread = json.dumps(thread)
        row.plan_fingerprint = print_
    else:
        # Same words, same plan, same day: reuse the stored result for free.
        if text and not constraints:
            cached = (db.query(PlanChangeRequest).filter_by(user_id=user_id, plan_id=plan.id, request_text=text,
                                                            plan_fingerprint=print_)
                      .filter(PlanChangeRequest.status.in_(('proposed', 'no_safe_change', 'out_of_scope', 'no_change', 'safety')))
                      .order_by(PlanChangeRequest.id.desc()).first())
            if cached:
                return serialize(cached) | {'cached': True}
        row = PlanChangeRequest(user_id=user_id, plan_id=plan.id, request_text=text or 'Quick picker',
                                status='working', plan_fingerprint=print_, thread='[]', rejections='[]',
                                attempts=0, input_tokens=0, output_tokens=0)
        db.add(row)
    full_text = ' '.join([row.request_text] + [t['a'] for t in json.loads(row.thread or '[]')])
    row.safety = screen(full_text)

    if row.safety == 'red_flag':
        skip = [{'op': 'skip', 'date': d['date']} for d in ctx['days'] if d['editable'] and d['distance_miles'] > 0][:3]
        row.status = 'safety'
        row.proposal = json.dumps({'note': SAFETY_NOTES['red_flag'], 'ops': skip, 'understood': None, 'constraints': []})
        db.commit()
        return serialize(row)

    if constraints is not None:  # the quick picker: rules only, no model call
        picked = valid_constraints(constraints, ctx)
        ops, reasons = solver_proposal(plan, ctx, picked, db, reduce_only=row.safety != 'none')
        _finish(row, plan, ctx, kind='proposal', understood=_describe(picked), constraints=picked, ops=ops,
                explanation=_solver_explanation(ops, ctx) if ops else None, reasons=reasons, source='picker', db=db)
        row.rejections = json.dumps(reasons)
        db.commit()
        return serialize(row)

    if not ai_available(user):
        row.status = 'ai_unavailable'
        row.proposal = json.dumps({'reasons': ['AI plan changes need an OpenAI key and your consent to AI coaching. '
                                               'Use the quick picker below instead.']})
        db.commit()
        return serialize(row)

    _check_quota(user_id, db)
    rejections = json.loads(row.rejections or '[]')
    cons, result = [], None
    clarify_rounds = len(json.loads(row.thread or '[]'))
    previous = None
    for attempt in range(2):  # the first answer plus one retry with the rule failures
        row.model = settings.openai_plan_change_model or settings.openai_coach_model
        row.attempts += 1
        db.commit()  # count the attempt before the network call; no lock held across it
        try:
            result, usage = plan_change_ai.request(plan_change_ai.slim_context(ctx, user, row, previous))
        except Exception as exc:  # deliberately not str(exc): provider errors can echo inputs
            logger.warning('AI plan change unavailable (%s)', type(exc).__name__)
            result, usage = None, {}
        row = db.get(PlanChangeRequest, row.id)
        row.input_tokens += usage.get('input_tokens', 0)
        row.output_tokens += usage.get('output_tokens', 0)
        if result is None:
            break
        row.safety = tighten(row.safety, result.safety)
        if row.safety == 'red_flag':
            row.status = 'safety'
            row.proposal = json.dumps({'note': SAFETY_NOTES['red_flag'], 'ops': [], 'understood': result.understood, 'constraints': []})
            db.commit()
            return serialize(row)
        cons = valid_constraints([c.model_dump() for c in result.constraints], ctx)
        if result.kind == 'clarify' and clarify_rounds < MAX_CLARIFY_ROUNDS and result.question:
            _finish(row, plan, ctx, kind='clarify', understood=result.understood, constraints=cons, ops=None,
                    explanation=None, reasons=[], source='ai', db=db, question=result.question, choices=result.choices[:3])
            db.commit()
            return serialize(row)
        if result.kind in {'out_of_scope', 'no_change'}:
            _finish(row, plan, ctx, kind=result.kind, understood=result.understood, constraints=cons, ops=None,
                    explanation=result.explanation, reasons=[], source='ai', db=db)
            db.commit()
            return serialize(row)
        ops = [o.model_dump(exclude_none=True) for o in result.ops]
        after, reasons = evaluate(plan, ctx, ops, cons, db, reduce_only=row.safety != 'none')
        if not reasons and ops:
            _finish(row, plan, ctx, kind='proposal', understood=result.understood, constraints=cons, ops=ops,
                    explanation=result.explanation, reasons=[], source='ai' if attempt == 0 else 'ai_retry', db=db)
            row.rejections = json.dumps(rejections)
            db.commit()
            return serialize(row)
        rejections.extend(reasons or [{'code': 'no_ops', 'date': None, 'message': 'No changes were proposed.'}])
        previous = {'ops': ops, 'reasons': [r['message'] for r in reasons][:6]}
        try:
            _check_quota(user_id, db)
        except HTTPException:
            break
    # The model couldn't produce a passing proposal: the rules-only solver works from its constraints.
    understood = result.understood if result else None
    ops, reasons = solver_proposal(plan, ctx, cons, db, reduce_only=row.safety != 'none')
    rejections.extend(reasons)
    row.rejections = json.dumps(rejections)
    _finish(row, plan, ctx, kind='proposal', understood=understood, constraints=cons, ops=ops,
            explanation=_solver_explanation(ops, ctx) if ops else None,
            reasons=rejections if not ops else [], source='solver', db=db)
    db.commit()
    return serialize(row)


def _label(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DAY_NAMES[d.weekday()].title()} {d.strftime('%b')} {d.day}"


def _describe(constraints: list[dict]) -> str | None:
    words = {'no_run': 'no running', 'no_hard': 'nothing hard', 'prefer_rest': 'rest if possible', 'max_minutes': 'at most {m} min'}
    parts = [f"{_label(c['date'])}: {words[c['kind']].format(m=c.get('minutes'))}" for c in constraints]
    return '; '.join(parts) or None


def _solver_explanation(ops: list[dict] | None, ctx: dict) -> str | None:
    if not ops:
        return None
    by_date = {d['date']: d for d in ctx['days']}
    parts = []
    for o in ops:
        if o['op'] == 'swap':
            parts.append(f"{by_date[o['date']]['title']} and {by_date[o['target_date']]['title']} trade days")
        elif o['op'] == 'move':
            parts.append(f"{by_date[o['date']]['title']} moves to {_label(o['target_date'])}")
        elif o['op'] == 'easy':
            parts.append(f"{_label(o['date'])} becomes an easy run")
        elif o['op'] == 'skip':
            parts.append(f"{_label(o['date'])} becomes rest")
        elif o['op'] == 'shorten':
            parts.append(f"{_label(o['date'])} drops to {o['miles']:g} mi")
    return ('Rearranged by Stride\'s rules: ' + '; '.join(parts) + '. Hard days stay apart, and the week never gets bigger.')


def _snapshot(row: PlannedWorkout) -> dict:
    from app.api.plans import _snapshot as snap
    return json.loads(snap(row))


def apply(user_id: int, request_id: int, db) -> dict:
    from app.api.plans import _begin_schedule_write, _mark_changed
    _begin_schedule_write(db)
    row = db.get(PlanChangeRequest, request_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, 'Request not found')
    if row.status not in {'proposed', 'safety'}:
        raise HTTPException(409, 'This proposal can no longer be applied.')
    user, plan = _active(user_id, db)
    ctx = context(plan, user, db)
    if plan.id != row.plan_id or fingerprint(plan, user, db, ctx['days']) != row.plan_fingerprint:
        row.status = 'stale'
        db.commit()
        raise HTTPException(409, 'Your plan changed since this was suggested. Ask again for an up-to-date proposal.')
    proposal = json.loads(row.proposal or '{}')
    ops = proposal.get('ops') or []
    if not ops:
        raise HTTPException(409, 'Nothing to apply.')
    # Re-run the full validation under the write lock: the diff approved is exactly what is saved.
    after, reasons = evaluate(plan, ctx, ops, proposal.get('constraints', []), db, reduce_only=row.safety != 'none')
    if reasons:
        row.status = 'stale'
        db.commit()
        raise HTTPException(409, 'That change no longer passes the training rules: ' + '; '.join(r['message'] for r in reasons[:3]))
    touched = {o['date'] for o in ops} | {o['target_date'] for o in ops if o.get('target_date')}
    by_date = {d['date']: d for d in after}
    before, after_rows = {}, {}
    note = f"Your request #{row.id}: {proposal.get('understood') or row.request_text}"[:500]
    try:
        for pw in _rows(plan, db):
            if pw.date not in touched:
                continue
            before[pw.id] = _snapshot(pw) | {'original_prescription': pw.original_prescription,
                                             'adjustment_note': pw.adjustment_note}
            _mark_changed(pw, note)
            for key in CONTENT:
                value = by_date[pw.date][key]
                setattr(pw, key, json.dumps(value) if key == 'prescription' and value is not None else value)
            after_rows[pw.id] = _snapshot(pw)
        db.flush()
        row.before_rows, row.after_rows = json.dumps(before), json.dumps(after_rows)
        row.status, row.applied_at = 'applied', datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return serialize(row)


def undo(user_id: int, request_id: int, db) -> dict:
    from app.api.plans import _begin_schedule_write, _get_activities_for_date, _session_minutes, _validate_schedule
    _begin_schedule_write(db)
    row = db.get(PlanChangeRequest, request_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, 'Request not found')
    if row.status != 'applied':
        raise HTTPException(409, 'Only an applied change can be undone.')
    before, after = json.loads(row.before_rows or '{}'), json.loads(row.after_rows or '{}')
    today = athlete_today().isoformat()
    rows = {str(r.id): r for r in db.query(PlannedWorkout).filter(PlannedWorkout.id.in_([int(i) for i in before])).all()}
    for rid, snap in after.items():
        pw = rows.get(rid)
        if pw is None:
            raise HTTPException(409, 'That week has been replaced by a new block, so there is nothing to undo.')
        if _snapshot(pw) != snap:
            raise HTTPException(409, f'{_label(pw.date)} has changed since, so undo would overwrite a newer edit.')
        if pw.date < today or pw.activity_id or _get_activities_for_date(pw.date, user_id, db):
            raise HTTPException(409, f'{_label(pw.date)} is already run or past, so the change stays.')
    plan = db.get(Plan, row.plan_id)
    try:
        # Time limits judge only what undo adds back beyond the current (approved) days.
        current = {r.id: _session_minutes(plan, r) for r in rows.values()}
        for rid, snap in before.items():
            for key, value in snap.items():
                setattr(rows[rid], key, value)
        db.flush()
        _validate_schedule(plan, db, changed=current)
        row.status, row.undone_at = 'undone', datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return serialize(row)


def discard(user_id: int, request_id: int, db) -> dict:
    row = db.get(PlanChangeRequest, request_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, 'Request not found')
    if row.status in {'proposed', 'clarifying', 'no_safe_change', 'safety', 'out_of_scope', 'no_change', 'ai_unavailable'}:
        row.status = 'declined'
        db.commit()
    return serialize(row)


def history(user_id: int, db, limit: int = 10) -> list[dict]:
    rows = (db.query(PlanChangeRequest).filter_by(user_id=user_id).order_by(PlanChangeRequest.id.desc()).limit(limit).all())
    return [serialize(r) for r in rows]
