from datetime import date

from app.api.plans import _load_progression_state, _update_progression_from_evaluation
from app.core.workout_ladders import get_workout_at_level, program_key
from app.database import SessionLocal
from app.models.progression import WorkoutProgression


def test_each_distance_and_phase_has_content():
    paces = {'tempo_pace': 410, 'interval_pace': 360}
    for distance in ('5k', '10k', 'half', 'marathon', '50k', '100mi', 'general'):
        sessions = [get_workout_at_level('threshold', 6, paces, distance, p) for p in ('base', 'build', 'peak', 'taper')]
        assert sessions[0]['structure'] != sessions[1]['structure']
        assert sessions[3]['total_miles'] < sessions[1]['total_miles']
        assert sessions[0]['program_key'] == program_key(distance)
    assert get_workout_at_level('intervals', 6, paces, '5k')['structure'] != get_workout_at_level('intervals', 6, paces, 'marathon')['structure']
    for distance in ('5k', '10k', 'half', 'marathon'):
        assert get_workout_at_level('threshold' if distance in ('half', 'marathon') else 'intervals', 6, paces, distance, 'peak')['structure'] != get_workout_at_level('threshold' if distance in ('half', 'marathon') else 'intervals', 6, paces, distance, 'build')['structure']


def test_goal_transition_keeps_recent_pace_not_level_and_old_feedback_is_scoped():
    with SessionLocal() as db:
        db.add(WorkoutProgression(user_id=1, category='threshold', program_key=program_key('5k'), current_level=9,
                                  current_pace_sec=400, last_workout_date=date.today()))
        db.flush()
        new = _load_progression_state(1, db, 'marathon')
        assert new['threshold']['current_level'] == 1
        assert new['threshold']['current_pace_sec'] == 400
        _update_progression_from_evaluation(1, 'threshold', 'advance', 'old workout', date.today().isoformat(), None, db, program_key('5k'))
        assert _load_progression_state(1, db, 'marathon')['threshold']['current_level'] == 1
        assert _load_progression_state(1, db, '5k')['threshold']['current_level'] == 10


def test_legacy_levels_belong_only_to_5k():
    with SessionLocal() as db:
        db.add(WorkoutProgression(user_id=1, category='intervals', current_level=7))
        db.flush()
        assert _load_progression_state(1, db, 'half')['intervals']['current_level'] == 1
        assert _load_progression_state(1, db, '5k')['intervals']['current_level'] == 7
