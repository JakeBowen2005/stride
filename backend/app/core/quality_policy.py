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
    return QualityPolicy(True, 'Recent training supports threshold plus a light speed-support session, with an easy long run. Repeat the quality dose while building mileage; remove the second session if recovery deteriorates.')


def light_speed_support(paces, workout_format='distance'):
    """8min fartlek or ~9min relaxed 400s; effort guidance, no race-pace advancement."""
    easy = paces['long_run_pace']
    work = segment(8, seconds=60, recovery_seconds=60) if workout_format == 'time' else segment(6, meters=400, recovery_seconds=90)
    data = prescription('speed_support', 'time_intervals' if workout_format == 'time' else 'track_intervals', [work],
                        program='support-v1:mileage', phase='general',
                        note='Relaxed, controlled faster running; not a sprint or a pace test. Finish with a repetition in reserve. Jog recoveries. If soreness persists, run easy instead.')
    data['warmup'] = segment(meters=1.5*MI)
    data['cooldown'] = segment(meters=MI)
    work_miles = (work.get('distance_meters') or 60 / paces['interval_pace'] * MI) * work['reps'] / MI
    total = 2.5 + work_miles + (work['reps']-1)*work['recovery_seconds']/easy
    data['total_distance_meters'] = round(total*MI, 2)
    return {'name': '8x1min Light Fartlek' if workout_format == 'time' else '6x400m Relaxed Repetitions',
            'structure': render(data), 'prescription': data, 'total_miles': math.ceil(total*2)/2,
            'warmup': '1.5mi easy', 'cooldown': '1mi easy',
            'purpose': 'Small speed/economy stimulus supporting threshold development without a second demanding workout.'}


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
