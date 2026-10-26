"""One lever at a time for race-pace long runs, and simple time-based bookends.

Decided Oct 26 2026 (docs/demo-plan-audit.md, judgement calls 3 and 4): the week a
marathon-pace long-run segment is introduced, or grows materially, holds weekly volume
and mileage rises the week after; time-based warmups and cooldowns read in 5 minutes.
"""
import re

import app.api.plans as plans_api
from app.core import plan_engine
from app.core.load_policy import RACE_PACE_STEP_MILES, race_pace_step
from app.core.quality_policy import format_bookends
from app.core.workout_data import MI, long_run_prescription, race_pace_miles, segment
from tests.plan_invariants import MILES_TOLERANCE, plan_invariant_violations
from tests.test_plan_invariants_matrix import _plan, _profile, _seed_and_plan, _week


def _seed_sub3(monkeypatch):
    """Seed the sub-3 demo and keep the engine inputs the API used, to replay them."""
    calls = []
    real = plans_api.generate_plan
    monkeypatch.setattr(plans_api, "generate_plan", lambda **kw: calls.append(kw) or real(**kw))
    plan, completed = _seed_and_plan(_profile("sub3-marathon"))
    return plan, completed, calls[-1]


def _race_pace_weeks(plan):
    return [max([race_pace_miles(d) for d in w["days"] if d["type"] == "long_run"], default=0) for w in plan["weeks"]]


def test_race_pace_step_means_new_or_materially_longer():
    assert race_pace_step(10, 0) and race_pace_step(4, 0)
    assert race_pace_step(10 + RACE_PACE_STEP_MILES, 10)
    assert not race_pace_step(12, 10)  # 10 → 12 mi at MP is the next step of the same lever
    assert not race_pace_step(0, 0)


def test_new_marathon_pace_long_run_holds_that_weeks_volume(monkeypatch):
    plan, completed, _ = _seed_sub3(monkeypatch)
    mp = _race_pace_weeks(plan)
    # The block runs two or three weeks depending on the weekday; the first MP long run
    # (10 + 10 style) follows an easy long-run week.
    first = next(i for i, miles in enumerate(mp) if miles)
    assert first >= 1 and mp[first] >= 9, mp
    before, held = plan["weeks"][first - 1], plan["weeks"][first]
    assert held["budget_miles"] <= before["budget_miles"] + MILES_TOLERANCE
    assert held["target_mileage"] <= before["budget_miles"] + MILES_TOLERANCE
    if first + 1 < len(mp) and not race_pace_step(mp[first + 1], mp[first]):
        assert plan["weeks"][first + 1]["budget_miles"] > held["budget_miles"]  # volume grows the week after
    assert any("race pace in the long run: holding" in r for r in plan["load"]["reasons"])
    assert plan_invariant_violations(plan, completed_weeks=completed) == []


def test_already_absorbed_race_pace_lets_volume_grow(monkeypatch):
    held, _, kwargs = _seed_sub3(monkeypatch)
    # Same athlete, but a 10 mi MP long run was run last block: no new lever, volume builds.
    grown = plan_engine.generate_plan(**{**kwargs, "recent_race_pace_miles": 10})
    assert grown["weeks"][1]["budget_miles"] > held["weeks"][1]["budget_miles"] + 1
    assert not any("race pace in the long run: holding" in r for r in grown["load"]["reasons"])


def test_checker_catches_volume_raised_with_a_new_race_pace_long_run():
    mp_long = long_run_prescription([("easy", 10), ("race_pace", 10, 410)], "10mi easy, then 10mi at goal MP.")
    flat = [("easy", 5), ("workout", 6), ("easy", 5), ("easy", 5), ("rest", 0), ("long_run", 10), ("easy", 5)]
    more = [("easy", 6), ("workout", 6), ("easy", 6), ("easy", 6), ("rest", 0), ("long_run", 10), ("easy", 6)]
    weeks = [_week(1, "2026-10-19", flat, phase="peak"), _week(2, "2026-10-26", more, phase="peak")]
    weeks[1]["days"][5]["prescription"] = mp_long
    problems = plan_invariant_violations(_plan(weeks))
    assert any("one lever" in p for p in problems), problems
    weeks[1]["days"][5]["prescription"] = None  # the same growth with an easy long run is fine
    assert not any("one lever" in p for p in plan_invariant_violations(_plan(weeks)))


def test_time_based_bookends_round_to_five_minutes():
    workout = {"name": "3x8min Threshold", "warmup": "2mi easy", "cooldown": "1.5mi easy",
               "prescription": {"warmup": segment(meters=round(2 * MI, 2)), "cooldown": segment(meters=round(1.5 * MI, 2))}}
    # 2 mi at 8:15/mi is 16.5 min; 1.5 mi is 12.4 min
    out = format_bookends(workout, {"long_run_pace": 495}, "time")
    assert (out["warmup"], out["cooldown"]) == ("15min easy", "10min easy")
    assert out["prescription"]["warmup"]["duration_seconds"] == 900
    assert out["prescription"]["cooldown"]["duration_seconds"] == 600
    short = format_bookends({**workout, "prescription": {"warmup": segment(meters=400), "cooldown": None}},
                            {"long_run_pace": 495}, "time")
    assert short["warmup"] == "5min easy"  # never "0min"


def test_trail_demo_bookends_read_in_five_minutes():
    plan, _ = _seed_and_plan(_profile("trail-100k"))
    bookends = [d[k] for w in plan["weeks"] for d in w["days"] if d["type"] == "workout"
                for k in ("warmup", "cooldown") if d.get(k) and "min" in d[k]]
    assert bookends, "trail-100k uses time-based workouts"
    for text in bookends:
        minutes = re.match(r"(\d+)min easy$", text)
        assert minutes and int(minutes.group(1)) % 5 == 0, text


def test_scheduled_mp_work_only_counts_when_actual_laps_verify_its_dose():
    import json
    from app.models.activity import Activity
    from app.models.plan import PlannedWorkout
    data = long_run_prescription([('easy', 10), ('race_pace', 10, 410)], 'MP long run', easy_pace=540)
    workout = PlannedWorkout(type='long_run', prescription=json.dumps(data))
    run = Activity(id=1, distance_meters=20*MI, duration_seconds=20*540, splits='[]')
    assert plans_api._completed_race_pace_miles(workout, [run]) == 0  # distance alone is not MP work
    run.splits = json.dumps([
        {'intensity':'WARMUP','distance_m':10*MI,'duration_s':10*540},
        {'intensity':'ACTIVE','distance_m':10*MI,'duration_s':10*410},
    ])
    assert plans_api._completed_race_pace_miles(workout, [run]) == 10
    run.splits = run.splits.replace(str(10*410), str(10*540))
    assert plans_api._completed_race_pace_miles(workout, [run]) == 0  # completed distance, too slow for MP
    workout.swapped = True
    assert plans_api._completed_race_pace_miles(workout, [run]) == 0
