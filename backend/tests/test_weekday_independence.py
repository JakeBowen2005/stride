"""Plan generation is anchored on date.today(), so the weekday it runs on changes how
much of week 1 is left. Whatever the weekday, a fresh block must be valid and every
unstarted week must carry the same structure. (CI also runs the whole suite frozen to
each weekday via STRIDE_TEST_DATE; see tests/conftest.py.)"""
from datetime import date, datetime, timedelta

import pytest
import time_machine
from fastapi.testclient import TestClient

from app.core.plan_validator import is_hard
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity

client = TestClient(app)
WEEK = [date(2026, 10, 19) + timedelta(days=i) for i in range(7)]  # Mon .. Sun


@pytest.mark.parametrize('day', WEEK, ids=[d.strftime('%a') for d in WEEK])
def test_fresh_block_is_valid_on_every_weekday(day):
    with time_machine.travel(datetime.combine(day, datetime.min.time()).replace(hour=9), tick=False):
        with SessionLocal() as db:
            for i in range(1, 36):
                if i % 7:
                    db.add(Activity(user_id=1, source='manual', date=datetime.now() - timedelta(days=i),
                                    distance_meters=8000, duration_seconds=2700, average_pace_per_km=337.5))
            db.commit()
        r = client.post('/api/plans/1/preview')
        assert r.status_code == 200, r.text
        draft = r.json()
        assert draft['violations'] == []
        assert draft['start_date'] == (day - timedelta(days=day.weekday())).isoformat()
        days = [d for w in draft['weeks'] for d in w['days']]
        ahead = [d for d in days if d['date'] >= day.isoformat()]
        for a, b in zip(ahead, ahead[1:]):
            assert not (is_hard(a) and is_hard(b)), (a['date'], b['date'])
        full = [w for w in draft['weeks'] if w['days'][0]['date'] >= day.isoformat()]
        assert full, 'every block has at least one unstarted week'
        quality = {sum(d['type'] == 'workout' for d in w['days']) for w in full}
        assert len(quality) == 1 and quality.pop() >= 1
        assert client.post(f"/api/plans/1/drafts/{draft['id']}/approve").status_code == 200
