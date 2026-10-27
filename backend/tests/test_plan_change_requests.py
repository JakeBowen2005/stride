"""Plain-language plan changes: ops, rules, solver, safety, approve/undo and the AI loop."""
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.request_ops import OpError, apply_ops, request_violations, solve
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.plan_change import PlanChangeRequest
from app.models.user import User
from app.services import plan_change_ai
from app.services.plan_change_ai import Constraint, Op, PlanChangeProposal

client = TestClient(app)
# Jake's default week: Mon easy, Tue intervals, Wed easy, Thu threshold, Fri rest, Sat long run, Sun easy.
WEEK = [("easy", "Easy Run", 6), ("workout", "6x800m Intervals", 8), ("easy", "Easy Run", 6),
        ("workout", "3x10min Threshold", 8), ("rest", "Rest Day", 0), ("long_run", "Long Run", 13), ("easy", "Easy Run", 5)]


def monday():
    return date.today() + timedelta(days=7 - date.today().weekday())


def seed(phases=("build", "build"), weeks=2):
    start = monday()
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=start.isoformat(), end_date=(start + timedelta(days=7 * weeks - 1)).isoformat(),
                    prescribed_from=start.isoformat(), load=json.dumps({"weekly_budgets": [50] * weeks, "baseline": 45}),
                    phases=json.dumps([{"phase": p} for p in phases[:weeks]]),
                    athlete_snapshot=json.dumps({"easy_pace_seconds": 570}))
        db.add(plan)
        db.flush()
        for w in range(weeks):
            for i, (typ, title, miles) in enumerate(WEEK):
                db.add(PlannedWorkout(plan_id=plan.id, date=(start + timedelta(days=7 * w + i)).isoformat(), day_name="x",
                                      week_number=w + 1, type=typ, title=title, distance_miles=miles))
        db.commit()
    return start


def day(start, offset):
    return (start + timedelta(days=offset)).isoformat()


def rows():
    with SessionLocal() as db:
        return {r.date: (r.type, r.title, r.distance_miles, r.adjustment_note)
                for r in db.query(PlannedWorkout).order_by(PlannedWorkout.date)}


def no_hard(start, *offsets):
    return [{"date": day(start, o), "kind": "no_hard"} for o in offsets]


# ---------------------------------------------------------------- pure ops and rules

def _days():
    start = monday()
    return [{"date": day(start, i), "type": t, "title": ti, "distance_miles": m, "week_number": 1, "editable": True,
             "description": "", "purpose": "", "warmup": None, "cooldown": None, "prescription": None, "b2b": False}
            for i, (t, ti, m) in enumerate(WEEK)]


def test_ops_refuse_unsafe_shapes():
    days = _days()
    days[6]["week_number"] = 2
    with pytest.raises(OpError) as e:
        apply_ops(days, [{"op": "swap", "date": days[5]["date"], "target_date": days[6]["date"]}])
    assert e.value.reason["code"] == "cross_week"
    with pytest.raises(OpError) as e:
        apply_ops(days, [{"op": "shorten", "date": days[1]["date"], "miles": 5}])
    assert e.value.reason["code"] == "shorten_workout"
    with pytest.raises(OpError) as e:
        apply_ops(days, [{"op": "move", "date": days[1]["date"], "target_date": days[3]["date"]}])
    assert e.value.reason["code"] == "occupied"
    days[0]["editable"] = False
    with pytest.raises(OpError) as e:
        apply_ops(days, [{"op": "skip", "date": days[0]["date"]}])
    assert e.value.reason["code"] == "locked"


def test_move_goes_earlier_and_swap_keeps_paces():
    days = _days()
    after = apply_ops(days, [{"op": "move", "date": days[3]["date"], "target_date": days[2]["date"]}])
    assert after[2]["title"] == "3x10min Threshold" and after[3]["type"] == "rest"
    after = apply_ops(days, [{"op": "swap", "date": days[3]["date"], "target_date": days[5]["date"]}])
    assert after[3]["title"] == "Long Run" and after[5]["title"] == "3x10min Threshold"
    assert sum(d["distance_miles"] for d in after) == sum(d["distance_miles"] for d in days)


def test_rules_catch_spacing_volume_and_taper():
    days = _days()
    # Long run moved to Thursday, only 4 days after last Sunday's.
    after = apply_ops(days, [{"op": "swap", "date": days[3]["date"], "target_date": days[5]["date"]}])
    reasons = request_violations(days, after, [], phases={1: "build"}, last_long_run=day(monday(), -1),
                                 constraints=[], easy_pace=570)
    assert any(r["code"] == "long_run_spacing" for r in reasons)
    ops = [{"op": "swap", "date": days[3]["date"], "target_date": days[5]["date"]}]
    reasons = request_violations(days, after, ops, phases={1: "taper"}, last_long_run=None, constraints=[], easy_pace=570)
    assert any(r["code"] == "reduce_only" for r in reasons)
    grown = [dict(d) for d in days]
    grown[0]["distance_miles"] = 9
    reasons = request_violations(days, grown, [], phases={}, last_long_run=None, constraints=[], easy_pace=570)
    assert any(r["code"] == "volume_rose" for r in reasons)


def test_solver_halloween_moves_long_run_to_thursday():
    days = _days()
    plans = solve(days, no_hard(monday(), 5, 6), rest_days={"friday"}, phases={1: "build"},
                  last_long_run=day(monday(), -2 - 5), prior_hard=set(), easy_pace=570)
    assert plans[0] == [{"op": "swap", "date": days[3]["date"], "target_date": days[5]["date"]},
                        {"op": "easy", "date": days[5]["date"]}]


def test_solver_never_stacks_and_respects_rest_day():
    days = _days()
    # No hard running Wed-Sun: both workouts and the long run must fit Mon/Tue or be eased.
    for ops in solve(days, no_hard(monday(), 2, 3, 4, 5, 6), rest_days={"friday"}, phases={1: "build"},
                     last_long_run=None, prior_hard=set(), easy_pace=570):
        after = apply_ops(days, ops)
        hard = [d["date"] for d in after if d["type"] in {"workout", "long_run"}]
        assert all((date.fromisoformat(b) - date.fromisoformat(a)).days > 1 for a, b in zip(hard, hard[1:]))
        assert after[4]["type"] == "rest"


# ---------------------------------------------------------------- the API, rules only

def test_picker_proposal_apply_and_undo():
    start = seed()
    r = client.post("/api/plans/1/requests", json={"text": "", "constraints": no_hard(start, 5, 6)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "proposed" and body["source"] == "picker"
    assert [c["date"] for c in body["changes"]] == [day(start, 3), day(start, 5)]
    assert "Week 1" in body["summary"][0]
    before = rows()
    applied = client.post(f"/api/plans/1/requests/{body['id']}/apply")
    assert applied.status_code == 200, applied.text
    after = rows()
    assert after[day(start, 3)][1] == "Long Run" and after[day(start, 5)][0] == "easy"
    assert after[day(start, 3)][3].startswith(f"Your request #{body['id']}")
    plan = client.get("/api/plans/1/current").json()
    thursday = plan["weeks"][0]["days"][3]
    assert thursday["original_prescription"]["title"] == "3x10min Threshold"
    undone = client.post(f"/api/plans/1/requests/{body['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert rows() == before
    with SessionLocal() as db:
        assert db.query(PlannedWorkout).filter_by(date=day(start, 3)).one().original_prescription is None


def test_stale_proposal_is_refused():
    start = seed()
    body = client.post("/api/plans/1/requests", json={"constraints": no_hard(start, 5, 6)}).json()
    assert client.post(f"/api/plans/1/sessions/{day(start, 0)}", json={"action": "skip"}).status_code == 200
    r = client.post(f"/api/plans/1/requests/{body['id']}/apply")
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.get(PlanChangeRequest, body["id"]).status == "stale"


def test_undo_refuses_after_a_run():
    start = seed()
    body = client.post("/api/plans/1/requests", json={"constraints": no_hard(start, 5, 6)}).json()
    assert client.post(f"/api/plans/1/requests/{body['id']}/apply").status_code == 200
    with SessionLocal() as db:
        db.add(Activity(user_id=1, source="manual", date=datetime.combine(start + timedelta(days=3), datetime.min.time()),
                        distance_meters=21000, duration_seconds=6300))
        db.commit()
    r = client.post(f"/api/plans/1/requests/{body['id']}/undo")
    assert r.status_code == 409 and "already run" in r.json()["detail"]


def test_taper_week_only_reduces():
    start = seed(phases=("taper", "race_week"))
    body = client.post("/api/plans/1/requests", json={"constraints": no_hard(start, 5)}).json()
    assert body["status"] == "proposed"
    assert {o["op"] for o in body["ops"]} <= {"easy", "skip", "shorten"}


def test_illness_is_reduce_only_and_red_flag_offers_rest():
    start = seed()
    body = client.post("/api/plans/1/requests", json={"text": "I've got a fever", "constraints": no_hard(start, 1)}).json()
    assert body["safety"] == "illness" and body["note"]
    assert body["ops"] == [{"op": "easy", "date": day(start, 1)}]
    flag = client.post("/api/plans/1/requests", json={"text": "had chest pain on my last run"}).json()
    assert flag["status"] == "safety" and "medical" in flag["note"]
    assert all(o["op"] == "skip" for o in flag["ops"])


def test_ai_unavailable_points_to_picker():
    seed()
    body = client.post("/api/plans/1/requests", json={"text": "Busy Thursday"}).json()
    assert body["status"] == "ai_unavailable"


# ---------------------------------------------------------------- the AI loop (provider mocked)

@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    calls = []

    def respond(responses):
        def fake(payload):
            calls.append(payload)
            return responses[min(len(calls) - 1, len(responses) - 1)], {"input_tokens": 3000, "output_tokens": 300}
        monkeypatch.setattr(plan_change_ai, "request", fake)
        return calls
    return respond


def proposal(kind="proposal", ops=(), constraints=(), safety="none", question=None, choices=()):
    return PlanChangeProposal(kind=kind, understood="Out Friday and Saturday night; no hard running Sat or Sun morning.",
                              constraints=[Constraint(**c, minutes=None) for c in constraints],
                              ops=[Op(**{"target_date": None, "miles": None, **o}) for o in ops],
                              question=question, choices=list(choices), safety=safety,
                              explanation="The long run moves to Thursday so the weekend stays easy.")


def test_ai_retry_after_rule_failure(ai):
    start = seed()
    cons = no_hard(start, 5, 6)
    stacked = [{"op": "swap", "date": day(start, 2), "target_date": day(start, 5)}]  # long run Wed next to Tue/Thu workouts
    good = [{"op": "swap", "date": day(start, 3), "target_date": day(start, 5)}, {"op": "easy", "date": day(start, 5)}]
    calls = ai([proposal(ops=stacked, constraints=cons), proposal(ops=good, constraints=cons)])
    body = client.post("/api/plans/1/requests", json={"text": "Halloween weekend, out Fri and Sat night"}).json()
    assert body["status"] == "proposed" and body["source"] == "ai_retry"
    assert len(calls) == 2 and calls[1]["previous_attempt"]["reasons"]
    assert "request" in calls[0] and len(json.dumps(calls[0])) < 8000  # slim context
    with SessionLocal() as db:
        row = db.get(PlanChangeRequest, body["id"])
        assert row.attempts == 2 and row.input_tokens == 6000 and json.loads(row.rejections)
    again = client.post("/api/plans/1/requests", json={"text": "Halloween weekend, out Fri and Sat night"}).json()
    assert again["cached"] and len(calls) == 2


def test_ai_falls_back_to_solver(ai):
    start = seed()
    cons = no_hard(start, 5, 6)
    bad = [{"op": "swap", "date": day(start, 4), "target_date": day(start, 5)}]  # long run onto the Friday rest day
    ai([proposal(ops=bad, constraints=cons)])
    body = client.post("/api/plans/1/requests", json={"text": "out late Fri and Sat"}).json()
    assert body["status"] == "proposed" and body["source"] == "solver"
    assert body["ops"][0] == {"op": "swap", "date": day(start, 3), "target_date": day(start, 5)}


def test_ai_safety_can_only_tighten(ai):
    start = seed()
    ai([proposal(ops=[{"op": "swap", "date": day(start, 3), "target_date": day(start, 5)}], safety="injury",
                 constraints=no_hard(start, 5))])
    body = client.post("/api/plans/1/requests", json={"text": "my shin has been barking"}).json()
    assert body["safety"] == "injury" and body["source"] == "solver"
    assert {o["op"] for o in body["ops"]} <= {"easy", "skip", "shorten"}


def test_ai_clarify_then_answer(ai):
    seed()
    calls = ai([proposal(kind="clarify", question="Which morning do you want the long run: Thursday or Sunday?",
                         choices=["Thursday", "Sunday"]), proposal(kind="no_change")])
    body = client.post("/api/plans/1/requests", json={"text": "Can I move my long run?"}).json()
    assert body["status"] == "clarifying" and body["choices"] == ["Thursday", "Sunday"]
    answered = client.post(f"/api/plans/1/requests/{body['id']}/answer", json={"answer": "Thursday"}).json()
    assert answered["status"] == "no_change" and calls[1]["answers"][0]["a"] == "Thursday"


def test_ai_out_of_scope_and_quota(ai, monkeypatch):
    seed()
    ai([proposal(kind="out_of_scope")])
    assert client.post("/api/plans/1/requests", json={"text": "add a workout Thursday"}).json()["status"] == "out_of_scope"
    monkeypatch.setattr(settings, "openai_plan_change_daily_limit", 1)
    r = client.post("/api/plans/1/requests", json={"text": "different words now"})
    assert r.status_code == 429 and "quick picker" in r.json()["detail"]


def test_requests_listed_with_remaining(ai):
    start = seed()
    ai([proposal(kind="no_change")])
    client.post("/api/plans/1/requests", json={"text": "Is my week fine?"})
    listing = client.get("/api/plans/1/requests").json()
    assert listing["ai_available"] and listing["remaining_today"] == settings.openai_plan_change_daily_limit - 1
    assert listing["requests"][0]["request_text"] == "Is my week fine?"
    assert start
