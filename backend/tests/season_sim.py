"""Whole-season simulation: seed a synthetic athlete, then run every block to race day.

Each day the athlete runs exactly what the active plan prescribes (workouts with
laps at the prescribed paces), or, when ``struggle`` is set, 80% of easy miles and
every second workout skipped. On the Monday after a block ends the next block is
generated and approved through the real API code. Used by test_season_matrix.py;
single-block invariants can't see season-level problems (post-race rest, long-run
growth, taper shape).
"""
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import time_machine

from app.api.plans import PlanRequest, approve_draft, generate_training_plan
from app.core.workout_data import MI
from app.database import Base, SessionLocal, engine
from app.models.activity import Activity
from app.models.plan import Plan, PlannedWorkout
from app.models.wellness import DailyWellness
from app.services.demo_seed import seed_demo
from app.services.lap_analyzer import lap_split

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "demo" / "scenarios"
START = date(2026, 11, 2)  # a Monday


def scenario(name: str, **overrides) -> dict:
    return json.loads((SCENARIO_DIR / f"{name}.json").read_text()) | overrides


INTERMEDIATE = {
    "id": "intermediate", "name": "Sim · Intermediate", "description": "Synthetic intermediate road runner.", "age": 33,
    "experience": "intermediate", "years_running": 3, "distance": "half", "target_seconds": 6000, "weeks_to_race": 12,
    "terrain": "road", "days_per_week": 5, "rest_days": ["monday", "friday"], "long_run_day": "saturday",
    "weekly_miles": [26, 28, 30, 24, 30, 31, 32, 26, 32, 33, 33, 32], "easy_pace": 570, "threshold_pace": 440,
    "interval_pace": 410, "long_miles": 11, "ladder_level": 3, "prs": {"5k": 1260, "10k": 2640, "half": 5880},
}


def profiles() -> dict[str, dict]:
    beg, adv, trail = scenario("beginner-marathon"), scenario("sub3-marathon"), scenario("trail-100k")
    return {
        "beg-10k": beg | {"id": "beg-10k", "distance": "10k", "target_seconds": 3600, "weeks_to_race": 10},
        "beg-half": beg | {"id": "beg-half", "distance": "half", "target_seconds": 8400, "weeks_to_race": 14},
        "beg-marathon": beg | {"weeks_to_race": 18},
        "int-10k": INTERMEDIATE | {"id": "int-10k", "distance": "10k", "target_seconds": 2700, "weeks_to_race": 10},
        "int-half": INTERMEDIATE,
        "int-marathon": INTERMEDIATE | {"id": "int-marathon", "distance": "marathon", "target_seconds": 12600, "weeks_to_race": 18},
        "int-50k": INTERMEDIATE | {"id": "int-50k", "distance": "50k", "target_seconds": 21600, "weeks_to_race": 16,
                                   "terrain": "trail", "elevation_gain_ft": 5000},
        "adv-5k": scenario("sub17-5k", weeks_to_race=12),
        "adv-10k": adv | {"id": "adv-10k", "distance": "10k", "target_seconds": 2100, "weeks_to_race": 10},
        "adv-half": adv | {"id": "adv-half", "distance": "half", "target_seconds": 4740, "weeks_to_race": 12},
        "adv-marathon": adv | {"weeks_to_race": 18},
        "adv-50mi": adv | {"id": "adv-50mi", "distance": "50mi", "target_seconds": 32400, "weeks_to_race": 20,
                           "terrain": "trail", "elevation_gain_ft": 8000},
        "exp-100k": trail | {"weeks_to_race": 16},
        "exp-100mi": trail | {"id": "exp-100mi", "distance": "100mi", "target_seconds": 90000, "weeks_to_race": 24,
                              "elevation_gain_ft": 18000},
    }


def _laps(pres: dict, easy: float) -> list[tuple[str, float, float]]:
    def meters(seg, pace):
        return (seg.get("distance_meters") or 0) or (seg.get("duration_seconds") or 0) / pace * MI

    laps = []
    if pres.get("warmup"):
        m = meters(pres["warmup"], easy)
        laps.append(("WARMUP", m, m / MI * easy))
    for seg in pres.get("segments") or []:
        rng = seg.get("pace_range_sec_per_mile") or {}
        pace = ((rng.get("fast") or easy) + (rng.get("slow") or easy)) / 2
        reps = seg.get("reps") or 1
        for rep in range(reps):
            m = meters(seg, pace)
            if m:
                laps.append(("ACTIVE", m, m / MI * pace))
            if seg.get("recovery_seconds") and rep < reps - 1:
                laps.append(("RECOVERY", seg["recovery_seconds"] / easy * MI, seg["recovery_seconds"]))
    if pres.get("cooldown"):
        m = meters(pres["cooldown"], easy)
        laps.append(("COOLDOWN", m, m / MI * easy))
    return laps


def _run_day(day: date, race: date, profile: dict, struggle: bool, skip: list[int], share: float = 1.0) -> None:
    easy = profile["easy_pace"]
    with SessionLocal() as db:
        if not db.query(DailyWellness).filter_by(user_id=1, date=day.isoformat()).first():
            db.add(DailyWellness(user_id=1, date=day.isoformat(), sleep_seconds=7.6 * 3600, sleep_score=84, hrv_last_night=70,
                                 hrv_baseline_low=58, hrv_baseline_high=82, resting_hr=46, readiness_score=80, acwr=1.05))
        plan = db.query(Plan).filter_by(user_id=1, is_active=True).first()
        rows = db.query(PlannedWorkout).filter_by(plan_id=plan.id, date=day.isoformat()).all() if plan else []
        for pw in rows:
            miles = pw.distance_miles or 0
            if pw.type in ("rest", "race") or miles <= 0 or day >= race:
                continue
            pres = json.loads(pw.prescription or "{}")
            hard = pw.type == "workout"
            if struggle:
                if hard:
                    skip[0] ^= 1
                    if skip[0]:
                        continue
                else:
                    miles = round(miles * .8, 1)
            elif share < 1 and not hard:
                miles = round(miles * share, 1)  # runs cut short, workouts done, feel normal
            laps = _laps(pres, easy) if pres.get("segments") else []
            extra = miles * MI - sum(m for _, m, _ in laps)
            if laps and extra > 200:
                laps.append(("COOLDOWN", extra, extra / MI * easy))
            duration = sum(s for _, _, s in laps) if laps else miles * easy
            kind = pres.get("category") if pres.get("category") in ("threshold", "intervals", "tempo") else (
                "long_run" if pw.type == "long_run" else "easy")
            activity = Activity(user_id=1, source="manual", external_id=f"season-{day}-{pw.id}", name=pw.title,
                                date=datetime.combine(day, time(7)), distance_meters=miles * MI, duration_seconds=duration,
                                average_pace_per_km=duration / (miles * 1.60934), average_heartrate=150 if hard else 135,
                                description=pw.description, workout_type=kind, feel_rating=4 if struggle and hard else 7,
                                splits=json.dumps([lap_split(i + 1, m, s, intensity=k) for i, (k, m, s) in enumerate(laps)]),
                                elevation_gain=miles * (40 if profile.get("terrain") == "trail" else 5))
            db.add(activity)
            db.flush()
            pw.activity_id = activity.id
        db.commit()


def simulate(profile: dict, *, struggle: bool = False, share: float = 1.0, start: date = START) -> dict:
    """Run one season. Returns {race_date, blocks: [preview], days: [planned day rows], errors}."""
    Base.metadata.drop_all(bind=engine)  # every season starts from an empty schema
    Base.metadata.create_all(bind=engine)
    log = {"blocks": [], "days": [], "errors": []}
    traveller = time_machine.travel(datetime.combine(start, time(9)), tick=False)
    traveller.start()
    try:
        with SessionLocal() as db:
            seeded = seed_demo(db, profile)
            log["blocks"].append(json.loads(db.get(Plan, seeded["preview_id"]).preview_data))
        race = date.fromisoformat(seeded["race_date"])
        log["race_date"] = race
        day, skip = start, [0]
        while day <= race + timedelta(days=13):
            traveller.stop()
            traveller = time_machine.travel(datetime.combine(day, time(9)), tick=False)
            traveller.start()
            with SessionLocal() as db:
                plan = db.query(Plan).filter_by(user_id=1, is_active=True).first()
                if plan and date.fromisoformat(plan.end_date) < day:
                    preview = generate_training_plan(1, PlanRequest(scope="next"), db)
                    if preview.get("violations"):
                        log["errors"].append((day.isoformat(), preview["violations"]))
                    approve_draft(1, preview["id"], db)
                    log["blocks"].append(preview)
            _run_day(day, race, profile, struggle, skip, share)
            day += timedelta(days=1)
        with SessionLocal() as db:
            # The approved schedule, day by day: the latest approved plan covering each date
            seen = {}
            for pw in (db.query(PlannedWorkout).join(Plan, PlannedWorkout.plan_id == Plan.id)
                       .filter(Plan.user_id == 1, Plan.preview_state.is_(None), PlannedWorkout.date >= start.isoformat())
                       .order_by(Plan.id)):
                seen.setdefault(pw.date, {})[pw.plan_id] = pw
            for d in sorted(seen):
                latest = seen[d][max(seen[d])]
                log["days"].append({"date": d, "type": latest.type, "title": latest.title, "miles": latest.distance_miles or 0})
    finally:
        traveller.stop()
    return log
