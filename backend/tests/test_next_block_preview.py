"""Early previews use disposable databases and frozen athlete dates."""
import json
import os
from datetime import date, datetime, timedelta

import pytest
import time_machine
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.coaching import CoachingJob
from app.models.plan import Plan, PlannedWorkout
from app.models.user import Goal, User

client = TestClient(app)
END = date(2026, 11, 1)


def seed():
    with SessionLocal() as db:
        user = db.get(User, 1)
        user.current_weekly_mileage = 30
        user.peak_weekly_mileage = 40
        user.experience_level = 'intermediate'
        user.long_run_day = 'sunday'
        db.query(Goal).filter_by(user_id=1).one().goal_type = 'general'
        plan = Plan(user_id=1, start_date='2026-10-19', end_date=str(END),
                    prescribed_from='2026-10-19', load=json.dumps({'weekly_budgets': [32, 32]}),
                    athlete_snapshot=json.dumps({'schedule_preferences': {
                        'rest_days': ['friday'], 'long_run_day': 'sunday', 'days_per_week': 6}}))
        db.add(plan)
        db.flush()
        for offset in range(14):
            day = date(2026, 10, 19) + timedelta(days=offset)
            kind = 'rest' if day.weekday() == 4 else 'long_run' if day.weekday() == 6 else 'easy'
            miles = 0 if kind == 'rest' else 12 if kind == 'long_run' else 4
            db.add(PlannedWorkout(plan_id=plan.id, date=str(day), day_name=day.strftime('%A').lower(),
                                 week_number=offset // 7 + 1, type=kind, title=kind, distance_miles=miles))
        for offset in range(1, 65):
            day = date(2026, 10, 30) - timedelta(days=offset)
            if day.weekday() == 4:
                continue
            miles = 12 if day.weekday() == 6 else 4
            db.add(Activity(user_id=1, source='manual', date=datetime.combine(day, datetime.min.time()),
                            workout_type='long_run' if day.weekday() == 6 else 'easy',
                            distance_meters=miles * 1609.34, duration_seconds=miles * 540))
        db.commit()
        return plan.id


def preview(**kwargs):
    return client.post('/api/plans/1/preview', json={'scope': 'next', 'provisional': True, **kwargs})


@pytest.mark.parametrize('today,state', [('2026-10-29', 'upcoming'), ('2026-10-30', 'available'),
    ('2026-10-31', 'available'), ('2026-11-01', 'available'), ('2026-11-02', 'available')])
def test_server_eligibility(today, state):
    with time_machine.travel(today + ' 12:00:00', tick=False):
        seed()
        current = client.get('/api/plans/1/current').json()
        assert current['next_preview']['state'] == state
        assert current['next_preview']['provisional'] == (today <= str(END))
        assert current['next_preview']['next_start'] == '2026-11-02'
        if state == 'upcoming' or today > str(END):
            assert preview().status_code == 409


def test_sunday_preview_is_inactive_and_protects_monday_after_long_run():
    with time_machine.travel('2026-11-01 19:00:00', tick=False):
        active = seed()
        response = preview()
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft['provisional'] and draft['preview_scope'] == 'next'
        assert draft['start_date'] == '2026-11-02' and draft['end_date'] == '2026-11-15'
        assert draft['weeks'][0]['days'][0]['type'] not in {'workout', 'long_run', 'race'}
        assert draft['violations'] == []
        assert any(d['date'] == '2026-11-01' for d in draft['projected_days'])
        assert client.get('/api/plans/1/current').json()['id'] == active
        assert client.get('/api/plans/1/draft').json() is None
        assert client.get('/api/plans/1/draft?scope=next').json()['id'] == draft['id']
        assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 409
        with SessionLocal() as db:
            assert not db.get(Plan, draft['id']).is_active
            assert db.query(CoachingJob).count() == 0
            assert db.query(Activity).filter(Activity.date >= datetime(2026, 10, 30)).count() == 0


def test_current_revision_does_not_destroy_next_preview_and_blocks_refresh():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        next_draft = preview().json()
        current = client.post('/api/plans/1/preview', json={'scope': 'current'})
        assert current.status_code == 200, current.text
        assert client.get('/api/plans/1/draft').json()['id'] == current.json()['id']
        assert client.get('/api/plans/1/draft?scope=next').json()['id'] == next_draft['id']
        assert client.get('/api/plans/1/current').json()['next_preview']['state'] == 'blocked'
        assert preview().status_code == 409
        client.post(f"/api/plans/1/drafts/{current.json()['id']}/discard")
        assert preview().status_code == 200


def test_final_rebuild_is_required_after_midnight_and_approvable():
    with time_machine.travel('2026-11-01 19:00:00', tick=False):
        active = seed()
        early = preview().json()
    with time_machine.travel('2026-11-02 09:00:00', tick=False):
        assert client.get('/api/plans/1/draft?scope=next').json()['stale']
        assert client.post(f"/api/plans/1/drafts/{early['id']}/approve").status_code == 409
        response = client.post('/api/plans/1/preview', json={'scope': 'next'})
        assert response.status_code == 200, response.text
        final = response.json()
        assert not final['provisional'] and final['since_preview']
        assert final['load']['baseline'] <= early['load']['baseline']
        assert all(f['target_mileage'] <= p['target_mileage'] for f, p in zip(final['weeks'], early['weeks']))
        assert client.get('/api/plans/1/current').json()['id'] == active
        approve = client.post(f"/api/plans/1/drafts/{final['id']}/approve")
        assert approve.status_code == 200, approve.text
        assert client.get('/api/plans/1/current').json()['id'] == final['id']


def test_synced_sunday_is_actual_and_not_projected_twice():
    with time_machine.travel('2026-11-01 19:00:00', tick=False):
        seed()
        with SessionLocal() as db:
            db.add(Activity(user_id=1, source='manual', date=datetime(2026, 11, 1, 8),
                            workout_type='long_run', distance_meters=12 * 1609.34, duration_seconds=6480))
            db.commit()
        response = preview()
        assert response.status_code == 200, response.text
        assert not any(d['date'] == '2026-11-01' for d in response.json()['projected_days'])


def test_goal_race_blocks_projection():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        with SessionLocal() as db:
            db.query(Goal).filter_by(user_id=1).one().race_date = '2026-11-01'
            db.commit()
        assert client.get('/api/plans/1/current').json()['next_preview']['state'] == 'blocked'
        assert preview().status_code == 409


def test_appearance_round_trip_is_user_scoped_and_does_not_stale_plan():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        early = preview().json()
        for choice in ['light', 'dark', 'system']:
            assert client.put('/api/users/1/profile', json={'theme': choice}).status_code == 200
            assert client.get('/api/users/1').json()['theme'] == choice
            assert not client.get('/api/plans/1/draft?scope=next').json()['stale']
        with SessionLocal() as db:
            db.add(User(id=2, name='Other athlete'))
            db.commit()
            assert db.get(User, 2).theme is None
        for invalid in ['dusk', '', None]:
            assert client.put('/api/users/1/profile', json={'theme': invalid}).status_code == 422
        assert client.get('/api/plans/1/draft?scope=next').json()['id'] == early['id']


def test_eligibility_uses_athlete_timezone():
    with time_machine.travel('2026-10-30T06:30:00Z', tick=False):
        seed()
        with SessionLocal() as db:
            db.get(User, 1).timezone = 'America/Los_Angeles'
            db.commit()
        # It is still Thursday in the athlete's timezone.
        assert client.get('/api/plans/1/current').json()['next_preview']['state'] == 'upcoming'
        assert preview().status_code == 409


def test_projected_baseline_and_deload_match_completed_week():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        early = preview().json()
        with SessionLocal() as db:
            for day in early['projected_days']:
                db.add(Activity(user_id=1, source='manual', date=datetime.fromisoformat(day['date']),
                                workout_type='long_run' if day['date'] == '2026-11-01' else 'easy',
                                distance_meters=day['miles'] * 1609.34, duration_seconds=day['miles'] * 540))
            db.commit()
    with time_machine.travel('2026-11-02 09:00:00', tick=False):
        response = client.post('/api/plans/1/preview', json={'scope': 'next'})
        assert response.status_code == 200, response.text
        final = response.json()
        assert final['load']['baseline'] == early['load']['baseline']
        assert final['is_deload'] == early['is_deload']


def test_lighter_choice_survives_preview_refresh_and_final_build():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        early = preview(lighter=True).json()
        assert early['lighter']
        assert preview().json()['lighter']
    with time_machine.travel('2026-11-02 09:00:00', tick=False):
        final = client.post('/api/plans/1/preview', json={'scope': 'next'}).json()
        assert final['lighter']
        assert all(f['target_mileage'] <= p['target_mileage'] for f, p in zip(final['weeks'], early['weeks']))


from tests.season_sim import profiles as season_profiles


@pytest.mark.parametrize('profile', sorted(season_profiles()) if os.environ.get('STRIDE_SEASON_FULL') else ['beg-10k', 'adv-5k', 'exp-100k'])
def test_seasons_preview_on_friday_then_build_and_approve(profile):
    from tests.season_sim import profiles, simulate
    log = simulate(profiles()[profile], preview_next=True)
    assert log['early_blocks']
    assert log['errors'] == []
    assert all(p['provisional'] for p in log['early_blocks'])
    assert any(p.get('since_preview') for p in log['blocks'])


def test_projected_long_run_spacing_is_visible_before_approval():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        # The approved block still has a Sunday long run; next block uses new preferences.
        assert client.put('/api/users/1/profile', json={'long_run_day': 'wednesday'}).status_code == 200
        response = preview()
        assert response.status_code == 200, response.text
        assert any(v['code'] == 'long_run_spacing' for v in response.json()['violations'])


def test_late_final_build_keeps_preview_window_and_diff_on_rebuild():
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        early = preview().json()
    with time_machine.travel('2026-11-05 09:00:00', tick=False):
        response = client.post('/api/plans/1/preview', json={'scope': 'next'})
        assert response.status_code == 200, response.text
        final = response.json()
        assert final['start_date'] == early['start_date'] and final['end_date'] == early['end_date']
        assert len(final['weeks']) == 2 and final['since_preview']
        lighter = client.post('/api/plans/1/preview', json={'scope': 'next', 'lighter': True}).json()
        assert lighter['since_preview'] and lighter['preview_volume_caps'] == final['preview_volume_caps']


def test_run_walk_projection_counts_this_week_without_banking_assumptions():
    from app.api.plans import _run_days_since
    with time_machine.travel('2026-10-30 12:00:00', tick=False):
        seed()
        with SessionLocal() as db:
            user = db.get(User, 1)
            user.continuous_run_minutes = 1
            user.continuous_run_set_on = '2026-10-26'
            before = user.continuous_run_minutes
            projected = _run_days_since(user, db, as_of=date(2026, 11, 2), projected_dates={'2026-10-31', '2026-11-01'})
            assert projected == [6]
            assert user.continuous_run_minutes == before
