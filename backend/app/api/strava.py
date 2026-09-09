import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.activity import Activity
from app.models.user import User
import httpx

from app.config import settings
from app.database import SessionLocal
from app.services.strava import (
    StravaRateLimited,
    exchange_token,
    fetch_activity_detail,
    fetch_all_activities,
    fetch_and_save_single_activity,
    fetch_descriptions_for_activities,
    get_authorization_url,
    get_valid_token,
    is_workout_description,
    parse_splits_from_detail,
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

    # Send the browser back to the app rather than leaving the athlete
    # staring at a JSON blob at the end of the OAuth handshake.
    target = settings.frontend_url.rstrip("/")
    return RedirectResponse(url=f"{target}/?strava=connected&user_id={user.id}", status_code=303)


@router.post("/sync/{user_id}")
async def sync_activities(user_id: int, db: Session = Depends(get_db)):
    """Pull all running activities from Strava and store them."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.strava_connected:
        raise HTTPException(status_code=404, detail="User not found or Strava not connected")

    access_token = await get_valid_token(user)
    try:
        raw_activities = await fetch_all_activities(access_token)
    except Exception as e:
        if "429" in str(e):
            raise HTTPException(status_code=429, detail="Strava rate limit reached. Try again in 15 minutes.")
        raise

    new_count = 0
    skipped = 0
    needs_detail = []  # activity IDs to fetch full details (description + splits)

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
            date=parsed["date"] or datetime.now(),
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
        needs_detail.append(parsed["external_id"])

    db.commit()

    # Fetch full details (description + splits) for all new activities.
    # The service-level limiter paces these; a 429 stops the loop cleanly
    # so we report progress instead of silently dropping descriptions.
    detail_count = 0
    rate_limited = False
    for i, ext_id in enumerate(needs_detail):
        try:
            detail = await fetch_activity_detail(access_token, ext_id)
        except StravaRateLimited:
            rate_limited = True
            break
        except Exception:
            continue

        if detail:
            act = (
                db.query(Activity)
                .filter(Activity.external_id == ext_id, Activity.user_id == user_id)
                .first()
            )
            if act:
                if detail.get("description"):
                    act.description = detail["description"]
                    act.has_workout_description = is_workout_description(detail["description"])
                splits_json = parse_splits_from_detail(detail)
                if splits_json:
                    act.splits = splits_json
                detail_count += 1

        if (i + 1) % 25 == 0:
            db.commit()
    db.commit()

    # Backfill: fetch details for recent activities missing description or splits (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    missing_detail = (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.date >= thirty_days_ago,
            (Activity.description.is_(None)) | (Activity.splits.is_(None)),
        )
        .order_by(Activity.date.desc())
        .all()
    )
    backfill_count = 0
    for i, act in enumerate(missing_detail):
        if not act.external_id:
            continue
        if rate_limited:
            break
        try:
            detail = await fetch_activity_detail(access_token, act.external_id)
        except StravaRateLimited:
            rate_limited = True
            break
        except Exception:
            continue

        if detail:
            if act.description is None and detail.get("description"):
                act.description = detail["description"]
                act.has_workout_description = is_workout_description(detail["description"])
            if act.splits is None:
                splits_json = parse_splits_from_detail(detail)
                if splits_json:
                    act.splits = splits_json
            backfill_count += 1

        if (i + 1) % 25 == 0:
            db.commit()
    db.commit()

    message = f"Sync complete. {new_count} new, {backfill_count} backfilled, {skipped} skipped."
    if rate_limited:
        message += " Strava rate limit reached — re-run in 15 minutes to finish fetching descriptions."

    return {
        "message": message,
        "new_activities": new_count,
        "skipped": skipped,
        "total_strava_activities": len(raw_activities),
        "details_fetched": detail_count,
        "backfilled": backfill_count,
        "rate_limited": rate_limited,
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


@router.get("/webhook")
async def strava_webhook_validation(request: Request):
    """Strava subscription validation — echo back the hub.challenge.

    Strava sends query params with dots (hub.mode, hub.verify_token, hub.challenge)
    which FastAPI can't auto-map, so we read from raw query params.
    """
    params = request.query_params
    hub_verify_token = params.get("hub.verify_token")
    hub_challenge = params.get("hub.challenge")

    if hub_verify_token != settings.strava_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    return {"hub.challenge": hub_challenge}


async def _process_webhook_activity(user_id: int, object_id: str) -> None:
    """Background worker for a webhook event.

    Runs on its own DB session: the request-scoped session from Depends()
    is already closed by the time a BackgroundTask executes.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        activity = await fetch_and_save_single_activity(user, object_id, db)
        if activity:
            # Keep workout_type in sync so the plan view and history filters
            # classify the new run without waiting for a manual re-classify.
            from app.services.analyzer import classify_activities
            classify_activities(user_id, db)
    except StravaRateLimited as e:
        print(f"Webhook sync deferred, rate limited: {e}")
    except Exception as e:
        print(f"Webhook activity sync error: {e}")
    finally:
        db.close()


@router.post("/webhook")
async def strava_webhook_event(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Receive Strava activity webhook events.

    Strava expects a 200 within 2 seconds and retries otherwise, so the
    actual fetch happens in a background task rather than inline.
    """
    body = await request.json()

    object_type = body.get("object_type")
    aspect_type = body.get("aspect_type")
    object_id = str(body.get("object_id"))
    owner_id = body.get("owner_id")

    # Only process activity create/update events. "update" matters as much as
    # "create": that is how an edited title or description (the splits the
    # pace calibrator reads) reaches us.
    if object_type != "activity" or aspect_type not in ("create", "update"):
        return {"status": "ignored"}

    user = db.query(User).filter(User.strava_athlete_id == owner_id).first()
    if not user:
        return {"status": "unknown_user"}

    background_tasks.add_task(_process_webhook_activity, user.id, object_id)
    return {"status": "accepted"}


@router.post("/subscribe")
async def create_webhook_subscription():
    """Register a Strava webhook subscription (one-time setup)."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.strava.com/api/v3/push_subscriptions",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "callback_url": settings.strava_webhook_url,
                "verify_token": settings.strava_webhook_verify_token,
            },
        )
        if response.status_code == 409:
            return {"message": "Subscription already exists", "detail": response.json()}
        response.raise_for_status()
        return {"message": "Subscription created", "subscription": response.json()}


def _seconds_to_pace(seconds_per_unit: float) -> str:
    """Convert seconds per mile/km to mm:ss format."""
    minutes = int(seconds_per_unit // 60)
    secs = int(seconds_per_unit % 60)
    return f"{minutes}:{secs:02d}"
