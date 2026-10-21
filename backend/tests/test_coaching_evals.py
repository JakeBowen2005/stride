"""Offline coach evidence contracts and reviewed example answers.

These cases evaluate the local data/validation pipeline, not an actual model's
prose quality. Live candidate-model scoring requires a separate explicit eval run.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.core.workout_data import MI, prescription, render, segment
from app.database import SessionLocal
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.services import coaching, openai_coach

CASES = json.loads((Path(__file__).parent/'fixtures/coaching_cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=[case['id'] for case in CASES])
def test_review_receives_the_ground_truth_and_preserves_model_boundaries(monkeypatch, case):
    today = date.today()
    target = 435 if case['category'] == 'threshold' else 375
    pace = 435 if case.get('actual_category') == 'threshold' else target
    spec = segment(case['reps'], seconds=case.get('seconds'), meters=case.get('meters'),
                   fast=target if case['category'] != 'hills' else None,
                   slow=target if case['category'] != 'hills' else None,
                   recovery_seconds=120, category=case.get('segment_category'))
    data = prescription(case['category'], 'time_intervals' if case.get('seconds') else 'track_intervals',
                        [spec], program='program-v1:5k', phase=case['phase'])
    data.update(easy_pace_sec_per_mile=570, warmup=segment(meters=MI), cooldown=segment(meters=MI))
    if case.get('goal_pace'):
        data['goal_pace'] = True
    seconds = case.get('actual_seconds') or case.get('seconds') or case['meters']/MI*pace
    meters = seconds/pace*MI if case.get('actual_seconds') else case.get('meters') or seconds/pace*MI
    laps = [{'intensity':'WARMUP','distance_m':MI,'duration_s':570}]
    for i in range(case['reps']):
        laps.append({'intensity':'ACTIVE','distance_m':meters,'duration_s':seconds})
        if i < case['reps']-1:
            laps.append({'intensity':'RECOVERY','distance_m':120/570*MI,'duration_s':120})
    laps.append({'intensity':'COOLDOWN','distance_m':MI,'duration_s':570})
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=today.isoformat(), end_date=(today+timedelta(days=13)).isoformat(),
                    prescribed_from=today.isoformat(), is_active=True,
                    phases=json.dumps([{'phase':case['phase']}]),
                    load=json.dumps({'weekly_budgets':[40,40]}),
                    training_paces=json.dumps({'broken_threshold_pace':435,'threshold_pace':445,'interval_pace':375,'long_run_pace':570}))
        db.add(plan);db.flush()
        row = PlannedWorkout(plan_id=plan.id, date=today.isoformat(), day_name=today.strftime('%A').lower(),
                             week_number=1,type='workout',title='Recorded quality session',description=render(data),
                             distance_miles=7,prescription=json.dumps(data),feel_rating=case['feel'])
        activity = Activity(user_id=1, source='manual', name='Synthetic evidence', date=datetime.combine(today,datetime.min.time()).replace(hour=8),
                            distance_meters=7*MI,duration_seconds=sum(lap['duration_s'] for lap in laps),
                            workout_type='workout',splits=json.dumps(laps),feel_rating=case['feel'])
        db.add_all([row,activity]);db.flush()
        if case.get('split_recordings'):
            db.add(Activity(user_id=1,source='manual',date=activity.date-timedelta(hours=1),name='Separate warmup',
                            distance_meters=8*MI,duration_seconds=8*570,workout_type='easy'))
        if case.get('walk_after'):
            db.add(Activity(user_id=1,source='manual',date=activity.date+timedelta(hours=10),name='Later walk',
                            distance_meters=.89*MI,duration_seconds=1127,workout_type='walk',activity_subtype='walking'))
        db.commit()
        activity_id, plan_id, row_id = activity.id, plan.id, row.id
    calls = []
    def fake_advice(context, research):
        calls.append(context)
        assert context['run']['id'] == activity_id
        assert context['run']['miles'] == 7
        assert context['execution']['completion'] == case['expected_completion'] if not case['expected_off_plan'] else context['execution'] is None
        assert context['run']['athlete_feedback']['feel_1_to_10'] == case['feel']
        assert context['plan']['phases'][0]['phase'] == case['phase']
        verdict = context['deterministic_evaluation']
        if case['expected_decision']:
            assert verdict['decision'] == case['expected_decision']
            assert verdict['completion'] == case['expected_completion']
        else:
            assert verdict is None
        assert ('OFF-PLAN' in (context['run_vs_plan'] or '')) == case['expected_off_plan']
        return openai_coach.CoachAdvice(summary=case['summary'], plan_fit='insufficient_evidence' if case['feel'] is None else 'consistent',
                                       observations=[], uncertainties=[], research_ids=[], suggestions=[]), {}
    monkeypatch.setattr(settings, 'openai_api_key', 'offline-eval-placeholder')
    monkeypatch.setattr(coaching, 'request_advice', fake_advice)
    with SessionLocal() as db:
        before = db.get(PlannedWorkout, row_id).prescription
        result = coaching.review_training(1, db, activity_id=activity_id, plan_id=plan_id)
        assert result['status'] == 'ready' and not result['suggestions'] and len(calls) == 1
        assert db.get(PlannedWorkout, row_id).prescription == before
        assert db.get(PlannedWorkout, row_id).execution is None  # Read-only provisional analysis cannot apply progression.
