from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan
from app.models.user import Goal

client = TestClient(app)


def seed():
    with SessionLocal() as db:
        for i in range(1, 35):
            db.add(Activity(user_id=1, source='manual', date=datetime.now() - timedelta(days=i), distance_meters=8000,
                            duration_seconds=2700, average_pace_per_km=337.5))
        old = Plan(user_id=1, start_date=date.today().isoformat(), end_date=(date.today() + timedelta(days=1)).isoformat())
        db.add(old)
        db.commit()
        return old.id


def test_preview_does_not_activate_and_approval_is_once():
    old = seed()
    r = client.post('/api/plans/1/preview')
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft['preview'] is True
    assert client.get('/api/plans/1/current').json()['id'] == old
    assert client.get('/api/plans/1/draft').json()['id'] == draft['id']
    approved = client.post(f"/api/plans/1/drafts/{draft['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert client.get('/api/plans/1/current').json()['id'] == draft['id']
    assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 409


def test_goal_change_invalidates_preview():
    old = seed()
    draft = client.post('/api/plans/1/preview').json()
    with SessionLocal() as db:
        db.query(Goal).filter_by(active=True).one().target_time_seconds = 1200
        db.commit()
    assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 409
    assert client.get('/api/plans/1/current').json()['id'] == old


def test_lighter_supersedes_and_reduces_volume_without_pace_change():
    seed()
    a = client.post('/api/plans/1/preview').json()
    b = client.post('/api/plans/1/preview', json={'lighter': True}).json()
    assert sum(w['target_mileage'] for w in b['weeks']) < sum(w['target_mileage'] for w in a['weeks'])
    assert a['pacing_guide'] == b['pacing_guide']
    assert client.post(f"/api/plans/1/drafts/{a['id']}/approve").status_code == 409
    assert client.post(f"/api/plans/1/drafts/{b['id']}/discard").status_code == 200
    assert client.get('/api/plans/1/draft').json() is None
