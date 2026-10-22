"""Priority 1: mileage goals and constraints govern the plan (budget enforcement,
session sizing, partial weeks, boundary spacing)."""

from datetime import date, timedelta

import pytest

from app.core.block_assessment import DayRecord, assess_block
from app.core.load_policy import plan_load
from app.core.plan_engine import generate_plan
from app.core.plan_validator import BUDGET_OVER_TOLERANCE, validate_plan

MONDAY = date(2026, 10, 19)


def plan(**kw):
    base = dict(
        goal_type="mileage", goal_distance=None, target_time_seconds=None,
        current_weekly_mileage=31, peak_weekly_mileage=70, experience_level="advanced",
        days_per_week=6, rest_days=["sunday"], long_run_day="saturday", easy_pace_seconds=545,
        start_date=MONDAY, num_weeks=2, first_prescribe_date=MONDAY,
        progression_state={"intervals": {"current_level": 5}, "threshold": {"current_level": 1}},
    )
    base.update(kw)
    return generate_plan(**base)


def assert_fits(p):
    for w in p["weeks"]:
        if any(d["type"] == "race" for d in w["days"]):
            continue
        assert w["target_mileage"] <= w["budget_miles"] + BUDGET_OVER_TOLERANCE, (w["week_number"], w["target_mileage"], w["budget_miles"])
        assert w["target_mileage"] == round(sum(d["distance_miles"] for d in w["days"]), 1)
    assert p["violations"] == []


# ── Load policy ─────────────────────────────────────────────────

def test_destination_75_sets_direction_not_this_block():
    load = plan_load(31, 70, "advanced", "mileage", 2, target_weekly_mileage=75)
    assert load.destination == 75 and load.mode == "build"
    assert load.weekly_budgets[-1] < 40  # no jump toward 75


def test_historical_peak_is_not_a_ceiling():
    load = plan_load(70, 70, "advanced", "mileage", 2, target_weekly_mileage=80)
    assert load.weekly_budgets[-1] > 70  # can build past the old peak (slowly)
    assert load.rate == 0.10  # new territory = the conservative rate


def test_reaching_destination_holds():
    load = plan_load(74, 75, "advanced", "mileage", 2, target_weekly_mileage=75)
    assert load.mode == "hold" and load.weekly_budgets == [75.0, 75.0]


def test_lower_destination_reduces_gradually():
    load = plan_load(60, 70, "advanced", "mileage", 2, target_weekly_mileage=40)
    assert load.mode == "reduce"
    assert load.weekly_budgets == [54.0, 48.6]  # -10%/week, never below 40


@pytest.mark.parametrize("bad", [0, None, float("nan"), float("inf"), -5])
def test_zero_or_invalid_history_has_a_defined_start(bad):
    load = plan_load(bad, bad, "beginner", "general", 2)
    assert load.mode == "start" and load.weekly_budgets == [10.0, 10.0]


def test_reported_mileage_used_when_no_history():
    load = plan_load(0, 0, "intermediate", "general", 2, reported_mileage=20)
    assert load.weekly_budgets == [20.0, 20.0]


@pytest.mark.parametrize("decision,factor", [("hold", 1.0), ("reduce", 0.85), ("recovery", 0.70)])
def test_assessment_controls_growth(decision, factor):
    load = plan_load(40, 70, "advanced", "race", 2, assessment=decision)
    assert load.weekly_budgets == [round(40 * factor, 1)] * 2 and load.mode == decision


# ── Session sizing within budget ────────────────────────────────

def test_high_ladder_low_mileage_fits_budget():
    p = plan(goal_type="race", goal_distance="half", current_weekly_mileage=22, days_per_week=5,
             rest_days=["friday", "sunday"],
             progression_state={"intervals": {"current_level": 10}, "threshold": {"current_level": 11}})
    assert_fits(p)
    workouts = [d for w in p["weeks"] for d in w["days"] if d["type"] == "workout"]
    assert all(d["distance_miles"] <= max(5.0, 26.4 * 0.30) + 0.5 for d in workouts)


def test_four_run_days_allow_one_workout():
    p = plan(goal_type="race", goal_distance="5k", current_weekly_mileage=25, days_per_week=4,
             rest_days=["wednesday", "friday", "sunday"])
    for w in p["weeks"]:
        assert sum(d["type"] == "workout" for d in w["days"]) <= 1


def test_threshold_only_week_is_accounted():
    # Base phase, non-advanced: one quality session, which is threshold for a half
    p = plan(goal_type="race", goal_distance="half", experience_level="intermediate",
             race_date=MONDAY + timedelta(weeks=20, days=5))
    assert_fits(p)
    wk1 = p["weeks"][0]["days"]
    assert sum(d["type"] == "workout" for d in wk1) == 1


@pytest.mark.parametrize("mpw", [12, 20, 31, 45, 60])
@pytest.mark.parametrize("days", [3, 4, 5, 6, 7])
def test_budget_respected_across_volumes_and_run_days(mpw, days):
    rest = ["monday", "wednesday", "friday", "sunday"][: 7 - days] if days < 7 else []
    p = plan(current_weekly_mileage=mpw, days_per_week=days, rest_days=rest or ["sunday"])
    assert_fits(p)


def test_ultra_back_to_back_fits_and_is_flagged():
    p = plan(goal_type="race", goal_distance="100mi", current_weekly_mileage=55,
             race_date=MONDAY + timedelta(weeks=12, days=6), terrain="mountain",
             rest_days=["monday"])
    assert_fits(p)
    pairs = [d for w in p["weeks"] for d in w["days"] if d.get("b2b")]
    assert len(pairs) in (0, 2, 4) and all(d["type"] == "long_run" for d in pairs)


def test_no_unconditional_week_to_week_growth_padding():
    # An untouched Monday can start recovery now; the following week returns to baseline.
    p = plan(current_weekly_mileage=40, block_number=4)  # advanced: block 4 is a deload
    assert p["is_deload"]
    assert p["weeks"][0]["target_mileage"] < p["weeks"][1]["target_mileage"]
    assert p["weeks"][0]["budget_miles"] == 30


def test_deload_lands_on_a_full_future_week():
    p = plan(current_weekly_mileage=40, block_number=4, first_prescribe_date=MONDAY + timedelta(days=2))
    assert p["load"]["mode"] == "deload"
    assert p["weeks"][1]["budget_miles"] == 30.0  # 75% of 40, in the week that hasn't started


# ── Partial weeks and boundaries ────────────────────────────────

def test_midweek_plan_counts_real_miles_already_run():
    wed = MONDAY + timedelta(days=2)
    completed = {MONDAY.isoformat(): 6.0, (MONDAY + timedelta(days=1)).isoformat(): 8.0}
    p = plan(first_prescribe_date=wed, completed_by_date=completed)
    wk1 = p["weeks"][0]
    past = [d for d in wk1["days"] if d["date"] < wed.isoformat()]
    assert [d["distance_miles"] for d in past] == [6.0, 8.0]
    assert all(d["prescribed"] is False for d in past)
    assert_fits(p)  # remaining prescription = budget - real miles


def test_missed_days_are_not_hypothetical_training():
    wed = MONDAY + timedelta(days=2)
    p = plan(first_prescribe_date=wed, completed_by_date={})
    past = [d for d in p["weeks"][0]["days"] if d["date"] < wed.isoformat()]
    assert all(d["distance_miles"] == 0 and d["type"] == "rest" for d in past)


def test_sunday_long_run_then_monday_workout_is_prevented():
    # Real long run yesterday (Sunday) → the plan must not open with a hard Monday
    p = plan(goal_type="race", goal_distance="5k", rest_days=["friday"], long_run_day="sunday",
             prior_hard_dates={(MONDAY - timedelta(days=1)).isoformat()})
    mon = p["weeks"][0]["days"][0]
    assert mon["type"] not in ("workout", "long_run")
    assert p["violations"] == []


def test_validator_flags_hard_stack_across_week_boundary():
    weeks = [
        {"week_number": 1, "budget_miles": 30, "days": [{"date": "2026-10-25", "type": "long_run", "distance_miles": 10}]},
        {"week_number": 2, "budget_miles": 30, "days": [{"date": "2026-10-26", "type": "workout", "distance_miles": 6}]},
    ]
    assert [v["code"] for v in validate_plan(weeks)] == ["hard_after_hard"]


def test_validator_only_allows_flagged_b2b_pairs():
    days = [{"date": "2026-10-24", "type": "long_run", "distance_miles": 12},
            {"date": "2026-10-25", "type": "long_run", "distance_miles": 7}]
    assert validate_plan([{"week_number": 1, "days": days}])  # unflagged pair = violation
    for d in days:
        d["b2b"] = True
    assert validate_plan([{"week_number": 1, "days": days}]) == []


def test_rest_days_respected():
    p = plan(rest_days=["sunday", "monday"], days_per_week=5)
    for w in p["weeks"]:
        for d in w["days"]:
            if d["day"] in ("sunday", "monday"):
                assert d["type"] == "rest"


# ── Two-block cycle: next block responds to evidence ────────────

def _block(completion: float, feels: list[int | None]) -> list[DayRecord]:
    plan_days = [("easy", 5), ("workout", 7), ("easy", 5), ("workout", 6), ("easy", 5), ("long_run", 10)] * 2
    return [DayRecord(date=f"2026-10-{i + 1:02d}", type=t, planned_miles=m, actual_miles=m * completion,
                      feel=feels[i] if i < len(feels) else None,
                      execution_complete=completion >= .9 if t == "workout" else None) for i, (t, m) in enumerate(plan_days)]


def test_successful_block_builds():
    a = assess_block(_block(1.0, [7, 8, 7]))
    assert a.decision == "build"


def test_missing_feedback_is_not_a_bad_block():
    assert assess_block(_block(0.95, [])).decision == "build"


def test_mixed_block_holds():
    assert assess_block(_block(0.75, [6, 7])).decision == "hold"


def test_interrupted_block_reduces_without_makeup_miles():
    a = assess_block(_block(0.4, []))
    assert a.decision == "reduce"
    load = plan_load(18, 70, "advanced", "race", 2, assessment=a.decision)
    assert load.weekly_budgets[0] < 18  # never "catch up" on missed miles


def test_fatigued_block_recovers():
    assert assess_block(_block(1.0, [3, 4, 2, 6])).decision == "recovery"


def test_barely_started_block_is_not_assessed():
    assert assess_block(_block(1.0, [9])[:3]).decision is None


# ── Deloads from completed history ──────────────────────────────

from app.core.load_policy import deload_due  # noqa: E402


def test_deload_due_after_loaded_streak():
    assert deload_due([30, 32, 34, 36, 38], "intermediate")[0] is True
    assert deload_due([30, 32, 34, 36], "advanced")[0] is False
    assert deload_due([30, 32, 34, 36, 38], "advanced")[0] is False
    assert deload_due([30, 32, 34, 36, 38, 40, 42], "advanced")[0] is True


def test_natural_down_week_resets_the_streak():
    due, why = deload_due([30, 32, 34, 22, 30], "intermediate")
    assert due is False and "1 loaded week" in why or "2 loaded weeks" in why


def test_missed_weeks_reset_rather_than_accumulate():
    assert deload_due([30, 0, 30], "intermediate")[0] is False


def test_history_based_deload_overrides_block_counter():
    p = plan(current_weekly_mileage=40, block_number=1, deload_is_due=True)
    assert p["is_deload"] and p["load"]["mode"] == "deload"
    p = plan(current_weekly_mileage=40, block_number=4, deload_is_due=False)  # block 4 alone doesn't deload
    assert not p["is_deload"]


# ── Priority 4: goals shape session selection ───────────────────

def test_mileage_goal_gets_one_threshold_session_not_5k_intervals():
    p = plan(goal_type="mileage", current_weekly_mileage=45, target_weekly_mileage=75)
    for w in p["weeks"]:
        workouts = [d for d in w["days"] if d["type"] == "workout"]
        assert len(workouts) <= 1
        assert all("800" not in d["title"] and "1K" not in d["title"] for d in workouts)


def test_5k_goal_still_gets_two_sessions_with_intervals():
    from tests.test_quality_transition import READY
    p = plan(goal_type="race", goal_distance="5k", current_weekly_mileage=45,
             completed_weeks=[45]*8, weekly_run_days=[6]*4, recent_long_run_miles=10, quality_evidence=READY)
    titles = [d["title"] for d in p["weeks"][0]["days"] if d["type"] == "workout"]
    assert len(titles) == 2 and any("800" in t or "1K" in t or "mi" in t for t in titles)


def test_mp_readiness_sessions_need_marathon_build_or_peak():
    from app.core.plan_engine import _eligible

    mp = {"min_mpw": 50, "requires_mp_readiness": True}
    assert not _eligible(mp, 55, "5k", "peak")
    assert not _eligible(mp, 55, "marathon", "base")
    assert not _eligible(mp, 45, "marathon", "peak")
    assert _eligible(mp, 55, "marathon", "peak")


def test_low_volume_long_run_is_never_shorter_than_an_easy_day():
    # Beginner deload: 5.6 mi over three runs. Easy days sit at the 2-mile floor, so the
    # long run can't borrow from them; it must still not be the shortest run of the week.
    from app.core.plan_validator import fit_week_to_budget
    days = [{"date": "2026-10-27", "type": "easy", "title": "Easy Run", "distance_miles": 3},
            {"date": "2026-10-29", "type": "easy", "title": "Easy Run", "distance_miles": 3},
            {"date": "2026-10-31", "type": "long_run", "title": "Easy Long Run", "distance_miles": 1.5}]
    notes = fit_week_to_budget(days, 5.6, "easy")
    easy = [d["distance_miles"] for d in days if d["type"] == "easy"]
    long_run = next(d["distance_miles"] for d in days if d["type"] == "long_run")
    assert long_run >= max(easy) and sum(d["distance_miles"] for d in days) <= 5.6 + 0.5
    assert all("not shorter than the easy days" not in n or long_run >= max(easy) for n in notes)
