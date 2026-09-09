"""Set the active training goal directly against the database.

Useful when you want to change the goal without the API running, and as a
record of exactly what a goal change does.

Changing goal DISTANCE is not just a row update: workout progression levels
are ladder-specific (level 5 on the 5K interval ladder is 6x800m, on the
marathon ladder it is 4x1mi). The plan engine re-seeds both ladders from
recent Strava history the next time a plan is generated, so after running
this you should regenerate the plan.

Usage:
    cd backend
    python scripts/set_goal.py --marathon 2:45:00 --date 2028-02-06
    python scripts/set_goal.py --distance 10k --time 35:00 --date 2027-06-12
    python scripts/set_goal.py --show
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, engine, Base, ensure_schema  # noqa: E402
import app.models  # noqa: F401,E402
from app.models.user import Goal, User  # noqa: E402

DISTANCE_LABELS = {
    "5k": "5K",
    "10k": "10K",
    "half": "Half Marathon",
    "marathon": "Marathon",
}


def parse_time(s: str) -> float:
    """Parse H:MM:SS or MM:SS into seconds."""
    parts = [int(p) for p in s.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    raise ValueError(f"Could not parse time: {s!r}. Use H:MM:SS or MM:SS.")


def format_time(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_pace(seconds_per_mile: float) -> str:
    m, s = divmod(int(round(seconds_per_mile)), 60)
    return f"{m}:{s:02d}"


RACE_MILES = {"5k": 3.10686, "10k": 6.21371, "half": 13.1094, "marathon": 26.2188}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--distance", choices=sorted(RACE_MILES))
    ap.add_argument("--time", help="Goal time, H:MM:SS or MM:SS")
    ap.add_argument("--marathon", help="Shorthand for --distance marathon --time X")
    ap.add_argument("--date", help="Race date, YYYY-MM-DD")
    ap.add_argument("--description", help="Overrides the auto-generated description")
    ap.add_argument("--show", action="store_true", help="Print the active goal and exit")
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_schema()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == args.user_id).first()
        if not user:
            print(f"No user with id {args.user_id}. Connect Strava first.")
            return 1

        if args.show:
            goal = db.query(Goal).filter(Goal.user_id == user.id, Goal.active.is_(True)).first()
            if not goal:
                print("No active goal.")
                return 0
            print(f"Active goal: {goal.description}")
            print(f"  distance   {goal.race_distance}")
            print(f"  target     {format_time(goal.target_time_seconds or 0)}")
            print(f"  race date  {goal.race_date}")
            return 0

        distance = args.distance
        time_str = args.time
        if args.marathon:
            distance, time_str = "marathon", args.marathon
        if not distance or not time_str:
            ap.error("need --distance and --time (or --marathon TIME)")

        target_seconds = parse_time(time_str)
        pace = target_seconds / RACE_MILES[distance]
        label = DISTANCE_LABELS[distance]
        description = args.description or f"Sub-{format_time(target_seconds)} {label}"

        previous = db.query(Goal).filter(Goal.user_id == user.id, Goal.active.is_(True)).first()
        if previous:
            print(f"Deactivating previous goal: {previous.description} ({previous.race_distance})")
            db.query(Goal).filter(Goal.user_id == user.id, Goal.active.is_(True)).update(
                {"active": False}
            )

        goal = Goal(
            user_id=user.id,
            goal_type="race",
            race_distance=distance,
            target_time_seconds=target_seconds,
            race_date=args.date,
            description=description,
            active=True,
        )
        db.add(goal)
        db.commit()

        print(f"\nGoal set: {description}")
        print(f"  race pace   {format_pace(pace)}/mi")
        print(f"  race date   {args.date or '(not set)'}")

        if previous and previous.race_distance != distance:
            print(
                f"\n  Goal distance changed ({previous.race_distance} -> {distance}). "
                "Workout progression levels refer to a different ladder now and will be\n"
                "  re-seeded from your recent Strava history on the next plan generation."
            )
        print("\nNext: POST /api/plans/{}/generate to build a plan against this goal.".format(user.id))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
