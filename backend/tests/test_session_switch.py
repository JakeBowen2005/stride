"""Switch two days by hand, beginner threshold vs intervals, and long-run length rules."""
import json
from datetime import datetime, timedelta

import pytest

from app.core import developmental
from app.database import SessionLocal
from app.models.plan import Plan, PlannedWorkout
from app.models.user import User
from app.models.activity import Activity
from tests.test_adaptive_sessions import client, menu, seed


def week(plan_id):
    with SessionLocal() as db:
        return {r.date: (r.type, r.distance_miles, bool(r.b2b), r.adjustment_note)
                for r in db.query(PlannedWorkout).filter_by(plan_id=plan_id)}


def switch(day, target):
    preview = client.get(f'/api/plans/1/sessions/{day}/switch-targets')
    choices = preview.json().get('targets', []) if preview.status_code == 200 else []
    token = next((t.get('token') for t in choices if t['date'] == target.isoformat()), None)
    return client.post(f'/api/plans/1/sessions/{day}', json={'action': 'switch', 'target_date': target.isoformat(), 'switch_token': token})


def test_rest_day_override_survives_reload_and_followup_edits():
    plan, monday = seed()
    fri, sat = (monday + timedelta(days=i) for i in (4, 5))
    assert switch(sat, fri).status_code == 200
    assert client.get('/api/plans/1/current').status_code == 200
    # Independent HTTP requests use fresh sessions, as after a page reload/restart.
    response = client.post(f'/api/plans/1/sessions/{monday + timedelta(days=2)}', json={'action': 'skip'})
    assert response.status_code == 200, response.text
    options = menu(monday + timedelta(days=1), 'threshold').json()['options']
    assert options
    response = client.post(f'/api/plans/1/sessions/{monday + timedelta(days=1)}',
                           json={'action': 'replace', 'replacement': 'threshold', 'option_id': options[0]['id']})
    assert response.status_code == 200, response.text
    assert switch(fri, sat).status_code == 200
    with SessionLocal() as db:
        assert db.get(User, 1).rest_days == 'friday'
        assert all(monday.isoformat() <= d <= (monday + timedelta(days=6)).isoformat()
                   for d in json.loads(db.get(Plan, plan).load)['rest_date_overrides'])


@pytest.mark.parametrize('kind', ['long_run', 'easy'])
def test_switch_counts_completed_long_run_before_block(kind):
    plan, monday = seed()
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source='manual', date=datetime.combine(monday - timedelta(days=3), datetime.min.time()),
                        workout_type=kind, distance_meters=10 * 1609.34, duration_seconds=5700))
        db.commit()
    before = week(plan)
    sat, tue = monday + timedelta(days=5), monday + timedelta(days=1)
    targets = client.get(f'/api/plans/1/sessions/{sat}/switch-targets').json()['targets']
    target = next(t for t in targets if t['date'] == tue.isoformat())
    assert not target['ok'] and '4 days apart' in target['reason']
    assert switch(sat, tue).status_code == 409
    assert week(plan) == before


def test_long_run_switch_allows_five_day_gap():
    _, monday = seed()
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source='manual', date=datetime.combine(monday - timedelta(days=4), datetime.min.time()),
                        workout_type='long_run', distance_meters=10 * 1609.34, duration_seconds=5700))
        db.commit()
    response = switch(monday + timedelta(days=5), monday + timedelta(days=1))
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('phase', ['taper', 'race_week'])
def test_switch_is_reduce_only_in_taper_and_race_week(phase):
    plan, monday = seed(phase=phase)
    if phase == 'race_week':
        with SessionLocal() as db:
            race = db.query(PlannedWorkout).filter_by(plan_id=plan, type='long_run').one()
            race.type, race.title, race.distance_miles = 'race', '5K Race', 3.1
            db.commit()
    before = week(plan)
    tue, thu = monday + timedelta(days=1), monday + timedelta(days=3)
    targets = client.get(f'/api/plans/1/sessions/{tue}/switch-targets').json()['targets']
    assert targets and all(not t['ok'] and 'taper and race week' in t['reason'] for t in targets)
    assert switch(tue, thu).status_code == 409
    assert week(plan) == before
    # Reduce-only still permits recovery actions.
    for action in ({'action': 'replace', 'replacement': 'easy'}, {'action': 'skip'}):
        response = client.post(f'/api/plans/1/sessions/{tue}', json=action)
        assert response.status_code == 200, response.text


@pytest.mark.parametrize('change', ['session', 'availability', 'activity', 'classification', 'midnight', 'missing_token'])
def test_switch_rejects_stale_or_missing_approval(change, monkeypatch):
    plan, monday = seed()
    tue, wed, thu = (monday + timedelta(days=i) for i in (1, 2, 3))
    target = next(t for t in client.get(f'/api/plans/1/sessions/{tue}/switch-targets').json()['targets']
                  if t['date'] == wed.isoformat())
    assert target['ok'] and len(target['changes']) == 2
    with SessionLocal() as db:
        if change == 'session':
            rows = {r.date: r for r in db.query(PlannedWorkout).filter_by(plan_id=plan)}
            for key in ('type', 'title', 'distance_miles', 'prescription'):
                setattr(rows[thu.isoformat()], key, getattr(rows[tue.isoformat()], key))
            rows[thu.isoformat()].title = '6x800m'
        elif change == 'availability':
            db.get(User, 1).day_time_budgets = json.dumps({'wednesday': 90})
        elif change == 'activity':
            db.add(Activity(user_id=1, source='manual', date=datetime.combine(monday - timedelta(days=1), datetime.min.time()),
                            workout_type='easy', distance_meters=1609.34, duration_seconds=600))
        elif change == 'classification':
            db.query(Activity).first().workout_type = 'workout'
        db.commit()
    if change == 'midnight':
        from app.api import plans
        today = plans.athlete_today()
        monkeypatch.setattr(plans, 'athlete_today', lambda: today + timedelta(days=1))
    before = week(plan)
    response = client.post(f'/api/plans/1/sessions/{tue}', json={'action': 'switch', 'target_date': wed.isoformat(),
                           'switch_token': None if change == 'missing_token' else target['token']})
    assert response.status_code == 409 and 'preview is out of date' in response.text, response.text
    assert week(plan) == before
    if change == 'session':
        # A fresh preview exposes all four affected days and can then be accepted.
        updated = next(t for t in client.get(f'/api/plans/1/sessions/{tue}/switch-targets').json()['targets']
                       if t['date'] == wed.isoformat())
        assert len(updated['changes']) == 4 and updated['token'] != target['token']
        response = client.post(f'/api/plans/1/sessions/{tue}', json={'action': 'switch', 'target_date': wed.isoformat(),
                               'switch_token': updated['token']})
        assert response.status_code == 200 and response.json()['changes'] == updated['changes']


def test_switch_moves_the_long_run_to_sunday_in_one_step():
    plan, monday = seed()  # Mon easy, Tue workout, Wed/Thu easy, Fri rest, Sat long 10, Sun easy 5
    sat, sun = monday + timedelta(days=5), monday + timedelta(days=6)
    r = switch(sat, sun)
    assert r.status_code == 200, r.text
    after = week(plan)
    assert after[sat.isoformat()][:2] == ('easy', 5) and after[sun.isoformat()][:2] == ('long_run', 10)
    assert 'Switched with' in after[sat.isoformat()][3] and 'Switched with' in after[sun.isoformat()][3]


def test_switch_targets_grey_out_days_that_break_hard_day_spacing():
    _, monday = seed()
    targets = client.get(f'/api/plans/1/sessions/{monday + timedelta(days=1)}/switch-targets').json()['targets']
    by_date = {t['date']: t for t in targets}
    friday = by_date[(monday + timedelta(days=4)).isoformat()]  # workout on Friday sits next to Saturday's long run
    assert friday['ok'] is False and friday['reason']
    thursday = by_date[(monday + timedelta(days=3)).isoformat()]
    assert thursday['ok'] is True and [c['date'] for c in thursday['changes']] == sorted(c['date'] for c in thursday['changes'])
    # Previewing every target wrote nothing.
    assert all(note is None for *_, note in week(_plan_id()).values())


def _plan_id():
    with SessionLocal() as db:
        return db.query(Plan).filter_by(user_id=1).one().id


def test_back_to_back_weekend_shifts_as_a_pair():
    plan, monday = seed()
    fri, sat, sun = (monday + timedelta(days=i) for i in (4, 5, 6))
    with SessionLocal() as db:
        rows = {r.date: r for r in db.query(PlannedWorkout).filter_by(plan_id=plan)}
        rows[fri.isoformat()].type, rows[fri.isoformat()].title, rows[fri.isoformat()].distance_miles = 'long_run', 'Back-to-Back Long Run (day 1, shorter)', 5
        rows[fri.isoformat()].b2b = rows[sat.isoformat()].b2b = True
        thu = rows[(monday + timedelta(days=3)).isoformat()]
        thu.type, thu.distance_miles = 'rest', 0  # keep the week inside its 35 mi budget
        db.commit()
    r = switch(sat, sun)  # "move my back-to-back to Saturday-Sunday"
    assert r.status_code == 200, r.text
    after = week(plan)
    assert after[fri.isoformat()][:3] == ('easy', 5, False)
    assert after[sat.isoformat()][:3] == ('long_run', 5, True) and after[sun.isoformat()][:3] == ('long_run', 10, True)
    # A shift that would push the pair out of the week is refused with a reason.
    targets = client.get(f'/api/plans/1/sessions/{sun}/switch-targets').json()['targets']
    assert not any(t['ok'] and t['date'] == monday.isoformat() and len(t['changes']) == 2 for t in targets)


def test_switching_onto_a_preferred_rest_day_is_the_athletes_call():
    plan, monday = seed()
    with SessionLocal() as db:
        db.get(User, 1).rest_days = 'friday'
        db.commit()
    r = switch(monday + timedelta(days=5), monday + timedelta(days=4))
    assert r.status_code == 200, r.text
    assert week(plan)[(monday + timedelta(days=4)).isoformat()][0] == 'long_run'


def test_replacing_the_long_run_with_easy_is_never_the_weeks_longest_run():
    plan, monday = seed()
    sat = monday + timedelta(days=5)
    r = client.post(f'/api/plans/1/sessions/{sat}', json={'action': 'replace', 'replacement': 'easy'})
    assert r.status_code == 200, r.text
    assert week(plan)[sat.isoformat()][:2] == ('easy', 5)


def test_beginner_long_run_options_are_at_least_an_hour_and_longer_than_easy_days():
    plan, monday = seed('beginner')
    sat = monday + timedelta(days=5)
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan, date=sat.isoformat()).one()
        row.type, row.distance_miles = 'easy', 5
        db.commit()
    body = menu(sat, 'long_run').json()
    assert body['options'], body
    for option in body['options']:
        minutes = int(option['title'].split('min')[0])
        assert minutes >= 60 and option['distance_miles'] > 5


def test_intro_threshold_and_intervals_are_different_sessions():
    pace, miles = 660, 20
    threshold = [developmental.workout(6, pace, miles, shape=s) for s in ('continuous', 'cruise', 'cruise_short')]
    intervals = [developmental.intro_intervals(6, pace, miles, shape=s) for s in ('short', 'medium', 'long')]
    threshold, intervals = [w for w in threshold if w], [w for w in intervals if w]
    assert threshold and intervals
    assert not {w['name'] for w in threshold} & {w['name'] for w in intervals}
    for w in threshold:
        seg = w['prescription']['segments'][0]
        assert '6/10' in seg['effort'] and (seg.get('recovery_seconds') or 0) <= seg['duration_seconds'] / 2
    for w in intervals:
        seg = w['prescription']['segments'][0]
        assert '8/10' in seg['effort'] and seg['recovery_seconds'] >= seg['duration_seconds'] and seg['duration_seconds'] <= 180
        assert w['prescription']['progression_eligible'] is False and w['name'].endswith('Intervals')
    # Harder effort, smaller dose.
    hard = lambda w: w['prescription']['segments'][0]['reps'] * w['prescription']['segments'][0]['duration_seconds']
    assert max(map(hard, intervals)) < max(map(hard, threshold))


def test_beginner_menu_threshold_and_intervals_do_not_overlap():
    plan, monday = seed('beginner')
    with SessionLocal() as db:
        p = db.get(Plan, plan)
        p.load = json.dumps({'weekly_budgets': [35], 'developmental': True})
        db.commit()
    tue = monday + timedelta(days=1)
    threshold, intervals = menu(tue, 'threshold').json(), menu(tue, 'intervals').json()
    assert threshold['options'] and intervals['options'], (threshold['reasons'], intervals['reasons'])
    assert not {o['title'] for o in threshold['options']} & {o['title'] for o in intervals['options']}


def test_switch_rearranges_like_a_coach_instead_of_dropping_a_workout():
    plan, monday = seed()
    tue, wed, thu = (monday + timedelta(days=i) for i in (1, 2, 3))
    with SessionLocal() as db:
        rows = {r.date: r for r in db.query(PlannedWorkout).filter_by(plan_id=plan)}
        src = rows[tue.isoformat()]
        for key in ('type', 'title', 'distance_miles', 'prescription'):
            setattr(rows[thu.isoformat()], key, getattr(src, key))
        rows[thu.isoformat()].title = '6x800m'
        db.commit()
    targets = {t['date']: t for t in client.get(f'/api/plans/1/sessions/{thu}/switch-targets').json()['targets']}
    wed_target = targets[wed.isoformat()]
    # Wednesday sits next to Tuesday's workout, so Tuesday's workout slides to Monday rather than being dropped.
    assert wed_target['ok'] and wed_target['rearranged'], wed_target
    assert switch(thu, wed).status_code == 200
    after = week(plan)
    types = [after[(monday + timedelta(days=i)).isoformat()][0] for i in range(7)]
    assert types.count('workout') == 2 and types[2] == 'workout' and types[5] == 'long_run'
    assert not any(a == b == 'workout' for a, b in zip(types, types[1:]))


def test_a_switch_never_rewrites_a_past_day():
    plan, monday = seed()
    tue, thu, fri, sat = (monday + timedelta(days=i) for i in (1, 3, 4, 5))
    with SessionLocal() as db:
        rows = {r.date: r for r in db.query(PlannedWorkout).filter_by(plan_id=plan)}
        day1 = rows[fri.isoformat()]
        day1.type, day1.title, day1.distance_miles = 'long_run', 'Back-to-Back Long Run (day 1, shorter)', 5
        day1.b2b = rows[sat.isoformat()].b2b = True
        rows[thu.isoformat()].type, rows[thu.isoformat()].distance_miles = 'rest', 0
        db.get(Plan, plan).prescribed_from = tue.isoformat()  # Monday is history
        db.commit()
    # Saturday -> Tuesday shifts the pair back four days, which would land day 1 on Monday.
    assert switch(sat, tue).status_code == 409
    targets = {t['date']: t for t in client.get(f'/api/plans/1/sessions/{sat}/switch-targets').json()['targets']}
    assert monday.isoformat() not in targets and targets[tue.isoformat()]['ok'] is False
    assert all(monday.isoformat() not in [c['date'] for c in t.get('changes', [])] for t in targets.values())


def test_switch_preview_respects_daily_time_limits():
    plan, monday = seed()
    wed, sat = monday + timedelta(days=2), monday + timedelta(days=5)
    with SessionLocal() as db:
        db.get(User, 1).day_time_budgets = json.dumps({'wednesday': 60})
        db.commit()
    targets = {t['date']: t for t in client.get(f'/api/plans/1/sessions/{sat}/switch-targets').json()['targets']}
    # A 10 mi long run doesn't fit Wednesday's 60 minutes: greyed out in the preview and refused on apply.
    assert targets[wed.isoformat()]['ok'] is False and '60 minutes' in targets[wed.isoformat()]['reason']
    assert switch(sat, wed).status_code == 409
