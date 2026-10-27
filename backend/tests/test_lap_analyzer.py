from app.services.lap_analyzer import summarize_workout
from app.services.pace_calibrator import _extract_splits, _extract_mile_splits, _extract_threshold_paces

MI = 1609.34
EASY = 540  # 9:00/mi


def lap(dist, dur, intensity=None):
    return {"distance_m": dist, "duration_s": dur, "intensity": intensity}


def test_800_repeats_from_manual_laps():
    laps = [lap(MI * 1.5, 810)]
    for t in (182, 184, 181, 185, 183, 184):
        laps += [lap(800, t), lap(250, 90)]
    laps.append(lap(MI * 1.5, 820))
    s = summarize_workout(laps, EASY)
    assert s.startswith("Garmin laps: 6x800 (3:02, 3:04, 3:01, 3:05, 3:03, 3:04)")
    assert "90s recovery" in s
    # The existing pace calibrator can read it
    assert len(_extract_splits(s.lower(), "800")) == 6


def test_structured_workout_threshold_minutes():
    laps = [lap(MI * 1.5, 800, "WARMUP")]
    for _ in range(4):
        laps += [lap(1450, 600, "ACTIVE"), lap(300, 120, "RECOVERY")]
    laps.append(lap(MI, 540, "COOLDOWN"))
    s = summarize_workout(laps, EASY)
    assert "4x10min threshold" in s
    assert len(_extract_threshold_paces(s.lower())) == 4


def test_mile_repeats():
    laps = [lap(MI * 2, 1080)]
    for t in (384, 379, 385, 371):
        laps += [lap(MI, t), lap(400, 180)]
    s = summarize_workout(laps, EASY)
    assert "4x1 mile (6:24, 6:19, 6:25, 6:11)" in s
    assert len(_extract_mile_splits(s.lower())) == 4


def test_continuous_tempo_auto_laps():
    laps = [lap(MI, 545), lap(MI, 540), lap(MI, 410), lap(MI, 405), lap(MI, 402), lap(MI, 400), lap(MI, 560)]
    s = summarize_workout(laps, EASY)
    assert s.startswith("Garmin laps: tempo 4 miles")


def test_easy_run_is_not_a_workout():
    laps = [lap(MI, t) for t in (552, 540, 535, 548, 530, 541)]
    assert summarize_workout(laps, EASY) is None


def test_easy_run_with_one_fast_downhill_mile():
    laps = [lap(MI, t) for t in (552, 540, 470, 548, 530)]
    assert summarize_workout(laps, EASY) is None


def test_slow_hilly_run_without_easy_pace_is_not_reps():
    # Real Oct 16 2026 run: all laps tagged INTERVAL, 10:50-13:19/mi, no easy-pace reference
    laps = [lap(MI, t, "INTERVAL") for t in (650, 776, 799, 661, 739, 677, 650)]
    assert summarize_workout(laps, None) is None
    assert summarize_workout(laps, EASY) is None


def _threshold_with_brisk_warmup():
    """2x12min threshold after a warmup that drifts quick (8:53 then 8:03 / 8:11), auto-lapped:
    the athlete's real session that read as a "3-rep fartlek"."""
    def at(miles, pace):
        return lap(MI * miles, miles * pace)
    return [at(1, 533), at(1, 483), at(0.37, 491), at(1, 410), at(0.75, 414), at(0.23, 770),
            at(1, 406), at(0.78, 404), at(0.88, 513)]


def test_brisk_warmup_mile_is_not_a_rep():
    # A slow easy reference (9:50) lets the 8:03 warmup mile pass the work cutoff on its own
    from app.services.lap_analyzer import analyze_laps
    for easy in (540, 590, 620):
        found = analyze_laps(_threshold_with_brisk_warmup(), easy)
        assert found["label"] == "2x12min" and found["category"] == "threshold", easy
        assert [round(r["pace_sec_per_mile"]) for r in found["reps"]] == [412, 405]


def test_athletes_comment_names_the_reps(monkeypatch):
    from app.services import lap_analyzer
    from app.services.lap_analyzer import analyze_laps, structure_hint
    assert structure_hint("instead of the 3 mile tempo i did 2x12 min at threshold") == {"reps": 2, "seconds": 720}
    assert structure_hint("6x800 w/ 90s jog") == {"reps": 6, "meters": 800}
    assert structure_hint("3 x 2 miles") == {"reps": 3, "meters": 2 * MI}
    assert structure_hint("did 2x12 today") is None  # minutes or laps? not guessed
    # Without the warmup trim the laps alone read three reps; the comment says which two
    monkeypatch.setattr(lap_analyzer, "_trim_edges", lambda laps, work, paces: work)
    laps = _threshold_with_brisk_warmup()
    assert analyze_laps(laps, 590)["label"] == "3-rep fartlek"
    found = analyze_laps(laps, 590, "Felt good, did 2x12 min at threshold")
    assert found["label"] == "2x12min" and found["category"] == "threshold"
    assert found["work_miles"] == 3.53
    # A description that matches none of the measured reps leaves the lap read alone
    assert analyze_laps(laps, 590, "8x400m")["label"] == "3-rep fartlek"
