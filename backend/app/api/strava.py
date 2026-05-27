from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import Activity
from app.models.user import User
from app.services.strava import (
    exchange_token,
    fetch_all_activities,
    fetch_descriptions_for_activities,
    get_authorization_url,
    get_valid_token,
    is_workout_description,
    parse_strava_activity,
)

router = APIRouter(prefix="/api/strava", tags=["strava"])


@router.get("/connect")
def connect_strava():
    """Redirect user to Strava OAuth page."""
    url = get_authorization_url()
    return {"authorization_url": url}


@router.get("/callback")
async def strava_callback(code: str, scope: str = "", db: Session = Depends(get_db)):
    """Handle Strava OAuth callback and store tokens."""
    token_data = await exchange_token(code)

    athlete = token_data.get("athlete", {})
    strava_id = athlete.get("id")

    # Find or create user
    user = db.query(User).filter(User.strava_athlete_id == strava_id).first()
    if not user:
        user = User(
            name=f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
            strava_athlete_id=strava_id,
        )
        db.add(user)

    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]
    user.strava_connected = True
    db.commit()
    db.refresh(user)

    return {
        "message": "Strava connected successfully",
        "user_id": user.id,
        "athlete_name": user.name,
    }


@router.post("/sync/{user_id}")
async def sync_activities(user_id: int, db: Session = Depends(get_db)):
    """Pull all running activities from Strava and store them."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.strava_connected:
        raise HTTPException(status_code=404, detail="User not found or Strava not connected")

    access_token = await get_valid_token(user)
    raw_activities = await fetch_all_activities(access_token)

    new_count = 0
    skipped = 0
    needs_description = []  # activity IDs we want to fetch descriptions for

    for raw in raw_activities:
        parsed = parse_strava_activity(raw)
        if parsed is None:  # not a run
            continue

        # Skip if already imported
        existing = (
            db.query(Activity)
            .filter(Activity.external_id == parsed["external_id"], Activity.user_id == user_id)
            .first()
        )
        if existing:
            skipped += 1
            continue

        activity = Activity(
            user_id=user_id,
            external_id=parsed["external_id"],
            source=parsed["source"],
            name=parsed["name"],
            date=datetime.fromisoformat(parsed["date"]) if parsed["date"] else datetime.utcnow(),
            distance_meters=parsed["distance_meters"],
            duration_seconds=parsed["duration_seconds"],
            elapsed_seconds=parsed["elapsed_seconds"],
            average_pace_per_km=parsed["average_pace_per_km"],
            average_heartrate=parsed["average_heartrate"],
            max_heartrate=parsed["max_heartrate"],
            elevation_gain=parsed["elevation_gain"],
            average_cadence=parsed["average_cadence"],
            strava_workout_type=parsed["strava_workout_type"],
            workout_type=parsed["workout_type"],
            suffer_score=parsed["suffer_score"],
            pr_count=parsed["pr_count"],
        )
        db.add(activity)
        new_count += 1

        # Decide whether to fetch description for this activity
        # Rules:
        #   1. Marathon block (Aug 1 2025 - Feb 7 2026): fetch for 12+ miles always
        #   2. Marathon block: fetch for 7-12 miles IF avg pace < 8:30/mi
        #   3. Outside marathon block: skip descriptions
        act_date = activity.date.replace(tzinfo=None) if activity.date else None
        distance_miles = parsed["distance_meters"] / 1609.34
        pace_per_mile_sec = (parsed["average_pace_per_km"] * 1.60934) if parsed["average_pace_per_km"] else None

        marathon_block_start = datetime(2025, 8, 1)
        marathon_block_end = datetime(2026, 2, 7)
        in_marathon_block = act_date is not None and marathon_block_start <= act_date <= marathon_block_end
        pace_under_830 = pace_per_mile_sec is not None and pace_per_mile_sec < 510  # 8:30 = 510 seconds

        if in_marathon_block:
            if distance_miles >= 12:
                needs_description.append(parsed["external_id"])
            elif distance_miles >= 7 and pace_under_830:
                needs_description.append(parsed["external_id"])

    db.commit()

    # Now fetch descriptions for key activities
    desc_count = 0
    if needs_description:
        descriptions = await fetch_descriptions_for_activities(
            access_token, needs_description, batch_size=10, delay=2.0
        )
        for ext_id, desc in descriptions.items():
            activity = (
                db.query(Activity)
                .filter(Activity.external_id == ext_id, Activity.user_id == user_id)
                .first()
            )
            if activity and desc:
                activity.description = desc
                activity.has_workout_description = is_workout_description(desc)
                desc_count += 1
        db.commit()

    return {
        "message": f"Sync complete. {new_count} new runs imported, {skipped} already existed.",
        "new_activities": new_count,
        "skipped": skipped,
        "total_strava_activities": len(raw_activities),
        "descriptions_fetched": desc_count,
        "activities_queued_for_descriptions": len(needs_description),
    }


@router.get("/activities/{user_id}")
def get_activities(user_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Get stored activities for a user."""
    activities = (
        db.query(Activity)
        .filter(Activity.user_id == user_id)
        .order_by(Activity.date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "name": a.name,
            "date": a.date.isoformat() if a.date else None,
            "distance_miles": round(a.distance_meters / 1609.34, 2),
            "distance_km": round(a.distance_meters / 1000, 2),
            "duration_seconds": a.duration_seconds,
            "pace_per_mile": _seconds_to_pace(a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None,
            "pace_per_km": _seconds_to_pace(a.average_pace_per_km) if a.average_pace_per_km else None,
            "average_heartrate": a.average_heartrate,
            "elevation_gain_ft": round(a.elevation_gain * 3.28084, 1) if a.elevation_gain else None,
            "cadence": a.average_cadence,
            "feel_rating": a.feel_rating,
            "workout_type": a.workout_type,
            "strava_workout_type": a.strava_workout_type,
            "description": a.description,
            "has_workout_description": a.has_workout_description,
            "suffer_score": a.suffer_score,
        }
        for a in activities
    ]


@router.get("/workouts/{user_id}")
def get_workout_activities(user_id: int, db: Session = Depends(get_db)):
    """Get activities flagged as workouts with descriptions."""
    activities = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            (Activity.has_workout_description == True)
            | (Activity.strava_workout_type.in_([1, 2, 3])),
        )
        .order_by(Activity.date.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "name": a.name,
            "date": a.date.isoformat() if a.date else None,
            "distance_miles": round(a.distance_meters / 1609.34, 2),
            "duration_seconds": a.duration_seconds,
            "pace_per_mile": _seconds_to_pace(a.average_pace_per_km * 1.60934) if a.average_pace_per_km else None,
            "workout_type": a.workout_type,
            "strava_workout_type": a.strava_workout_type,
            "description": a.description,
            "has_workout_description": a.has_workout_description,
            "average_heartrate": a.average_heartrate,
            "suffer_score": a.suffer_score,
        }
        for a in activities
    ]


def _seconds_to_pace(seconds_per_unit: float) -> str:
    """Convert seconds per mile/km to mm:ss format."""
    minutes = int(seconds_per_unit // 60)
    secs = int(seconds_per_unit % 60)
    return f"{minutes}:{secs:02d}"
