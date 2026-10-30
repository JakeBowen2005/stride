import io
import json
from datetime import date, timedelta

import fitdecode
import pytest
from fastapi.testclient import TestClient

from app.core.workout_data import MI, long_run_prescription, prescription, segment
from app.database import SessionLocal
from app.main import app
from app.models.plan import Plan, PlannedWorkout
from app.services.fit_workout import build_steps, encode, workout_fit

client = TestClient(app)


def intervals():
    data = prescription("intervals", "distance_intervals",
                        [segment(6, meters=800, fast=365, slow=372, recovery_seconds=90)], level=5)
    data.update(warmup=segment(meters=1.5 * MI), cooldown=segment(meters=MI))
    return {"date": "2026-11-03", "type": "workout", "title": "6x800m", "distance_miles": 6,
            "warmup": "1.5mi easy", "cooldown": "1mi easy", "prescription": json.dumps(data)}


def decode(raw):
    """Messages by name, parsed by an independent FIT reader that checks both CRCs."""
    out = {}
    with fitdecode.FitReader(io.BytesIO(raw), check_crc=fitdecode.CrcCheck.RAISE) as reader:
        for frame in reader:
            if isinstance(frame, fitdecode.FitDataMessage):
                out.setdefault(frame.name, []).append({f.name: f.value for f in frame.fields})
    return out


def test_interval_session_round_trips_through_a_fit_reader():
    _, raw = workout_fit(intervals(), created=1793750400)
    msgs = decode(raw)
    assert msgs["file_id"][0]["type"] == "workout"
    workout = msgs["workout"][0]
    assert workout["sport"] == "running" and workout["wkt_name"] == "11/03 6x800m"
    steps = msgs["workout_step"]
    assert workout["num_valid_steps"] == len(steps) == 5
    warm, rep, jog, repeat, cool = steps
    assert warm["intensity"] == "warmup" and warm["duration_type"] == "distance"
    assert warm["duration_distance"] == pytest.approx(1.5 * MI, abs=0.01)
    assert rep["duration_distance"] == 800 and rep["target_type"] == "speed"
    # 6:05-6:12/mi widened to a 10s range, as m/s: the slower pace is the low bound
    assert rep["custom_target_speed_low"] == pytest.approx(MI / 373.5, abs=0.001)
    assert rep["custom_target_speed_high"] == pytest.approx(MI / 363.5, abs=0.001)
    assert jog["intensity"] == "recovery" and jog["duration_time"] == 90
    assert repeat["duration_type"] == "repeat_until_steps_cmplt"
    assert repeat["duration_step"] == 1 and repeat["repeat_steps"] == 6
    assert cool["intensity"] == "cooldown"


def test_single_pace_targets_are_widened_so_the_watch_does_not_nag():
    data = prescription("threshold", "time_intervals",
                        [segment(2, seconds=420, fast=410, slow=410, recovery_seconds=120)])
    steps = build_steps({"type": "workout", "distance_miles": 6, "prescription": data,
                         "warmup": "2mi easy + 4 strides", "cooldown": "1.5mi easy"})
    work = steps[1]
    assert work["duration_value"] == 420_000
    assert work["pace"] == {"fast": 405, "slow": 415}
    # Warmup text from the plan row becomes a distance step; strides stay in the note.
    assert steps[0]["duration_value"] == round(2 * MI * 100) and "strides" in steps[0]["notes"]


def test_easy_runs_have_no_pace_alarm():
    steps = build_steps({"type": "easy", "distance_miles": 6, "description": "Conversational."})
    assert len(steps) == 1 and steps[0]["pace"] is None
    assert steps[0]["duration_value"] == round(6 * MI * 100)


def test_long_run_only_targets_the_race_pace_part():
    data = long_run_prescription([("easy", 6), ("race_pace", 6, 410), ("easy", 2)], "Finish at MP.")
    steps = build_steps({"type": "long_run", "distance_miles": 14, "prescription": data})
    assert [s["pace"] is None for s in steps] == [True, False, True]
    assert steps[1]["pace"] == {"fast": 405, "slow": 415}


def test_unparseable_warmup_becomes_a_lap_button_step():
    data = prescription("intervals", "distance_intervals", [segment(4, meters=400, fast=340, slow=345)])
    steps = build_steps({"type": "workout", "distance_miles": 4, "prescription": data, "warmup": "Easy jog + drills"})
    assert steps[0]["duration_type"] == 5 and "Press lap" in steps[0]["notes"]


def test_rest_day_and_unstructured_workouts_are_refused():
    with pytest.raises(ValueError):
        build_steps({"type": "rest", "distance_miles": 0})
    with pytest.raises(ValueError, match="no step structure"):
        build_steps({"type": "workout", "title": "4x800m", "distance_miles": 6, "prescription": None})


def test_long_names_are_truncated_on_character_boundaries():
    raw = encode("Tempo é" * 10, [{"name": "é" * 30, "duration_type": 5, "duration_value": None,
                                   "intensity": 0, "pace": None, "notes": None}])
    assert decode(raw)["workout_step"][0]["wkt_step_name"] == "é" * 11


def test_download_endpoint():
    monday = date.today() + timedelta(days=7 - date.today().weekday())
    with SessionLocal() as db:
        p = Plan(user_id=1, start_date=monday.isoformat(), end_date=(monday + timedelta(days=13)).isoformat(),
                 prescribed_from=monday.isoformat(), load=json.dumps({"weekly_budgets": [30, 30]}))
        db.add(p)
        db.flush()
        row = intervals()
        db.add(PlannedWorkout(plan_id=p.id, date=monday.isoformat(), day_name="monday", week_number=1,
                              type=row["type"], title=row["title"], distance_miles=6, warmup=row["warmup"],
                              cooldown=row["cooldown"], prescription=row["prescription"]))
        db.add(PlannedWorkout(plan_id=p.id, date=(monday + timedelta(days=1)).isoformat(), day_name="tuesday",
                              week_number=1, type="rest", title="Rest", distance_miles=0))
        db.commit()
    r = client.get(f"/api/plans/me/sessions/{monday}/workout.fit")
    assert r.status_code == 200 and r.headers["content-type"] == "application/vnd.ant.fit"
    assert f'stride-{monday}-6x800m.fit' in r.headers["content-disposition"]
    assert len(decode(r.content)["workout_step"]) == 5
    assert client.get(f"/api/plans/me/sessions/{monday + timedelta(days=1)}/workout.fit").status_code == 400
