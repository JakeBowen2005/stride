"""Deterministic quality selection. Personal coaching heuristics, not cutoffs proven safe.

The Long Game dossier describes a threshold + light speed-support rebuild before
returning to two substantial workouts. A past PR alone does not establish readiness.
"""
from dataclasses import dataclass
import math

from app.core.workout_data import MI, prescription, render, segment


@dataclass(frozen=True)
class QualityPolicy:
    light_second: bool
    reason: str


def select_quality_policy(goal_type, experience, days_per_week, weekly_miles, weekly_run_days,
                          recent_long_run_miles, assessment=None, fatigue=False):
    if goal_type != 'mileage' or experience != 'advanced':
        return QualityPolicy(False, 'Standard goal-specific quality allocation.')
    ready = (days_per_week >= 5 and len(weekly_miles) >= 4 and len(weekly_run_days) >= 4
             and min(weekly_miles[-4:]) >= 20 and weekly_miles[-1] >= 30
             and weekly_miles[-1] <= 1.35 * (sum(weekly_miles[-4:]) / 4)
             and min(weekly_run_days[-2:]) >= 4 and recent_long_run_miles >= 8)
    if fatigue or assessment in {'hold', 'reduce', 'recovery'}:
        return QualityPolicy(False, 'Recovery feedback takes priority: omit the light second session.')
    if not ready:
        return QualityPolicy(False, 'One threshold session plus strides until recent volume, frequency and long-run tolerance support a light second session.')
    return QualityPolicy(True, 'Recent training supports threshold plus a light speed-support session, with an easy long run. Keep the threshold dose stable and the second stimulus light while building mileage; remove the second session if recovery deteriorates.')


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
