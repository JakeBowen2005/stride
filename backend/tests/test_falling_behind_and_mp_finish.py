"""Falling behind (size to what's run, then ask about the goal), developing marathon-pace finishes, deload cadence."""
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.core.load_policy import DELOAD_AFTER_WEEKS, deload_due, plan_load
from app.core.plan_engine import generate_plan
from app.core.workout_data import race_pace_miles
from app.database import SessionLocal
from app.main import app
from app.models.plan import Plan
from app.models.user import Goal

client = TestClient(app)
MONDAY = date(2026, 10, 19)
PREVIOUS = {'weekly_budgets': [65.5, 65.5], 'mode': 'build'}


def _load(completion, **kw):
    args = dict(baseline=56, peak=70, experience='advanced', goal_type='race', num_weeks=2, assessment='hold',
                completed_weeks=[62, 60, 52, 52], previous_block=PREVIOUS, completion=completion)
    return plan_load(**(args | kw))


def test_a_short_block_is_sized_to_what_was_run_not_the_unfinished_plan():
    load = _load(.80)
    assert all(55 <= b <= 56 for b in load.weekly_budgets)  # 65.5 x 0.85 = 55.7, never under the 56 average
    assert load.mode == 'reduce' and 'You ran 80%' in ' '.join(load.reasons)
    # Proportional, not one flat cut (a lower 4-week average so the floor doesn't bind)
    low = dict(baseline=45, completed_weeks=[55, 52, 40, 33])
    assert max(_load(.62, **low).weekly_budgets) < max(_load(.80, **low).weekly_budgets)


def test_a_hold_for_feel_or_quality_keeps_last_blocks_volume():
    load = _load(None)
    assert load.weekly_budgets == [65.5, 65.5] and load.mode == 'hold'


def _approved(block, start, completion):
    with SessionLocal() as db:
        db.add(Plan(user_id=1, start_date=start, end_date=(date.fromisoformat(start) + timedelta(days=13)).isoformat(),
                    block_number=block, is_active=False, assessment=json.dumps({'decision': 'hold', 'completion': completion})))
        db.commit()


def test_two_short_blocks_in_a_row_ask_about_the_goal_and_keep_answers_it():
    _approved(1, '2026-09-21', .78)
    assert client.get('/api/plans/1/outlook').json()['decision'] is None  # one short block isn't a pattern
    _approved(2, '2026-10-05', .74)
    _approved(2, '2026-10-05', .99)  # a regeneration of block 2 is not a third block...
    _approved(2, '2026-10-05', .74)  # ...and only the newest plan per block counts
    outlook = client.get('/api/plans/1/outlook').json()
    assert outlook['decision']['key'] == 'falling_behind'
    assert [o['key'] for o in outlook['decision']['options']] == ['keep', 'completion', 'later_race', 'shorter']
    kept = client.post('/api/users/1/goal/decision', json={'goal_id': outlook['goal_id'], 'choice': 'keep'})
    assert kept.status_code == 200, kept.text
    assert kept.json()['outlook']['decision'] is None
    with SessionLocal() as db:
        assert json.loads(db.query(Goal).filter_by(active=True).one().decision)['choice'] == 'keep'


def test_keep_cannot_dismiss_any_other_decision():
    goal_id = client.get('/api/plans/1/outlook').json()['goal_id']
    assert client.post('/api/users/1/goal/decision', json={'goal_id': goal_id, 'choice': 'keep'}).status_code == 422


def _marathon(experience='beginner', level=3, target=16200, monday=MONDAY + timedelta(weeks=1), **kw):
    args = dict(goal_type='race', goal_distance='marathon', target_time_seconds=target, current_weekly_mileage=26,
                peak_weekly_mileage=28, experience_level=experience, days_per_week=4,
                rest_days=['monday', 'wednesday', 'friday'], long_run_day='saturday', easy_pace_seconds=660,
                start_date=monday, first_prescribe_date=monday, num_weeks=2, completed_weeks=[24, 25, 26, 26],
                weekly_run_days=[4] * 4, deload_is_due=False, race_date=MONDAY + timedelta(weeks=12, days=6),
                progression_state={'development': {'current_level': level, 'last_completed_level': level}},
                recent_long_run_miles=10)
    return generate_plan(**(args | kw))


def _mp_weeks(plan):
    return [max([race_pace_miles(d) for d in w['days'] if d['type'] == 'long_run'], default=0) for w in plan['weeks']]


def test_developing_marathoner_with_a_time_goal_finishes_alternate_long_runs_at_goal_pace():
    plan = _marathon()
    assert plan['violations'] == []
    mp = _mp_weeks(plan)
    assert sum(1 for m in mp if m) == 1 and 2 <= max(mp) <= 3, mp
    week = plan['weeks'][[i for i, m in enumerate(mp) if m][0]]
    long = next(d for d in week['days'] if d['type'] == 'long_run')
    assert long['title'] == 'Long Run with MP Finish' and 'marathon pace (' in long['description']
    if mp.index(max(mp)) > 0:  # one lever: the MP week doesn't add volume over the week before
        assert week['budget_miles'] <= plan['weeks'][0]['budget_miles'] + .1


def test_intermediates_get_a_longer_finish_and_no_finish_without_a_time_goal_or_experience():
    assert max(_mp_weeks(_marathon('intermediate'))) >= 3
    assert max(_mp_weeks(_marathon(target=None))) == 0
    assert max(_mp_weeks(_marathon(level=1))) == 0


def test_experienced_runners_deload_every_seven_or_eight_weeks():
    assert DELOAD_AFTER_WEEKS['advanced'] == 6 and DELOAD_AFTER_WEEKS['expert'] == 7
    # Due after 6 (7) loaded weeks: the 7th (8th) week is the lighter one
    assert not deload_due([50] * 5, 'advanced')[0] and deload_due([50] * 6, 'advanced')[0]
    assert not deload_due([50] * 6, 'expert')[0] and deload_due([50] * 7, 'expert')[0]
