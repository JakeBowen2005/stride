"""Tests for the training plan generator.

These are the tests that matter most in this codebase. `generate_plan` is a
pure function with no I/O, and every bug in it produces a plausible-looking
plan that is quietly wrong — which an athlete then runs.

Each test below corresponds to a bug that was actually shipped.
"""

from datetime import date, timedelta

import pytest

from app.core.plan_engine import (
    RETURN_THRESHOLD_MPW,
    _build_current_paces,
    _calculate_target_mileage,
    _effective_days_per_week,
    _is_deload_block,
    _mp_is_realistic,
    _should_include_workouts,
    generate_plan,
)

MARATHON_245 = 9900.0  # 2:45:00 -> 6:17/mi
JAKE_PEAK = 70.1


def build(
    mileage=45.0,
    peak=JAKE_PEAK,
    experience="advanced",
    block=1,
    weeks=2,
    start=None,
    race_date=None,
    distance="marathon",
    target=MARATHON_245,
    paces=None,
    days=6,
):
    start = start or date(2026, 9, 7)  # a Monday
    return generate_plan(
        goal_type="race",
        goal_distance=distance,
        target_time_seconds=target,
        current_weekly_mileage=mileage,
        peak_weekly_mileage=peak,
        experience_level=experience,
        days_per_week=days,
        rest_days=["sunday"],
        long_run_day="saturday",
        easy_pace_seconds=540,
        current_workout_paces=paces,
        start_date=start,
        end_date=start + timedelta(days=weeks * 7 - 1),
        num_weeks=weeks,
        first_prescribe_date=start,
        block_number=block,
        progression_state={
            "intervals": {"current_level": 5},
            "threshold": {"current_level": 4},
        },
        race_date=race_date,
    )


def all_days(plan):
    return [d for w in plan["weeks"] for d in w["days"]]


# ── Mileage ramp ──────────────────────────────────────────────────

@pytest.mark.parametrize("current", [0.0, 0.5, 2.0, 5.0, 8.0])
def test_returning_runner_never_gets_an_empty_week(current):
    """The ceiling used to be `current * 1.5`, which collapses near zero.

    An athlete at 0 mpw was handed a 0-mile week.
    """
    week1, week2 = _calculate_target_mileage(current, JAKE_PEAK, "advanced", "race")
    assert week1 >= 3.0
    assert week2 > week1


def test_return_ramp_is_capped_by_training_history():
    """Coming back from nothing must not jump straight to old volume."""
    week1, week2 = _calculate_target_mileage(0.0, JAKE_PEAK, "advanced", "race")
    assert week1 <= JAKE_PEAK * 0.30
    assert week2 <= JAKE_PEAK * 0.30


def test_ramp_has_no_cliff_at_the_return_threshold():
    """The absolute-step ramp must hand off smoothly to the percentage ramp."""
    below, _ = _calculate_target_mileage(RETURN_THRESHOLD_MPW - 0.5, JAKE_PEAK, "advanced", "race")
    above, _ = _calculate_target_mileage(RETURN_THRESHOLD_MPW + 0.5, JAKE_PEAK, "advanced", "race")
    assert abs(below - above) < 3.0, f"discontinuity at the seam: {below} -> {above}"


def test_weekly_increase_respects_the_ten_percent_rule_for_beginners():
    week1, week2 = _calculate_target_mileage(20.0, 25.0, "beginner", "race")
    assert week2 <= 20.0 * 1.11


def test_mileage_never_exceeds_ninety_percent_of_peak():
    week1, week2 = _calculate_target_mileage(65.0, JAKE_PEAK, "advanced", "race")
    assert week2 <= JAKE_PEAK * 0.9 + 0.05


# ── Week structure ────────────────────────────────────────────────

def test_no_back_to_back_hard_days():
    """Principle 3. Non-negotiable."""
    plan = build(mileage=55.0)
    days = all_days(plan)
    hard = {"workout", "long_run", "race"}
    for prev, nxt in zip(days, days[1:]):
        assert not (prev["type"] in hard and nxt["type"] in hard), (
            f"{prev['day']} ({prev['type']}) followed by {nxt['day']} ({nxt['type']})"
        )


def test_long_run_is_the_longest_run_of_the_week():
    """Principle 9. At low volume the easy-day floor used to beat the long run."""
    for mileage in (0.0, 8.0, 20.0, 45.0, 62.0):
        plan = build(mileage=mileage)
        for week in plan["weeks"]:
            runs = [d for d in week["days"] if d["distance_miles"] > 0]
            if len(runs) < 2:
                continue
            longest = max(runs, key=lambda d: d["distance_miles"])
            assert longest["type"] in ("long_run", "race"), (
                f"at {mileage}mpw the longest run was a {longest['type']}"
            )


def test_low_volume_weeks_use_fewer_longer_runs():
    """Six run days against a 12-mile week produced 5x3mi + a long run = 18.5mi."""
    assert _effective_days_per_week(12.0, 6) < 6
    assert _effective_days_per_week(60.0, 6) == 6


def test_week_mileage_stays_near_target():
    for mileage in (15.0, 30.0, 45.0, 62.0):
        plan = build(mileage=mileage)
        for week in plan["weeks"]:
            actual = sum(d["distance_miles"] for d in week["days"])
            assert actual == pytest.approx(week["target_mileage"], abs=0.6)


# ── Base building ─────────────────────────────────────────────────

def test_no_quality_work_below_the_mileage_base():
    """Principle 1: build mileage BEFORE adding intensity."""
    plan = build(mileage=6.0)
    assert not any(d["type"] == "workout" for d in all_days(plan))


def test_quality_returns_once_volume_supports_it():
    plan = build(mileage=45.0)
    assert any(d["type"] == "workout" for d in all_days(plan))


def test_should_include_workouts_thresholds():
    assert not _should_include_workouts(10.0, "race", "advanced")
    assert _should_include_workouts(25.0, "race", "advanced")
    assert not _should_include_workouts(15.0, "race", "beginner")


# ── Deload ────────────────────────────────────────────────────────

def test_advanced_deload_schedule():
    assert not _is_deload_block(1, "advanced")
    assert not _is_deload_block(3, "advanced")
    assert _is_deload_block(4, "advanced")
    assert _is_deload_block(7, "advanced")


def test_deload_week_actually_reduces_volume():
    """`wk == 0 and not current_week_overlap` was always False.

    No deload week had ever been generated. Then, once it was, positional
    workout-mileage accounting made a "deload" come out at 62.5mi against a
    63mi build week.
    """
    plan = build(mileage=68.0, block=4, weeks=2)
    assert plan["is_deload"]
    totals = [w["target_mileage"] for w in plan["weeks"]]
    assert min(totals) < 68.0 * 0.85, f"deload did not reduce volume: {totals}"


def test_deload_keeps_one_quality_session_and_drops_the_speed_one():
    plan = build(mileage=68.0, block=4, weeks=2)
    deload_week = min(plan["weeks"], key=lambda w: w["target_mileage"])
    workouts = [d for d in deload_week["days"] if d["type"] == "workout"]
    assert len(workouts) == 1
    # Controlled aerobic work absorbs training; VO2max work is the opposite.
    assert "400m" not in workouts[0]["title"]
    assert "800m" not in workouts[0]["title"]


def test_deload_never_lands_on_a_week_already_underway():
    """Deloading a week the athlete has half-run just shortens it for nothing."""
    monday = date(2026, 9, 7)
    plan = generate_plan(
        goal_type="race", goal_distance="marathon", target_time_seconds=MARATHON_245,
        current_weekly_mileage=60.0, peak_weekly_mileage=JAKE_PEAK,
        experience_level="advanced", days_per_week=6,
        rest_days=["sunday"], long_run_day="saturday", easy_pace_seconds=540,
        start_date=monday, end_date=monday + timedelta(days=13), num_weeks=2,
        first_prescribe_date=monday + timedelta(days=2),  # mid-week
        block_number=4,
        progression_state={"intervals": {"current_level": 5}, "threshold": {"current_level": 4}},
    )
    first_week_total = plan["weeks"][0]["target_mileage"]
    second_week_total = plan["weeks"][1]["target_mileage"]
    assert second_week_total < first_week_total


# ── Pacing ────────────────────────────────────────────────────────

def test_continuous_tempo_is_slower_than_broken_threshold_reps():
    """`tempo = threshold * 0.96` had this exactly backwards.

    Rest between reps is what lets you hold the faster pace.
    """
    paces = _build_current_paces(540, None, goal_distance="marathon")
    assert paces["tempo_pace"] > paces["threshold_pace"]


def test_race_pace_is_the_goal_pace_not_an_interval_estimate():
    """The calibrator derives race_pace from 800m splits — 5K effort.

    Labelling that "marathon pace" would prescribe a 5K-pace long run.
    """
    from app.core.pacing import goal_paces

    goal = goal_paces("marathon", MARATHON_245)
    paces = _build_current_paces(
        540,
        {"interval_pace": 352, "threshold_pace": 400, "race_pace": 370},
        goal_pace_data=goal,
        current_mileage=60.0,
        goal_distance="marathon",
    )
    assert paces["race_pace"] == paces["goal_race_pace"]
    assert paces["goal_race_pace"] == pytest.approx(378, abs=5)


def test_threshold_is_faster_than_marathon_pace_but_slower_than_5k_pace():
    from app.core.pacing import goal_paces

    marathon = _build_current_paces(
        480, None, goal_pace_data=goal_paces("marathon", MARATHON_245),
        current_mileage=70.0, goal_distance="marathon",
    )
    assert marathon["threshold_pace"] < marathon["goal_race_pace"]

    five_k = _build_current_paces(
        480, None, goal_pace_data=goal_paces("5k", 1019),  # 16:59
        current_mileage=70.0, goal_distance="5k",
    )
    assert five_k["threshold_pace"] > five_k["goal_race_pace"]


def test_paces_round_to_five_seconds():
    paces = _build_current_paces(547, None, goal_distance="marathon")
    for key in ("threshold_pace", "tempo_pace", "interval_pace", "steady_pace"):
        assert paces[key] % 5 == 0, f"{key} = {paces[key]}"


# ── Goal-pace gating ──────────────────────────────────────────────

def test_mp_work_is_withheld_when_goal_pace_beats_current_threshold():
    """Race-pace reps must not be harder than the threshold session.

    Goal MP 6:17 with threshold at 6:35 means MP work would be the hardest
    session of the week — physiologically backwards.
    """
    assert not _mp_is_realistic(377, 395)   # goal faster than threshold
    assert not _mp_is_realistic(377, 370)   # goal slower but not by enough
    assert _mp_is_realistic(377, 350)       # threshold comfortably faster


def test_plan_explains_why_race_pace_work_is_on_hold():
    plan = build(mileage=45.0)
    assert any("threshold" in n.lower() and "hold" in n.lower() for n in plan["notes"])


def test_no_goal_pace_workouts_while_gated():
    plan = build(mileage=45.0)
    for day in all_days(plan):
        if day["type"] in ("workout", "long_run"):
            assert "goal MP" not in (day["description"] or "")


# ── Taper ─────────────────────────────────────────────────────────

def test_taper_reduces_volume_progressively():
    """`goal.race_date` was stored but never read. There was no taper at all."""
    race = date(2028, 2, 6)
    start = date(2028, 1, 17)  # Monday, 3 weeks out
    plan = build(
        mileage=68.0, start=start, weeks=3, race_date=race.isoformat(),
        paces={"interval_pace": 330, "threshold_pace": 348, "strides_pace": 290},
    )
    totals = [w["target_mileage"] for w in plan["weeks"]]
    assert totals[0] < 68.0
    assert totals[1] < totals[0]
    assert plan["phase"] == "taper"


def test_taper_keeps_workout_frequency():
    """Bosquet: runners who cut training days taper worse. Shorten, don't drop."""
    race = date(2028, 2, 6)
    plan = build(
        mileage=68.0, start=date(2028, 1, 17), weeks=2, race_date=race.isoformat(),
        paces={"interval_pace": 330, "threshold_pace": 348, "strides_pace": 290},
    )
    for week in plan["weeks"]:
        assert sum(1 for d in week["days"] if d["type"] == "workout") == 2


def test_taper_workouts_are_short():
    """A 12.5mi threshold session six days out undoes the taper it belongs to."""
    race = date(2028, 2, 6)
    plan = build(
        mileage=68.0, start=date(2028, 1, 17), weeks=3, race_date=race.isoformat(),
        paces={"interval_pace": 330, "threshold_pace": 348, "strides_pace": 290},
    )
    for day in all_days(plan):
        if day["type"] == "workout":
            assert day["distance_miles"] <= 8.0, day["title"]


def test_the_two_taper_sessions_in_a_week_differ():
    race = date(2028, 2, 6)
    plan = build(
        mileage=68.0, start=date(2028, 1, 17), weeks=1, race_date=race.isoformat(),
        paces={"interval_pace": 330, "threshold_pace": 348, "strides_pace": 290},
    )
    titles = [d["title"] for d in all_days(plan) if d["type"] == "workout"]
    assert len(set(titles)) == len(titles), titles


def test_race_week_has_race_day_a_shakeout_and_a_rest_day():
    race = date(2028, 2, 6)
    plan = build(
        mileage=68.0, start=date(2028, 1, 31), weeks=1, race_date=race.isoformat(),
        paces={"interval_pace": 330, "threshold_pace": 348, "strides_pace": 290},
    )
    days = all_days(plan)
    race_days = [d for d in days if d["type"] == "race"]
    assert len(race_days) == 1
    assert race_days[0]["date"] == race.isoformat()
    assert race_days[0]["distance_miles"] == pytest.approx(26.2, abs=0.1)

    day_before = next(d for d in days if d["date"] == (race - timedelta(days=1)).isoformat())
    assert day_before["distance_miles"] <= 2.5

    two_days_before = next(d for d in days if d["date"] == (race - timedelta(days=2)).isoformat())
    assert two_days_before["type"] == "rest"


def test_no_taper_when_the_race_is_far_away():
    plan = build(mileage=60.0, race_date="2028-02-06", start=date(2026, 9, 7))
    assert plan["phase"] in ("base", "build")
    assert plan["weeks_to_race"] > 3


# ── Distance routing ──────────────────────────────────────────────

def test_marathon_goal_gets_marathon_workouts():
    """The marathon library was dead code: get_ladder() ignored `distance`."""
    plan = build(mileage=55.0, distance="marathon")
    titles = " ".join(d["title"] for d in all_days(plan) if d["type"] == "workout")
    assert "mi Threshold" in titles or "MP" in titles


def test_5k_goal_gets_5k_workouts():
    plan = build(mileage=45.0, distance="5k", target=1019.0)
    titles = " ".join(d["title"] for d in all_days(plan) if d["type"] == "workout")
    assert "min" in titles or "800m" in titles or "Tempo" in titles


# ── Regression: every day is well-formed ──────────────────────────

@pytest.mark.parametrize("mileage", [0.0, 5.0, 12.0, 25.0, 45.0, 62.0, 75.0])
def test_every_generated_day_is_complete(mileage):
    plan = build(mileage=mileage)
    for day in all_days(plan):
        assert day["title"]
        assert day["type"] in ("easy", "workout", "long_run", "rest", "race")
        assert day["distance_miles"] >= 0
        if day["type"] != "rest":
            assert day["description"]
            assert day["purpose"]
