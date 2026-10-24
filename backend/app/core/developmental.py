"""Introductory aerobic quality, separate from calibrated threshold/VO2 ladders.

These are Stride coaching choices: duration and reported control earn progression,
never a fabricated pace target. Advanced/expert and ultra programs do not use this path.
"""
import math
from datetime import timedelta

from app.core.workout_data import MI, prescription, render, segment


def uses_developmental(experience, goal_type, distance=None):
    return experience in {'beginner', 'intermediate'} and goal_type != 'comeback' and distance not in {'50k', '50mi', '100k', '100mi'}


# (reps, minutes, easy recovery minutes). Repeat a dose before extending it;
# short reps, continuous efforts and longer reps practice different skills.
STEPS = ((1, 10, 0), (5, 2, 1), (1, 12, 0), (6, 2, 1),
         (3, 4, 2), (1, 15, 0), (5, 3, 1), (3, 5, 2),
         (1, 18, 0), (6, 3, 1), (3, 6, 2), (1, 20, 0))


def workout(level, easy_pace, weekly_miles, *, program=None, phase='general', reduced=False, shape=None):
    """Ten easy / ten purposeful / ten easy, scaled down when the week is smaller.

    Mileage is an estimate at 90% of easy pace for budgeting only. The athlete
    runs by effort. Numeric work durations and time bookends remain authoritative.
    """
    level = max(1, min(int(level), len(STEPS)))
    reps, minutes, recovery = STEPS[level - 1]
    work_minutes = reps * minutes
    # At most ~15% of the week at estimated work effort; never use a training
    # pace guessed from easy pace as a threshold or interval prescription.
    estimate = easy_pace * .9
    cap = max(0, math.floor(weekly_miles * .15 * estimate / 60))
    if reduced:
        # Taper keeps ~2/3 of the dose (volume drops, rhythm stays); deload, recovery
        # and race week halve it.
        keep = round(work_minutes * 2 / 3) if phase == 'taper' else work_minutes // 2
        cap = min(cap, max(3, keep))
    dose = min(work_minutes, cap)
    if dose < 3:
        return None
    if shape == 'short':
        reps, minutes, recovery = dose, 1, 1
    elif shape == 'long':
        reps, minutes, recovery = max(1, dose // 3), 3, 2
    elif shape == 'continuous':
        reps, minutes, recovery = 1, dose, 0
    elif dose < work_minutes:
        reps, minutes, recovery = 1, dose, 0
    dose = reps * minutes
    bookend = 10
    total = (2 * bookend * 60 + max(0, reps - 1) * recovery * 60) / easy_pace + dose * 60 / estimate
    # A small week still has room for its easy days and long run. Shorten the
    # bookends to five minutes before deciding the session cannot fit.
    if total > weekly_miles * .4:
        bookend = 5
        total = (2 * bookend * 60 + max(0, reps - 1) * recovery * 60) / easy_pace + dose * 60 / estimate
    if total > weekly_miles * .4 or total < .1:
        return None
    name = f'{reps}x{minutes}min Controlled Intervals' if reps > 1 else f'{minutes}min Controlled Effort'
    cue = ('Short phrases are possible. Finish able to do a little more; slow down if breathing or form gets ragged. '
           + ('Jog or walk the recoveries. ' if reps > 1 else '') + 'Effort is the target, not a pace test.')
    data = prescription('development', 'time_intervals' if reps > 1 else 'continuous',
                        [segment(reps, seconds=minutes * 60, recovery_seconds=recovery * 60 or None)],
                        program=program, phase=phase, level=level, note=cue)
    data.update(warmup=segment(seconds=bookend * 60), cooldown=segment(seconds=bookend * 60),
                easy_pace_sec_per_mile=easy_pace, estimated_work_pace_sec_per_mile=estimate,
                progression_eligible=not reduced and dose == work_minutes and shape is None,
                total_distance_meters=round(total * MI, 2))
    data['segments'][0]['effort'] = 'controlled medium-to-hard effort (about 6/10 effort)'
    return {'name': name, 'structure': render(data), 'prescription': data,
            'total_miles': math.ceil(total * 10) / 10,
            'warmup': f'{bookend}min easy', 'cooldown': f'{bookend}min easy',
            'purpose': 'Build sustained aerobic effort and pacing control before longer or harder workouts.'}


def ready_for_workout(history, run_days, weekly_miles, evidence, assessment, fatigue):
    if fatigue or assessment in {'reduce', 'recovery'} or evidence.get('recent_low_feel') or evidence.get('recent_failure'):
        return False
    return (weekly_miles >= 6 and len(history) >= 2 and min(history[-2:]) > 0
            and len(run_days) >= 2 and min(run_days[-2:]) >= 2)


def deload_supported(history, evidence, first_date):
    """Calendar cadence needs actual training stress, not merely old easy weeks."""
    reset = 0
    for i, miles in enumerate(history):
        if miles <= 0 or (i and miles <= max(history[max(0, i-3):i]) * .85):
            reset = i + 1
    monday = first_date - timedelta(days=first_date.weekday())
    since = (monday - timedelta(weeks=len(history) - reset)).isoformat()
    dates = set(evidence.get('development_dates', [])) | set(evidence.get('matched_quality_dates', []))
    # Pure mileage builders can also earn a lighter week after sustained growth.
    recent = history[-4:]
    grew = len(recent) == 4 and min(recent) > 0 and recent[-1] >= min(recent) * 1.25
    return sum(d >= since for d in dates) >= 3 or grew


# Long-run shape for developing runners (Stride coaching choices, docs/training-principles.md).
# Half/marathon long runs may reach ~40-45% of the week on low-frequency schedules,
# growing about a mile a week (cutback weeks drop back) and never past ~3 hours.
LONG_RUN_SHARE = {'half': .40, 'marathon': .42}
LONG_RUN_FLOOR_SHARE = .35  # the +1 mi/week step never pulls a long run below this share
LONG_RUN_STEP_MILES = 1.0
LONG_RUN_MAX_MINUTES = 180
DAY_AFTER_LONG_SHARE = .18  # the run after the long run is the week's shortest, <= ~15-20%
CLEARLY_LONGEST = 1.2  # the long run should be at least this much longer than any easy day


def long_run_cap(week_miles, longest_recent, easy_pace):
    """Most a developing half/marathon long run may be this week (None = no cap)."""
    cap = LONG_RUN_MAX_MINUTES * 60 / easy_pace
    if longest_recent > 0:
        cap = min(cap, max(longest_recent + LONG_RUN_STEP_MILES, week_miles * LONG_RUN_FLOOR_SHARE))
    return round(cap, 1)


def fit_week(days, budget, easy_desc, restructure_long, long_cap=None):
    """Preserve frequency with tenth-mile easy runs; never enlarge a workout.

    Completed days are locked. If the full session cannot fit alongside short
    easy runs, downgrade it rather than silently editing its work prescription.
    The run after the long run is the week's shortest; the long run is clearly the
    longest (up to ``long_cap``).
    """
    from app.core.plan_validator import _easy
    live = [d for d in days if d.get('prescribed', True) and d['type'] != 'race']
    locked = sum(d['distance_miles'] for d in days if d not in live and d['type'] != 'race')
    available = max(0, budget - locked)
    running = [d for d in live if d['type'] != 'rest' and d['distance_miles'] > 0]
    if not running:
        return []
    notes = []
    workouts = [d for d in running if d['type'] == 'workout']
    for day in workouts:
        if sum(d['distance_miles'] for d in workouts) + .5 * (len(running) - len(workouts)) > available:
            _easy(day, easy_desc, .5)
            notes.append('Controlled workout became easy: its full work and bookends do not fit the remaining week.')
    fixed = sum(d['distance_miles'] for d in running if d['type'] == 'workout')
    aerobic = [d for d in running if d['type'] != 'workout']
    remaining = max(0, available - fixed)
    if not aerobic:
        return notes
    long = next((d for d in aerobic if d['type'] == 'long_run'), None)
    # Retain the authored long-run share, spread the rest without a 2/3mi floor.
    long_miles = (remaining if len(aerobic) == 1 else min(long['distance_miles'], remaining)) if long else 0
    if long and len(aerobic) > 1:
        long_miles = max(long_miles, remaining / len(aerobic))
        long_miles = min(long_miles, max(0, remaining - .5 * (len(aerobic) - 1)))
    easy_count = len(aerobic) - bool(long)
    per = max(0, remaining - long_miles) / easy_count if easy_count else 0
    for d in aerobic:
        miles = long_miles if d is long else per
        d['distance_miles'] = math.floor((miles + 1e-8) * 10) / 10
        if d['distance_miles'] < .5:
            _easy(d, easy_desc, 0)
            d.update(type='rest', title='Recovery / Rest', description='No remaining mileage budget. Rest and recover.')
        elif d is long:
            d.update(restructure_long(d['distance_miles']))
    # Allocate residual tenths rather than losing growth at each rounding step.
    for d in sorted(aerobic, key=lambda d: d['distance_miles']):
        if d['type'] == 'rest':
            continue
        total = locked + sum(x['distance_miles'] for x in live)
        if total + .1 <= budget + 1e-8:
            d['distance_miles'] = round(d['distance_miles'] + .1, 1)
            if d is long:
                d.update(restructure_long(d['distance_miles']))
    if long and long['type'] == 'long_run':
        easy = [d for d in aerobic if d is not long and d['type'] == 'easy']
        idx = days.index(long)
        after = days[idx + 1] if idx + 1 < len(days) and days[idx + 1] in easy else None
        others = [d for d in easy if d is not after]
        if after:
            cap = math.floor(budget * DAY_AFTER_LONG_SHARE * 10) / 10
            if others:
                cap = min(cap, min(d['distance_miles'] for d in others))
            excess = round(after['distance_miles'] - max(cap, .5), 1)
            if excess > 0:
                after['distance_miles'] = round(after['distance_miles'] - excess, 1)
                # Move the miles to the other easy days, else onto the long run within its
                # cap. With nowhere left (e.g. a partial first week), the remainder stays on
                # the day after: silently losing volume would read as a spike next block.
                for _ in range(round(excess * 10)):
                    if others:
                        target = min(others, key=lambda d: d['distance_miles'])
                    elif long_cap is None or long['distance_miles'] + .1 <= long_cap + 1e-8:
                        target = long
                    else:
                        target = after
                    target['distance_miles'] = round(target['distance_miles'] + .1, 1)

        def move_to_long(condition):
            while easy and condition():
                donor = max(easy, key=lambda d: d['distance_miles'])
                if donor['distance_miles'] - .1 < .5:
                    break
                donor['distance_miles'] = round(donor['distance_miles'] - .1, 1)
                long['distance_miles'] = round(long['distance_miles'] + .1, 1)

        def longest_easy():
            return max(d['distance_miles'] for d in easy)

        limit = long_cap if long_cap is not None else float('inf')
        move_to_long(lambda: long['distance_miles'] + .1 <= limit + 1e-8
                     and long['distance_miles'] + 1e-8 < CLEARLY_LONGEST * longest_easy())
        move_to_long(lambda: long['distance_miles'] + 1e-8 < longest_easy()
                     and long['distance_miles'] + .1 <= limit + 1e-8)
        # A long run already at its cap: easy days are trimmed to it rather than
        # pushing it past ~3 hours or the weekly step (fail safe: prescribe less).
        if any(d['distance_miles'] > long['distance_miles'] for d in easy):
            for d in easy:
                d['distance_miles'] = min(d['distance_miles'], long['distance_miles'])
            notes.append('Easy runs capped at the long run, which is already at its limit: the week holds less than its budget.')
        long.update(restructure_long(long['distance_miles']))
    return notes


# Run/walk on-ramp for someone who can't yet run 20 minutes without stopping:
# (run minutes, walk minutes, repeats). One step per week with any running; a long
# break restarts from the athlete's stated ability. Stride's coaching choice,
# following the common couch-to-5K shape: total time stays ~25-30min while the
# running share grows, so the step is the progression, not extra volume.
RUN_WALK = ((1, 2, 8), (2, 2, 6), (3, 2, 5), (5, 2, 4), (8, 2, 3), (12, 1, 2), (15, 1, 2))
WALK_PACE = 1080  # 18:00/mi, budgeting estimate for walk breaks


RUN_WALK_THRESHOLDS = (2, 3, 5, 8, 12, 15, 20)  # continuous minutes that start each step


def run_walk_stage(continuous_minutes, weekly_run_days=None, week_index=0, holding=False):
    """Run/walk step for a block week, or None once 20 continuous minutes is reached.

    `weekly_run_days` are completed weeks since the starting point was set (oldest
    first). A week with at least two runs completes a step; a week with no running
    drops one step (not back to the start). Within a block, later weeks preview the
    next step unless the block is holding.
    """
    if continuous_minutes is None:
        return None
    base = next((i for i, t in enumerate(RUN_WALK_THRESHOLDS) if continuous_minutes < t), None)
    if base is None:
        return None
    stage = base
    for days in weekly_run_days or []:
        stage = stage + 1 if days >= 2 else stage - 1 if days == 0 else stage
        stage = max(0, stage)
        if stage >= len(RUN_WALK):
            return None  # graduated: continuous running from here
    stage += 0 if holding else week_index
    return stage if stage < len(RUN_WALK) else None


def stage_minutes(stage):
    """The continuous-minutes value that starts a step (for saving progress)."""
    return RUN_WALK_THRESHOLDS[-1] if stage is None else (0 if stage == 0 else RUN_WALK_THRESHOLDS[stage - 1])


def run_walk_day(day, stage, easy_pace, long=False):
    """Rewrite an easy or long day as a time-based run/walk session."""
    run, walk, reps = RUN_WALK[stage]
    reps += 1 if long else 0
    warm = 5
    total = warm + reps * (run + walk)
    miles = round((reps * run * 60) / easy_pace + ((warm + reps * walk) * 60) / WALK_PACE, 1)
    day.update(
        title='Run/Walk' + (' (longer)' if long else ''),
        description=(f'{warm}min brisk walk, then {reps} x ({run}min easy run + {walk}min walk). '
                     f'About {total} minutes. Run slowly enough to talk; walk briskly.'),
        purpose=('Build the habit and the durability to run continuously. Each week the running '
                 'share grows while total time stays similar.'),
        distance_miles=max(miles, .5), warmup=None, cooldown=None, prescription=None,
        type='long_run' if long else 'easy',
    )
    spec=prescription('run_walk','run_walk',[segment(reps,seconds=run*60,recovery_seconds=walk*60,recovery_meters=round(walk*60/WALK_PACE*MI,2))],
                      note='Easy run portions, brisk walk recoveries. Build continuity before adding intensity.')
    spec.update(warmup=segment(seconds=warm*60,meters=round(warm*60/WALK_PACE*MI,2)),
                cooldown=segment(seconds=walk*60,meters=round(walk*60/WALK_PACE*MI,2)),progression_eligible=False)
    day['prescription']=spec
    return day
