import json
import math
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models.activity import Activity, PersonalRecord, is_walk, runs_only
from app.models.user import User


def analyze_athlete(user_id: int, db: Session) -> dict:
    """Analyze all of an athlete's running data to determine baseline fitness."""
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id, runs_only())
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
            "workout_type": a.workout_type,
            "duration_seconds": a.duration_seconds,
            "pace_per_mile_seconds": (a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None,
            "pace_per_km_seconds": a.average_pace_per_km,
            "average_heartrate": a.average_heartrate,
            "elevation_gain_ft": (a.elevation_gain * 3.28084) if a.elevation_gain else 0,
            "cadence": a.average_cadence,
        })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    # ISO year + ISO week together: Dec 29-31 can belong to week 1 of the NEXT year
    iso = df["date"].dt.isocalendar()
    df["week"] = iso.week.astype(int)
    df["year"] = iso.year.astype(int)
    df["year_week"] = df["year"].astype(str) + "-W" + df["week"].astype(str).str.zfill(2)

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

    history_weeks = max((now - df["date"].min()).days / 7, 1)

    def weekly_avg(subset, window_weeks):
        # Divide by the whole window (not the span between the first and last run in it):
        # 30mi over the last 8 days after a break is ~7.5 mpw over 4 weeks, not ~26.
        # Brand-new athletes with less history than the window use their actual history length.
        if subset.empty:
            return 0
        weeks = min(window_weeks, history_weeks)
        return round(subset["distance_miles"].sum() / weeks, 1)

    from app.services.load_history import completed_week_load
    workload = completed_week_load(user_id, db)
    current_weekly_avg = workload['baseline_miles']
    eight_week_avg = workload['eight_week_average']
    twelve_week_avg = workload['twelve_week_average']

    # Peak mileage week ever
    peak_week = weekly.loc[weekly["miles"].idxmax()]
    peak_weekly_mileage = round(peak_week["miles"], 1)
    peak_week_date = peak_week["start"].strftime("%Y-%m-%d")

    # --- Pace Analysis ---
    valid_pace = df[df["pace_per_mile_seconds"].notna() & (df["pace_per_mile_seconds"] > 300)]  # faster than 5:00/mi sanity check

    # High-volume athletes often run 9+ mile EASY days. A 3–8 mile-only
    # heuristic can otherwise select their shorter threshold/interval workouts.
    explicit_easy = valid_pace[valid_pace["workout_type"].isin(["easy", "recovery"])]
    easy_runs = explicit_easy if not explicit_easy.empty else valid_pace[(valid_pace["distance_miles"] >= 3) & (valid_pace["distance_miles"] <= 8)]
    if not easy_runs.empty:
        easy_pace_seconds = easy_runs["pace_per_mile_seconds"].quantile(0.6)  # 60th percentile = typical easy
    else:
        easy_pace_seconds = valid_pace["pace_per_mile_seconds"].median()

    # Fastest paces (likely workouts or races)
    fastest_pace_seconds = valid_pace["pace_per_mile_seconds"].quantile(0.05)  # top 5%
    workout_pace_seconds = valid_pace["pace_per_mile_seconds"].quantile(0.15)  # top 15%

    # Recent easy pace (last 4 weeks)
    recent_explicit = recent_4w[recent_4w["workout_type"].isin(["easy", "recovery"]) & recent_4w["pace_per_mile_seconds"].notna()]
    recent_easy = recent_explicit if not recent_explicit.empty else recent_4w[
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
    runs_per_week = round(len(recent_8w) / max((recent_8w["date"].max() - recent_8w["date"].min()).days / 7, 1), 1) if not recent_8w.empty else 0

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
    if peak_weekly_mileage >= 50 and date_range_days > 365:
        experience = "advanced"
    elif peak_weekly_mileage >= 25 and date_range_days > 180:
        experience = "intermediate"
    else:
        experience = "beginner"

    profile = db.get(User, user_id)
    if profile and profile.experience_level in {'beginner', 'intermediate', 'advanced', 'expert'}:
        experience = profile.experience_level

    # --- Injury Risk: Acute/Chronic Workload ---
    acute_load = workload['acute_miles']
    chronic_load = workload['baseline_miles']
    acwr = workload['ratio']
    injury_risk = workload['label']

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
            "as_of": workload["as_of"], "baseline_start": workload["baseline_start"], "baseline_end": workload["baseline_end"],
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
        "workload": workload,
        "injury_risk": {
            **workload,
            "acute_chronic_ratio": acwr,
            "assessment": injury_risk,
            "acute_weekly_avg": round(acute_load, 1),
            "chronic_weekly_avg": round(chronic_load, 1),
        },
        "mileage_trend": mileage_trend,
    }


def _format_pace(seconds_per_mile: float | None) -> str | None:
    """Convert seconds per mile to mm:ss format."""
    if seconds_per_mile is None or not math.isfinite(seconds_per_mile):
        return None
    minutes, secs = divmod(round(seconds_per_mile), 60)
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
        .filter(Activity.user_id == user_id, runs_only())
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
    """Fastest contiguous stretch of splits covering target_miles, scaled to exactly target_miles.

    Legacy Strava splits are 1 mile each (pace_seconds = time for that mile).
    Garmin laps carry their own distance_miles/duration_seconds and can be any
    length (400m reps, recovery jogs), so each split's real distance is used —
    otherwise a single fast 400m lap would look like a mile PR.
    """
    if not activity.splits:
        return None
    try:
        splits = json.loads(activity.splits)
    except (json.JSONDecodeError, TypeError):
        return None
    if not splits:
        return None

    segments = []
    for s in splits:
        dist = s.get("distance_miles", 1.0) or 0
        if "duration_seconds" in s:
            secs = s.get("duration_seconds") or 0
        else:
            secs = (s.get("pace_seconds") or 600) * dist
        if dist > 0 and secs > 0:
            segments.append((dist, secs))

    best = None
    for start in range(len(segments)):
        dist = secs = 0.0
        for d, t in segments[start:]:
            dist += d
            secs += t
            if dist >= target_miles * 0.95:
                break
        if dist < target_miles * 0.95 or dist > target_miles * 1.25:
            continue
        estimate = secs * (target_miles / dist)
        if best is None or estimate < best:
            best = estimate
    return best


# Garmin training-effect labels that reliably mean a quality session
# ("TEMPO" is left out: hot or hilly easy runs often get it)
HARD_TRAINING_EFFECT_LABELS = {"VO2MAX", "LACTATE_THRESHOLD", "THRESHOLD", "ANAEROBIC_CAPACITY", "SPRINT"}


def classify_activities(user_id: int, db: Session) -> dict:
    """Classify all activities by workout type (Garmin data + legacy Strava flags)."""
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .all()
    )

    counts = {"easy": 0, "workout": 0, "long_run": 0, "race": 0, "recovery": 0, "walk": 0}

    for act in activities:
        dist_miles = act.distance_meters / 1609.34 if act.distance_meters else 0

        # Walks first: never part of the running plan, whatever the watch called them
        if is_walk(act):
            act.workout_type = "walk"
        # Explicit race / workout flags (Garmin event type, legacy Strava workout_type)
        elif act.strava_workout_type == 1 or act.event_type == "race":
            act.workout_type = "race"
        elif act.has_workout_description:
            act.workout_type = "workout"
        elif (
            (act.training_effect_label or "").upper() in HARD_TRAINING_EFFECT_LABELS
            and (act.anaerobic_training_effect or 0) >= 2.0
        ):
            # Garmin's label alone over-fires on hot/hilly easy runs; real quality
            # sessions also carry meaningful anaerobic load.
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
        .filter(Activity.user_id == user_id, Activity.date >= start, runs_only())
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
