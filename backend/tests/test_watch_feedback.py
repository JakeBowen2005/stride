"""Garmin's on-watch rating, measured-vs-planned run reviews, and distinct review scopes."""
import json
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.coaching import CoachingReview
from app.models.garmin import GarminConnection
from app.services import coaching, garmin, openai_coach
from tests.test_api import FakeGarmin
from tests.test_off_plan_sessions import seed_day

client = TestClient(app)


class RatedGarmin(FakeGarmin):
    """Detail payloads carry the watch's post-run self-evaluation."""
    def __init__(self, ids, rating=(75, 40)):
        super().__init__(ids)
        self.rating, self.detail_calls = rating, []

    def get_activity(self, aid):
        self.detail_calls.append(str(aid))
        feel, rpe = self.rating
        return {"summaryDTO": {"directWorkoutFeel": feel, "directWorkoutRpe": rpe}}


def test_watch_rating_maps_onto_stride_scales():
    assert garmin.watch_rating({"summaryDTO": {"directWorkoutFeel": 75, "directWorkoutRpe": 40}}) == (75, 40)
    assert garmin.watch_rating({"summaryDTO": {"directWorkoutRpe": 0}}) == (None, None)
    assert garmin.watch_rating(None) == (None, None)
    run = Activity(garmin_feel=75, garmin_rpe=40)
    assert (run.watch_feel, run.watch_effort, run.effective_feel) == (8, 4, 8)
    assert [Activity(garmin_feel=f).watch_feel for f in (0, 25, 50, 75, 100)] == [2, 4, 6, 8, 10]
    run.feel_rating = 5
    assert run.effective_feel == 5  # the app answer wins over the watch


def test_sync_reads_the_watch_rating_for_new_runs_and_checks_known_runs_once(monkeypatch):
    fake = RatedGarmin([1, 2])
    monkeypatch.setattr(garmin, "get_client", lambda: fake)
    db = SessionLocal()
    db.add(Activity(user_id=1, source="garmin", external_id="2", name="Run 2", date=datetime(2026, 8, 31, 7),
                    distance_meters=8000, duration_seconds=2700, splits='[{"distance_m": 8000, "duration_s": 2700}]'))
    db.add(GarminConnection(user_id=1, connected=True, full_sync_done=True, display_name="x",
                            last_reconciled_at=datetime.now()))
    db.commit()
    garmin.sync_garmin(1, db)
    rows = {a.external_id: a for a in db.query(Activity).all()}
    assert (rows["1"].garmin_feel, rows["1"].garmin_rpe) == (75, 40)  # new run
    assert (rows["2"].garmin_feel, rows["2"].garmin_rpe) == (75, 40)  # known run, inside the window
    calls = len(fake.detail_calls)
    garmin.sync_garmin(1, db)
    assert len(fake.detail_calls) == calls  # checked once, not on every poll
    db.close()


def _review_context(monkeypatch, **activity_fields):
    from app.config import settings
    _, today = seed_day()
    with SessionLocal() as db:
        run = db.query(Activity).one()
        for key, value in activity_fields.items():
            setattr(run, key, value)
        db.commit()
        activity_id = run.id
    monkeypatch.setattr(settings, "openai_api_key", "unit-test-secret")
    calls = []

    def request(context, sources):
        calls.append(context)
        return openai_coach.CoachAdvice(summary="ok", plan_fit="consistent", observations=[], uncertainties=[],
                                        research_ids=[], suggestions=[]), {}
    monkeypatch.setattr(coaching, "request_advice", request)
    assert client.post("/api/coaching/1/review", json={"activity_id": activity_id}).status_code == 200
    return calls[-1], activity_id


def test_run_review_uses_the_watch_rating_when_the_app_was_not_used(monkeypatch):
    ctx, _ = _review_context(monkeypatch, garmin_feel=75, garmin_rpe=40)
    feedback = ctx["run"]["athlete_feedback"]
    assert feedback["feel_1_to_10"] == 8 and feedback["feel_source"] == "watch" and feedback["effort_1_to_10"] == 4
    assert ctx["run"]["watch_self_evaluation"]["provenance"] == "garmin_watch_prompt_after_the_run"


def test_run_review_separates_measured_recovery_from_the_plan(monkeypatch):
    ctx, _ = _review_context(monkeypatch, description="Garmin laps: 3x8min threshold w/ 61s recovery")
    run = ctx["run"]
    assert run["measured_lap_summary"] == "Garmin laps: 3x8min threshold w/ 61s recovery"
    session = run["detected_session"]
    assert "measured_recovery_s" in session and "planned_recovery_s" in session and "recovery_s" not in session
    assert all("time_s" in rep and "meters" in rep for rep in session["reps"])
    assert "Never present planned rest" in openai_coach.INSTRUCTIONS
    assert "DIFFERENT jobs" in openai_coach.INSTRUCTIONS


def test_run_reviews_dont_inherit_week_reviews_but_week_reviews_see_runs():
    seed_day()
    with SessionLocal() as db:
        run = db.query(Activity).one()
        other = Activity(user_id=1, source="garmin", external_id="t0", name="Run",
                         date=run.date - timedelta(days=2), distance_meters=5 * 1609.34, duration_seconds=2700)
        db.add(other)
        db.flush()
        db.add(CoachingReview(user_id=1, plan_id=1, context_hash="w", status="ready", result=json.dumps({"summary": "Week note"})))
        db.add(CoachingReview(user_id=1, activity_id=other.id, context_hash="r", status="ready", result=json.dumps({"summary": "Run note"})))
        db.commit()
        for_run = coaching.prior_reviews(1, db, activity_id=run.id)
        for_week = coaching.prior_reviews(1, db, plan_id=999)
    assert [n["scope"] for n in for_run] == ["run"]
    assert {n["scope"] for n in for_week} == {"run", "week"}


def test_watch_rating_counts_as_fatigue_evidence():
    from app.api.plans import _recent_fatigue_assessment
    today = date.today()
    with SessionLocal() as db:
        for back in (1, 2):
            db.add(Activity(user_id=1, source="garmin", external_id=f"tired{back}", name="Run",
                            date=datetime.combine(today - timedelta(days=back), datetime.min.time()).replace(hour=7),
                            distance_meters=5 * 1609.34, duration_seconds=2700, garmin_feel=25))
        db.commit()
        assessment = _recent_fatigue_assessment(1, None, db)
    assert assessment and assessment.decision == "recovery"


def test_late_watch_rating_refreshes_and_enqueues_new_review(monkeypatch):
    from app.config import settings
    from app.models.coaching import CoachingJob
    class RecentGarmin(RatedGarmin):
        def _run(self, n, i):
            raw = super()._run(n, i)
            raw['startTimeLocal'] = datetime.combine(date.today(), datetime.min.time()).replace(hour=7).strftime('%Y-%m-%d %H:%M:%S')
            return raw
        def get_laps(self, aid):
            return [{'distance_m': 8000, 'duration_s': 2700}]
    fake = RecentGarmin([1], rating=(None, None))
    monkeypatch.setattr(garmin, 'get_client', lambda: fake)
    monkeypatch.setattr(settings, 'openai_auto_reviews', True)
    monkeypatch.setattr(garmin, 'FULL_SYNC_DELAY', 0)
    with SessionLocal() as db:
        db.add(GarminConnection(user_id=1, connected=True, full_sync_done=True, display_name='test', last_reconciled_at=datetime.now()))
        db.commit()
        garmin.sync_garmin(1, db)
        row = db.query(Activity).one()
        row.feel_notes = 'Comment written before the watch rating arrived.'
        db.commit()
        before = db.query(CoachingJob).count()
        fake.rating = (75, 40)
        garmin.sync_garmin(1, db)
        assert row.garmin_feel is None
        row.garmin_rating_checked_at = datetime.now() - timedelta(minutes=16)
        db.commit()
        garmin.sync_garmin(1, db)
        assert row.garmin_feel == 75
        assert db.query(CoachingJob).count() == before + 1
        row.date = datetime.now() - timedelta(days=8)
        row.garmin_rating_checked_at = datetime.now() - timedelta(days=1)
        assert not garmin._watch_rating_due(row)


def test_activity_feedback_without_plan_and_on_double_is_independent():
    from app.models.user import User
    from app.models.progression import WorkoutProgression
    with SessionLocal() as db:
        db.add(User(id=2, name='Other'))
        for uid, ext in [(1,'first'), (1,'second'), (2,'private')]:
            db.add(Activity(user_id=uid, source='manual', external_id=ext, name='Run', date=datetime.now(), distance_meters=3000, duration_seconds=1200))
        db.commit()
        runs = {a.external_id:a.id for a in db.query(Activity)}
    for ext, feel in [('first',8), ('second',4)]:
        r = client.post(f'/api/analysis/1/activities/{runs[ext]}/feedback', json={'feel_rating':feel, 'effort_rating':6, 'feel_notes':ext})
        assert r.status_code == 200, r.text
    assert client.post(f'/api/analysis/1/activities/{runs["private"]}/feedback',json={'feel_notes': 'Test run notes.', 'feel_rating':1}).status_code == 404
    with SessionLocal() as db:
        assert db.get(Activity,runs['first']).feel_rating == 8
        assert db.get(Activity,runs['second']).feel_rating == 4
        assert db.query(WorkoutProgression).count() == 0


def test_goal_decision_is_persisted_and_does_not_change_approved_block():
    from app.models.user import Goal
    from app.models.plan import Plan
    with SessionLocal() as db:
        goal = db.query(Goal).one()
        goal.race_date = (date.today()+timedelta(weeks=8)).isoformat()
        goal_id = goal.id
        db.commit()
    r = client.post('/api/users/1/goal/decision',json={'goal_id':goal_id,'choice':'completion'})
    assert r.status_code == 200, r.text
    assert r.json()['outlook']['decision'] is None
    with SessionLocal() as db:
        goal = db.get(Goal,goal_id)
        assert goal.intent == 'completion' and goal.target_time_seconds is None
        assert json.loads(goal.decision)['before']['target_time'] == 1020
        assert db.query(Plan).count() == 0
    assert client.post('/api/users/1/goal/decision',json={'goal_id':goal_id+100,'choice':'completion'}).status_code == 409
    assert client.post('/api/users/1/goal/decision',json={'goal_id':goal_id,'choice':'later_race','race_date':date.today().isoformat()}).status_code == 422


def test_feedback_requires_a_comment_on_both_endpoints():
    from tests.test_adaptation_edge_cases import _plan, _easy_run
    _plan([(0, "easy", "Easy Run", 4.0)])
    _easy_run(0, 4)
    today = date.today().isoformat()
    assert client.post(f"/api/plans/1/feedback/{today}", json={}).status_code == 422
    assert client.post(f"/api/plans/1/feedback/{today}", json={"feel_notes": "  "}).status_code == 422
    with SessionLocal() as db:
        run_id = db.query(Activity).one().id
    r = client.post(f"/api/analysis/1/activities/{run_id}/feedback", json={"feel_rating": 8})
    assert r.status_code == 422 and "comment" in r.json()["detail"]


def test_comment_only_feedback_uses_the_watch_rating_and_queues_the_review(monkeypatch):
    from app.config import settings
    from app.models.coaching import CoachingJob
    from app.models.plan import PlannedWorkout
    from tests.test_adaptation_edge_cases import _plan, _easy_run
    monkeypatch.setattr(settings, "openai_auto_reviews", True)
    _plan([(0, "easy", "Easy Run", 4.0), (2, "workout", "Threshold", 6.0)])
    _easy_run(0, 4)
    with SessionLocal() as db:
        run = db.query(Activity).one()
        run.garmin_feel, run.garmin_rpe, run.feel_rating = 25, 80, None  # watch: weak, effort 8
        db.commit()
    today = date.today().isoformat()
    r = client.post(f"/api/plans/1/feedback/{today}", json={"feel_notes": "Felt flat, legs heavy all run."})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        run = db.query(Activity).one()
        assert run.feel_notes == "Felt flat, legs heavy all run." and run.feel_rating is None  # no invented app rating
        job = db.query(CoachingJob).one()
        assert job.status == "queued" and job.activity_id == run.id  # review starts now, not after a sync
        nxt = db.query(PlannedWorkout).filter_by(date=(date.today() + timedelta(days=2)).isoformat()).one()
        assert nxt.type == "easy"  # the watch's "weak" rating (4/10) still triggers the recovery rule


def test_run_review_context_carries_comment_watch_rating_and_garmin_metrics(monkeypatch):
    ctx, _ = _review_context(monkeypatch, garmin_feel=75, garmin_rpe=40, feel_notes="Reps felt smooth, recoveries short.",
                             training_load=120.0, training_effect_label="LACTATE_THRESHOLD", average_cadence=86)
    run = ctx["run"]
    assert run["athlete_feedback"]["notes"] == "Reps felt smooth, recoveries short."
    assert run["athlete_feedback"]["feel_1_to_10"] == 8 and run["athlete_feedback"]["effort_1_to_10"] == 4
    assert run["garmin_metrics"]["training_load"] == 120.0 and run["garmin_metrics"]["cadence_spm"] == 172
    assert "respond to it directly" in openai_coach.INSTRUCTIONS
    assert "never ask for one" in openai_coach.INSTRUCTIONS
