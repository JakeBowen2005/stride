import json
from datetime import date

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.coaching import CoachingReview, CoachingAttempt
from app.models.plan import Plan, PlannedWorkout
from app.services import coaching, openai_coach
from tests.test_openai_coaching import seed, fake, review

client = TestClient(app)


def test_explicit_effort_and_completion_reach_model_with_report_provenance(monkeypatch):
    plan, act, _ = seed(); calls = fake(monkeypatch)
    with SessionLocal() as db:
        p = db.get(Plan, plan); p.start_date = p.prescribed_from = date.today().isoformat()
        db.add(PlannedWorkout(plan_id=plan, date=date.today().isoformat(), day_name='today', week_number=1,
            type='workout', title='Controlled effort', distance_miles=5, feedback_activity_id=act,
            effort_rating=8, reported_completion=json.dumps({'status': 'partial', 'minutes': 8, 'source': 'self_reported'})))
        db.commit()
    assert review(plan, act).json()['status'] == 'ready'
    feedback = calls[0]['run']['athlete_feedback']
    assert feedback['effort_1_to_10'] == 8
    assert feedback['reported_completion']['status'] == 'partial'
    assert feedback['provenance'] == 'athlete_report'
    with SessionLocal() as db:
        stored = db.query(CoachingReview).one()
        snapshot = json.loads(stored.input_snapshot)
        assert snapshot['context']['run']['athlete_feedback'] == feedback
        assert db.query(CoachingAttempt).one().input_snapshot == stored.input_snapshot
        assert db.query(CoachingAttempt).one().status == 'ready'
        assert stored.input_revision is not None
        assert 'unit-test-secret' not in stored.input_snapshot
        assert 'Private location' not in stored.input_snapshot


def test_saved_review_get_reuses_expensive_context_without_model_or_menu_calls(monkeypatch):
    plan, act, _ = seed(); calls = fake(monkeypatch)
    first = review(plan, act).json()
    assert first['status'] == 'ready'
    monkeypatch.setattr(coaching, '_build_context', lambda *args: (_ for _ in ()).throw(AssertionError('Rebuilt cached context')))
    for _ in range(2):
        assert client.get(f'/api/coaching/1/latest?activity_id={act}').json()['stale'] is False
    assert len(calls) == 1


def test_only_supplied_historical_insights_can_be_displayed(monkeypatch):
    plan, act, _ = seed(); fake(monkeypatch)
    def request(context, sources):
        return openai_coach.CoachAdvice(summary='The recorded history provides context.', plan_fit='consistent',
            observations=[], uncertainties=[], research_ids=[], suggestions=[],
            history_insight_ids=['historical-long-run']), {}
    monkeypatch.setattr(coaching, 'request_advice', request)
    result = review(plan, act).json()
    assert result['status'] == 'ready'
    assert result['history_insights'][0]['activity_ids'] == [act]
    assert 'current' in result['history_insights'][0]['text']


def test_invented_historical_evidence_rejects_model_output(monkeypatch):
    plan, act, _ = seed(); fake(monkeypatch)
    def request(context, sources):
        return openai_coach.CoachAdvice(summary='Unsupported history.', plan_fit='consistent', observations=[],
            uncertainties=[], research_ids=[], suggestions=[], history_insight_ids=['some-other-athlete']), {}
    monkeypatch.setattr(coaching, 'request_advice', request)
    result = review(plan, act).json()
    assert result['status'] == 'fallback' and result['history_insights'] == []


def test_changed_effort_invalidates_saved_analysis(monkeypatch):
    plan, act, _ = seed(); fake(monkeypatch)
    with SessionLocal() as db:
        row = PlannedWorkout(plan_id=plan, date=date.today().isoformat(), day_name='today', week_number=1,
            type='easy', title='Easy', distance_miles=5, feedback_activity_id=act, effort_rating=5)
        db.add(row); db.commit(); row_id = row.id
    assert review(plan, act).json()['status'] == 'ready'
    with SessionLocal() as db:
        db.get(PlannedWorkout, row_id).effort_rating = 9; db.commit()
    assert client.get(f'/api/coaching/1/latest?activity_id={act}').json()['stale'] is True


def test_reparsing_original_fit_uses_no_provider_and_preserves_feedback(monkeypatch):
    from tests.test_history_ingestion import FakeGarmin, tiny_fit, setup_client
    from app.services import garmin
    fake_client = FakeGarmin([1]); fake_client.get_fit = lambda _: tiny_fit()
    setup_client(monkeypatch, fake_client)
    with SessionLocal() as db:
        garmin.sync_garmin(1, db)
        a = db.query(Activity).one(); a.splits = '[]'; a.feel_rating = 8; db.commit()
    monkeypatch.setattr(garmin, 'get_client', lambda: (_ for _ in ()).throw(AssertionError('Network')))
    response = client.post('/api/analysis/1/history/reparse-fits?force=true')
    assert response.status_code == 200 and response.json()['reparsed'] == 1
    with SessionLocal() as db:
        a = db.query(Activity).one()
        assert a.feel_rating == 8 and json.loads(a.splits)[0]['duration_s'] == 360
