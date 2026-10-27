"""One "what was run" record per day: swapped long runs, the block summary and the coach agree."""
from datetime import timedelta

from app.athlete_clock import athlete_zone, day_start_utc
from app.config import settings
from app.core.session_match import pair_swaps, ran_session
from app.database import SessionLocal
from app.models.activity import Activity
from app.services import coaching, openai_coach
from tests.test_adaptation_edge_cases import TODAY, _easy_run, _plan, client


def test_distance_decides_long_vs_easy_without_quality_laps():
    assert ran_session("long_run", "Easy Long Run", 10, 3, None, False)["title"] == "Easy Run"
    assert ran_session("recovery", "Recovery Run", 3, 10, None, False) | {} == {
        "title": "Long Run", "type": "long_run", "off_plan": True, "planned_title": "Recovery Run",
        "planned_type": "recovery", "swapped_with": None}
    # Normal variation is not a different session
    assert not ran_session("long_run", "Easy Long Run", 10, 9, None, False)["off_plan"]
    assert not ran_session("easy", "Easy Run", 5, 7, None, False)["off_plan"]
    # 6 on a 3-mile recovery day is a longer easy run, not a stand-in for a 10-mile long run
    assert not ran_session("recovery", "Recovery Run", 3, 6, None, False, week_long_run_miles=10)["off_plan"]
    assert ran_session("recovery", "Recovery Run", 3, 10, None, False, week_long_run_miles=10)["type"] == "long_run"


def test_swaps_pair_only_nearby_days():
    days = [{"date": "2026-10-24", "session": ran_session("long_run", "Easy Long Run", 10, 3, None, False)},
            {"date": "2026-10-25", "session": ran_session("recovery", "Recovery Run", 3, 10, None, False)}]
    pair_swaps(days)
    assert [d["session"]["swapped_with"] for d in days] == ["2026-10-25", "2026-10-24"]
    far = [{"date": "2026-10-20", "session": ran_session("long_run", "Long Run", 10, 3, None, False)},
           {"date": "2026-10-25", "session": ran_session("easy", "Easy Run", 3, 10, None, False)}]
    pair_swaps(far)
    assert far[0]["session"]["swapped_with"] is None


def _swapped_week():
    _plan([(-1, "long_run", "Easy Long Run", 10.0), (0, "recovery", "Recovery Run", 3.0), (2, "workout", "3x1200m Intervals", 6.0)])
    _easy_run(-1, 3)
    _easy_run(0, 10)


def test_plan_payload_and_block_summary_show_the_swap():
    _swapped_week()
    plan = client.get("/api/plans/1/current").json()
    days = {d["date"]: d for w in plan["weeks"] for d in w["days"]}
    sat, sun = days[(TODAY - timedelta(days=1)).isoformat()], days[TODAY.isoformat()]
    assert (sat["actual"]["session"]["title"], sat["actual"]["session"]["swapped_with"]) == ("Easy Run", sun["date"])
    assert (sun["actual"]["session"]["title"], sun["actual"]["session"]["type"]) == ("Long Run", "long_run")
    assert sat["title"] == "Easy Long Run"  # the prescription itself is untouched
    assert sun["comparison"]["distance_diff_miles"] == 0  # 10 vs the long run's 10, not "+7 over"
    assert sat["comparison"]["distance_diff_miles"] == 0
    week = plan["expectations"][0]
    sessions = {s["date"]: s for s in week["priority_sessions"]}
    assert sat["date"] not in sessions  # the 3-mile day is no longer the week's long run
    long_run = sessions[sun["date"]]
    assert long_run["completed"] and long_run["title"] == "Long Run" and long_run["swapped_with"] == sat["date"]
    assert long_run["planned_title"] == "Recovery Run" and long_run["ran_miles"] == 10
    assert not sessions[(TODAY + timedelta(days=2)).isoformat()]["completed"]
    assert week["completed_days"] == 2 and week["ran_miles"] == 13


def test_coach_judges_the_swapped_long_run_as_a_long_run(monkeypatch):
    _swapped_week()
    monkeypatch.setattr(settings, "openai_api_key", "unit-test-secret")
    calls = []
    monkeypatch.setattr(coaching, "request_advice", lambda context, sources: (calls.append(context), (
        openai_coach.CoachAdvice(summary="ok", plan_fit="consistent", observations=[], uncertainties=[],
                                 research_ids=[], suggestions=[]), {}))[1])
    with SessionLocal() as db:
        sunday = db.query(Activity).filter(Activity.distance_meters > 15000).one().id
    assert client.post("/api/coaching/1/review", json={"activity_id": sunday}).status_code == 200
    ctx = calls[-1]
    assert "ran this as Long Run" in ctx["run_vs_plan"] and "swapped with" in ctx["run_vs_plan"]
    ran = {s["date"]: s["ran_as"] for s in ctx["plan"]["sessions"]}
    assert ran[TODAY.isoformat()]["type"] == "long_run"


def test_ai_allowance_resets_at_the_athletes_midnight_and_says_so(monkeypatch):
    from app.models.coaching import CoachingReview
    with athlete_zone("America/Los_Angeles"):
        start = day_start_utc()
    with athlete_zone("Asia/Tokyo"):
        assert day_start_utc() != start  # local midnight, not one UTC boundary for everyone
    monkeypatch.setattr(settings, "openai_coach_daily_limit", 2)
    with SessionLocal() as db:
        for _ in range(2):
            db.add(CoachingReview(user_id=1, context_hash=f"h{_}", status="ready", model="m", attempts=1, result="{}"))
        db.commit()
        try:
            coaching._check_ai_budget(1, db, True)
            raise AssertionError("limit not enforced")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 429 and "2 of 2 today" in exc.detail and "midnight" in exc.detail


def test_each_run_of_the_day_carries_its_own_comment_and_watch_rating():
    _plan([(0, "easy", "Easy Run + Strides", 5.0)])
    _easy_run(0, 5)
    _easy_run(0, 2, ext="second")
    with SessionLocal() as db:
        first, second = sorted(db.query(Activity).all(), key=lambda a: -a.distance_meters)
        first.feel_notes, second.garmin_feel, second.garmin_rpe = "recovered nicely", 50, 10
        db.commit()
    day = next(d for w in client.get("/api/plans/1/current").json()["weeks"] for d in w["days"] if d["date"] == TODAY.isoformat())
    assert day["actual"]["notes"] == "recovered nicely"
    extra = day["actual"]["other_runs"][0]
    assert extra["notes"] is None and (extra["watch_feel"], extra["watch_effort"]) == (6, 1)


def test_block_review_offers_refresh_only_after_a_new_run_arrives(monkeypatch):
    from datetime import datetime, timezone
    from app.models.coaching import CoachingReview
    from app.services.history_evidence import capture, source_for
    plan_id = _plan([(0, "easy", "Easy Run", 5.0)])
    with SessionLocal() as db:
        db.add(CoachingReview(user_id=1, plan_id=plan_id, context_hash="h", status="ready", model="m", attempts=1,
                              result='{"summary":"ok","suggestions":[]}', created_at=datetime.now(timezone.utc)))
        db.commit()
    latest = lambda: client.get(f"/api/coaching/1/latest?plan_id={plan_id}").json()
    assert latest()["new_run_since"] is False
    _easy_run(0, 4, ext="late")
    with SessionLocal() as db:
        run = db.query(Activity).filter_by(external_id="late0").one()
        capture(source_for(run, "garmin", run.external_id, db), "summary", db, payload={"id": 1})
        db.commit()
    assert latest()["new_run_since"] is True
