"""Shadow hours budgets: computed and saved with the block, never enforced."""
from datetime import datetime, timedelta

from app.athlete_clock import today
from app.database import SessionLocal
from app.models.activity import Activity
from app.services.aerobic_hours import history, longest_recent, session_caps, shadow

MI = 1609.34


def _runs(weeks=6, per_week=((6, 3000), (8, 4000), (12, 6300))):
    monday = today() - timedelta(days=today().weekday())
    with SessionLocal() as db:
        n = 0
        for w in range(1, weeks + 1):
            for i, (miles, seconds) in enumerate(per_week):
                n += 1
                db.add(Activity(user_id=1, source="garmin", external_id=f"r{n}", name="Run",
                                date=datetime.combine(monday - timedelta(weeks=w) + timedelta(days=i * 2), datetime.min.time()),
                                distance_meters=miles * MI, duration_seconds=seconds))
        db.commit()


def test_history_hours_baseline_and_sustainable():
    _runs()
    with SessionLocal() as db:
        h = history(1, db)
    assert h["miles_baseline"] == 26.0 and h["hours_baseline"] == round(13300 / 3600, 2)
    assert h["sustainable_hours"] == round(13300 / 3600, 2)


def test_session_caps_have_floors():
    assert session_caps({"miles": 3, "minutes": 30}) == {"miles": 4.0, "minutes": 40}
    assert session_caps({"miles": 15, "minutes": 140}) == {"miles": 16.5, "minutes": 154}
    assert session_caps({"miles": None, "minutes": None}) == {"miles": None, "minutes": None}


def test_shadow_flags_but_never_changes_the_block():
    _runs()
    plan = {"load": {"training_level": 26.0, "weekly_budgets": [28.0, 30.0]},
            "weeks": [{"week_number": 1, "days": [
                {"date": "2026-11-02", "type": "easy", "title": "Easy", "distance_miles": 8},
                {"date": "2026-11-07", "type": "long_run", "title": "Long Run", "distance_miles": 16},
                {"date": "2026-11-08", "type": "race", "title": "Race", "distance_miles": 26.2}]}]}
    before = repr(plan)
    with SessionLocal() as db:
        assert longest_recent(1, db)["miles"] == 12.0
        out = shadow(plan, 1, db, easy_pace=540)
    assert repr(plan) == before and out["enforced"] is False
    week = out["weeks"][0]
    assert [f["date"] for f in week["sessions_over_cap"]] == ["2026-11-07"]  # race exempt
    assert week["hours_budget"] == round(out["hours_level"] * 28 / 26, 2)
    assert any("not enforced" in n for n in out["notes"])


def test_generated_block_records_shadow_hours():
    from fastapi.testclient import TestClient
    from app.main import app
    _runs()
    r = TestClient(app).post("/api/plans/1/preview")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        from app.models.plan import Plan
        import json
        load = json.loads(db.query(Plan).order_by(Plan.id.desc()).first().load)
    assert load["shadow_hours"]["enforced"] is False and load["shadow_hours"]["weeks"]
