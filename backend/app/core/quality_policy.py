"""Deterministic quality selection. Personal coaching heuristics, not cutoffs proven safe.

The Long Game dossier describes a threshold + light speed-support rebuild before
returning to two substantial workouts. A past PR alone does not establish readiness.
"""
from dataclasses import dataclass
import math

from app.core.workout_data import MI, prescription, render, segment


@dataclass(frozen=True)
class QualityPolicy:
    stage: str  # single | support | dual
    reason: str
    criteria: list
    evidence: dict

    @property
    def light_second(self):
        return self.stage == 'support'

    @property
    def sessions(self):
        return 2 if self.stage in {'support', 'dual'} else 1

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self) | {'sessions': self.sessions}


def select_quality_policy(goal_type, experience, days_per_week, weekly_miles, weekly_run_days,
                          recent_long_run_miles, assessment=None, fatigue=False, evidence=None):
    from app.core.experience import experience_policy, experienced
    evidence = evidence or {}
    policy = experience_policy(experience)
    history = weekly_miles[-4:]
    baseline = sum(history)/4 if len(history)==4 else 0
    run_days = (evidence.get('weekly_run_days') or weekly_run_days)[-policy.stable_weeks:]
    recovery_ok = (evidence.get('recovery_days',0)>=3 and (evidence.get('recovery_average') or 0)>=6
                   and not evidence.get('recent_low_feel') and not evidence.get('recent_failure'))
    support_ready = (days_per_week>=5 and len(history)==4 and min(history)>=15
                     and history[-1]>= (30 if experienced(experience) else 25)
                     and history[-1]<=1.35*baseline and len(weekly_run_days)>=2
                     and min(weekly_run_days[-2:])>=4 and recent_long_run_miles>=8
                     and evidence.get('primary_successes',0)>=policy.support_primary_days)
    stable = (len(weekly_miles)>=policy.stable_weeks
              and min(weekly_miles[-policy.stable_weeks:])>=policy.dual_weekly_miles*.75
              and len(run_days)>=policy.stable_weeks and min(run_days)>=5
              and baseline>=policy.dual_weekly_miles
              and .9*baseline<=weekly_miles[-1]<=1.2*baseline)
    established = evidence.get('dual_weeks',0)>=2
    dual_evidence = (evidence.get('primary_successes',0)>=policy.dual_primary_days
                     and evidence.get('recent_primary_successes',0)>=1
                     and ((evidence.get('support_successes',0)>=policy.dual_support_days and evidence.get('recent_support_successes',0)>=1) or established))
    criteria = [
        {'label':'Schedule supports two sessions', 'met':days_per_week>=5},
        {'label':f'{policy.stable_weeks} consistent completed weeks', 'met':stable},
        {'label':'Quality sessions completed with rep evidence', 'met':dual_evidence},
        {'label':'Long run completed and recovered well', 'met':evidence.get('long_run_successes',0)>=1 and (evidence.get('latest_long_run_feel') or 0)>=6},
        {'label':'Recent recovery feedback supports progression', 'met':recovery_ok},
    ]
    if goal_type=='comeback' or fatigue or assessment in {'hold','reduce','recovery'} or evidence.get('recent_failure') or evidence.get('recent_low_feel'):
        return QualityPolicy('single','Recovery or interrupted training takes priority; consolidate with at most one quality session.',criteria,evidence)
    if goal_type in {'mileage','race'} and all(c['met'] for c in criteria):
        return QualityPolicy('dual','Completed quality, consistent volume and recovery support two substantial goal-specific sessions. Repeat volume when introducing the second hard session.',criteria,evidence)
    if support_ready:
        return QualityPolicy('support','Threshold plus a light second stimulus. Complete this work and log recovery to earn two substantial sessions.',criteria,evidence)
    return QualityPolicy('single','Build repeatable training and demonstrate one controlled quality session before adding a second stimulus.',criteria,evidence)


# These are authored Stride doses inspired by the sources in docs/research/
# secondary-session-variety.md, not experimentally equivalent training loads.
# (id, name, family, reps, seconds, meters, recovery seconds, effort guidance)
SUPPORT_SESSIONS = (
    ('fartlek_60', '8x1min Light Fartlek', 'fartlek', 8, 60, None, 60,
     'Controlled faster aerobic effort, never all-out; keep every repetition repeatable.'),
    ('pickups_30', '10x30sec Light Pickups', 'pickups', 10, 30, None, 90,
     'Smooth relaxed pickups with generous easy jogging; avoid sprinting.'),
    ('fartlek_90', '6x90sec Light Fartlek', 'fartlek', 6, 90, None, 90,
     'Controlled aerobic running with equal-time easy jogging; do not chase VO2 effort.'),
    ('strides_20', '6x20sec Relaxed Strides', 'leg_speed', 6, 20, None, 100,
     'Accelerate gradually, run tall and relaxed, then ease off. Recover fully; extend the jog if needed.'),
    ('steady_10', '10min Light Steady Finish', 'aerobic_rhythm', 1, 600, None, None,
     'Move gradually from easy to a modest steady rhythm, below threshold. Breathing remains controlled; no fast finish or pace test.'),
    ('reps_400', '6x400m Relaxed Repetitions', 'track_rhythm', 6, None, 400, 90,
     'Controlled relaxed repetitions, not a 5K-pace test. Finish with a repetition in reserve.'),
    ('reps_200', '8x200m Relaxed Repetitions', 'leg_speed', 8, None, 200, 90,
     'Smooth quick mechanics, never an all-out 200m sprint. Take full easy-jog recovery.'),
    ('reps_300', '6x300m Relaxed Repetitions', 'track_rhythm', 6, None, 300, 90,
     'Controlled rhythm rather than maximal speed. Keep the last repetition as relaxed as the first.'),
    ('reps_600', '4x600m Relaxed Repetitions', 'track_rhythm', 4, None, 600, 120,
     'Controlled faster aerobic rhythm with generous jogging. Avoid turning the longer reps into a hard interval workout.'),
    ('hills_20', '6x20sec Controlled Short Hills', 'hills', 6, 20, None, 120,
     'Use a gentle familiar incline, smooth controlled form, and walk/jog down fully. No maximal hill sprinting or hard descending; use flat relaxed strides if hills are unfamiliar or soreness persists.'),
)


def light_speed_support(paces, workout_format='distance', *, week_start=None, terrain=None):
    """Stable calendar rotation within a bounded support role, not random difficulty.

    Format biases selection; hills require explicit trail/mountain terrain. Work
    mileage is an estimate from current reference pace, never a prescribed target.
    """
    easy = paces['long_run_pace']
    candidates = []
    for template in SUPPORT_SESSIONS:
        _, _, family, reps, seconds, meters, _, _ = template
        if family == 'hills' and terrain not in {'trail', 'mountain'}:
            continue
        if family != 'hills' and ((workout_format == 'time') != (seconds is not None)):
            continue
        estimate = paces.get('steady_pace', easy) if family == 'aerobic_rhythm' else paces['interval_pace']
        # Do not turn a distance option into a long quality session at slower fitness.
        if (seconds * reps if seconds else meters / MI * estimate * reps) <= 600:
            candidates.append(template)
    # A reference pace can rule out every distance option. Strides remain a low-dose fallback.
    if not candidates:
        candidates = [SUPPORT_SESSIONS[3]]
    from datetime import date
    anchor = week_start or date(2026, 10, 19)
    # Absolute calendar-week seed: revising or regenerating the same week does not
    # create novelty or imply progression. Consecutive weeks cycle the eligible pool.
    index = ((anchor.toordinal() - date(2026, 10, 19).toordinal()) // 7) % len(candidates)
    key, name, family, reps, seconds, meters, recovery, guidance = candidates[index]
    work = segment(reps, seconds=seconds, meters=meters, recovery_seconds=recovery)
    fmt = 'continuous' if family == 'aerobic_rhythm' else 'time_intervals' if seconds else 'track_intervals'
    data = prescription('speed_support', fmt, [work], program='support-v2:mileage', phase='general',
                        note=guidance + ' If recovery is incomplete, run easy instead.')
    data.update({'template_id': key, 'stimulus': family, 'pace_is_estimate_only': True})
    data['warmup'] = segment(meters=1.5*MI)
    data['cooldown'] = segment(meters=MI)
    estimate = paces.get('steady_pace', easy) if family == 'aerobic_rhythm' else paces['interval_pace']
    work_miles = (meters / MI if meters else seconds / estimate) * reps
    total = 2.5 + work_miles + (reps-1)*(recovery or 0)/easy
    data['total_distance_meters'] = round(total*MI, 2)
    return {'name': name, 'structure': render(data), 'prescription': data,
            'total_miles': math.ceil(total*2)/2, 'warmup': '1.5mi easy', 'cooldown': '1mi easy',
            'purpose': {
                'fartlek': 'Maintain controlled faster aerobic running with easy recoveries.',
                'pickups': 'Small changes of rhythm without a sustained hard effort.',
                'leg_speed': 'Relaxed mechanics and coordination with full recovery.',
                'aerobic_rhythm': 'Practice a modest steady rhythm below threshold; keep the rest easy.',
                'track_rhythm': 'Controlled faster rhythm without a full interval-session dose.',
                'hills': 'Small uphill coordination stimulus on familiar terrain, with full recovery.',
            }[family]}


def format_bookends(workout, paces, workout_format):
    """Use the requested bookend format; work reps retain their authored stimulus.

    Threshold duration and track distance are intentionally specific. Converting
    reps by a pace estimate would change the workout/evidence contract.
    """
    if workout_format != 'time' or not workout:
        return workout
    import copy
    workout = copy.deepcopy(workout)
    data = workout.get('prescription')
    if not data:
        return workout
    for key in ('warmup', 'cooldown'):
        spec = data.get(key)
        if spec and spec.get('distance_meters'):
            seconds = round(spec['distance_meters'] / MI * paces['long_run_pace'])
            workout[key] = f'{seconds/60:g}min easy'
            data[key] = segment(seconds=seconds)
    return workout


def secondary_quality(paces, program, phase, week_number, current_mileage, progression_state=None, *,
                      experience='intermediate', deload=False):
    """Two-workout stage: goal-specific substantial secondary dose, not maximal.

    This is a coordinated prescription, not a second independent progression ladder.
    Primary ladder advancement remains evidence-gated; secondary completion helps
    demonstrate weekly tolerance without double-incrementing threshold level.

    Dose comes from the same catalog and dose band as the replace menu
    (core/session_catalog.py), taken at the band FLOOR: the smallest session that
    reaches the athlete's experience floor, so the two systems never disagree.
    Odd weeks (and base) are threshold for longer goals; marathoners in build/peak
    use a continuous marathon-pace run on the other weeks, everyone else short reps.
    """
    from app.core.goal_pace import allows_goal_pace
    from app.core.session_catalog import at_floor, build_workout, dose_band
    from app.core.workout_ladders import program_key
    threshold_focus = (program in {'mileage','half','marathon'} and (phase=='base' or week_number%2==1))
    if threshold_focus:
        # Controlled broken threshold at the current evidence-based pace.
        families, dose, pace = ('cruise_time', 'cruise_distance'), 'threshold', paces.get('broken_threshold_pace', paces['tempo_pace']-10)
        purpose = 'Second controlled aerobic-strength stimulus; finish repeatable, not racing the primary workout.'
    elif program == 'marathon' and paces.get('specific_pace') and allows_goal_pace(program, phase, deload=deload):
        families, dose, pace = ('mp_continuous', 'mp_block'), 'marathon_pace', paces['specific_pace']
        purpose = 'Marathon-pace rhythm as the second session; controlled, the long run stays the priority.'
    else:
        families, dose, pace = ('short_reps', 'time_reps'), 'intervals', paces['interval_pace']
        purpose = 'Shorter faster aerobic work complements threshold; preserve recovery for the long run.'
    band = dose_band(dose, experience, current_mileage, pace, phase, deload)
    template = at_floor(families, band, paces, program)
    workout = build_workout(template, paces, program=program_key(program), phase=phase)
    data = workout['prescription']
    data['note'] = 'Controlled effort with a repetition in reserve; no maximal finish.'
    data['role'] = 'secondary_quality'
    data['dose_band'] = {'low': band.low, 'high': band.high}
    return workout | {'name': f'Controlled {template.name}', 'structure': render(data), 'purpose': purpose}
