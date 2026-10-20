"""Goal-pace specificity: where race-specific work is allowed and how fast it is.

Peak-phase work should look like the race (Daniels/Pfitzinger: goal-pace reps for
5K/10K, marathon-pace running inside long and medium-long runs). Goal pace is an
aspiration, not evidence, so it is never prescribed outright. Each session targets

    max(goal pace, demonstrated race pace - STEP_SEC)

i.e. it steps at most STEP_SEC s/mi from what the athlete has shown toward the
goal, and never faster than the goal. When completed goal-pace reps calibrate a
faster demonstrated pace (pace_calibrator `race_pace_<distance>`), the next
prescription steps again. Deterministic: same paces in, same pace out.

Demonstrated race pace comes from calibrated goal-pace reps when they exist,
otherwise from the category paces already used for training. The offsets below
are Stride heuristics following Daniels' relationships (I pace is roughly 3K-5K
race pace; 10K pace sits a little faster than T; M pace ~15-20 s/mi slower than
T). They are not a VDOT table.
"""

STEP_SEC = 5
# Phases where each goal may prescribe goal-pace work. Readiness (quality stage,
# volume) is gated by the caller exactly as before; this only opens the phase.
SPECIFIC_PHASES = {'5k': {'peak'}, '10k': {'peak'}, 'marathon': {'build', 'peak'}}


def demonstrated_race_pace(distance, paces):
    """Current race-pace equivalent (sec/mi) from evidence-based training paces."""
    calibrated = paces.get(f'race_pace_{distance}')
    if calibrated:
        return round(calibrated)
    threshold = paces.get('broken_threshold_pace') or (paces.get('tempo_pace', 420) - 10)
    if distance == '5k':
        return round(paces.get('interval_pace', threshold - 25) + 5)
    if distance == '10k':
        return round(threshold - 10)
    if distance == 'marathon':
        return round(threshold + 20)
    return None


def specific_pace(distance, paces):
    """Today's goal-pace target: one step from demonstrated pace toward the goal."""
    demonstrated = demonstrated_race_pace(distance, paces)
    goal = paces.get('goal_race_pace')
    if demonstrated is None:
        return None
    if not goal:
        return demonstrated  # no goal time: race-specific rhythm at current fitness
    return round(max(goal, demonstrated - STEP_SEC))


def allows_goal_pace(distance, phase, *, deload=False):
    return not deload and phase in SPECIFIC_PHASES.get(distance, set())


def with_specific_pace(paces, distance):
    """Copy of `paces` carrying `specific_pace` (or None outside goal-pace goals)."""
    out = dict(paces)
    out['specific_pace'] = specific_pace(distance, paces) if distance in SPECIFIC_PHASES else None
    return out


def step_note(distance, paces):
    """Coach-voice explanation of where today's goal-pace target came from."""
    from app.core.pacing import format_pace
    target, goal = paces.get('specific_pace'), paces.get('goal_race_pace')
    demonstrated = demonstrated_race_pace(distance, paces)
    if not target:
        return ''
    if not goal:
        return f'Race-specific rhythm at your current {format_pace(target)}/mi; set a goal time to progress toward it.'
    if target <= goal:
        return f'You have shown goal pace ({format_pace(goal)}/mi): hold it and keep every rep smooth.'
    return (f'Goal is {format_pace(goal)}/mi; you have shown about {format_pace(demonstrated)}/mi, so today steps to '
            f'{format_pace(target)}/mi. Hit these and the next step moves closer.')
