from datetime import date, timedelta

import pytest

from app.core.periodization import check_readiness, plan_phases, week_phase
from app.core.plan_engine import generate_plan
from app.core.special_weeks import HARD_TYPES

MONDAY = date(2026, 10, 19)


def sat(weeks_out: int) -> date:
    return MONDAY + timedelta(days=7 * weeks_out + 5)


def plan(distance="5k", race_date=None, weeks=3, mpw=40.0, experience="advanced",
         terrain=None, target=None, long_run_day="saturday", rest_days=("friday",)):
    return generate_plan(
        goal_type="race" if race_date or distance else "general",
        goal_distance=distance,
        target_time_seconds=target,
        current_weekly_mileage=mpw,
        peak_weekly_mileage=70,
        experience_level=experience,
        days_per_week=6,
        rest_days=list(rest_days),
        long_run_day=long_run_day,
        easy_pace_seconds=545,
        start_date=MONDAY,
        num_weeks=weeks,
        first_prescribe_date=MONDAY,
        race_date=race_date,
        terrain=terrain,
    )


def all_days(p):
    return [d for w in p["weeks"] for d in w["days"]]


# ── Phase math ──────────────────────────────────────────────────

def test_phases_count_back_from_race_marathon():
    race = sat(16)
    phases = [week_phase(MONDAY + timedelta(days=7 * w), "race", "marathon", race).phase for w in range(18)]
    assert phases[16] == "race_week"
    assert phases[15] == "taper"  # 2-week marathon taper: 1 taper week + race week
    assert phases[10:15] == ["peak"] * 5
    assert phases[5:10] == ["build"] * 5
    assert phases[:5] == ["base"] * 5
    assert phases[17] == "recovery"


def test_5k_taper_is_just_race_week():
    race = sat(5)
    phases = [week_phase(MONDAY + timedelta(days=7 * w), "race", "5k", race).phase for w in range(6)]
    assert phases[5] == "race_week" and phases[4] == "peak"


def test_100mi_has_three_week_taper_with_falling_volume():
    race = sat(10)
    taper = [week_phase(MONDAY + timedelta(days=7 * w), "race", "100mi", race) for w in (8, 9, 10)]
    assert [t.phase for t in taper] == ["taper", "taper", "race_week"]
    vols = [t.volume_multiplier for t in taper]
    assert vols[0] > vols[1] > vols[2]


def test_no_race_date_is_general():
    assert week_phase(MONDAY, "race", "5k", None).phase == "general"
    assert week_phase(MONDAY, "mileage", None, None).phase == "general"


def test_recovery_after_100mi_lasts_four_weeks():
    race = MONDAY - timedelta(days=2)
    phases = [week_phase(MONDAY + timedelta(days=7 * w), "race", "100mi", race) for w in range(5)]
    assert [p.phase for p in phases[:4]] == ["recovery"] * 4
    assert all(p.max_workouts == 0 for p in phases[:4])
    assert phases[4].phase == "general"


def test_b2b_only_in_build_peak_and_spaced():
    race = sat(20)
    wps = plan_phases(MONDAY, 21, "race", "100mi", race)
    b2b_weeks = [i for i, w in enumerate(wps) if w.back_to_back]
    assert b2b_weeks, "100mi build should include back-to-back weekends"
    assert all(wps[i].phase in ("build", "peak") for i in b2b_weeks)
    assert all(b - a >= 2 for a, b in zip(b2b_weeks, b2b_weeks[1:]))


# ── Readiness gates ─────────────────────────────────────────────

def test_first_100_without_ultra_and_short_runway_is_gated():
    r = check_readiness("100mi", MONDAY + timedelta(weeks=16), 26.2, 30, today=MONDAY)
    assert not r["ready"] and "50-mile" in r["suggestion"]


def test_100_after_a_50_miler_with_runway_is_ok():
    r = check_readiness("100mi", MONDAY + timedelta(weeks=26), 50.0, 45, today=MONDAY)
    assert r["ready"]


def test_50k_for_marathoner_is_ok():
    assert check_readiness("50k", MONDAY + timedelta(weeks=14), 26.2, 35, today=MONDAY)["ready"]


def test_past_race_date_rejected():
    assert not check_readiness("5k", MONDAY - timedelta(days=1), 10, 30, today=MONDAY)["ready"]


# ── Engine integration ──────────────────────────────────────────

def test_race_week_has_race_day_sharpener_and_shakeout():
    race = sat(1)
    p = plan("5k", race, weeks=2, target=17 * 60)
    wk2 = p["weeks"][1]["days"]
    race_day = next(d for d in wk2 if d["type"] == "race")
    assert race_day["date"] == race.isoformat()
    assert "5:28/mi" in race_day["description"]  # goal pace for sub-17
    assert sum(d["type"] == "workout" for d in wk2) == 1
    assert wk2[4]["title"] == "Rest Day"  # friday rest day respected
    assert p["weeks"][1]["phase"]["phase"] == "race_week"


def test_taper_week_volume_drops():
    race = sat(2)
    p = plan("marathon", race, weeks=3, mpw=50, target=2 * 3600 + 50 * 60)
    vols = [w["target_mileage"] for w in p["weeks"]]
    assert p["weeks"][1]["phase"]["phase"] == "taper"
    assert vols[1] < vols[0]
    assert sum(1 for d in p["weeks"][1]["days"] if d["type"] == "workout") >= 1  # intensity stays


def test_post_race_week_has_no_workouts():
    race = MONDAY - timedelta(days=1)
    p = plan("marathon", race, weeks=2, mpw=50)
    assert all(d["type"] != "workout" for d in p["weeks"][0]["days"])


def test_100mi_plan_has_time_based_long_runs_with_fueling():
    race = MONDAY + timedelta(weeks=24, days=5)
    p = plan("100mi", race, weeks=3, mpw=55, terrain="mountain", target=24 * 3600)
    longs = [d for d in all_days(p) if d["type"] == "long_run"]
    assert longs
    assert all("h" in d["description"].split()[0] for d in longs)
    assert any("carbs/hr" in d["description"] for d in longs)
    # mountain ultra: hills instead of track intervals
    assert any("Hill" in d["title"] or "Climb" in d["title"] for d in all_days(p) if d["type"] == "workout")
    # ultra goal pace must not leak into threshold pace
    assert p["pacing_guide"]["current_threshold"] < "8:00"


def test_100mi_b2b_weekend_present_in_build():
    race = MONDAY + timedelta(weeks=12, days=5)  # puts the first weeks in build
    p = plan("100mi", race, weeks=3, mpw=60, terrain="trail")
    b2b = [d for d in all_days(p) if d["title"].startswith("Back-to-Back")]
    assert b2b
    for d in b2b:
        assert d["distance_miles"] > 0


@pytest.mark.parametrize("distance", ["5k", "10k", "half", "marathon", "50k", "50mi", "100k", "100mi"])
@pytest.mark.parametrize("long_run_day", ["saturday", "sunday", "wednesday"])
@pytest.mark.parametrize("weeks_out", [1, 3, 8, 20])
def test_never_back_to_back_hard_days(distance, long_run_day, weeks_out):
    race = MONDAY + timedelta(weeks=weeks_out, days=5)
    p = plan(distance, race, weeks=3, mpw=50, long_run_day=long_run_day, terrain="trail")
    days = all_days(p)
    for a, b in zip(days, days[1:]):
        if a["type"] in HARD_TYPES and b["type"] in HARD_TYPES:
            assert a["type"] == b["type"] == "long_run", (distance, a["date"], a["title"], b["title"])
    assert all(d is not None for d in days)


def test_week_label_pluralization():
    race = sat(1)
    assert week_phase(MONDAY, "race", "5k", race).label == "Peak — 1 week to race"


def test_sharpener_uses_exact_goal_pace():
    p = plan("5k", sat(1), weeks=2, target=17 * 60)
    sharp = next(d for d in p["weeks"][1]["days"] if d["type"] == "workout")
    assert "5:28/mi" in sharp["description"]


def test_b2b_before_long_run_when_day_after_is_rest():
    race = MONDAY + timedelta(weeks=12, days=6)  # week 2 of the plan is a B2B week
    p = plan("100mi", race, weeks=2, mpw=40, terrain="mountain", rest_days=("sunday",))
    b2b_weeks = [w for w in p["weeks"] if w["phase"]["back_to_back"]]
    assert b2b_weeks
    wk = b2b_weeks[0]["days"]
    assert wk[4]["title"].startswith("Back-to-Back Long Run (day 1")  # friday
    assert wk[5]["type"] == "long_run" and wk[6]["type"] == "rest"
    assert not any("hard-day stack" in d["title"] for d in wk)  # planned cleanly, not patched
    assert wk[1]["type"] == "workout"  # tuesday quality kept
