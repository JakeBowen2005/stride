"""Every demo scenario's generated plan follows the running rules.

The demo deploy branches (codex/demo-*) differ from main only by
demo/default-scenario.json, so seeding each scenario here and checking the plan
the real engine produces covers "plans on every branch follow the rules".
Race-approach variants move each race goal's date up so the same athletes also
get taper and race-week blocks.
"""

import json
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.models.plan import Plan
from app.models.user import Goal, User
from app.services.demo_seed import seed_demo
from app.services.load_history import completed_week_load
from tests.plan_invariants import assert_plan_invariants, plan_invariant_violations

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "demo" / "scenarios"
SCENARIOS = sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))
RACE_SCENARIOS = [s for s in SCENARIOS if json.loads((SCENARIO_DIR / f"{s}.json").read_text()).get("goal_type", "race") == "race"]


def _profile(scenario: str, **overrides) -> dict:
    return json.loads((SCENARIO_DIR / f"{scenario}.json").read_text()) | overrides


def _seed_and_plan(profile: dict) -> tuple[dict, list[float]]:
    """Seed the scenario through the real engine; return its plan and completed weeks."""
    with SessionLocal() as db:
        db.query(Goal).delete()
        db.query(User).delete()
        db.commit()
        result = seed_demo(db, profile)  # generates, validates and approves via the API code
        plan = json.loads(db.get(Plan, result["preview_id"]).preview_data)
        # Same eight full calendar weeks the API hands load_policy.deload_due
        completed = [w["miles"] for w in completed_week_load(1, db)["weeks"][-8:]]
    return plan, completed


def test_every_demo_scenario_is_covered():
    # A new scenario file is picked up automatically; this guards the glob itself.
    assert {"beginner-5k", "beginner-marathon", "beginner-mileage", "sub17-5k", "sub3-marathon", "trail-100k"} <= set(SCENARIOS)
    default = json.loads((SCENARIO_DIR.parent / "default-scenario.json").read_text())["scenario"]
    assert default in SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_demo_scenario_plan_follows_running_rules(scenario):
    plan, completed = _seed_and_plan(_profile(scenario))
    assert plan["violations"] == []
    assert_plan_invariants(plan, completed_weeks=completed)


# Known gap, found by this matrix: build_race_week sizes the sharpener (5 mi) and
# the easy days (≥2 mi each) with fixed doses and race weeks skip budget fitting,
# so a ~7.5 mpw beginner gets a 9 mi race week whose sharpener is longer than
# their long run. Fixing it means choosing a beginner race-week dose, which is a
# policy call; strict xfail so the test flags itself once that lands.
LOW_VOLUME_RACE_WEEK_GAP = {"beginner-5k"}


@pytest.mark.parametrize("weeks_to_race", [0, 1, 2])
@pytest.mark.parametrize("scenario", RACE_SCENARIOS)
def test_race_approach_plan_follows_running_rules(scenario, weeks_to_race, request):
    plan, completed = _seed_and_plan(_profile(scenario, weeks_to_race=weeks_to_race))
    phases = [w["phase"]["phase"] for w in plan["weeks"]]
    if weeks_to_race < len(phases):  # 2-week (Mon-Wed) blocks end before a race 2 weeks out
        assert "race_week" in phases, phases
    race_weeks = [w for w in plan["weeks"] if w["phase"]["phase"] == "race_week"]
    sharpener_ahead = any(d["type"] == "workout" and d.get("prescribed", True) for w in race_weeks for d in w["days"])
    if scenario in LOW_VOLUME_RACE_WEEK_GAP and sharpener_ahead:
        request.applymarker(pytest.mark.xfail(strict=True, reason=(
            "Race week uses fixed sharpener/easy doses and skips budget fitting, so a low-volume "
            "beginner's race week exceeds the ramp ceiling; needs a policy decision.")))
    assert_plan_invariants(plan, completed_weeks=completed)


# ── The checker itself must catch broken plans ─────────────────────────────


def _week(n: int, start: str, days: list[tuple[str, float]], phase="general", budget=None, title=None):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    rows = [{"date": (d0 + timedelta(days=i)).isoformat(), "type": t, "distance_miles": m,
             "title": (title or {}).get(i, t), "prescribed": True} for i, (t, m) in enumerate(days)]
    total = sum(m for _, m in days)
    return {"week_number": n, "budget_miles": budget if budget is not None else total,
            "phase": {"phase": phase}, "days": rows}


EASY_WEEK = [("easy", 5), ("workout", 6), ("easy", 5), ("easy", 5), ("rest", 0), ("long_run", 10), ("easy", 5)]


def _plan(weeks, baseline=36.0, **load):
    return {"weeks": weeks, "load": {"baseline": baseline, "mode": "build", **load},
            "athlete": {"experience_level": "intermediate", "peak_weekly_mileage": 40,
                        "schedule_preferences": {"rest_days": ["friday"]}},
            "goal": {"type": "race"}}


def test_checker_accepts_a_sound_plan():
    assert plan_invariant_violations(_plan([_week(1, "2026-10-19", EASY_WEEK), _week(2, "2026-10-26", EASY_WEEK)])) == []


@pytest.mark.parametrize("broken,expected", [
    (lambda: _plan([_week(1, "2026-10-19", EASY_WEEK),
                    _week(2, "2026-10-26", [("easy", 8), ("workout", 6), ("easy", 8), ("easy", 8), ("rest", 0), ("long_run", 14), ("easy", 8)])]), "ramp"),
    (lambda: _plan([_week(1, "2026-10-19", [("easy", 5), ("workout", 6), ("workout", 6), ("easy", 5), ("rest", 0), ("long_run", 10), ("easy", 4)])]), "hard_after_hard"),
    (lambda: _plan([_week(1, "2026-10-19", [("easy", 5), ("workout", 6), ("easy", 5), ("easy", 5), ("easy", 4), ("long_run", 10), ("easy", 1)])]), "rest_day_run"),
    (lambda: _plan([_week(1, "2026-10-19", [("easy", 3), ("workout", 9), ("easy", 3), ("workout", 9), ("rest", 0), ("long_run", 9), ("easy", 3)])]), "80/20"),
    (lambda: _plan([_week(1, "2026-10-19", EASY_WEEK, phase="taper", budget=30),
                    _week(2, "2026-10-26", EASY_WEEK, phase="race_week", budget=34)]), "taper"),
    (lambda: _plan([_week(1, "2026-10-19", [("easy", 3), ("easy", 3), ("easy", 3), ("easy", 3), ("rest", 0), ("workout", 5), ("race", 3.1)],
                         phase="race_week", title={5: "Sharpener"})]), "race week"),
    (lambda: _plan([_week(1, "2026-10-19", EASY_WEEK), _week(2, "2026-10-26", EASY_WEEK)], deload_week=1), "deload"),
])
def test_checker_catches_broken_plans(broken, expected):
    problems = plan_invariant_violations(broken(), completed_weeks=[30, 30, 30, 30, 30, 30, 30, 30])
    assert any(expected in p for p in problems), problems
