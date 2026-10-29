"""Whole seasons, block by block to race day, checked against coach-level rules.

The single-block invariant matrix can't see these: rest after a Sunday race, how
long a 10K long run gets after ten weeks of growth, or what the week after a
100-miler looks like. A representative subset runs by default; set
STRIDE_SEASON_FULL=1 for every athlete × distance. Skipped under the weekday
matrix (STRIDE_TEST_DATE): each season pins its own calendar.
"""
import os
from datetime import date, timedelta

import pytest

from app.core.periodization import POST_RACE_REST_DAYS
from app.core.plan_engine import ROAD_LONG_RUN_CAP
from tests.season_sim import profiles, simulate

pytestmark = pytest.mark.skipif(bool(os.environ.get("STRIDE_TEST_DATE")), reason="seasons pin their own dates")

DEFAULT = ["beg-marathon", "adv-10k", "adv-half", "adv-marathon", "exp-100mi"]
SEASONS = sorted(profiles()) if os.environ.get("STRIDE_SEASON_FULL") else DEFAULT


@pytest.fixture(scope="module")
def seasons():
    return {}


def _season(name, cache):
    if name not in cache:
        cache[name] = simulate(profiles()[name])
    return cache[name]


@pytest.mark.parametrize("name", SEASONS)
def test_season_reaches_race_day_without_violations(name, seasons):
    log = _season(name, seasons)
    assert log["errors"] == []
    race = log["race_date"].isoformat()
    assert any(d["date"] == race and d["type"] == "race" for d in log["days"])


@pytest.mark.parametrize("name", SEASONS)
def test_no_running_right_after_the_race_and_no_long_run_the_week_after(name, seasons):
    log = _season(name, seasons)
    distance = profiles()[name]["distance"]
    race, rest = log["race_date"], POST_RACE_REST_DAYS[distance]
    for d in log["days"]:
        after = (date.fromisoformat(d["date"]) - race).days
        if 1 <= after <= rest:
            assert d["miles"] == 0, (d, f"{rest} days off after a {distance}")
        elif rest < after <= rest + 7:
            assert d["type"] not in ("long_run", "workout"), d


@pytest.mark.parametrize("name", [n for n in SEASONS if profiles()[n]["distance"] in ROAD_LONG_RUN_CAP])
def test_road_long_runs_stay_within_the_goal_distance_cap(name, seasons):
    log = _season(name, seasons)
    profile = profiles()[name]
    miles, minutes = ROAD_LONG_RUN_CAP[profile["distance"]]
    longest = max(d["miles"] for d in log["days"] if d["type"] == "long_run")
    assert longest <= min(miles, minutes * 60 / profile["easy_pace"]) + 0.5


def test_ultra_season_keeps_back_to_back_weekends_and_a_three_week_taper(seasons):
    log = _season("exp-100mi", seasons)
    titles = [d["title"] for d in log["days"]]
    assert any("Back-to-Back" in t for t in titles)
    race = log["race_date"]
    week = lambda n: sum(d["miles"] for d in log["days"]  # noqa: E731
                         if race - timedelta(days=7 * n + 6) <= date.fromisoformat(d["date"]) <= race - timedelta(days=7 * n))
    peak = max(week(n) for n in range(4, 10))
    assert week(3) < peak and week(2) < week(3)


def _week_miles(log, weeks_out):
    race = log["race_date"]
    lo, hi = race - timedelta(days=7 * weeks_out + 6), race - timedelta(days=7 * weeks_out)
    return sum(d["miles"] for d in log["days"] if lo <= date.fromisoformat(d["date"]) <= hi and d["type"] != "race")


def test_half_marathon_peak_holds_the_training_level_reached_in_build(seasons):
    # Introducing a second hard session holds the demonstrated level, not a deload-dragged average
    log = _season("adv-half", seasons)
    build_top = max(_week_miles(log, n) for n in range(6, 9))
    assert max(_week_miles(log, n) for n in range(1, 5)) >= build_top * 0.95


def test_marathon_build_keeps_marathon_pace_long_runs_into_peak(seasons):
    log = _season("adv-marathon", seasons)
    race = log["race_date"]
    mp = [d for d in log["days"] if d["type"] == "long_run" and "MP" in d["title"]]
    assert len(mp) >= 3
    assert any((race - date.fromisoformat(d["date"])).days <= 35 for d in mp)  # in the final five weeks


def test_short_race_week_keeps_most_of_the_volume(seasons):
    log = _season("adv-10k", seasons)
    assert _week_miles(log, 0) >= 0.5 * _week_miles(log, 1)  # was ~0.47 with a flat 5 mi easy-day cap
