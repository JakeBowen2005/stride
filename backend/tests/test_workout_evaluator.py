"""Tests for post-workout evaluation and ladder progression decisions.

The descriptions used here are real formats from Jake's Strava log. If the
parser stops recognising them, pace calibration and progression both silently
fall back to guessing.
"""

import pytest

from app.core.workout_evaluator import (
    calculate_fade,
    determine_starting_level,
    evaluate_workout,
    extract_rep_count,
    extract_splits_from_description,
    identify_workout_type,
)


# ── Split parsing ─────────────────────────────────────────────────

def test_parses_800m_repeat_splits():
    splits = extract_splits_from_description("6x800 (3:01,3:04,3:02,3:05,3:03,3:04) 90s jog")
    assert splits["800"] == [181, 184, 182, 185, 183, 184]


def test_parses_mile_repeat_splits():
    splits = extract_splits_from_description("4x1 mile (6:24,6:19,6:25,6:11) 3 min walk rest")
    assert splits["mile"] == [384, 379, 385, 371]


def test_parses_multi_mile_threshold_reps():
    """3x2mi is THE marathon threshold workout and used to parse to nothing.

    Values logged for multi-mile reps are per-mile paces, not rep times.
    """
    splits = extract_splits_from_description("Main set 3x2 miles (6:36,6:36,6:20) 0.25 mile jog rest")
    assert splits["mile"] == [396, 396, 380]


def test_parses_two_by_three_mile_reps():
    splits = extract_splits_from_description("Main set 2x3 miles (6:47,6:45) 1 mile float")
    assert splits["mile"] == [407, 405]


def test_ignores_nonsense_values():
    """Sanity ranges keep stray numbers out of the pace data."""
    splits = extract_splits_from_description("6x800 (3:01, 0:02, 99:00, 3:04)")
    assert splits["800"] == [181, 184]


def test_handles_missing_description():
    assert extract_splits_from_description("") == {}
    assert extract_splits_from_description(None) == {}


def test_rep_count_extraction():
    assert extract_rep_count("6x800m") == (6, "800")
    assert extract_rep_count("5x1K") == (5, "1k")
    assert extract_rep_count("") == (0, "")


# ── Fade ──────────────────────────────────────────────────────────

def test_fade_is_positive_when_slowing():
    assert calculate_fade([180, 180, 190, 192]) > 0


def test_fade_is_negative_on_a_negative_split():
    """Jake negative-splits workouts naturally — this must not read as failure."""
    assert calculate_fade([396, 396, 380, 358]) < 0


def test_fade_needs_at_least_two_splits():
    assert calculate_fade([180]) == 0.0
    assert calculate_fade([]) == 0.0


# ── Workout type detection ────────────────────────────────────────

@pytest.mark.parametrize("desc,expected", [
    ("6x800 (3:01,3:04)", "intervals"),
    ("3x2 miles threshold", "threshold"),
    ("20min tempo", "threshold"),
    ("fartlek 8x1min", "intervals"),
    ("easy shakeout", "easy"),
])
def test_workout_type_detection(desc, expected):
    assert identify_workout_type(desc) == expected


# ── The bug that froze the threshold ladder ───────────────────────

def test_time_based_session_can_advance():
    """This is the big one.

    With no parseable rep splits, the evaluator compared the WHOLE RUN's
    average pace — warmup, cooldown and recovery jogs included — against the
    prescribed rep pace. That reads ~90 sec/mi slow no matter how well the
    reps went, so `pace_diff <= 5` was unreachable and every time-based
    threshold session returned HOLD or REGRESS. Forever.
    """
    result = evaluate_workout(
        actual_description="2x10min hard, felt controlled throughout",
        actual_avg_pace_sec=480,      # whole-run average, incl. warmup/cooldown
        actual_distance_miles=7.0,
        prescribed_type="workout",
        prescribed_pace_sec=395,      # the rep pace
        prescribed_name="2x10min Hard",
        feel_rating=8,
    )
    assert result.decision == "advance"
    assert result.pace_confidence == "none"


def test_whole_run_average_is_never_treated_as_rep_pace():
    result = evaluate_workout(
        actual_description="25min continuous tempo",
        actual_avg_pace_sec=520,
        actual_distance_miles=6.5,
        prescribed_type="workout",
        prescribed_pace_sec=400,
        prescribed_name="25min Continuous Tempo",
        feel_rating=7,
    )
    assert result.pace_diff_sec == 0.0


def test_effort_only_session_regresses_on_a_bad_feel():
    result = evaluate_workout(
        actual_description="2x10min hard",
        actual_avg_pace_sec=520, actual_distance_miles=7.0,
        prescribed_type="workout", prescribed_pace_sec=395,
        prescribed_name="2x10min Hard", feel_rating=3,
    )
    assert result.decision == "regress"


def test_effort_only_session_holds_on_a_middling_feel():
    result = evaluate_workout(
        actual_description="2x10min hard",
        actual_avg_pace_sec=520, actual_distance_miles=7.0,
        prescribed_type="workout", prescribed_pace_sec=395,
        prescribed_name="2x10min Hard", feel_rating=6,
    )
    assert result.decision == "hold"


# ── Decisions with real split data ────────────────────────────────

def test_double_advance_when_paces_are_beaten_comfortably():
    result = evaluate_workout(
        actual_description="Main set 3x2 miles (6:36,6:36,6:20) 0.25 jog",
        actual_avg_pace_sec=470, actual_distance_miles=11.0,
        prescribed_type="workout", prescribed_pace_sec=400,
        prescribed_name="3x2mi Threshold", feel_rating=9,
    )
    assert result.decision == "advance"
    assert result.advance_steps == 2
    assert result.pace_confidence == "splits"


def test_single_advance_on_solid_execution():
    result = evaluate_workout(
        actual_description="Main set 3x2 miles (6:38,6:40,6:39)",
        actual_avg_pace_sec=470, actual_distance_miles=11.0,
        prescribed_type="workout", prescribed_pace_sec=400,
        prescribed_name="3x2mi Threshold", feel_rating=7,
    )
    assert result.decision == "advance"
    assert result.advance_steps == 1


def test_regress_when_paces_are_badly_missed():
    result = evaluate_workout(
        actual_description="Main set 3x2 miles (7:10,7:15,7:22)",
        actual_avg_pace_sec=470, actual_distance_miles=11.0,
        prescribed_type="workout", prescribed_pace_sec=400,
        prescribed_name="3x2mi Threshold", feel_rating=4,
    )
    assert result.decision == "regress"


def test_recalibrate_when_paces_are_smashed():
    result = evaluate_workout(
        actual_description="6x800 (2:50,2:49,2:51,2:48,2:50,2:49)",
        actual_avg_pace_sec=430, actual_distance_miles=6.5,
        prescribed_type="workout", prescribed_pace_sec=380,
        prescribed_name="6x800m", feel_rating=8,
    )
    assert result.decision == "recalibrate"
    assert result.new_pace_sec is not None
    assert result.new_pace_sec < 380


def test_cut_short_session_holds_regardless_of_pace():
    """Two reps of a prescribed six is not a level you have consolidated."""
    result = evaluate_workout(
        actual_description="6x800 (2:50,2:49) — cut it short, legs done",
        actual_avg_pace_sec=430, actual_distance_miles=4.0,
        prescribed_type="workout", prescribed_pace_sec=380,
        prescribed_name="6x800m", feel_rating=8,
    )
    assert result.decision == "hold"
    assert result.reps_completed == 2
    assert result.reps_prescribed == 6


def test_swapped_workout_holds_rather_than_regressing():
    result = evaluate_workout(
        actual_description="easy 5 miles, legs felt flat",
        actual_avg_pace_sec=540, actual_distance_miles=5.0,
        prescribed_type="workout", prescribed_pace_sec=400,
        prescribed_name="3x2mi Threshold", feel_rating=6,
    )
    assert result.decision == "hold"


def test_no_data_at_all_holds():
    result = evaluate_workout(
        actual_description=None, actual_avg_pace_sec=None, actual_distance_miles=None,
        prescribed_type="workout", prescribed_pace_sec=400,
        prescribed_name="3x2mi Threshold", feel_rating=None,
    )
    assert result.decision == "hold"


# ── Starting level detection ──────────────────────────────────────

JAKE_MARATHON_BLOCK = [
    "Main set 3x2 miles (6:36,6:36,6:20) 0.25 mile jog rest",
    "4x1 mile (6:24,6:19,6:25,6:11) 3 min walk rest",
    "6x800 (3:01,3:04,3:02,3:05,3:03,3:04)",
]


def test_starting_level_is_ladder_specific():
    """6x800m is level 5 on the 5K ladder and level 3 on the marathon one.

    Carrying a level number across a goal change would silently prescribe a
    different workout than intended.
    """
    marathon_intervals = determine_starting_level("intervals", JAKE_MARATHON_BLOCK, None, "marathon")
    five_k_intervals = determine_starting_level("intervals", JAKE_MARATHON_BLOCK, None, "5k")
    assert marathon_intervals != five_k_intervals


def test_marathon_threshold_level_from_real_history():
    level = determine_starting_level("threshold", JAKE_MARATHON_BLOCK, None, "marathon")
    assert level == 4  # 3x2mi Threshold


def test_two_mile_reps_do_not_seed_the_interval_ladder():
    """2mi reps are threshold work, not VO2max."""
    level = determine_starting_level("intervals", ["Main set 3x2 miles (6:36,6:36,6:20)"], None, "marathon")
    assert level <= 3


def test_no_history_starts_at_level_one():
    assert determine_starting_level("threshold", [], None, "marathon") == 1
    assert determine_starting_level("intervals", [], None, "5k") == 1
