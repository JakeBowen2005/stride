"""Plan-structure fixes from the 2026-10-22 running-coach review of the demo programs.

Engine-level tests use generate_plan directly; the whole-program checks read the demo
documents, which test_developmental_plans regenerates and compares byte-for-byte, so
they describe what the engine actually produces.
"""
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core import developmental
from app.core.load_policy import latest_week_is_spike, plan_load
from app.core.outlook import LONG_RUN_TARGETS, TAPER_WEEKS, VOLUME_TARGETS, goal_outlook
from app.core.periodization import TAPER_DAYS, plan_phases, protects_peak, taper_weeks, week_phase
from app.core.plan_engine import _biggest_mp_long_run, generate_plan
from app.core.special_weeks import ultra_long_run
from app.core.workout_ladders import get_workout_at_level
from app.core.workouts import get_workout_library

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/demo-programs'
MONDAY = date(2026, 10, 19)
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


def beginner_marathon(**overrides):
    args = dict(goal_type='race', goal_distance='marathon', target_time_seconds=16200,
                current_weekly_mileage=30, peak_weekly_mileage=30, experience_level='beginner',
                days_per_week=4, rest_days=['monday', 'wednesday', 'friday'], long_run_day='saturday',
                easy_pace_seconds=660, start_date=MONDAY, first_prescribe_date=MONDAY, num_weeks=2,
                completed_weeks=[30] * 4, weekly_run_days=[4] * 4, recent_long_run_miles=11,
                race_date=MONDAY + timedelta(weeks=16, days=6), deload_is_due=False)
    return generate_plan(**(args | overrides))


def advanced(distance='5k', weeks_out=10, **overrides):
    args = dict(goal_type='race', goal_distance=distance, target_time_seconds=1020 if distance == '5k' else 10740,
                current_weekly_mileage=50, peak_weekly_mileage=60, experience_level='advanced',
                days_per_week=6, rest_days=['sunday'], long_run_day='saturday', easy_pace_seconds=480,
                start_date=MONDAY, first_prescribe_date=MONDAY, num_weeks=2, completed_weeks=[50] * 4,
                weekly_run_days=[6] * 4, race_date=MONDAY + timedelta(weeks=weeks_out, days=5))
    return generate_plan(**(args | overrides))


def runs(week):
    return [d for d in week['days'] if d['distance_miles'] > 0]


def doc_weeks(name):
    """{week number: (phase, miles, [(weekday, title, miles)])} from a demo document."""
    weeks, current = {}, None
    for line in (DOCS / f'{name}.md').read_text().splitlines():
        if m := re.match(r'### Week (\d+) · .* · (.+) · ([\d.]+) mi$', line):
            current = weeks.setdefault(int(m[1]), (m[2], float(m[3]), []))
        elif current and (m := re.match(r'- \*\*(\w{3}) (\w{3} \d\d)\*\* · (.+?) · ([\d.]+) mi', line)):
            current[2].append((m[1], m[2], m[3], float(m[4])))
    return weeks


# ── 1. Developing half/marathon long runs ──────────────────────

def test_developing_marathon_long_run_grows_a_mile_and_takes_about_forty_percent():
    p = beginner_marathon()
    longs = [next(d['distance_miles'] for d in w['days'] if d['type'] == 'long_run') for w in p['weeks']]
    assert longs[0] <= 11 + 1 and longs[1] <= longs[0] + 1  # ~1 mi/week from the longest recent run
    for w, long in zip(p['weeks'], longs):
        assert long / w['target_mileage'] <= developmental.LONG_RUN_SHARE['marathon'] + .01
        assert long > max(d['distance_miles'] for d in w['days'] if d['type'] == 'easy')
    big = beginner_marathon(current_weekly_mileage=45, completed_weeks=[45] * 4, recent_long_run_miles=20)
    for w in big['weeks']:  # ~3 hours at an 11:00 easy pace
        assert max(d['distance_miles'] for d in w['days'] if d['type'] == 'long_run') <= 180 * 60 / 660 + .05


def test_day_after_the_long_run_is_the_weeks_shortest_run():
    p = beginner_marathon()
    for w in p['weeks']:
        sunday = next(d for d in w['days'] if d['day'] == 'sunday')
        easy = [d['distance_miles'] for d in w['days'] if d['type'] == 'easy' and d is not sunday]
        assert sunday['type'] == 'easy'
        assert sunday['distance_miles'] <= w['target_mileage'] * developmental.DAY_AFTER_LONG_SHARE + .05
        assert sunday['distance_miles'] <= min(easy)
        assert abs(w['target_mileage'] - w['budget_miles']) <= .2  # the miles moved, they weren't dropped


def test_beginner_marathon_doc_has_no_tied_sunday_and_no_down_week_before_taper():
    weeks = doc_weeks('beginner-marathon')
    for number, (phase, miles, days) in weeks.items():
        if number == 1:
            continue  # partial first week: with no other easy day left, volume stays on the day after
        long = next((d for d in days if 'Long Run' in d[2]), None)
        sunday = next((d for d in days if d[0] == 'Sun' and d[2].startswith('Easy Run')), None)
        if long and sunday:
            assert sunday[3] <= miles * .2, (number, sunday)
    taper = min(n for n, w in weeks.items() if w[0] == 'Taper')
    peak_volume = max(w[1] for n, w in weeks.items() if n < taper)
    assert all(weeks[n][1] >= peak_volume * .9 for n in (taper - 2, taper - 1))  # no calendar down week
    longs = {n: max(d[3] for d in w[2] if 'Long Run' in d[2]) for n, w in weeks.items() if any('Long Run' in d[2] for d in w[2])}
    assert max(longs, key=lambda n: (longs[n], -n)) <= taper - 2  # longest run ≥ 3 weeks before race week


def test_outlook_targets_are_reachable_with_the_developing_long_run_share():
    for distance, share in developmental.LONG_RUN_SHARE.items():
        assert LONG_RUN_TARGETS[distance][0] <= VOLUME_TARGETS[distance][0] * share + .1
    assert all(TAPER_WEEKS[d] == taper_weeks(d) for d in TAPER_WEEKS)


# ── 2. No deload near the peak; the week back from a deload ────

@pytest.mark.parametrize('distance,weeks_out,protected', [('5k', 2, True), ('5k', 3, False),
                                                          ('marathon', 2, True), ('marathon', 4, False)])
def test_calendar_deload_is_suppressed_within_taper_plus_two_weeks(distance, weeks_out, protected):
    wp = week_phase(MONDAY, 'race', distance, MONDAY + timedelta(weeks=weeks_out, days=6))
    assert protects_peak(wp, distance) is protected


def test_due_deload_near_a_5k_peak_holds_instead_of_cutting():
    near = advanced(weeks_out=2, deload_is_due=True)
    assert not near['is_deload'] and near['load']['deload_week'] is None
    assert near['load']['mode'] == 'hold' and all(b <= 50 for b in near['load']['weekly_budgets'])
    far = advanced(weeks_out=10, deload_is_due=True)
    assert far['is_deload'] and far['load']['deload_week'] == 0


def test_first_week_back_from_a_down_week_has_one_quality_session():
    evidence = {'primary_successes': 12, 'recent_primary_successes': 4, 'long_run_successes': 4,
                'latest_long_run_feel': 7, 'dual_weeks': 4, 'recovery_days': 6, 'recovery_average': 7.5,
                'weekly_run_days': [6] * 8}
    p = advanced(deload_is_due=True, quality_evidence=evidence, num_weeks=3)
    assert p['quality_policy']['stage'] == 'dual' and p['load']['deload_week'] == 0
    assert [w['quality_sessions'] for w in p['weeks']] == [1, 1, 2]  # deload, week back, full return
    assert p['weeks'][1]['budget_miles'] >= 50  # volume is restored in the week back
    # After a completed down week the next block starts back at one session too.
    back = advanced(completed_weeks=[50, 52, 54, 40], quality_evidence=evidence)
    assert back['weeks'][0]['quality_sessions'] == 1 and back['weeks'][0]['budget_miles'] >= 50


# ── 3. Ultra / marathon taper ──────────────────────────────────

def test_100k_taper_is_three_weeks_and_peak_long_run_is_three_weeks_out():
    assert TAPER_DAYS['100k'] == 21 and TAPER_WEEKS['100k'] == 3
    race = MONDAY + timedelta(weeks=3, days=5)
    assert [w.phase for w in plan_phases(MONDAY, 4, 'race', '100k', race)] == ['peak', 'taper', 'taper', 'race_week']
    weeks = doc_weeks('trail-100k')
    race_week = next(n for n, w in weeks.items() if w[0] == 'Race Week')
    longs = {n: max(d[3] for d in w[2] if d[2] != 'RACE DAY — 100K' and 'Long Run' in d[2])
             for n, w in weeks.items() if any('Long Run' in d[2] for d in w[2])}
    assert max(longs, key=longs.get) <= race_week - 3


def test_biggest_marathon_pace_long_run_is_three_weeks_out():
    lib = get_workout_library({'easy_pace_low': 460, 'easy_pace_high': 510, 'steady_pace': 420, 'tempo_pace': 390,
                               'threshold_pace': 400, 'interval_pace': 360, 'interval_pace_fast': 350,
                               'race_pace': 360, 'strides_pace': 280, 'goal_race_pace': 410,
                               'broken_threshold_pace': 380, 'long_run_pace': 490}, 'marathon', 65)
    assert _biggest_mp_long_run(lib, 65)['name'] == 'MP Block Long Run'
    weeks = doc_weeks('sub3-marathon')
    taper = min(n for n, w in weeks.items() if w[0] == 'Taper')
    titles = {n: next(d[2] for d in w[2] if 'Long Run' in d[2]) for n, w in weeks.items() if n < taper}
    assert titles[taper - 2] == 'MP Block Long Run'
    assert titles[taper - 1] == 'Easy Long Run'
    long_miles = {n: next(d[3] for d in w[2] if 'Long Run' in d[2]) for n, w in weeks.items() if n < taper}
    assert long_miles[taper - 1] <= long_miles[taper - 2]


def test_taper_threshold_keeps_two_thirds_of_the_session():
    paces = {'tempo_pace': 395, 'broken_threshold_pace': 385, 'interval_pace': 360, 'interval_pace_fast': 350,
             'threshold_pace': 400, 'easy_pace_low': 460, 'easy_pace_high': 510}
    peak = get_workout_at_level('threshold', 8, paces, 'marathon', 'peak')
    taper = get_workout_at_level('threshold', 8, paces, 'marathon', 'taper')
    minutes = lambda w: int(re.match(r'(\d+)x(\d+)min', w['name'])[1]) * int(re.match(r'(\d+)x(\d+)min', w['name'])[2])
    assert .6 <= minutes(taper) / minutes(peak) <= .7 and taper['name'] == '2x13min Threshold'
    intro = developmental.workout(3, 660, 30, phase='taper', reduced=True)  # 12min step
    assert intro['prescription']['segments'][0]['duration_seconds'] == 8 * 60


def test_race_effort_long_run_text_does_not_say_easy_for_the_whole_run():
    wp = week_phase(MONDAY, 'race', '100k', MONDAY + timedelta(weeks=6, days=5))
    assert wp.phase == 'peak'
    day = ultra_long_run(MONDAY + timedelta(days=5), '100k', 70, wp,
                         {'easy_pace_low': 500, 'easy_pace_high': 560}, 'trail')
    assert day['title'] == 'Race-Effort Long Run'
    assert 'easy conversational effort for the first and last thirds' in day['description']
    assert '), easy conversational effort.' not in day['description']


# ── 4. Three-day beginner 5K ───────────────────────────────────

def test_three_day_5k_long_run_is_clearly_the_longest():
    p = generate_plan(goal_type='race', goal_distance='5k', target_time_seconds=1800, current_weekly_mileage=11.7,
                      peak_weekly_mileage=11.7, experience_level='beginner', days_per_week=3,
                      rest_days=['monday', 'wednesday', 'friday', 'sunday'], long_run_day='saturday',
                      easy_pace_seconds=720, start_date=MONDAY, first_prescribe_date=MONDAY, num_weeks=2,
                      completed_weeks=[11.7] * 4, weekly_run_days=[3] * 4)
    for w in p['weeks']:
        long = next(d['distance_miles'] for d in w['days'] if d['type'] == 'long_run')
        easy = max(d['distance_miles'] for d in w['days'] if d['type'] == 'easy')
        assert long >= developmental.CLEARLY_LONGEST * easy - .05
    for number, (_, miles, days) in doc_weeks('beginner-5k').items():
        long = [d[3] for d in days if 'Long Run' in d[2]]
        easy = [d[3] for d in days if d[2].startswith('Easy Run')]
        if long and easy:
            assert long[0] > max(easy), number


# ── 5. Spike guard for every experience level ──────────────────

def test_spike_guard_applies_to_advanced_runners_but_ignores_race_weeks():
    assert latest_week_is_spike([38, 40, 38, 52])
    assert not latest_week_is_spike([38, 40, 38, 52], [False, False, False, True])
    assert latest_week_is_spike([44, 44, 30, 45])
    assert not latest_week_is_spike([44, 44, 30, 45], [False, False, True, False])  # race week isn't the comparison
    spiked = plan_load(40, 60, 'advanced', 'race', 2, completed_weeks=[38, 40, 38, 52])
    assert spiked.weekly_budgets[1] == spiked.weekly_budgets[0]
    raced = plan_load(40, 60, 'advanced', 'race', 2, completed_weeks=[38, 40, 38, 52], race_weeks=[False] * 3 + [True])
    assert raced.weekly_budgets[1] > raced.weekly_budgets[0]


# ── 6. Volume gap inside build is a decision ───────────────────

def test_volume_far_below_target_in_build_requires_a_decision():
    common = dict(goal_type='race', distance='marathon', destination=None, recent_long_run=8, experience='beginner',
                  run_days_recent=[4] * 4, days_per_week=4, development_level=2, run_walk_stage=None)
    gap = goal_outlook(race_weeks_away=10, baseline=15, **common)
    assert gap['decision']['key'] == 'volume_gap' and gap['decision']['required']
    assert {o['key'] for o in gap['decision']['options']} == {'completion', 'later_race', 'shorter'}
    assert goal_outlook(race_weeks_away=30, baseline=15, **common)['decision'] is None  # still base
    assert goal_outlook(race_weeks_away=10, baseline=25, **common)['decision'] is None  # ≥50% of 38
