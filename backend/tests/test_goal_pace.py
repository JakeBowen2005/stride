"""Goal-pace / specific-endurance layer: gates, stepping, menus, ladders, dosing."""
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.goal_pace import (
    STEP_SEC,
    allows_goal_pace,
    demonstrated_race_pace,
    specific_pace,
    with_specific_pace,
)
from app.core.quality_policy import secondary_quality
from app.core.session_catalog import (
    CATALOG,
    EXPERIENCE_FLOOR,
    MAX_OPTIONS,
    MAX_SPECIFIC_FAMILIES,
    MEDIUM_LONG_SHARE,
    build_workout,
    dose_band,
    ranked_templates,
    specific_bands,
    ultra_vert_session,
)
from app.core.workout_data import MI, render
from app.core.workout_ladders import (
    get_deload_workout,
    get_workout_at_level,
    program_key,
)
from app.database import SessionLocal
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression

PACES = {'long_run_pace': 480, 'easy_pace_low': 460, 'easy_pace_high': 500, 'interval_pace': 330,
         'interval_pace_fast': 320, 'tempo_pace': 365, 'broken_threshold_pace': 355, 'threshold_pace': 360,
         'steady_pace': 385, 'strides_pace': 280}


def paces(goal, program):
    return with_specific_pace({**PACES, 'goal_race_pace': goal}, program)


def menu(category, program, phase, goal=None, *, experience='advanced', miles=50, terrain=None, deload=False):
    p = paces(goal, program)
    band = dose_band(category, experience, miles, p['broken_threshold_pace' if category == 'threshold' else 'interval_pace'], phase)
    specific = specific_bands(program, experience, miles, p, phase, deload=deload, terrain=terrain)
    seen, out = set(), []
    for t in ranked_templates(category, band, p, phase=phase, terrain=terrain, program=program,
                              specific=specific, weekly_miles=miles, week_index=3):
        if t.family not in seen:
            seen.add(t.family)
            out.append(t)
    return out[:MAX_OPTIONS], p


# ── Stepping toward goal pace ────────────────────────────────────────────────

def test_goal_pace_steps_from_demonstrated_never_jumps_and_never_overshoots():
    # 5K: demonstrated = interval pace + 5 = 335; goal 5:00 is far away -> one step only
    assert specific_pace('5k', {**PACES, 'goal_race_pace': 300}) == 335 - STEP_SEC
    # Goal within one step -> the goal itself, never faster
    assert specific_pace('5k', {**PACES, 'goal_race_pace': 332}) == 332
    # Already faster than goal -> hold goal pace
    assert specific_pace('5k', {**PACES, 'interval_pace': 300, 'goal_race_pace': 328}) == 328
    # No goal time: race-specific rhythm at current fitness, no step
    assert specific_pace('5k', PACES) == 335
    # Marathon anchors on threshold evidence (T + 20)
    assert demonstrated_race_pace('marathon', PACES) == 375
    assert specific_pace('marathon', {**PACES, 'goal_race_pace': 360}) == 370


def test_calibrated_goal_pace_reps_move_the_next_step():
    before = specific_pace('5k', {**PACES, 'goal_race_pace': 300})
    after = specific_pace('5k', {**PACES, 'goal_race_pace': 300, 'race_pace_5k': before})
    assert after == before - STEP_SEC
    # Evidence for another distance never leaks across goals
    assert specific_pace('5k', {**PACES, 'goal_race_pace': 300, 'race_pace_marathon': 250}) == before


def test_goal_pace_phase_gates():
    assert allows_goal_pace('5k', 'peak') and allows_goal_pace('10k', 'peak')
    assert not any(allows_goal_pace('5k', ph) for ph in ('base', 'build', 'taper', 'race_week', 'recovery', 'general'))
    assert allows_goal_pace('marathon', 'build') and allows_goal_pace('marathon', 'peak')
    assert not allows_goal_pace('marathon', 'base') and not allows_goal_pace('5k', 'peak', deload=True)
    assert not allows_goal_pace('half', 'peak') and not allows_goal_pace('100k', 'peak')
    assert with_specific_pace(PACES, 'mileage')['specific_pace'] is None


# ── Replace menu ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('program,goal', [('5k', 320), ('10k', 340)])
def test_short_race_peak_menu_leads_with_goal_pace_reps_and_keeps_a_general_shape(program, goal):
    options, p = menu('intervals', program, 'peak', goal)
    specific = [t for t in options if t.specific]
    assert 1 <= len(specific) <= MAX_SPECIFIC_FAMILIES and options[0].specific
    assert any(not t.specific for t in options)
    for t in specific:
        w = build_workout(t, p)
        seg = w['prescription']['segments'][0]
        assert seg['pace_range_sec_per_mile'] == {'fast': p['specific_pace'], 'slow': p['specific_pace']}
        assert seg['category'] == 'race_pace' and w['prescription']['goal_pace'] is True
        assert w['prescription']['progression_eligible'] is False


@pytest.mark.parametrize('phase,deload', [('build', False), ('taper', False), ('peak', True)])
def test_goal_pace_reps_stay_out_of_closed_phases(phase, deload):
    options, _ = menu('intervals', '5k', phase, 320, deload=deload)
    assert not any(t.specific for t in options)


def test_goal_pace_templates_only_for_their_goal():
    p = paces(320, '5k')
    band = dose_band('intervals', 'advanced', 50, 330, 'peak')
    wrong = ranked_templates('intervals', band, p, phase='peak', program='10k',
                             specific={'race_pace': band}, weekly_miles=50)
    assert not any('5K Goal Pace' in t.name for t in wrong)


@pytest.mark.parametrize('phase', ['build', 'peak'])
def test_marathon_threshold_menu_offers_mp_blocks_and_medium_long(phase):
    options, p = menu('threshold', 'marathon', phase, 360, miles=55)
    families = {t.family for t in options if t.specific}
    assert families and families <= {'mp_block', 'mp_continuous', 'medium_long'}
    assert any(not t.specific for t in options)
    all_ranked = ranked_templates('threshold', dose_band('threshold', 'advanced', 55, 355, phase), p, phase=phase,
                                  program='marathon', specific=specific_bands('marathon', 'advanced', 55, p, phase),
                                  weekly_miles=55)
    assert {t.family for t in all_ranked if t.specific} == {'mp_block', 'mp_continuous', 'medium_long'}
    for t in all_ranked:
        if t.family == 'medium_long':
            assert build_workout(t, p)['total_miles'] <= MEDIUM_LONG_SHARE * 55 + 0.5
    assert not any(t.specific for t in menu('threshold', 'marathon', 'base', 360)[0])


def test_trail_ultra_menu_has_vertical_and_downhill_with_climb_targets():
    options, p = menu('intervals', '100k', 'build', terrain='trail')
    specific = [t for t in options if t.specific]
    assert {t.family for t in specific} <= {'power_hike', 'downhill'} and specific
    for t in specific:
        w = build_workout(t, p)
        assert w['prescription']['vert_target_m'] > 0 and 'climbing' in w['structure']
    assert not any(t.specific for t in menu('intervals', '100k', 'build', terrain='road')[0])
    assert not any(t.specific for t in menu('intervals', '100k', 'taper', terrain='trail')[0])
    assert not any(t.family == 'downhill' for t in menu('intervals', '100k', 'base', terrain='trail')[0])


def test_specific_catalog_keys_unique_and_build():
    assert len({t.key for t in CATALOG}) == len(CATALOG)
    for t in CATALOG:
        if t.specific:
            program = next(iter(t.goals))
            w = build_workout(t, paces(330, program if program in {'5k', '10k', 'marathon'} else '5k'))
            assert w['structure'] == render(w['prescription']) and w['total_miles'] >= 3


# ── Ladders (plan engine primary sessions) ──────────────────────────────────

@pytest.mark.parametrize('distance', ['5k', '10k'])
def test_short_race_peak_ladder_is_goal_pace_reps_not_generic_800s(distance):
    p = paces(300, distance)
    for level in range(1, 13):
        w = get_workout_at_level('intervals', level, p, distance, 'peak')
        seg = w['prescription']['segments'][0]
        assert 'Goal Pace' in w['name'] and w['prescription']['goal_pace'] is True
        assert seg['category'] == 'race_pace'
        assert seg['pace_range_sec_per_mile']['slow'] == p['specific_pace']
        # one step from demonstrated pace: never goal pace outright, never faster than I pace
        assert p['goal_race_pace'] < seg['pace_range_sec_per_mile']['slow'] >= p['interval_pace']
        assert w['structure'] == render(w['prescription'])
    deload = get_deload_workout('intervals', 8, p, distance, 'peak')
    assert deload['prescription']['goal_pace'] is True and deload['level'] == 4
    # Build keeps the existing VO2 ladder
    assert not get_workout_at_level('intervals', 5, p, distance, 'build')['prescription'].get('goal_pace')


def test_ladder_without_goal_time_still_race_specific_from_evidence():
    w = get_workout_at_level('intervals', 3, PACES, '5k', 'peak')
    assert w['prescription']['segments'][0]['pace_range_sec_per_mile']['slow'] == demonstrated_race_pace('5k', PACES)


# ── Secondary quality shares the menu's dose floors ─────────────────────────

def _work_minutes(workout):
    total = 0
    for seg in workout['prescription']['segments']:
        pace = seg['pace_range_sec_per_mile']['slow']
        total += seg['reps'] * (seg['duration_seconds'] or seg['distance_meters'] / MI * pace)
    return total / 60


@pytest.mark.parametrize('experience', ['beginner', 'intermediate', 'advanced', 'expert'])
@pytest.mark.parametrize('program,week,dose', [('marathon', 1, 'threshold'), ('half', 2, 'intervals'),
                                                ('marathon', 2, 'marathon_pace'), ('mileage', 1, 'threshold')])
def test_secondary_quality_reaches_the_menu_floor(experience, program, week, dose):
    p = paces(380, program)
    w = secondary_quality(p, program, 'build', week, 60, experience=experience)
    floor = EXPERIENCE_FLOOR[dose][experience]
    assert _work_minutes(w) >= floor - 0.5
    assert w['prescription']['role'] == 'secondary_quality' and w['prescription']['progression_eligible'] is False
    assert w['prescription']['dose_band']['low'] == floor
    assert w['structure'] == render(w['prescription'])


def test_secondary_marathon_pace_only_in_open_phases_and_at_the_step():
    p = paces(360, 'marathon')
    mp = secondary_quality(p, 'marathon', 'peak', 2, 55, experience='advanced')
    assert mp['prescription']['segments'][0]['pace_range_sec_per_mile']['slow'] == p['specific_pace'] == 370
    assert secondary_quality(p, 'marathon', 'build', 2, 55, experience='advanced', deload=True)['prescription']['category'] == 'intervals'
    assert secondary_quality(p, 'marathon', 'base', 2, 55, experience='advanced')['prescription']['category'] == 'threshold'


# ── Plan engine wiring ──────────────────────────────────────────────────────

READY = {'primary_successes': 6, 'recent_primary_successes': 1, 'support_successes': 4, 'recent_support_successes': 1,
         'dual_weeks': 3, 'recovery_days': 5, 'recovery_average': 8, 'long_run_successes': 2, 'latest_long_run_feel': 8,
         'weekly_run_days': [6] * 8}


def generate(distance, race_date, target, terrain=None, miles=55):
    from app.core.plan_engine import generate_plan
    return generate_plan(goal_type='race', goal_distance=distance, target_time_seconds=target,
                         current_weekly_mileage=miles, peak_weekly_mileage=70, experience_level='advanced',
                         days_per_week=6, rest_days=['friday'], long_run_day='saturday', easy_pace_seconds=480,
                         current_workout_paces={'interval_pace': 330, 'threshold_pace': 355, 'tempo_pace': 365},
                         start_date=date(2026, 10, 19), first_prescribe_date=date(2026, 10, 19),
                         completed_weeks=[miles] * 8, weekly_run_days=[6] * 8, recent_long_run_miles=16,
                         quality_evidence=READY, deload_is_due=False, race_date=race_date, terrain=terrain)


def test_plan_engine_5k_peak_prescribes_stepped_goal_pace_reps():
    plan = generate('5k', date(2026, 11, 7), 960)  # 5:09/mi goal: far below demonstrated
    assert plan['phases'][0]['phase'] == 'peak' and plan['violations'] == []
    reps = [d for w in plan['weeks'] for d in w['days'] if d['type'] == 'workout' and (d.get('prescription') or {}).get('goal_pace')]
    assert reps
    for day in reps:
        seg = day['prescription']['segments'][0]
        assert seg['pace_range_sec_per_mile']['slow'] == plan['training_paces']['specific_pace']
        assert seg['pace_range_sec_per_mile']['slow'] >= demonstrated_race_pace('5k', plan['training_paces']) - STEP_SEC


def test_plan_engine_marathon_mp_work_uses_the_step_not_goal_pace():
    plan = generate('marathon', date(2026, 11, 28), 9000)  # 5:43/mi goal, far below demonstrated MP
    assert plan['phases'][0]['phase'] in {'build', 'peak'} and plan['violations'] == []
    paces_used = plan['training_paces']
    assert paces_used['specific_pace'] > paces_used['goal_race_pace']
    text = ' '.join(d.get('description') or '' for w in plan['weeks'] for d in w['days'])
    goal = f"{int(paces_used['goal_race_pace'] // 60)}:{int(paces_used['goal_race_pace'] % 60):02d}/mi"
    assert f'at goal MP ({goal}' not in text


def test_plan_engine_trail_ultra_build_places_vertical_session():
    plan = generate('100k', date(2026, 11, 28), None, terrain='trail')
    assert plan['phases'][0]['phase'] in {'build', 'peak'} and plan['violations'] == []
    vert = [d for w in plan['weeks'] for d in w['days'] if (d.get('prescription') or {}).get('vert_target_m')]
    assert vert and all(d['prescription']['stimulus'] in {'power_hike', 'downhill'} for d in vert)
    assert ultra_vert_session('base', '100k', 'trail', PACES, 'advanced', 50, date(2026, 10, 19)) is None


# ── Evidence: goal-pace reps calibrate race pace, never interval pace ───────

def _executed_row(db, plan, day, prescription, rep_pace, activity_id):
    reps = prescription['segments'][0]['reps']
    db.add(PlannedWorkout(plan_id=plan.id, date=day, day_name='x', week_number=1, type='workout', title='gp',
                          distance_miles=7, prescription=json.dumps(prescription),
                          execution=json.dumps({'schema_version': 1, 'matched_activity_ids': [activity_id], 'confidence': 'high',
                                                'completion': 1, 'rep_paces_sec_per_mile': [rep_pace] * reps})))


def test_goal_pace_execution_calibrates_race_pace_key_only():
    from app.services.pace_calibrator import calibrate_paces
    p = get_workout_at_level('intervals', 3, paces(300, '5k'), '5k', 'peak')['prescription']
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=(date.today() - timedelta(days=20)).isoformat(), end_date=date.today().isoformat())
        db.add(plan)
        db.flush()
        for i, ago in enumerate((3, 10), start=1):
            db.add(Activity(id=i, user_id=1, source='manual', date=datetime.now() - timedelta(days=ago),
                            distance_meters=11000, duration_seconds=3600))
            _executed_row(db, plan, (date.today() - timedelta(days=ago)).isoformat(), p, 328, i)
        db.commit()
        calibrated = calibrate_paces(1, db)
    assert calibrated['race_pace_5k'] == 328
    assert 'interval_pace' not in calibrated


def test_fast_goal_pace_session_never_recalibrates_interval_pace():
    from tests.test_workout_data import run_work
    today = datetime.now().date().isoformat()
    p = get_workout_at_level('intervals', 1, paces(300, '5k'), '5k', 'peak')['prescription']
    act = run_work(p)
    laps = json.loads(act.splits)
    for lap in laps:
        if lap['intensity'] == 'ACTIVE':
            lap['duration_s'] = lap['distance_m'] / 1609.34 * 310  # well under the step
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=today, end_date=today, prescribed_from=today,
                    goal_snapshot=json.dumps({'distance': '5k', 'type': 'race'}))
        db.add(plan)
        db.flush()
        db.add(PlannedWorkout(plan_id=plan.id, date=today, day_name='monday', week_number=1, type='workout',
                              title='4x1K at 5K Goal Pace', description=render(p), distance_miles=7,
                              prescription=json.dumps(p)))
        db.add(Activity(user_id=1, source='manual', date=datetime.now(), distance_meters=11000, duration_seconds=3600,
                        splits=json.dumps(laps)))
        db.add(WorkoutProgression(user_id=1, category='intervals', program_key=program_key('5k'), current_level=1,
                                  current_pace_sec=330))
        db.commit()
    r = TestClient(__import__('app.main', fromlist=['app']).app).post(f'/api/plans/1/feedback/{today}', json={'feel_notes': 'Test run notes.', 'feel_rating': 8})
    assert r.status_code == 200, r.text
    assert r.json()['evaluation']['decision'] == 'hold'
    with SessionLocal() as db:
        assert db.query(WorkoutProgression).one().current_pace_sec == 330


# ── Replace menu through the API ────────────────────────────────────────────

def test_api_5k_peak_interval_menu_offers_stepped_goal_pace_reps():
    from tests.test_adaptive_sessions import menu as api_menu
    from tests.test_adaptive_sessions import seed
    _, day = seed(phase='peak')
    data = api_menu(day + timedelta(days=1), 'intervals').json()
    goal_pace = [o for o in data['options'] if o['prescription'].get('goal_pace')]
    assert goal_pace and data['options'][0]['prescription'].get('goal_pace')
    # Seed: interval pace 6:30 -> demonstrated 5K 6:35; goal 17:00 (5:28) -> step to 6:30, not 5:28
    assert all(o['prescription']['segments'][0]['pace_range_sec_per_mile']['slow'] == 390 for o in goal_pace)
    assert any('Goal-specific' in r for r in data['reasons'])
    assert 'steps to 6:30/mi' in goal_pace[0]['purpose']


def test_api_marathon_menus_offer_mp_work_only_when_gated(monkeypatch):
    from app.core.quality_policy import QualityPolicy
    from app.models.user import Goal
    from app.services import session_options
    from tests.test_adaptive_sessions import menu as api_menu
    from tests.test_adaptive_sessions import seed
    plan_id, day = seed(phase='peak')
    with SessionLocal() as db:
        goal = db.query(Goal).one()
        goal.race_distance, goal.target_time_seconds = 'marathon', 10740  # 2:59 -> 6:50/mi
        p = db.get(Plan, plan_id)
        p.load = json.dumps({'weekly_budgets': [45]})
        db.commit()
    threshold = api_menu(day + timedelta(days=1), 'threshold').json()['options']
    mp = [o for o in threshold if o['prescription'].get('goal_pace')]
    assert mp and any(not o['prescription'].get('goal_pace') for o in threshold)
    # Demonstrated MP = broken threshold 7:30 + 20s = 7:50 -> one step: 7:45, never 6:50
    assert all(o['prescription']['segments'][0]['pace_range_sec_per_mile']['slow'] == 465 for o in mp)

    # Single-stage athlete with a midweek workout: no MP long run
    assert not any('MP' in o['title'] for o in api_menu(day + timedelta(days=5), 'long_run').json()['options'])
    original = session_options.context_for

    def dual(*args):
        ctx = original(*args)
        ctx['quality'] = QualityPolicy('dual', 'test established dual', [], ctx['evidence'])
        return ctx
    monkeypatch.setattr(session_options, 'context_for', dual)
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan_id, type='workout').one()
        row.type, row.prescription, row.title = 'easy', None, 'easy'
        db.commit()
    long_runs = api_menu(day + timedelta(days=5), 'long_run').json()['options']
    titles = [o['title'] for o in long_runs]
    assert 'MP Finish Long Run' in titles and 'MP Block Long Run' in titles
    mp_run = next(o for o in long_runs if o['title'] == 'MP Finish Long Run')
    assert 'MP step (7:45/mi, goal 6:50/mi)' in mp_run['description']
