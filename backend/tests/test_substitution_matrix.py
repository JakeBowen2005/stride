"""Substitutions: a similar but different session than prescribed, read from laps + comment.

Each scenario is a whole run as Garmin records it (warmup, reps, recoveries, cooldown, GPS
noise) with the athlete's comment. The label must name what was run (3x1200m, not the
prescribed 6x800m), and the plan must log it as a different session, while bailed workouts
stay partial attempts and sessions run as written stay matched.
"""
import json
import random
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.session_match import session_relationship
from app.core.workout_data import prescription, segment
from app.database import SessionLocal
from app.main import app
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.services.lap_analyzer import METERS_PER_MILE as MI, analyze_laps


EASY = 570  # 9:30/mi


def build(reps, *, rest=120, rest_pace=690, mode="pressed", warm=2.0, cool=1.5, brisk_warmup=False,
          seed=0, standing=False, km=False, extra=None):
    """reps: list of (meters or None, seconds or None, pace sec/mi). Rep is distance- or time-based."""
    rnd = random.Random(seed)
    unit = 1000.0 if km else MI
    laps = []

    def autolapped(meters, seconds, intensity):
        # Garmin auto-lap at every full unit since the last lap press; remainder is its own lap
        out, left_m, left_s = [], meters, seconds
        while left_m > unit * 1.001:
            s = seconds * unit / meters
            out.append({"distance_m": unit, "duration_s": s, "intensity": intensity})
            left_m -= unit; left_s -= s
        out.append({"distance_m": left_m, "duration_s": left_s, "intensity": intensity})
        return out

    def add(meters, seconds, intensity, split):
        meters *= 1 + rnd.uniform(-0.015, 0.015)  # GPS
        laps.extend(autolapped(meters, seconds, intensity) if split else
                    [{"distance_m": meters, "duration_s": seconds, "intensity": intensity}])

    structured = mode == "structured"
    tag = (lambda t: t) if structured else (lambda t: "INTERVAL")
    wpace = [EASY + 20] * int(warm)
    if brisk_warmup and wpace:
        wpace[-1] = 490  # last warmup mile drifts quick
    for p in wpace:
        add(MI, p, tag("WARMUP"), False)
    for i, (m, s, p) in enumerate(reps):
        p += rnd.uniform(-4, 4)
        if m is None:
            s += rnd.uniform(-1.5, 1.5); m = s / p * MI
        else:
            s = m / MI * p
        add(m, s, tag("ACTIVE"), mode in ("autolap",))
        if i < len(reps) - 1 and rest:
            r = rest + rnd.uniform(-3, 3)
            add(5 if standing else r / rest_pace * MI, r, tag("RECOVERY"), False)
    for x in extra or []:
        laps.append(x)
    left = cool
    while left > 0.01:
        d = min(1.0, left); add(d * MI, d * (EASY + 10), tag("COOLDOWN"), False); left -= d
    return laps


def T(n, minutes, pace):   # n time reps
    return [(None, minutes * 60, pace)] * n


def D(n, meters, pace):    # n distance reps
    return [(meters, None, pace)] * n


def rx_reps(cat, n, *, meters=None, seconds=None, fast, slow, rest=120):
    p = prescription(cat, "track_intervals" if meters else "cruise_intervals",
                     [segment(n, meters=meters, seconds=seconds, fast=fast, slow=slow, recovery_seconds=rest)])
    p["easy_pace_sec_per_mile"] = EASY
    return p


def rx_tempo(miles, fast, slow):
    p = prescription("threshold", "continuous", [segment(1, meters=miles * MI, fast=fast, slow=slow)])
    p["easy_pace_sec_per_mile"] = EASY
    return p


R6x800 = rx_reps("intervals", 6, meters=800, fast=355, slow=365, rest=90)
R5x1k = rx_reps("intervals", 5, meters=1000, fast=360, slow=370)
R3x1200 = rx_reps("intervals", 3, meters=1200, fast=365, slow=375)
R4x1mi = rx_reps("intervals", 4, meters=MI, fast=370, slow=380)
R8x400 = rx_reps("intervals", 8, meters=400, fast=340, slow=350, rest=90)
R3x10 = rx_reps("threshold", 3, seconds=600, fast=405, slow=415)
R3x8 = rx_reps("threshold", 3, seconds=480, fast=405, slow=415)
R2x15 = rx_reps("threshold", 2, seconds=900, fast=410, slow=420, rest=180)
R6x3 = rx_reps("intervals", 6, seconds=180, fast=375, slow=385)
TEMPO3 = rx_tempo(3, 410, 420)
TEMPO4 = rx_tempo(4, 410, 420)

SUB, SAME = ("different_session", "substituted"), ("matched",)


def make(SEED):
    B = lambda *a, **k: build(*a, seed=SEED, **k)
    return [
    ("6x800 -> 3x1200", R6x800, B(D(3, 1200, 365), rest=120), "Did 3x1200 instead of the 800s", "3x1200m", "intervals", SUB),
        ("6x800 -> 5x1k", R6x800, B(D(5, 1000, 368)), "swapped for 5 x 1k", "5x1k", "intervals", SUB),
        ("6x800 -> 4x1 mile", R6x800, B(D(4, MI, 375), rest=150), "4x1mi instead", "4x1 mile", "intervals", SUB),
        ("8x400 -> 6x600", R8x400, B(D(6, 600, 350), rest=90), "6x600m on the track", "6x600m", "intervals", SUB),
        ("8x400 -> 12x400 standing", R8x400, B(D(12, 400, 345), rest=60, standing=True), "12x400 w/ 60s standing", "12x400m", "speed", SUB),
        ("5x1k -> 3x1 mile", R5x1k, B(D(3, MI, 372), rest=150), "did 3x1 mile instead", "3x1 mile", "intervals", SUB),
        ("4x1mi -> 6x1k", R4x1mi, B(D(6, 1000, 365)), "6x1k felt better today", "6x1k", "intervals", SUB),
        ("3x1200 -> 3x1 mile", R3x1200, B(D(3, MI, 375), rest=150), "ran miles not 1200s", "3x1 mile", "intervals", SUB),
        ("3x10 -> 4x10", R3x10, B(T(4, 10, 410), rest=120), "4x10min at threshold", "4x10min", "threshold", SUB),
        ("3x10 -> 4x10 autolap", R3x10, B(T(4, 10, 410), rest=120, mode="autolap"), "4x10 min", "4x10min", "threshold", SUB),
        ("3x10 -> 2x15", R3x10, B(T(2, 15, 412), rest=180, mode="autolap"), "2x15min instead", "2x15min", "threshold", SUB),
        ("3x8 -> 4mi tempo", R3x8, B([(4 * MI, None, 412)], rest=0, mode="autolap"), "Did a 4 mile tempo instead", "4 mi tempo", "threshold", SUB),
        ("3x8 -> 3x2mi", R3x8, B(D(3, 2 * MI, 415), rest=120, mode="autolap"), "3 x 2 miles threshold", "3x2 miles", "threshold", SUB),
        ("2x15 -> 3x10", R2x15, B(T(3, 10, 408), rest=120, mode="autolap"), "3x10min", "3x10min", "threshold", SUB),
        ("6x3min -> 5x4min", R6x3, B(T(5, 4, 380), rest=120), "5x4 min", "5x4min", "intervals", SUB),
        ("tempo3 -> 2x2mi", TEMPO3, B(D(2, 2 * MI, 412), rest=120, mode="autolap"), "split the tempo into 2x2 miles", "2x2 miles", "threshold", SUB),
        ("tempo4 -> 6x1k", TEMPO4, B(D(6, 1000, 365), rest=90), "intervals instead, 6x1k", "6x1k", "intervals", SUB),
        ("6x800 -> 5x1k structured", R6x800, B(D(5, 1000, 368), mode="structured"), "5x1k", "5x1k", "intervals", SUB),
        ("3x10 -> 4x10 brisk warmup", R3x10, B(T(4, 10, 410), mode="autolap", brisk_warmup=True), "did 4x10min", "4x10min", "threshold", SUB),
        ("6x800 -> 3x1200 km laps", R6x800, B(D(3, 1200, 365), km=True, mode="autolap"), "3x1200", "3x1200m", "intervals", SUB),
        ("4x1mi -> 4x1mi + strides", R4x1mi, B(D(4, MI, 375), rest=150, extra=[
        {"distance_m": 200, "duration_s": 36, "intensity": "INTERVAL"}, {"distance_m": 100, "duration_s": 45, "intensity": "INTERVAL"}] * 4),
        "4x1 mile then 4 strides", "4x1 mile", "intervals", SAME),
    # Controls: ran what was prescribed
        ("6x800 as planned", R6x800, B(D(6, 800, 360), rest=90), "Felt good", "6x800m", "intervals", SAME),
        ("3x10 as planned", R3x10, B(T(3, 10, 410), mode="autolap"), "Smooth", "3x10min", "threshold", SAME),
        ("3x8 as planned brisk wu", R3x8, B(T(3, 8, 410), mode="autolap", brisk_warmup=True), "good one", "3x8min", "threshold", SAME),
    # Traps: comment names the planned session first, bailed workouts, ladders, km laps
        ("names planned first", R6x800, B(D(5, 1000, 368)), "skipped the 6x800, did 5x1k instead", "5x1k", "intervals", SUB),
        ("names planned first time", R3x10, B(T(3, 12, 410), mode="autolap"), "instead of 3x10min i did 3x12min", "3x12min", "threshold", SUB),
        ("bailed, explained", R6x800, B(D(3, 800, 360), rest=90), "only managed 3x800, legs dead", "3x800m", "intervals", ("partial",)),
        ("bailed, silent", R6x800, B(D(3, 800, 360), rest=90), "meh", "3x800m", "intervals", ("partial",)),
        ("3x1200 no comment", R6x800, B(D(3, 1200, 365)), "good day", "3x1200m", "intervals", ("partial",)),
        ("ladder 1-2-3-2-1", R6x3, B([(None, 60, 360), (None, 120, 370), (None, 180, 380), (None, 120, 370), (None, 60, 360)], rest=90), "ladder fartlek", "5-rep fartlek", "fartlek", ("partial",)),
        ("full ladder 1-2-3-4-3-2-1", R6x3, B([(None, s, p) for s, p in ((60, 360), (120, 370), (180, 380), (240, 385), (180, 380), (120, 370), (60, 360))], rest=90), "ladder instead", "7-rep fartlek", "fartlek", SUB),
        ("4x10 km autolap", R3x10, B(T(4, 10, 410), mode="autolap", km=True), "did 4 x 10 minutes", "4x10min", "threshold", SUB),
        ("4x10 time reps standing", R3x10, B(T(4, 10, 410), rest=90, standing=True), "4x10min, standing rest", "4x10min", "threshold", SUB),
        ("6x800 planned, said so", R6x800, B(D(6, 800, 360), rest=90), "6x800 as written, short recoveries", "6x800m", "intervals", SAME),
        ("tempo3 as planned", TEMPO3, B([(3 * MI, None, 412)], rest=0, mode="autolap"), "tempo felt fine", "3 mi tempo", "threshold", SAME),
]



@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("index", range(len(make(0))), ids=[c[0] for c in make(0)])
def test_label_and_plan_relationship(index, seed):
    name, rx, laps, comment, label, category, relationship = make(seed)[index]
    found = analyze_laps(laps, EASY, comment)
    assert found, name
    assert (found["label"], found["category"]) == (label, category), found["text"]
    assert session_relationship(rx, found)["status"] in relationship


def seed_day(rx, laps, title):
    today = date.today()
    with SessionLocal() as db:
        plan = Plan(user_id=1, start_date=today.isoformat(), end_date=(today + timedelta(days=13)).isoformat(),
                    prescribed_from=today.isoformat(), is_active=True, load=json.dumps({"weekly_budgets": [40, 40]}))
        db.add(plan); db.flush()
        for i in range(14):
            d = today + timedelta(days=i)
            db.add(PlannedWorkout(plan_id=plan.id, date=d.isoformat(), day_name=d.strftime("%A").lower(),
                                  week_number=i // 7 + 1, type="workout" if i == 0 else "easy",
                                  title=title if i == 0 else "Easy Run", distance_miles=7.0 if i == 0 else 5.0,
                                  prescription=json.dumps(rx) if i == 0 else None))
        miles = sum(lap["distance_m"] for lap in laps) / MI
        db.add(Activity(user_id=1, source="garmin", external_id="swap-1", name="Run", workout_type="workout",
                        date=datetime.combine(today, datetime.min.time()).replace(hour=7), distance_meters=miles * MI,
                        duration_seconds=sum(lap["duration_s"] for lap in laps), splits=json.dumps(laps),
                        description="Garmin laps: (pending)"))
        db.commit()
    return today


@pytest.mark.parametrize("rx, reps, title, comment, ran", [
    (R6x800, D(3, 1200, 365), "6x800m Intervals", "Did 3x1200 instead of the 800s", "3x1200m Intervals"),
    (R3x10, T(4, 10, 410), "3x10min Threshold", "4x10min at threshold today", "4x10min Threshold"),
    (R3x8, [(4 * MI, None, 412)], "3x8min Threshold", "Did a 4 mile tempo instead", "4 mi Tempo"),
])
def test_saved_comment_relabels_the_day(rx, reps, title, comment, ran):
    client = TestClient(app)
    today = seed_day(rx, build(reps, mode="autolap", rest=120 if len(reps) > 1 else 0), title)
    r = client.post(f"/api/plans/1/feedback/{today}", json={"feel_notes": comment})
    assert r.status_code == 200, r.text
    evaluation = r.json()["evaluation"]
    assert evaluation["decision"] == "off_plan" and ran in evaluation["reason"], evaluation
    day = next(d for w in client.get("/api/plans/1/current").json()["weeks"] for d in w["days"] if d["date"] == today.isoformat())
    assert day["actual"]["workout"]["title"] == ran and day["actual"]["workout"]["off_plan"] is True
    assert day["actual"]["session"]["title"] == ran
