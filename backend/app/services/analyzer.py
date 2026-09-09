import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.activity import Activity, PersonalRecord


def analyze_athlete(user_id: int, db: Session) -> dict:
    """Analyze all of an athlete's running data to determine baseline fitness."""
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .order_by(Activity.date.asc())
        .all()
    )

    if not activities:
        return {"error": "No activities found"}

    # Build dataframe
    rows = []
    for a in activities:
        rows.append({
            "date": a.date,
            "distance_miles": a.distance_meters / 1609.34,
            "distance_km": a.distance_meters / 1000,
            "duration_seconds": a.duration_seconds,
            "pace_per_mile_seconds": (a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None,
            "pace_per_km_seconds": a.average_pace_per_km,
            "average_heartrate": a.average_heartrate,
            "elevation_gain_ft": (a.elevation_gain * 3.28084) if a.elevation_gain else 0,
            "cadence": a.average_cadence,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["year"] = df["date"].dt.year
    df["year_week"] = df["year"].astype(str) + "-W" + df["week"].astype(str).str.zfill(2)

    # Activity dates are naive LOCAL datetimes (see strava.parse_local_datetime),
    # so the comparison window has to be local wall-clock too. utcnow() would
    # shift every window by the athlete's UTC offset.
    now = datetime.now()

    # --- Overall Stats ---
    total_runs = len(df)
    total_miles = df["distance_miles"].sum()
    total_hours = df["duration_seconds"].sum() / 3600
    date_range_days = (df["date"].max() - df["date"].min()).days
    first_run = df["date"].min().strftime("%Y-%m-%d")
    last_run = df["date"].max().strftime("%Y-%m-%d")

    # --- Weekly Mileage ---
    weekly = df.groupby("year_week").agg(
        miles=("distance_miles", "sum"),
        runs=("distance_miles", "count"),
        start=("date", "min"),
    ).reset_index()
    weekly = weekly.sort_values("start")

    # Recent weeks (last 4, 8, 12)
    recent_4w = df[df["date"] >= now - timedelta(weeks=4)]
    recent_8w = df[df["date"] >= now - timedelta(weeks=8)]
    recent_12w = df[df["date"] >= now - timedelta(weeks=12)]

    def weekly_avg(subset, window_weeks):
        """Average miles per week over a FIXED window.

        The denominator must be the window length, not the span between the
        first and last run inside it. Dividing by the observed span means a
        two-week layoff followed by one 40mi week reports as "40 mpw" instead
        of the true 10 mpw -- and that number feeds straight into the mileage
        ramp, so it has to be conservative.
        """
        if subset.empty:
            return 0
        return round(subset["distance_miles"].sum() / window_weeks, 1)

    current_weekly_avg = weekly_avg(recent_4w, 4)
    eight_week_avg = weekly_avg(recent_8w, 8)
    twelve_week_avg = weekly_avg(recent_12w, 12)

    # Peak mileage week ever
    peak_week = weekly.loc[weekly["miles"].idxmax()]
    peak_weekly_mileage = round(peak_week["miles"], 1)
    peak_week_date = peak_week["start"].strftime("%Y-%m-%d")

    # --- Pace Analysis ---
    valid_pace = df[df["pace_per_mile_seconds"].notna() & (df["pace_per_mile_seconds"] > 300)]  # faster than 5:00/mi sanity check

    # Easy pace estimate (runs between 3-8 miles, slower half of paces)
    easy_runs = valid_pace[(valid_pace["distance_miles"] >= 3) & (valid_pace["distance_miles"] <= 8)]
    if not easy_runs.empty:
        easy_pace_seconds = easy_runs["pace_per_mile_seconds"].quantile(0.6)  # 60th percentile = typical easy
    else:
        easy_pace_seconds = valid_pace["pace_per_mile_seconds"].median()

    # Fastest paces (likely workouts or races)
    fastest_pace_seconds = valid_pace["pace_per_mile_seconds"].quantile(0.05)  # top 5%
    workout_pace_seconds = valid_pace["pace_per_mile_seconds"].quantile(0.15)  # top 15%

    # Recent easy pace (last 4 weeks)
    recent_easy = recent_4w[
        (recent_4w["pace_per_mile_seconds"].notna()) &
        (recent_4w["distance_miles"] >= 3) &
        (recent_4w["distance_miles"] <= 8)
    ]
    recent_easy_pace = recent_easy["pace_per_mile_seconds"].median() if not recent_easy.empty else easy_pace_seconds

    # --- Long Run Analysis ---
    long_runs = df[df["distance_miles"] >= 10].sort_values("date", ascending=False)
    longest_run = df.loc[df["distance_miles"].idxmax()]

    # --- PR Estimates from Data ---
    # Find fastest efforts at various distances (approximate)
    pr_estimates = {}
    for dist_name, min_d, max_d in [("5K", 2.9, 3.3), ("10K", 5.8, 6.5), ("Half", 12.8, 13.5), ("Marathon", 25.5, 27.0)]:
        candidates = df[(df["distance_miles"] >= min_d) & (df["distance_miles"] <= max_d)]
        if not candidates.empty:
            fastest = candidates.loc[candidates["duration_seconds"].idxmin()]
            pr_estimates[dist_name] = {
                "time_seconds": fastest["duration_seconds"],
                "time_formatted": _format_time(fastest["duration_seconds"]),
                "pace_per_mile": _format_pace(fastest["pace_per_mile_seconds"]) if fastest["pace_per_mile_seconds"] else None,
                "date": fastest["date"].strftime("%Y-%m-%d"),
            }

    # --- Consistency ---
    # How many weeks in the last 12 had at least 1 run?
    last_12_weeks = df[df["date"] >= now - timedelta(weeks=12)]
    weeks_with_runs = last_12_weeks.groupby("year_week").size().count()
    consistency_pct = round((weeks_with_runs / 12) * 100)

    # Runs per week average (last 8 weeks)
    runs_per_week = round(len(recent_8w) / 8, 1) if not recent_8w.empty else 0

    # --- Heart Rate ---
    hr_data = df[df["average_heartrate"].notna()]
    avg_easy_hr = None
    if not hr_data.empty:
        easy_hr_runs = hr_data[(hr_data["distance_miles"] >= 3) & (hr_data["pace_per_mile_seconds"] > easy_pace_seconds * 0.95)]
        if not easy_hr_runs.empty:
            avg_easy_hr = round(easy_hr_runs["average_heartrate"].median(), 1)

    # --- Cadence ---
    cadence_data = df[df["cadence"].notna()]
    avg_cadence = round(cadence_data["cadence"].median() * 2, 0) if not cadence_data.empty else None  # Strava reports half cadence

    # --- Experience Level ---
    # Judged on demonstrated volume first, history length second. Requiring a
    # full year classified an athlete with six months at 48 mpw as a beginner
    # and capped their ramp at 10%/week, which is not what their body needs.
    if peak_weekly_mileage >= 45 and (date_range_days > 240 or total_runs >= 150):
        experience = "advanced"
    elif peak_weekly_mileage >= 25 and (date_range_days > 120 or total_runs >= 60):
        experience = "intermediate"
    else:
        experience = "beginner"

    # --- Injury Risk: Acute/Chronic Workload ---
    # Standard ACWR is the last 7 days against the rolling 28-day average.
    # The previous version compared a 4-week average to a 12-week average,
    # which smooths away exactly the one-week spike the ratio exists to catch.
    recent_1w = df[df["date"] >= now - timedelta(days=7)]
    acute_load = recent_1w["distance_miles"].sum() if not recent_1w.empty else 0
    chronic_load = (recent_4w["distance_miles"].sum() / 4) if not recent_4w.empty else 0
    acwr = round(acute_load / chronic_load, 2) if chronic_load > 0 else 0

    if acwr > 1.5:
        injury_risk = "HIGH — mileage spike detected, ease back"
    elif acwr > 1.3:
        injury_risk = "MODERATE — building quickly, monitor closely"
    elif acwr < 0.8:
        injury_risk = "LOW — undertrained, room to build safely"
    else:
        injury_risk = "LOW — good balance of load"

    # --- Mileage Trend (last 8 weeks) ---
    weekly_recent = weekly[weekly["start"] >= now - timedelta(weeks=8)].sort_values("start")
    mileage_trend = []
    for _, row in weekly_recent.iterrows():
        mileage_trend.append({
            "week": row["year_week"],
            "miles": round(row["miles"], 1),
            "runs": int(row["runs"]),
        })

    return {
        "overview": {
            "total_runs": total_runs,
            "total_miles": round(total_miles, 1),
            "total_hours": round(total_hours, 1),
            "running_since": first_run,
            "last_run": last_run,
            "days_of_data": date_range_days,
            "experience_level": experience,
        },
        "current_fitness": {
            "weekly_mileage_4w_avg": current_weekly_avg,
            "weekly_mileage_8w_avg": eight_week_avg,
            "weekly_mileage_12w_avg": twelve_week_avg,
            "peak_weekly_mileage": peak_weekly_mileage,
            "peak_week_date": peak_week_date,
            "runs_per_week": runs_per_week,
            "consistency_12w": f"{consistency_pct}%",
        },
        "paces": {
            "easy_pace": _format_pace(easy_pace_seconds),
            "recent_easy_pace": _format_pace(recent_easy_pace),
            "workout_pace_estimate": _format_pace(workout_pace_seconds),
            "fastest_pace_ever": _format_pace(fastest_pace_seconds),
        },
        "long_runs": {
            "longest_run_miles": round(longest_run["distance_miles"], 1),
            "longest_run_date": longest_run["date"].strftime("%Y-%m-%d"),
            "long_runs_10plus": len(long_runs),
            "recent_long_runs": [
                {
                    "miles": round(r["distance_miles"], 1),
                    "pace": _format_pace(r["pace_per_mile_seconds"]),
                    "date": r["date"].strftime("%Y-%m-%d"),
                }
                for _, r in long_runs.head(5).iterrows()
            ],
        },
        "pr_estimates": pr_estimates,
        "heart_rate": {
            "average_easy_hr": avg_easy_hr,
            "avg_cadence_spm": avg_cadence,
        },
        "injury_risk": {
            "acute_chronic_ratio": acwr,
            "assessment": injury_risk,
            "acute_weekly_avg": round(acute_load, 1),
            "chronic_weekly_avg": round(chronic_load, 1),
        },
        "mileage_trend": mileage_trend,
    }


def _format_pace(seconds_per_mile: float | None) -> str | None:
    """Convert seconds per mile to mm:ss format."""
    if seconds_per_mile is None:
        return None
    minutes = int(seconds_per_mile // 60)
    secs = int(seconds_per_mile % 60)
    return f"{minutes}:{secs:02d}"


def _format_time(total_seconds: float) -> str:
    """Convert total seconds to H:MM:SS or MM:SS format."""
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    secs = int(total_seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# --- PR Detection ---

PR_DISTANCES = [
    ("0.5 Mile", 0.5),
    ("1 Mile", 1.0),
    ("2 Mile", 2.0),
    ("5K", 3.10686),
    ("5 Mile", 5.0),
    ("10K", 6.21371),
    ("10 Mile", 10.0),
    ("15K", 9.32057),
    ("Half Marathon", 13.1094),
    ("Marathon", 26.2188),
]


def detect_prs(user_id: int, db: Session) -> list[dict]:
    """
    Scan all activities and find best times for standard distances.
    For each distance, finds the activity closest in distance with the fastest time.
    For longer activities, attempts segment extraction from splits.
    """
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .order_by(Activity.date.asc())
        .all()
    )

    # Clear existing PRs
    db.query(PersonalRecord).filter(PersonalRecord.user_id == user_id).delete()
    db.flush()

    prs_found = []

    for label, target_miles in PR_DISTANCES:
        best_time = None
        best_activity = None

        min_dist = target_miles * 0.95
        max_dist = target_miles * 1.05

        for act in activities:
            dist_miles = act.distance_meters / 1609.34
            duration = act.duration_seconds

            if dist_miles < min_dist or duration <= 0:
                continue

            if min_dist <= dist_miles <= max_dist:
                # Scale to exact target distance
                estimated_time = duration * (target_miles / dist_miles)
            elif dist_miles > max_dist:
                # Try extracting segment from splits
                segment_time = _extract_segment_time(act, target_miles)
                if segment_time:
                    estimated_time = segment_time
                else:
                    continue
            else:
                continue

            if best_time is None or estimated_time < best_time:
                best_time = estimated_time
                best_activity = act

        if best_time and best_activity:
            pace = best_time / target_miles if target_miles > 0 else 0
            pr = PersonalRecord(
                user_id=user_id,
                distance_label=label,
                distance_miles=target_miles,
                time_seconds=round(best_time, 1),
                pace_per_mile=round(pace, 1),
                date=best_activity.date,
                activity_id=best_activity.id,
                strava_activity_id=best_activity.external_id,
            )
            db.add(pr)
            prs_found.append({
                "distance": label,
                "time_seconds": round(best_time, 1),
                "time_formatted": _format_time(best_time),
                "pace_per_mile": _format_pace(pace),
                "date": best_activity.date.isoformat() if best_activity.date else None,
                "activity_name": best_activity.name,
            })

    db.commit()
    return prs_found


def _extract_segment_time(activity: Activity, target_miles: float) -> float | None:
    """Extract fastest consecutive segment of target_miles from splits."""
    if not activity.splits:
        return None
    try:
        splits = json.loads(activity.splits)
    except (json.JSONDecodeError, TypeError):
        return None

    if not splits:
        return None

    n_miles = max(1, int(round(target_miles)))
    if len(splits) < n_miles:
        return None

    best = None
    for start in range(len(splits) - n_miles + 1):
        segment = splits[start : start + n_miles]
        total = sum(s.get("pace_seconds", 600) for s in segment)
        if best is None or total < best:
            best = total

    if best and n_miles > 0:
        return best * (target_miles / n_miles)
    return best


def classify_activities(user_id: int, db: Session) -> dict:
    """Classify all activities by workout type based on Strava data."""
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .all()
    )

    counts = {"easy": 0, "workout": 0, "long_run": 0, "race": 0, "recovery": 0}

    for act in activities:
        dist_miles = act.distance_meters / 1609.34 if act.distance_meters else 0

        # Use Strava's workout_type if available
        if act.strava_workout_type == 1:
            act.workout_type = "race"
        elif act.has_workout_description:
            act.workout_type = "workout"
        elif act.strava_workout_type == 3:
            act.workout_type = "workout"
        elif act.strava_workout_type == 2:
            act.workout_type = "long_run"
        elif dist_miles >= 15:
            # Only 15+ miles is auto long run — many 10mi runs are just easy
            act.workout_type = "long_run"
        elif dist_miles <= 3:
            act.workout_type = "recovery"
        else:
            act.workout_type = "easy"

        counts[act.workout_type] = counts.get(act.workout_type, 0) + 1

    db.commit()
    return {"classified": len(activities), "counts": counts}


def compute_weekly_mileage(user_id: int, db: Session, weeks: int = 52) -> list[dict]:
    """Compute weekly mileage for the last N weeks."""
    now = datetime.now()
    start = now - timedelta(weeks=weeks)

    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id, Activity.date >= start)
        .order_by(Activity.date.asc())
        .all()
    )

    weekly: dict[str, float] = {}
    for act in activities:
        if act.date:
            week_start = act.date - timedelta(days=act.date.weekday())
            key = week_start.strftime("%Y-%m-%d")
            weekly[key] = weekly.get(key, 0) + act.distance_meters / 1609.34

    return [
        {"week_start": k, "actual": round(v, 1)}
        for k, v in sorted(weekly.items())
    ]
