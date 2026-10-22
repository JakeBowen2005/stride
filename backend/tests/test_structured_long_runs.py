"""Beginners build through deloads; structured long runs are verifiable quality."""
import json
from datetime import date, datetime, timedelta

from app.api.plans import _assess_previous_block
from app.core.load_policy import plan_load, training_level
from app.core.plan_validator import fit_week_to_budget
from app.core.workout_data import MI, day_prescription, demanding_long_run, long_run_prescription
from app.database import SessionLocal
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout


# ── Ramp: down weeks don't reset the build ──────────────────────────────────

def test_beginner_three_up_one_down_keeps_building():
    # Deload last week: return to the pre-deload level first, then grow. Never restart from the average.
    history = [14, 15, 16, 12]
    level, after_down = training_level(sum(history) / 4, history)
    assert level == 15 and after_down is True
    load = plan_load(sum(history) / 4, 16, "beginner", "race", 2, completed_weeks=history)
    assert load.weekly_budgets == [15.0, 15.8] and load.training_level == 15
    assert all(b > load.baseline for b in load.weekly_budgets)


def test_down_week_inside_the_window_resumes_from_the_loaded_weeks():
    history = [16, 12, 16.5, 17]  # deload two weeks ago, then back to full volume
    load = plan_load(sum(history) / 4, 17, "beginner", "race", 2, completed_weeks=history)
    assert load.training_level == round((16 + 16.5 + 17) / 3, 1)
    assert load.weekly_budgets[1] <= load.training_level * 1.10 + 0.05  # +10% over the block, the beginner limit


def test_spikes_breaks_and_steady_histories_keep_the_four_week_average():
    for history in ([10, 10, 10, 38], [38, 38, 0, 38], [20, 21, 22, 23]):
        baseline = sum(history) / 4
        assert training_level(baseline, history)[0] == baseline
    # A down week followed by a spike: the spike is ignored, not planned from.
    level, _ = training_level(13.5, [12, 9, 12, 21])
    assert level == 13.5


def test_fatigue_recovery_still_starts_from_the_conservative_average():
    history = [14, 15, 16, 12]
    load = plan_load(sum(history) / 4, 16, "beginner", "race", 2, completed_weeks=history, assessment="recovery")
    assert max(load.weekly_budgets) <= load.baseline * 0.7 + 0.05


# ── Structured long runs are numbers, not just text ─────────────────────────

def test_marathon_pace_long_run_has_a_checkable_prescription():
    data = long_run_prescription([("easy", 10), ("race_pace", 10, 410)], "10mi easy, then 10mi at goal MP.", easy_pace=500)
    assert data["format"] == "continuous" and len(data["segments"]) == 1
    work = data["segments"][0]
    assert work["category"] == "race_pace" and round(work["distance_meters"] / MI) == 10
    assert work["pace_range_sec_per_mile"] == {"fast": 405, "slow": 415}
    assert round(data["warmup"]["distance_meters"] / MI) == 10 and data["cooldown"] is None
    assert data["easy_pace_sec_per_mile"] == 500
    day = {"type": "long_run", "title": "10 + 10 MP Long Run", "distance_miles": 20, "prescription": data}
    assert day_prescription(day) is data and demanding_long_run({**day, "prescription": json.dumps(data)})


def test_repeated_marathon_pace_blocks_become_reps_with_float():
    parts = [("easy", 5)] + [p for _ in range(3) for p in (("race_pace", 4, 410), ("easy", 1))]
    data = long_run_prescription(parts, "5mi easy, then 3x4mi at MP with 1mi float, 1mi easy.")
    (block,) = data["segments"]
    assert block["reps"] == 3 and round(block["recovery_meters"] / MI) == 1 and data["format"] == "distance_intervals"


def test_a_shortened_long_run_drops_its_structure():
    days = [{"date": "2026-10-26", "type": "easy", "title": "Easy Run", "distance_miles": 3},
            {"date": "2026-10-31", "type": "long_run", "title": "10 + 10 MP Long Run", "distance_miles": 20,
             "prescription": long_run_prescription([("easy", 10), ("race_pace", 10, 410)], "x")}]
    fit_week_to_budget(days, 18, "easy", lambda miles: {"title": "Easy Long Run", "description": "easy", "prescription": None})
    assert days[1]["distance_miles"] < 20 and days[1]["prescription"] is None


# ── The block review verifies them from laps ────────────────────────────────

def _block_with_mp_long_run(mp_pace_run: float):
    monday = date.today() - timedelta(days=date.today().weekday() + 14)
    long_day = monday + timedelta(days=5)
    data = long_run_prescription([("easy", 10), ("race_pace", 10, 410)], "10mi easy, then 10mi at goal MP.", easy_pace=500)
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=13)).isoformat(),
                    prescribed_from=monday.isoformat(), is_active=True)
        db.add(plan)
        db.flush()
        db.add(PlannedWorkout(plan_id=plan.id, date=long_day.isoformat(), day_name="saturday", week_number=1, type="long_run",
                              title="10 + 10 MP Long Run", distance_miles=20, prescription=json.dumps(data)))
        # Two full weeks of easy running around it, all completed, so the block can be assessed.
        for offset in range(14):
            day = monday + timedelta(days=offset)
            if day == long_day or day.weekday() == 6:
                continue
            db.add(PlannedWorkout(plan_id=plan.id, date=day.isoformat(), day_name=day.strftime("%A").lower(),
                                  week_number=offset // 7 + 1, type="easy", title="Easy Run", distance_miles=6, feel_rating=7))
            db.add(Activity(user_id=1, source="manual", date=datetime.combine(day, datetime.min.time()), name="Easy",
                            distance_meters=6 * MI, duration_seconds=6 * 500))
        laps = [{"intensity": "WARMUP", "distance_m": 10 * MI, "duration_s": 10 * 500},
                {"intensity": "ACTIVE", "distance_m": 10 * MI, "duration_s": 10 * mp_pace_run},
                {"intensity": "COOLDOWN", "distance_m": 0.02 * MI, "duration_s": 10}]
        db.add(Activity(user_id=1, source="manual", date=datetime.combine(long_day, datetime.min.time()), name="MP long run",
                        distance_meters=20 * MI, duration_seconds=sum(lap["duration_s"] for lap in laps), splits=json.dumps(laps)))
        db.commit()
        return _assess_previous_block(plan, db)


def test_mp_long_run_run_on_target_counts_as_verified_quality():
    assessment = _block_with_mp_long_run(412)
    assert assessment.decision == "build", assessment.reasons
    assert any("Verified 1 of 1" in r for r in assessment.reasons)


def test_mp_long_run_run_far_too_slow_is_not_verified():
    assessment = _block_with_mp_long_run(440)  # 30s/mi slower than marathon pace
    assert assessment.decision == "hold", assessment.reasons
    assert any("demanding long run lacks" in r for r in assessment.reasons)
