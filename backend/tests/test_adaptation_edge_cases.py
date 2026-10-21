"""Adaptation edge cases: overtraining signals, bad workouts and an untrusted coach.

Follows the "Required scenario matrix" of docs/coaching-loop-reliability-plan.md.
Everything goes through the real API (feedback, session actions, plan preview,
AI review/accept), so the deterministic rules are exercised exactly as the app
applies them. The AI model is always mocked; it can only explain and pick.
"""

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.load_policy import RECOVERY_FACTOR, ramp_rate
from app.core.plan_validator import validate_plan
from app.core.workout_data import MI, prescription, segment
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.coaching import CoachingReview
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import User
from app.models.wellness import DailyWellness
from app.services import coaching, openai_coach
from tests.plan_invariants import MILES_TOLERANCE, assert_plan_invariants

client = TestClient(app)
TODAY = date.today()
EASY_PACE = 540
START_LEVEL = 5


def _contract(category: str) -> dict:
    if category == "threshold":
        p = prescription("threshold", "time_intervals", [segment(3, seconds=480, fast=400, slow=400, recovery_seconds=120)])
    else:
        p = prescription("intervals", "track_intervals", [segment(5, meters=1000, fast=360, slow=360, recovery_seconds=120)])
    p.update(warmup=segment(meters=1.5 * MI), cooldown=segment(meters=1.5 * MI))
    return p


def _plan(rows: list[tuple], budgets: list[float] | None = None) -> int:
    """rows: (offset from today, type, title, miles[, prescription]). Active, two weeks."""
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=(TODAY - timedelta(days=1)).isoformat(),
                 end_date=(TODAY + timedelta(days=12)).isoformat(), is_active=True,
                 prescribed_from=(TODAY - timedelta(days=1)).isoformat(),
                 load=json.dumps({"weekly_budgets": budgets}) if budgets else None)
        db.add(p)
        db.flush()
        for off, typ, title, miles, *contract in rows:
            db.add(PlannedWorkout(plan_id=p.id, date=(TODAY + timedelta(days=off)).isoformat(), day_name="x",
                                  week_number=1 if off < 6 else 2, type=typ, title=title, distance_miles=miles,
                                  description=title, prescription=json.dumps(contract[0]) if contract else None))
        db.get(User, 1).rest_days = ""  # fixed offsets must not land on a rest day on any test weekday
        for category in ("threshold", "intervals"):
            db.add(WorkoutProgression(user_id=1, category=category, current_level=START_LEVEL,
                                      current_pace_sec=400 if category == "threshold" else 360,
                                      sessions_at_level=0, format_rotation=0))
        db.commit()
        return p.id


def _workout_run(contract: dict, *, reps: int | None = None, pace_offset: float = 0, off: int = 0, feel=None) -> int:
    """A labeled Garmin recording of the contract: `reps` work laps at target + pace_offset s/mi."""
    s = contract["segments"][0]
    pace = s["pace_range_sec_per_mile"]["fast"] + pace_offset
    laps = [{"intensity": "WARMUP", "distance_m": 1.5 * MI, "duration_s": 1.5 * EASY_PACE}]
    n = s["reps"] if reps is None else reps
    for i in range(n):
        meters = s["distance_meters"] or s["duration_seconds"] / pace * MI
        seconds = s["duration_seconds"] or meters / MI * pace
        laps.append({"intensity": "ACTIVE", "distance_m": meters, "duration_s": seconds})
        if i < n - 1:
            laps.append({"intensity": "RECOVERY", "distance_m": 300, "duration_s": s["recovery_seconds"]})
    laps.append({"intensity": "COOLDOWN", "distance_m": 1.5 * MI, "duration_s": 1.5 * EASY_PACE})
    with SessionLocal() as db:
        a = Activity(user_id=1, source="garmin", external_id=f"w{off}-{n}-{pace_offset}", name="Workout",
                     date=datetime.combine(TODAY + timedelta(days=off), datetime.min.time()).replace(hour=7),
                     distance_meters=sum(l["distance_m"] for l in laps), duration_seconds=sum(l["duration_s"] for l in laps),
                     splits=json.dumps(laps), feel_rating=feel)
        db.add(a)
        db.commit()
        return a.id


def _easy_run(off: int, miles: float, feel=None, ext="e"):
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source="garmin", external_id=f"{ext}{off}", name="Run",
                        date=datetime.combine(TODAY + timedelta(days=off), datetime.min.time()).replace(hour=7),
                        distance_meters=miles * MI, duration_seconds=miles * EASY_PACE,
                        average_pace_per_km=EASY_PACE / 1.60934, feel_rating=feel))
        db.commit()


def _history(weekly: list[float], *, skip_last_days: int = 0):
    """Completed calendar weeks of easy running, oldest first, ending last Sunday; 6 runs a week."""
    monday = TODAY - timedelta(days=TODAY.weekday())
    with SessionLocal() as db:
        for w, miles in enumerate(weekly):
            start = monday - timedelta(weeks=len(weekly) - w)
            for i in (0, 1, 2, 3, 5, 6):
                d = start + timedelta(days=i)
                if (TODAY - d).days <= skip_last_days:
                    continue
                db.add(Activity(user_id=1, source="garmin", external_id=f"h{d}", name="Run",
                                date=datetime.combine(d, datetime.min.time()).replace(hour=7),
                                distance_meters=miles / 6 * MI, duration_seconds=miles / 6 * EASY_PACE,
                                average_pace_per_km=EASY_PACE / 1.60934))
        db.get(User, 1).experience_level = "intermediate"
        db.commit()


def _day(off: int) -> PlannedWorkout:
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(date=(TODAY + timedelta(days=off)).isoformat()).one()
        db.expunge(row)
        return row


def _progression(category: str) -> WorkoutProgression:
    with SessionLocal() as db:
        row = db.query(WorkoutProgression).filter_by(category=category).one()
        db.expunge(row)
        return row


def _feedback(off: int = 0, **body):
    r = client.post(f"/api/plans/1/feedback/{TODAY + timedelta(days=off)}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _preview() -> dict:
    r = client.post("/api/plans/1/preview", json={})
    assert r.status_code == 200, r.text
    return r.json()


# ── Bad workouts ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("category", ["threshold", "intervals"])
@pytest.mark.parametrize("reps,pace_offset,feel", [
    (None, 25, 3),  # every rep, but 25 s/mi slow and felt awful
    (None, 25, 5),  # slow and a middling feel is still a clear miss
    (1, 15, 4),     # bailed after one rep (under 60% done) and struggled
])
def test_bad_quality_session_regresses_progression(category, reps, pace_offset, feel):
    contract = _contract(category)
    _plan([(0, "workout", f"{category} session", 7, contract), (2, "easy", "Easy Run", 5)])
    _workout_run(contract, reps=reps, pace_offset=pace_offset)
    body = _feedback(feel_rating=feel)
    assert body["progression_decision"] == "regress", body["evaluation"]
    assert _progression(category).current_level == START_LEVEL - 1
    other = "intervals" if category == "threshold" else "threshold"
    assert _progression(other).current_level == START_LEVEL  # one lever, one category


@pytest.mark.parametrize("category", ["threshold", "intervals"])
@pytest.mark.parametrize("pace_offset", [0, -20])  # on target, and much faster than target
def test_partial_reps_never_advance(category, pace_offset):
    contract = _contract(category)
    for reps in range(1, contract["segments"][0]["reps"]):
        with SessionLocal() as db:
            db.query(PlannedWorkout).delete()
            db.query(Plan).delete()
            db.query(WorkoutProgression).delete()
            db.query(Activity).delete()
            db.commit()
        _plan([(0, "workout", f"{category} session", 7, contract)])
        _workout_run(contract, reps=reps, pace_offset=pace_offset)
        body = _feedback(feel_rating=10)
        assert body["progression_decision"] not in ("advance", "recalibrate"), (reps, body["evaluation"])
        prog = _progression(category)
        assert prog.current_level == START_LEVEL and prog.current_pace_sec == (400 if category == "threshold" else 360)


# ── Fatigue ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("feel", [1, 3, 4])
def test_low_feel_turns_next_unrun_hard_day_easy(feel):
    _plan([(-1, "workout", "Missed yesterday", 7, _contract("threshold")),  # the past is never rewritten
           (0, "easy", "Easy Run", 5), (2, "workout", "Threshold", 8, _contract("threshold")),
           (4, "workout", "Intervals", 7, _contract("intervals"))])
    _easy_run(0, 5)
    body = _feedback(feel_rating=feel)
    nxt = _day(2)
    assert nxt.type == "easy" and nxt.distance_miles <= 4.0
    assert json.loads(nxt.original_prescription)["title"] == "Threshold" and nxt.adjustment_note
    assert json.loads(nxt.prescription)["category"] == "easy"
    assert [c["change"] for c in body["changes"]] == ["downgraded"]
    assert _day(4).type == "workout" and _day(-1).type == "workout"  # only the next one, never the past


def test_feel_five_changes_nothing():
    _plan([(0, "easy", "Easy Run", 5), (2, "workout", "Threshold", 8, _contract("threshold"))])
    _easy_run(0, 5)
    assert _feedback(feel_rating=5)["changes"] == []
    assert _day(2).type == "workout" and _day(2).original_prescription is None


def test_two_low_feels_in_seven_days_make_the_next_block_recovery():
    _history([24, 25, 24, 25, 24, 25, 24, 25])
    _easy_run(-2, 4, feel=3, ext="low")
    _easy_run(-5, 4, feel=4, ext="low")
    plan = _preview()
    assert plan["assessment"]["decision"] == "recovery"
    assert plan["load"]["mode"] == "recovery"
    baseline = plan["load"]["baseline"]
    for w in plan["weeks"]:
        assert w["budget_miles"] <= baseline * RECOVERY_FACTOR + MILES_TOLERANCE
    current = next(w for w in plan["weeks"] if any(d["date"] == TODAY.isoformat() for d in w["days"]))
    assert not any(d["type"] == "workout" for d in current["days"] if d.get("prescribed", True))
    assert_plan_invariants(plan)


def test_low_feels_more_than_a_week_apart_are_not_a_recovery_block():
    _history([24, 25, 24, 25, 24, 25, 24, 25])
    _easy_run(-1, 4, feel=3, ext="low")
    _easy_run(-9, 4, feel=3, ext="low")  # outside the 7-day window
    assert (_preview()["assessment"] or {}).get("decision") != "recovery"


# ── Skipped and swapped sessions ────────────────────────────────────────────


def test_skipped_workout_adds_nothing_and_leaves_progression_alone():
    _plan([(0, "easy", "Easy Run", 5), (2, "workout", "Threshold", 8, _contract("threshold")),
           (3, "easy", "Easy Run", 5), (4, "easy", "Easy Run", 5)])
    r = client.post(f"/api/plans/1/sessions/{TODAY + timedelta(days=2)}", json={"action": "skip", "reason": "work trip"})
    assert r.status_code == 200, r.text
    skipped = _day(2)
    assert skipped.session_status == "skipped" and skipped.type == "rest" and skipped.distance_miles == 0
    assert _day(3).type == "easy" and _day(4).type == "easy"  # nothing squeezed in to make up for it
    assert _progression("threshold").current_level == START_LEVEL
    again = client.post(f"/api/plans/1/sessions/{TODAY + timedelta(days=2)}", json={"action": "skip"})
    assert again.status_code == 409


@pytest.mark.parametrize("feel", [2, 8])
def test_swapped_workout_is_not_judged_and_only_reschedules_on_request(feel):
    _plan([(0, "workout", "Threshold", 7, _contract("threshold")), (2, "workout", "Intervals", 7, _contract("intervals")),
           (4, "easy", "Easy Run", 5)])
    _easy_run(0, 5)
    body = _feedback(feel_rating=feel, swapped=True, actual_workout_type="easy")
    assert body["evaluation"] is None and body["changes"] == []
    assert _progression("threshold").current_level == START_LEVEL
    assert _day(2).type == "workout"  # no fatigue downgrade from a swap; the next workout stays


def test_swapped_workout_reschedules_into_a_valid_schedule():
    _plan([(0, "workout", "Threshold", 7, _contract("threshold")), (1, "easy", "Easy Run", 5), (2, "easy", "Easy Run", 5),
           (3, "easy", "Easy Run", 5), (5, "long_run", "Long Run", 10)], budgets=[45, 45])
    _easy_run(0, 4)
    body = _feedback(feel_rating=7, swapped=True, actual_workout_type="easy", desired_reschedule_type="threshold")
    moved = [c for c in body["changes"] if c["change"] == "rescheduled"]
    assert moved, body["changes"]
    with SessionLocal() as db:
        rows = db.query(PlannedWorkout).order_by(PlannedWorkout.date).all()
        days = [{"date": r.date, "type": r.type, "distance_miles": r.distance_miles, "b2b": r.b2b} for r in rows]
    # The reschedule never stacks hard days (today's easy recording counts as easy).
    assert validate_plan([{"week_number": 1, "days": days}]) == []


# ── Load spikes ─────────────────────────────────────────────────────────────


def _spike_history():
    # Last completed week doubled. The lighter week before it keeps a deload from
    # being due, so no deload week can mask how the block treats the spike.
    _history([20, 20, 20, 20, 20, 16, 20, 40])
    return _preview()


def test_mileage_spike_is_not_chased():
    plan = _spike_history()
    load = plan["load"]
    baseline = load["baseline"]  # four completed weeks, spike included
    assert baseline == pytest.approx(24, abs=0.2)
    assert load["deload_week"] is None
    assert plan["athlete"]["injury_risk"].startswith("HIGH")
    ceiling = baseline * (1 + ramp_rate(baseline, plan["athlete"]["peak_weekly_mileage"], "intermediate", "race"))
    for w in plan["weeks"]:
        scheduled = sum(d["distance_miles"] for d in w["days"])
        assert scheduled <= ceiling + MILES_TOLERANCE and scheduled < 40 * 0.8
    assert_plan_invariants(plan)


@pytest.mark.xfail(strict=True, reason=(
    "Policy gap, decision pending (Jake): the ACWR / injury_risk label from "
    "services/load_history.completed_week_load (HIGH > 1.5, MODERATE > 1.3) is recorded in the "
    "plan's athlete snapshot but generate_training_plan never acts on it, so a block right after "
    "a doubled week still builds above the four-week baseline."))
def test_high_acwr_holds_volume_at_or_below_baseline():
    plan = _spike_history()
    assert plan["athlete"]["injury_risk"].startswith("HIGH")
    assert max(plan["load"]["weekly_budgets"]) <= plan["load"]["baseline"] + MILES_TOLERANCE


# ── Wellness ───────────────────────────────────────────────────────────────


def _shape(plan: dict) -> list:
    return [plan["load"]["weekly_budgets"], plan["load"]["mode"],
            [(d["date"], d["type"], d["distance_miles"]) for w in plan["weeks"] for d in w["days"]]]


@pytest.mark.parametrize("age_days,readiness", [(2, 99), (5, 99), (2, 10)])
def test_stale_wellness_neither_implies_readiness_nor_changes_the_plan(age_days, readiness):
    _history([24, 25, 24, 25, 24, 25, 24, 25])
    without = _shape(_preview())
    with SessionLocal() as db:
        db.add(DailyWellness(user_id=1, date=(TODAY - timedelta(days=age_days)).isoformat(), sleep_score=99,
                             hrv_last_night=95 if readiness > 50 else 30, hrv_baseline_low=60, hrv_baseline_high=85,
                             resting_hr=40, readiness_score=readiness, acwr=0.9))
        db.commit()
    assert _shape(_preview()) == without
    body = client.get("/api/wellness/1?days=7").json()
    assert body["freshness"] == "stale" and body["today"] is None and body["signals"] == []


def test_missing_wellness_reports_absent_not_ready():
    body = client.get("/api/wellness/1?days=7").json()
    assert body["freshness"] == "absent" and body["today"] is None and body["signals"] == []


# ── Coach unavailable ───────────────────────────────────────────────────────


def test_coach_unavailable_still_persists_feedback_and_adjustments(monkeypatch):
    contract = _contract("intervals")
    _plan([(0, "workout", "Intervals", 7, contract), (2, "workout", "Threshold", 8, _contract("threshold"))])
    act = _workout_run(contract, pace_offset=25)
    # The only model path (OpenAI) is configured but failing.
    monkeypatch.setattr(settings, "openai_api_key", "unit-test-secret")

    def down(*a, **k):
        raise TimeoutError("openai down")

    monkeypatch.setattr(openai_coach, "request_advice", down)
    monkeypatch.setattr(coaching, "request_advice", down)
    body = _feedback(feel_rating=3, feel_notes="legs were dead")
    assert body["coach_response"]  # deterministic template, never empty
    assert body["progression_decision"] == "regress"
    assert _progression("intervals").current_level == START_LEVEL - 1
    today, nxt = _day(0), _day(2)
    assert today.feel_rating == 3 and today.feel_notes == "legs were dead" and today.evaluation
    assert nxt.type == "easy" and nxt.distance_miles <= 4.0
    with SessionLocal() as db:
        assert db.get(Activity, act).feel_rating == 3
        assert all(r.status == "fallback" for r in db.query(CoachingReview))


# ── The model can only pick server-made candidates ──────────────────────────


def _review_seed():
    """A future workout the review can offer server-validated alternatives for."""
    monday = TODAY + timedelta(days=7 - TODAY.weekday())
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=6)).isoformat(),
                 prescribed_from=monday.isoformat(), is_active=True,
                 training_paces=json.dumps({"long_run_pace": 570, "interval_pace": 390}),
                 load=json.dumps({"weekly_budgets": [30]}))
        db.add(p)
        db.flush()
        contract = prescription("threshold", "time_intervals", [segment(2, seconds=360, fast=450, slow=450, recovery_seconds=120)])
        contract.update(warmup=segment(meters=1.5 * MI), cooldown=segment(meters=1.5 * MI))
        for i, typ, miles in [(0, "workout", 6), (1, "easy", 4), (2, "easy", 4), (3, "easy", 4), (4, "rest", 0),
                              (5, "long_run", 8), (6, "rest", 0)]:
            db.add(PlannedWorkout(plan_id=p.id, date=(monday + timedelta(days=i)).isoformat(), day_name="x", week_number=1,
                                  type=typ, title="2x6min Threshold" if typ == "workout" else typ, distance_miles=miles,
                                  prescription=json.dumps(contract) if typ == "workout" else None))
        a = Activity(user_id=1, source="manual", date=datetime.combine(TODAY, datetime.min.time()), name="Run",
                     distance_meters=5 * MI, duration_seconds=2700, feel_rating=7, description="Easy run")
        db.add(a)
        db.commit()
        return p.id, a.id, monday


def _model_picks(monkeypatch, pick):
    """Mock the OpenAI call; `pick(candidates)` returns the candidate_ids the 'model' answers with."""
    monkeypatch.setattr(settings, "openai_api_key", "unit-test-secret")
    seen = []

    def request(context, sources):
        seen.append(context["candidates"])
        return openai_coach.CoachAdvice(
            summary="Mocked advice.", plan_fit="consider_change", observations=[], uncertainties=[], research_ids=[],
            suggestions=[openai_coach.Suggestion(candidate_id=c, reason="mocked") for c in pick(context["candidates"])]), {}

    monkeypatch.setattr(openai_coach, "request_advice", request)
    monkeypatch.setattr(coaching, "request_advice", request)  # coaching imports the name directly
    return seen


def _review(plan_id, act_id):
    r = client.post("/api/coaching/1/review", json={"plan_id": plan_id, "activity_id": act_id})
    assert r.status_code == 200, r.text
    return r.json()


def _workout_row(plan_id, day):
    with SessionLocal() as db:
        row = db.query(PlannedWorkout).filter_by(plan_id=plan_id, date=day.isoformat()).one()
        db.expunge(row)
        return row


@pytest.mark.parametrize("pick", [
    lambda cs: ["invented-option"],
    lambda cs: [cs[0]["id"], "invented-option"],          # one bad id poisons the whole answer
    lambda cs: [cs[0]["id"] + " "],                       # near-miss of a real id
    lambda cs: [c["id"] for c in cs if c["date"] == cs[0]["date"]][:2],  # two changes to one day
], ids=["invented", "mixed", "near-miss", "same-day-conflict"])
def test_model_answers_outside_server_candidates_are_never_offered_or_applied(monkeypatch, pick):
    plan_id, act_id, day = _review_seed()
    seen = _model_picks(monkeypatch, pick)
    data = _review(plan_id, act_id)
    assert seen and len(seen[0]) >= 2  # the server did offer real candidates
    if pick(seen[0]) == [seen[0][0]["id"]]:
        pytest.skip("only one candidate on that date: nothing conflicting to send")
    assert data["status"] == "fallback" and data["suggestions"] == []
    url = f"/api/coaching/1/reviews/{data['id']}/accept"
    for candidate_id in ["invented-option", *(c["id"] for c in seen[0])]:
        assert client.post(url, json={"candidate_id": candidate_id}).status_code in (409, 422)
    row = _workout_row(plan_id, day)
    assert row.title == "2x6min Threshold" and row.original_prescription is None and row.session_status is None


def test_only_the_model_selected_server_candidate_can_be_applied(monkeypatch):
    plan_id, act_id, day = _review_seed()
    seen = _model_picks(monkeypatch, lambda cs: [cs[0]["id"]])
    data = _review(plan_id, act_id)
    assert data["status"] == "ready"
    chosen = seen[0][0]
    assert [s["id"] for s in data["suggestions"]] == [chosen["id"]]
    url = f"/api/coaching/1/reviews/{data['id']}/accept"
    not_selected = [c["id"] for c in seen[0] if c["id"] != chosen["id"]]
    for candidate_id in ["invented-option", *not_selected]:
        assert client.post(url, json={"candidate_id": candidate_id}).status_code == 422
    assert _workout_row(plan_id, day).original_prescription is None  # rejected attempts changed nothing
    assert client.post(url, json={"candidate_id": chosen["id"]}).status_code == 200
    row = _workout_row(plan_id, day)
    if not chosen.get("session_option_id"):
        # What lands is exactly the server-built replacement, field for field.
        for key, value in chosen["replacement"].items():
            assert getattr(row, key) == value, key
    assert row.session_status == "replaced" and json.loads(row.original_prescription)["title"] == "2x6min Threshold"
