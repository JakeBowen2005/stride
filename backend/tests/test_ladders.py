"""Tests for the workout ladders and pace injection.

A ladder bug shows up as a workout that reads perfectly well but is at the
wrong pace or the wrong distance for the goal — the kind of thing you only
notice halfway through the third rep.
"""

import pytest

from app.core.workout_ladders import (
    get_deload_workout,
    get_ladder,
    get_taper_workout,
    get_workout_at_level,
    highest_non_mp_level,
    level_requires_mp,
    max_level,
)

PACES = {
    "interval_pace": 352,       # 5:52/mi, anchored on 800m repeats
    "interval_pace_fast": 342,
    "threshold_pace": 400,      # 6:40/mi
    "tempo_pace": 410,          # 6:50/mi continuous
    "strides_pace": 300,
    "goal_race_pace": 378,      # 6:18/mi
    "race_pace": 378,
}

CATEGORIES = ["threshold", "intervals"]
DISTANCES = ["5k", "10k", "half", "marathon"]


@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("distance", DISTANCES)
def test_every_ladder_exists_and_is_complete(category, distance):
    ladder = get_ladder(category, distance)
    assert ladder, f"no {category} ladder for {distance}"
    for i, level in enumerate(ladder, 1):
        assert level["level"] == i, f"{category}/{distance} level {i} misnumbered"
        assert level["name"]
        assert level["purpose"]
        assert level["total_miles"] > 0


def test_marathon_and_5k_use_different_ladders():
    """get_ladder() used to ignore `distance` entirely."""
    assert get_ladder("threshold", "marathon") is not get_ladder("threshold", "5k")
    assert get_ladder("intervals", "marathon") is not get_ladder("intervals", "5k")


def test_marathon_threshold_ladder_is_built_on_cruise_intervals():
    names = [lvl["name"] for lvl in get_ladder("threshold", "marathon")]
    assert any("3x2mi" in n for n in names), "3x2mi is the staple marathon workout"
    assert any("4x2mi" in n for n in names)


@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("distance", DISTANCES)
def test_every_level_renders_without_leftover_placeholders(category, distance):
    for level in range(1, max_level(category, distance) + 1):
        workout = get_workout_at_level(category, level, PACES, distance)
        assert "{" not in workout["structure"], (
            f"{category}/{distance} L{level}: {workout['structure']}"
        )
        assert workout["name"]
        assert workout["total_miles"] > 0


@pytest.mark.parametrize("category", CATEGORIES)
@pytest.mark.parametrize("distance", DISTANCES)
def test_ladder_volume_trends_upward(category, distance):
    """Level 12 should be a bigger session than level 1."""
    first = get_workout_at_level(category, 1, PACES, distance)
    last = get_workout_at_level(category, max_level(category, distance), PACES, distance)
    assert last["total_miles"] >= first["total_miles"]


def test_levels_are_clamped_to_the_ladder():
    workout = get_workout_at_level("threshold", 999, PACES, "marathon")
    assert workout["name"] == get_ladder("threshold", "marathon")[-1]["name"]
    workout = get_workout_at_level("threshold", -3, PACES, "marathon")
    assert workout["name"] == get_ladder("threshold", "marathon")[0]["name"]


# ── Pace injection ────────────────────────────────────────────────

def test_broken_reps_are_faster_than_continuous_tempo():
    """Rest between reps is what lets you hold the faster pace."""
    broken = get_workout_at_level("threshold", 1, PACES, "marathon")   # 2x2mi
    continuous = get_workout_at_level("threshold", 2, PACES, "marathon")  # 20min tempo
    assert "6:40" in broken["structure"]
    assert "6:50" in continuous["structure"]


def test_longer_reps_get_slower_paces():
    """interval_pace is anchored on 800m splits.

    Prescribing mile repeats at 800m repeat pace asked Jake for 5:42 miles
    when his real mile repeats are 6:06-6:24.
    """
    eight = get_workout_at_level("intervals", 1, PACES, "marathon")   # 4x800m
    mile = get_workout_at_level("intervals", 5, PACES, "marathon")    # 4x1mi
    assert "5:42-5:52" in eight["structure"]
    assert "5:54-6:04" in mile["structure"]


def test_mp_levels_use_goal_pace():
    for level in range(1, max_level("threshold", "marathon") + 1):
        if level_requires_mp("threshold", level, "marathon"):
            workout = get_workout_at_level("threshold", level, PACES, "marathon")
            assert "6:18" in workout["structure"], workout["structure"]
            return
    pytest.fail("marathon threshold ladder has no goal-pace level")


def test_highest_non_mp_level_avoids_goal_pace_work():
    top = max_level("threshold", "marathon")
    safe = highest_non_mp_level("threshold", top, "marathon")
    assert not level_requires_mp("threshold", safe, "marathon")
    assert safe <= top


# ── Deload and taper variants ─────────────────────────────────────

@pytest.mark.parametrize("category", CATEGORIES)
def test_deload_workout_is_smaller_than_the_current_level(category):
    full = get_workout_at_level(category, 10, PACES, "marathon")
    deload = get_deload_workout(category, 10, PACES, "marathon")
    assert deload["total_miles"] <= full["total_miles"]


@pytest.mark.parametrize("distance", DISTANCES)
@pytest.mark.parametrize("category", CATEGORIES)
def test_taper_workouts_render_and_stay_short(distance, category):
    for weeks_out in (1, 2, 3):
        workout = get_taper_workout(weeks_out, PACES, distance, category)
        assert workout is not None
        assert "{" not in workout["structure"]
        assert workout["total_miles"] <= 8.0


def test_taper_categories_give_different_sessions():
    speed = get_taper_workout(2, PACES, "marathon", "intervals")
    threshold = get_taper_workout(2, PACES, "marathon", "threshold")
    assert speed["name"] != threshold["name"]
