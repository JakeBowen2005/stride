"""Priority 2: evaluate actual work before progressing it."""

from app.core.workout_evaluator import evaluate_workout

TARGET_800 = 360  # 6:00/mi


def ev(desc, name="6x800m", feel=8, target=TARGET_800, avg=None):
    return evaluate_workout(desc, avg, None, "workout", target, name, feel)


def test_partial_reps_at_target_do_not_advance():
    # From the review: 3 of 6 reps at target pace, feel 8 used to return "advance"
    r = ev("3x800 (2:58, 2:58, 2:58)")
    assert r.decision == "hold" and r.completion == 0.5
    assert "3 of 6" in r.reason


def test_feel_only_never_advances():
    r = ev(None)
    assert r.decision == "insufficient" and r.evidence == "none"


def test_whole_run_average_cannot_advance():
    r = ev(None, name="2x10min Hard", target=405, avg=380)  # "fast" average incl. warmup/cooldown
    assert r.decision == "insufficient" and r.evidence == "average"


def test_complete_on_target_session_advances():
    r = ev("6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)")
    assert r.decision == "advance" and r.completion == 1.0 and r.new_pace_sec is None  # level only


def test_fast_start_big_fade_cannot_recalibrate():
    r = ev("6x800 (2:40, 2:42, 2:45, 3:00, 3:05, 3:10)")
    assert r.decision != "recalibrate"


def test_clean_fast_session_recalibrates_pace_only():
    r = ev("6x800 (2:50, 2:50, 2:51, 2:50, 2:51, 2:50)")
    assert r.decision == "recalibrate" and r.new_pace_sec == TARGET_800 - 5


def test_no_feel_rating_holds_instead_of_assuming_neutral():
    r = ev("6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)", feel=None)
    assert r.decision == "hold" and "Rate how it felt" in r.reason


def test_incomplete_and_struggling_regresses():
    r = ev("2x800 (3:20, 3:25)", feel=3)
    assert r.decision == "regress"


def test_time_based_threshold_uses_paced_reps():
    r = ev("Garmin laps: 2x10min threshold (6:44, 6:46/mi) w/ 2min recovery", name="2x10min Hard", target=405)
    assert r.evidence == "splits" and r.completion == 1.0 and r.decision == "advance"


def test_time_based_partial_holds():
    r = ev("Garmin laps: 2x10min threshold (6:44/mi)", name="3x10min Hard", target=405)
    assert r.decision == "hold" and r.completion < 1


def test_easy_run_instead_of_workout_is_a_neutral_hold():
    r = ev("easy shakeout with friends", feel=5)
    assert r.decision == "hold" and r.evidence == "different_session"


def test_evaluation_is_serializable_with_policy_version():
    d = ev("6x800 (2:58, 2:59, 2:58, 2:57, 2:58, 2:59)").to_dict()
    assert d["policy_version"] == "eval-v2" and d["evidence"] == "splits"
