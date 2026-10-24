from app.athlete_clock import today as athlete_today
"""Server-authored alternatives: a model selects IDs, never writes prescriptions."""
import copy
import json
import math
from datetime import date

from fastapi import HTTPException

from app.core.workout_data import MI, day_prescription, loads, render
from app.models.plan import PlannedWorkout

FIELDS = ('type', 'title', 'description', 'purpose', 'distance_miles', 'warmup', 'cooldown', 'prescription', 'b2b')


def snapshot(row):
    return {key: getattr(row, key) for key in FIELDS}


def _work_seconds(spec, pace):
    return (spec.get('duration_seconds') or (spec.get('distance_meters') or 0) / MI * pace) * spec['reps']


def _variants(row, paces):
    """Same category and pace, no more work, no shorter rest; retain bookends.

    These are Stride alternatives, not scientifically equivalent stimuli. Reduced
    or reshaped sessions cannot advance a full ladder level through feedback.
    """
    original = loads(row.prescription)
    if not original or len(original['segments']) != 1 or not original.get('warmup') or not original.get('cooldown'):
        return []
    spec = original['segments'][0]
    if original['category'] not in {'threshold', 'intervals', 'speed_support'}:
        return []
    easy = paces.get('long_run_pace', 570)
    pace = (spec.get('pace_range_sec_per_mile') or {}).get('slow') or paces.get('interval_pace', 420)
    alternatives = []
    if spec['reps'] > 1:
        shorter = copy.deepcopy(spec)
        shorter['reps'] -= 1
        alternatives.append(('Less work', shorter))
    if original['category'] == 'threshold' and spec.get('duration_seconds') and not spec.get('recovery_meters'):
        broken = copy.deepcopy(spec)
        broken['reps'] += 1
        broken['duration_seconds'] = math.floor(spec['duration_seconds'] * spec['reps'] / broken['reps'] / 30) * 30
        broken['recovery_seconds'] = max(spec.get('recovery_seconds') or 0, 120)
        if broken['duration_seconds'] >= 120:
            alternatives.append(('Shorter repetitions', broken))
    result = []
    for label, work in alternatives:
        data = copy.deepcopy(original)
        data['segments'] = [work]
        if data['format'] == 'continuous' and work['reps'] > 1:
            data['format'] = 'time_intervals'
        data['progression_eligible'] = False
        data['evidence_source'] = 'validated_coaching_alternative'
        data['note'] = (original.get('note') or '') + ' Alternative dose; hold the ladder level. Do not race this session.'
        def miles(s):
            return (s.get('distance_meters') or 0) / MI + (s.get('duration_seconds') or 0) / easy
        work_miles = (work.get('distance_meters') / MI if work.get('distance_meters') else work['duration_seconds'] / pace) * work['reps']
        recovery = (work['reps'] - 1) * ((work.get('recovery_seconds') or 0) / easy + (work.get('recovery_meters') or 0) / MI)
        total = math.ceil((miles(data['warmup']) + miles(data['cooldown']) + work_miles + recovery) * 2) / 2
        if total > row.distance_miles or _work_seconds(work, pace) > _work_seconds(spec, pace):
            continue
        data['total_distance_meters'] = round(total * MI, 2)
        replacement = snapshot(row)
        replacement.update(title=f'{label}: {render({**data, "note": None}).rstrip(".")}'[:200], description=render(data),
                           purpose='Same training category at a bounded dose; selected after reviewing recovery.',
                           distance_miles=total, prescription=json.dumps(data), b2b=False)
        result.append(replacement)
    return result


def build_options(plan, db):
    """Dry-run every candidate through the SAME validator used on acceptance.

    Isolated identity maps validate proposed rows without writing to SQLite.
    GET requests must never acquire a writer lock while listing alternatives.
    """
    from app.api.plans import _get_activities_for_date, _validate_schedule
    from app.services.session_options import read_only_trial
    candidates = []
    paces = json.loads(plan.training_paces or '{}')
    rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id).order_by(PlannedWorkout.date).all()
    for row in rows:
        if (row.date < max(athlete_today().isoformat(), plan.prescribed_from or plan.start_date)
                or row.type != 'workout' or row.activity_id or row.moved_to
                or row.session_status in {'skipped', 'moved'}
                or _get_activities_for_date(row.date, plan.user_id, db)):
            continue
        before = snapshot(row)
        replacements = _variants(row, paces)
        easy = snapshot(row)
        easy.update(type='easy', title='Easy Run', description='Conversational effort, truly easy.',
                    purpose='Recovery instead of quality work.', distance_miles=min(row.distance_miles, 6),
                    warmup=None, cooldown=None, b2b=False)
        easy['prescription'] = json.dumps(day_prescription(easy))
        rest = snapshot(row)
        rest.update(type='rest', title='Rest Day', description='Rest and recover.', purpose='Recovery.',
                    distance_miles=0, warmup=None, cooldown=None, b2b=False)
        rest['prescription'] = json.dumps(day_prescription(rest))
        replacements.extend([easy, rest])
        for replacement in replacements:
            with read_only_trial(plan, db) as (trial_plan, trial_rows, trial):
                trial_row = next(r for r in trial_rows if r.id == row.id)
                try:
                    for key, value in replacement.items():
                        setattr(trial_row, key, value)
                    _validate_schedule(trial_plan, trial)
                    candidates.append({'id': f'option-{len(candidates)+1}', 'date': row.date,
                                       'session_id': row.id, 'before': before,
                                       'replacement': replacement})
                except HTTPException:
                    pass
        if len(candidates) >= 16:
            break
    # The same personalized menu powers manual choices and model suggestions.
    # Include easy-to-quality options only when earned weekly slots allow them.
    from app.services.session_options import build_session_options, context_for
    context = context_for(plan, db)
    targets = [r for r in rows if r.date >= max(athlete_today().isoformat(), plan.prescribed_from or plan.start_date)
               and r.type in {'easy','workout'} and not r.activity_id and not r.moved_to
               and not _get_activities_for_date(r.date,plan.user_id,db)][:3]
    for target in targets:
        for category in ('threshold','intervals'):
            try:
                menu = build_session_options(plan,target,category,db,context)
            except HTTPException:
                continue
            # Menus already hold at most three distinct shapes; offer all of them.
            for option in menu['options']:
                change = next(c for c in option['changes'] if c['session_id']==target.id)
                candidates.append({'id':'choice-'+option['id'],'date':target.date,'session_id':target.id,
                    'before':change['before'],'replacement':change['replacement'],'category':category,
                    'session_option_id':option['id'],'changes':option['changes']})
    return candidates[:24]
