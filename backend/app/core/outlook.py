"""Where the training is heading: milestones toward the goal, and the block review.

Prescriptions stay rolling (two weeks at a time). This module only explains the
route: which capacities the goal needs, where the athlete is now, a rough number of
weeks at the current ramp, and whether a race date leaves enough time. The volume
and long-run targets are Stride review heuristics for an athlete of this level,
not guarantees of readiness; they are reassessed from real training every block.
"""
import math

from app.core.periodization import BUILD_WEEKS, PEAK_WEEKS, taper_weeks

# Weekly volume / long run a goal typically needs, by experience band. Developing
# half/marathon long runs are at most developmental.LONG_RUN_SHARE of the week (and
# ~3 hours), so the developing long-run target must be reachable at the volume target.
VOLUME_TARGETS = {  # (developing, established) mi/week
    '5k': (15, 35), '10k': (20, 40), 'half': (25, 45), 'marathon': (38, 55),
    '50k': (40, 55), '50mi': (45, 60), '100k': (50, 65), '100mi': (55, 70),
}
LONG_RUN_TARGETS = {  # (developing, established) miles
    '5k': (5, 10), '10k': (7, 12), 'half': (10, 14), 'marathon': (16, 20),
    '50k': (18, 22), '50mi': (22, 26), '100k': (24, 28), '100mi': (26, 30),
}
TAPER_WEEKS = {d: taper_weeks(d) for d in VOLUME_TARGETS}  # the plan's own taper (race week included)
VOLUME_DECISION_SHARE = .5  # below this share of the volume target once build starts: the athlete decides
DEVELOPMENT_TOP_LEVEL = 12


def _weeks_to_grow(current: float, target: float, weekly_rate: float, deload_every: int = 4) -> int:
    """Weeks of compounding growth, plus one lighter week per (deload_every - 1) builds."""
    if current >= target:
        return 0
    start = max(current, 1.0)
    builds = math.ceil(math.log(target / start) / math.log(1 + weekly_rate))
    return builds + builds // max(1, deload_every - 1)


def goal_outlook(*, goal_type: str, distance: str | None, race_weeks_away: float | None,
                 destination: float | None, baseline: float, recent_long_run: float,
                 experience: str, run_days_recent: list[int], days_per_week: int,
                 development_level: int | None, run_walk_stage: int | None,
                 weekly_rate: float = .08) -> dict:
    developing = experience in {'beginner', 'intermediate'}
    band = 0 if developing else 1
    milestones = []

    def add(key, label, current, target, unit, weeks, detail):
        done = current is not None and target is not None and current >= target
        milestones.append({'key': key, 'label': label, 'current': current, 'target': target, 'unit': unit,
                           'status': 'done' if done else 'in_progress', 'est_weeks': 0 if done else weeks,
                           'detail': detail})

    if run_walk_stage is not None:
        add('continuous', 'Run 20 minutes without stopping', run_walk_stage, 7, 'run/walk step',
            7 - run_walk_stage, 'One run/walk step per week you run; a missed week repeats the step.')

    target_days = min(max(days_per_week, 3), 6)
    streak = 0
    for days in reversed(run_days_recent or []):
        if days < target_days:
            break
        streak += 1
    add('consistency', f'{target_days} runs a week, three weeks in a row', min(streak, 3), 3, 'weeks',
        3 - min(streak, 3), 'Consistency comes first: it is what makes every later increase safe.')

    volume = destination if goal_type == 'mileage' and destination else (
        VOLUME_TARGETS.get(distance, (None, None))[band] if goal_type == 'race' else destination)
    if volume:
        add('volume', f'Build to {volume:g} mi/week', round(baseline, 1), volume, 'mi/week',
            _weeks_to_grow(baseline, volume, weekly_rate, 4 if developing else 7),
            'Grows at most one step at a time; down weeks absorb the work.')

    long_target = LONG_RUN_TARGETS.get(distance, (None, None))[band] if goal_type == 'race' else None
    if long_target:
        # Long runs grow with weekly volume (about 40% of the week for developing marathoners)
        long_weeks = _weeks_to_grow(recent_long_run or 1, long_target, weekly_rate, 4 if developing else 7)
        add('long_run', f'Long run of {long_target:g} miles', round(recent_long_run, 1), long_target, 'miles',
            long_weeks, 'Rises with weekly volume, never as a one-off jump.')

    if development_level is not None and goal_type in {'race', 'mileage', 'general'} and developing:
        add('workouts', 'Sustain a 20-minute controlled effort', development_level, DEVELOPMENT_TOP_LEVEL, 'step',
            (DEVELOPMENT_TOP_LEVEL - development_level) * (4 if experience == 'beginner' else 2),
            'Each step is earned by completing its dose at a controlled effort and recovering well.')

    gaps = []
    if race_weeks_away is not None and goal_type == 'race':
        usable = race_weeks_away - TAPER_WEEKS.get(distance, 1)
        for m in milestones:
            if m['status'] != 'done' and m['key'] in {'volume', 'long_run', 'continuous'} and m['est_weeks'] > usable:
                gaps.append({'milestone': m['key'], 'message':
                    f"{m['label']} needs about {m['est_weeks']} weeks at a safe ramp; about {max(0, round(usable))} "
                    f"remain before taper. Consider a later race or a shorter distance, or race it as a "
                    f"completion goal. Stride won't cram the missing work into the final weeks."})
    decision = volume_gap_decision(goal_type, distance, race_weeks_away, baseline, volume)
    # Workout development continues past goal readiness; it doesn't set the headline
    remaining = [m['est_weeks'] for m in milestones if m['status'] != 'done' and m['key'] != 'workouts']
    return {'milestones': milestones, 'gaps': gaps, 'decision': decision,
            'est_weeks_to_ready': max(remaining) if remaining else 0,
            'note': 'Estimates assume steady training at the current safe ramp. They are reassessed every block from what you actually run.'}


def volume_gap_decision(goal_type: str, distance: str | None, race_weeks_away: float | None,
                        baseline: float, volume_target: float | None) -> dict | None:
    """Once build has started, volume under half the goal's target is the athlete's call.

    A note is easy to scroll past; this asks how to race it (completion goal, a later
    race, or a shorter distance) instead of quietly training on toward an unready race.
    """
    if goal_type != 'race' or not distance or race_weeks_away is None or not volume_target:
        return None
    before_taper = race_weeks_away - (taper_weeks(distance) - 1)
    in_build = 0 < before_taper <= PEAK_WEEKS.get(distance, 4) + BUILD_WEEKS.get(distance, 4)
    if not in_build or baseline >= volume_target * VOLUME_DECISION_SHARE:
        return None
    return {
        'key': 'volume_gap', 'required': True,
        'question': (f"Training is at {baseline:g} mi/week, under half the ~{volume_target:g} mi/week this race "
                     f"usually needs, and the build phase has started. How do you want to approach it?"),
        'options': [
            {'key': 'completion', 'label': 'Keep the date and race it as a completion goal',
             'detail': 'Training keeps its safe ramp; the target time is not the measure.'},
            {'key': 'later_race', 'label': 'Choose a later race', 'detail': 'More weeks to build volume safely.'},
            {'key': 'shorter', 'label': 'Switch to a shorter distance', 'detail': 'Race what current training supports.'},
        ],
    }


def block_review(assessment: dict | None, load: dict | None, notes: list[str] | None = None) -> dict | None:
    """Completed → learned → changes next → why, from the stored assessment and load policy."""
    if not assessment:
        return None
    a, load = assessment, load or {}
    completed = []
    if a.get('planned_miles'):
        completed.append(f"Ran {a['completed_miles']:g} of {a['planned_miles']:g} planned miles"
                         + (f" ({a['completion']:.0%})." if a.get('completion') is not None else '.'))
    if a.get('quality_planned'):
        completed.append(f"Verified {a['quality_done']} of {a['quality_planned']} quality sessions.")
    if a.get('long_runs_planned'):
        completed.append(f"Completed {a['long_runs_done']} of {a['long_runs_planned']} long runs.")
    if a.get('avg_feel') is not None:
        completed.append(f"Average feel {a['avg_feel']:.1f}/10 across {a['feel_count']} rated runs.")

    learned = {
        'build': 'You absorbed the block: the volume and sessions were the right size.',
        'hold': 'Signals were mixed, so the evidence supports consolidating, not adding.',
        'reduce': 'The block was interrupted. Missed miles are not made up; the next block eases back in.',
        'recovery': 'Several runs felt bad. Recovery comes before the next build.',
    }.get(a.get('decision'), 'Not enough of the last block was run to judge it yet.')
    if a.get('decision') == 'hold' and load.get('mode') == 'reduce':
        learned = 'Part of the block was missed, so the next one is sized to what you are completing.'

    changes = []
    budgets = load.get('weekly_budgets') or []
    if budgets:
        changes.append(f"Weekly volume: {' → '.join(f'{b:g}' for b in budgets)} mi"
                       + (f" (from a {load['baseline']:g} mi/week baseline)." if load.get('baseline') is not None else '.'))
    if load.get('deload_week') is not None:
        changes.append(f"Week {load['deload_week'] + 1} is a lighter week to absorb training.")

    earned, missing = [], []
    if a.get('quality_done'):
        earned.append(f"{a['quality_done']} verified quality session(s) count toward workout progression.")
    if a.get('decision') == 'build':
        earned.append('A volume increase.')
    if a.get('quality_unknown'):
        missing.append(f"{a['quality_unknown']} session(s) had no lap evidence. Report completion and effort in the "
                       f"feedback form so they still count.")
    if a.get('quality_incomplete'):
        missing.append(f"{a['quality_incomplete']} session(s) were incomplete or not controlled, so they repeat.")
    if a.get('quality_substituted'):
        missing.append(f"{a['quality_substituted']} session(s) were swapped for different work. That's logged, but it "
                       f"doesn't progress the prescribed ladder.")
    return {'decision': a.get('decision'), 'completed': completed, 'learned': learned, 'changes': changes,
            'why': list(a.get('reasons') or []) + list(load.get('reasons') or []),
            'earned': earned, 'missing': missing}
