"""Multi-user prep: consent in every mode, dollar caps, terms acceptance, device attribution."""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.coaching import CoachingAttempt, CoachingReview
from app.models.user import User
from app.services import ai_budget
from app.services.garmin import parse_activity

client = TestClient(app)


def test_owner_mode_needs_consent_too():
    with SessionLocal() as db:
        db.get(User, 1).ai_consent = False
        db.commit()
    r = client.post("/api/coaching/1/review", json={})
    assert r.status_code == 403
    assert client.get("/api/coaching/1/status").json()["consent"] is False


def _spend(user_id, model, tokens_in, tokens_out):
    with SessionLocal() as db:
        review = CoachingReview(user_id=user_id, context_hash=f"h{tokens_in}{model}", status="ready", model=model)
        db.add(review)
        db.flush()
        db.add(CoachingAttempt(review_id=review.id, number=1, input_snapshot="{}", model=model, policy_version="t",
                               status="ready", input_tokens=tokens_in, output_tokens=tokens_out,
                               created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()


def test_cost_table_and_unknown_model_priced_high():
    assert ai_budget.cost("gpt-5.4-mini", 30_000, 500) == pytest.approx(0.02475)
    assert ai_budget.cost("some-new-model", 1_000_000, 0) == 5.0
    assert ai_budget.cost(None, 10, 10) == 0


def test_monthly_caps(monkeypatch):
    _spend(1, "gpt-5.4-mini", 1_000_000, 0)  # $0.75
    with SessionLocal() as db:
        assert ai_budget.spent(db, 1) == pytest.approx(0.75)
        monkeypatch.setattr(settings, "openai_owner_monthly_budget_usd", 0.5)
        with pytest.raises(HTTPException) as e:
            ai_budget.check(1, db)
        assert "allowance" in e.value.detail
        monkeypatch.setattr(settings, "openai_owner_monthly_budget_usd", 10)
        monkeypatch.setattr(settings, "openai_monthly_budget_usd", 0.7)
        with pytest.raises(HTTPException) as e:
            ai_budget.check(1, db)
        assert "app AI budget" in e.value.detail
    assert client.get("/api/coaching/1/status").json()["usage"]["spent_usd"] == pytest.approx(0.75)


def test_device_name_is_parsed_for_attribution():
    raw = {"activityId": 1, "activityType": {"typeKey": "running"}, "startTimeLocal": "2026-10-27 07:00:00",
           "distance": 8000, "duration": 2400, "deviceName": "Forerunner 965"}
    assert parse_activity(raw)["device_name"] == "Forerunner 965"
    assert parse_activity(raw | {"deviceName": None})["device_name"] is None
