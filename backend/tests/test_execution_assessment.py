"""Dose/intent and block evidence must remain distinct from mileage adherence."""
import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.block_assessment import DayRecord, assess_block
from app.core.session_match import executed_session, off_plan, session_relationship, work_minutes
from app.core.workout_data import MI, prescription, segment
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import PlannedWorkout
from app.services.quality_history import quality_history
from tests.test_off_plan_sessions import seed_day
from tests.test_workout_data import run_work

client = TestClient(app)


def contract():
    data = prescription('threshold', 'time_intervals', [segment(3, seconds=480, fast=435, slow=435, recovery_seconds=120)])
    data['easy_pace_sec_per_mile'] = 570
    return data


def test_short_repetitions_are_partial_without_confirmed_substitution():
    planned = contract()
    done = executed_session([run_work(planned, seconds=240, meters=240 / 435 * MI)], 570)
    assert session_relationship(planned, done)['status'] == 'partial'
    assert off_plan(planned, done) is False
    assert off_plan(planned, done, substitution_confirmed=True) is True
    assert session_relationship(planned, done, substitution_confirmed=True)['intent'] == 'confirmed_substitution'


def test_mixed_segment_work_minutes_sum_each_repetition():
    planned = prescription('intervals', 'track_intervals', [segment(2, meters=400, fast=360, slow=360),
                                                          segment(1, seconds=180, fast=360, slow=360),
                                                          segment(4, seconds=20, category='strides')])
    minutes, _ = work_minutes(planned, None)
    assert minutes == round((2 * 400 / MI * 360 + 180) / 60, 1)


@pytest.mark.parametrize('old_verdict', [None, 'off_plan'])
def test_truncated_rep_evidence_cannot_hide_behind_an_old_off_plan_tag(old_verdict):
    plan_id, today = seed_day('Cut every rep short')
    planned = contract()
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan_id, date=today.isoformat()).one()
        row.title, row.prescription = '3x8min Threshold', json.dumps(planned)
        row.evaluation = json.dumps({'decision': old_verdict}) if old_verdict else None
        row.feel_rating = 6
        activity = db.query(Activity).one()
        activity.splits = run_work(planned, seconds=240, meters=240 / 435 * MI).splits
        activity.feel_rating = 6
        db.commit()
        evidence = quality_history(1, db)
        assert evidence['recent_failure'] is True
        assert evidence['primary_successes'] == 0
    result = client.post(f'/api/plans/1/feedback/{today}', json={'feel_rating': 6, 'feel_notes': 'Had to stop reps early'})
    assert result.status_code == 200, result.text
    assert result.json()['evaluation']['decision'] != 'off_plan'
    assert result.json()['evaluation']['completion'] == 0


def block(**quality):
    types = ['easy', 'workout', 'easy', 'workout', 'easy', 'long_run']
    return [DayRecord(date=(date.today()-timedelta(days=10-i)).isoformat(), type=kind,
                      planned_miles=10 if kind == 'long_run' else 5,
                      actual_miles=10 if kind == 'long_run' else 5,
                      **quality if kind == 'workout' else {}) for i, kind in enumerate(types)]


def test_easy_mileage_cannot_claim_completed_quality():
    result = assess_block(block())
    assert result.completion == 1 and result.quality_done == 0
    assert result.quality_unknown == 2 and result.decision == 'hold'
    assert result.long_runs_done == 1
    assert any('had no laps to check' in reason for reason in result.reasons)


def test_complete_quality_without_feel_is_unknown_recovery_not_bad_feel():
    result = assess_block(block(execution_complete=True, evaluation_decision='advance'))
    assert result.decision == 'build' and result.quality_done == 2
    assert result.feel_count == 0 and result.low_feels == 0


@pytest.mark.parametrize('quality', [
    {'execution_complete': False},
    {'execution_complete': True, 'evaluation_decision': 'regress'},
    {'execution_complete': True, 'session_status': 'skipped'},
    {'execution_complete': True, 'session_status': 'moved'},
])
def test_incomplete_or_uncontrolled_quality_holds_even_when_miles_are_complete(quality):
    result = assess_block(block(**quality))
    assert result.quality_done == 0 and result.quality_incomplete == 2 and result.decision == 'hold'


def test_substitution_is_separate_from_completed_prescription_and_failure():
    result = assess_block(block(substituted=True, evaluation_decision='off_plan'))
    assert result.quality_substituted == 2 and result.quality_done == 0
    assert result.quality_incomplete == 0 and result.quality_unknown == 0
    assert result.decision == 'hold'


def test_demanding_long_run_needs_hard_segment_evidence_even_when_weekday_quality_is_complete():
    records = block(execution_complete=True, evaluation_decision='advance')
    long_run = next(day for day in records if day.type == 'long_run')
    long_run.demanding_long_run = True
    result = assess_block(records)
    assert result.long_runs_done == 1  # Endurance adherence remains true.
    assert result.quality_planned == 3 and result.quality_done == 2
    assert result.quality_unknown == 1 and result.decision == 'hold'
    long_run.execution_complete = False
    long_run.evaluation_decision = 'regress'
    assert assess_block(records).decision == 'hold'
    long_run.execution_complete = True
    long_run.evaluation_decision = 'hold'
    result = assess_block(records)
    assert result.quality_done == 3 and result.decision == 'build'
