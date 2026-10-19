import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.plan_engine import _build_current_paces
from app.core.workout_data import execution_from_activities, render
from app.core.workout_evaluator import evaluate_workout
from app.core.workout_ladders import get_workout_at_level
from app.database import SessionLocal
from app.models.activity import Activity
from app.services.pace_calibrator import calibrate_paces

PACES = {'tempo_pace': 415, 'interval_pace': 360, 'interval_pace_fast': 350, 'long_run_pace': 540}


def activity(laps, id=1):
    return SimpleNamespace(id=id, splits=json.dumps(laps))


def run_work(p, n=None, seconds=None, meters=None, labeled=True):
    laps = [{'distance_m': 1609.34, 'duration_s': 540, 'intensity': 'WARMUP' if labeled else None}]
    for spec in p['segments']:
        target = sum(spec['pace_range_sec_per_mile'].values()) / 2
        dist = meters or spec['distance_meters'] or spec['duration_seconds'] / target * 1609.34
        dur = seconds or spec['duration_seconds'] or target * dist / 1609.34
        for _ in range(spec['reps'] if n is None else n):
            laps.extend([{'distance_m': dist, 'duration_s': dur, 'intensity': 'ACTIVE' if labeled else None},
                         {'distance_m': 300, 'duration_s': 120, 'intensity': 'RECOVERY' if labeled else None}])
    return activity(laps)


def evaluate(p, act):
    ex = execution_from_activities([act], p)
    ev = evaluate_workout(None, None, None, 'workout', None, 'label can change freely', 8, p, ex)
    return ex, ev


def test_all_program_templates_render_from_numeric_data():
    for distance in ('5k', '10k', 'half', 'marathon', '50k', '100mi', 'general'):
        for phase in ('base', 'build', 'peak', 'taper'):
            for category in ('threshold', 'intervals'):
                for level in range(1, 13):
                    w = get_workout_at_level(category, level, PACES, distance, phase)
                    assert w['structure'] == render(w['prescription'])
                    assert w['prescription']['schema_version'] == 1
                    assert all(s['reps'] > 0 and (s['distance_meters'] or s['duration_seconds']) for s in w['prescription']['segments'])
    w = get_workout_at_level('threshold', 1, PACES)
    assert w['prescription']['segments'][0]['pace_range_sec_per_mile']['fast'] == 405


def test_numeric_execution_ignores_workout_label_and_requires_full_duration():
    p = get_workout_at_level('threshold', 1, PACES)['prescription']
    ex, ev = evaluate(p, run_work(p))
    assert ex['completion'] == 1 and ev.decision == 'advance'
    assert ev.reps_prescribed == 2
    ex, ev = evaluate(p, run_work(p, seconds=300))
    assert ex['completion'] == 0 and ev.decision == 'hold'
    ex, ev = evaluate(p, run_work(p, n=1))
    assert ex['completion'] == .5 and ev.decision == 'hold'


def test_wrong_distance_combo_missing_kicker_and_multiple_workouts_cannot_advance():
    p = get_workout_at_level('intervals', 5, PACES)['prescription']
    assert evaluate(p, run_work(p, meters=400))[1].decision == 'hold'
    p = get_workout_at_level('intervals', 6, PACES)['prescription']
    act = run_work(p)
    laps = json.loads(act.splits)[:-8]  # all 800s, no 200s
    assert evaluate(p, activity(laps))[1].decision == 'hold'
    ex = execution_from_activities([act, run_work(p)], p)
    assert ex['confidence'] == 'low'


def test_manual_laps_inference_is_recorded_and_matching_is_still_required():
    p = get_workout_at_level('intervals', 1, PACES)['prescription']
    ex, ev = evaluate(p, run_work(p, labeled=False))
    assert ex['evidence_source'] == 'garmin_inferred_work_laps'
    assert ex['confidence'] == 'medium' and ev.decision == 'advance'


def test_calibration_requires_two_distinct_days_and_fresh_category_evidence():
    with SessionLocal() as db:
        def add(days, description):
            db.add(Activity(user_id=1, source='manual', date=datetime.now() - timedelta(days=days), distance_meters=8000,
                            duration_seconds=2700, has_workout_description=True, description=description))
            db.flush()
        add(1, 'threshold (6:45,6:46)')
        assert 'threshold_pace' not in calibrate_paces(1, db)
        add(4, 'threshold (6:44,6:45)')
        paces = calibrate_paces(1, db)
        assert 'threshold_pace' in paces and 'tempo_pace' not in paces and 'interval_pace' not in paces
        add(40, '6x800 (2:58,2:59,3:00)')
        add(50, '6x800 (2:58,2:59,3:00)')
        assert 'interval_pace' not in calibrate_paces(1, db)
        add(3, '6x800 (2:58,2:59,3:00)')
        assert 'interval_pace' in calibrate_paces(1, db)
        add(90, 'threshold (5:45,5:46)')
        assert calibrate_paces(1, db)['threshold_pace'] > 400


def test_mileage_and_goal_time_do_not_prove_faster_training_paces():
    a = _build_current_paces(540, None, {'race_pace': 300, 'interval_pace': 280}, 80)
    b = _build_current_paces(540, None, {'race_pace': 500, 'interval_pace': 450}, 30)
    for key in ('tempo_pace', 'threshold_pace', 'interval_pace'):
        assert a[key] == b[key]
    # Existing deliberate default tempo multiplier remains intact (rounded to 5s).
    assert a['tempo_pace'] == round(540 * .77 * .96 / 5) * 5


def test_broken_threshold_and_continuous_calibrate_independently():
    paces = _build_current_paces(540, {'threshold_pace': 405, 'tempo_pace': 430})
    broken = get_workout_at_level('threshold', 1, paces)['prescription']
    continuous = get_workout_at_level('threshold', 2, paces)['prescription']
    assert broken['segments'][0]['pace_range_sec_per_mile']['fast'] == 405
    assert continuous['segments'][0]['pace_range_sec_per_mile']['fast'] == 430


def test_broken_work_cannot_prove_a_continuous_tempo():
    p = get_workout_at_level('threshold', 2, PACES)['prescription']
    # Two 10-minute efforts do not prove a continuous 20-minute effort.
    broken = get_workout_at_level('threshold', 1, PACES)['prescription']
    assert evaluate(p, run_work(broken))[1].decision != 'advance'


def test_numeric_feedback_persists_and_recalibrates_only_five_seconds():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.plan import Plan, PlannedWorkout
    from app.models.progression import WorkoutProgression
    from app.core.workout_ladders import program_key
    today = datetime.now().date().isoformat()
    p = get_workout_at_level('threshold', 1, PACES)['prescription']
    act = run_work(p)
    laps = json.loads(act.splits)
    for lap in laps:
        if lap['intensity'] == 'ACTIVE':
            lap['distance_m'] = lap['duration_s'] / 390 * 1609.34
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=today, end_date=today, prescribed_from=today,
                    goal_snapshot=json.dumps({'distance': '5k', 'type': 'race'}))
        db.add(plan)
        db.flush()
        db.add(PlannedWorkout(plan_id=plan.id, date=today, day_name='monday', week_number=1, type='workout',
                              title='Renamed workout', description=render(p), distance_miles=6, prescription=json.dumps(p)))
        db.add(Activity(user_id=1, source='manual', date=datetime.now(), distance_meters=10000, duration_seconds=3500,
                        splits=json.dumps(laps)))
        db.add(WorkoutProgression(user_id=1, category='threshold', program_key=program_key('5k'), current_level=1))
        db.commit()
    client = TestClient(app)
    r = client.post(f'/api/plans/1/feedback/{today}', json={'feel_rating': 8})
    assert r.status_code == 200, r.text
    assert r.json()['evaluation']['decision'] == 'recalibrate'
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).one()
        assert json.loads(row.execution)['evidence_source'] == 'garmin_labeled_laps'
        state = db.query(WorkoutProgression).one()
        assert state.current_level == 1 and state.current_pace_sec == 410  # tempo base 415 -> 410; broken 405 -> 400
    r = client.post(f'/api/plans/1/feedback/{today}', json={'feel_rating': 8})
    assert r.json()['side_effects_applied'] is False
    day = client.get('/api/plans/1/current').json()['weeks'][0]['days'][0]
    assert day['prescription'] == p and day['description'] == render(p)
    assert day['session_status'] == 'completed' and day['execution']['completion'] == 1


def test_full_session_budget_and_guide_use_the_numeric_prescription():
    from app.core.plan_engine import _pacing_guide
    paces = _build_current_paces(540, {'threshold_pace': 405, 'tempo_pace': 430})
    w = get_workout_at_level('threshold', 1, paces)
    data = w['prescription']
    assert w['total_miles'] >= data['total_distance_meters'] / 1609.34
    assert w['total_miles'] - data['total_distance_meters'] / 1609.34 < .5
    assert data['warmup']['distance_meters'] == 1.5 * 1609.34
    assert _pacing_guide('9:00', paces)['threshold_reps'] == '6:45'
