import asyncio
import json
import re
import time
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.models.activity import Activity

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Keywords that suggest a description contains workout details
WORKOUT_KEYWORDS = [
    "tempo", "threshold", "interval", "repeat", "rep", "mile repeat",
    "800", "400", "1k", "1600", "fartlek", "progression",
    "race pace", "marathon pace", "mp", "half marathon pace", "hmp",
    "5k pace", "10k pace", "goal pace",
    "warmup", "warm up", "cooldown", "cool down",
    "splits", "split", "negative split",
    "easy then", "then hard", "then fast",
    "x2", "x3", "x4", "x5", "x6", "x7", "x8",
    "2x", "3x", "4x", "5x", "6x", "7x", "8x",
    "workout", "speed work", "track",
    "recovery jog", "jog rest", "rest between",
    "pr", "personal record", "personal best", "pb",
    "race", "raced",
    "sub 3", "sub 17", "sub 18", "sub 19", "sub 20",
    "6:30", "6:00", "5:30", "7:00",  # common pace references
    "miles at", "mile at", "min at", "minutes at",
]

# Compiled regex for efficiency
WORKOUT_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in WORKOUT_KEYWORDS),
    re.IGNORECASE,
)


def get_authorization_url() -> str:
    """Generate the Strava OAuth authorization URL."""
    params = {
        "client_id": settings.strava_client_id,
        "response_type": "code",
        "redirect_uri": settings.strava_redirect_uri,
        "scope": "read,activity:read_all",
        "approval_prompt": "auto",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRAVA_AUTH_URL}?{query}"


async def exchange_token(code: str) -> dict:
    """Exchange authorization code for access/refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_valid_token(user) -> str:
    """Get a valid access token, refreshing if expired."""
    if user.strava_token_expires_at and user.strava_token_expires_at < int(time.time()):
        token_data = await refresh_access_token(user.strava_refresh_token)
        user.strava_access_token = token_data["access_token"]
        user.strava_refresh_token = token_data["refresh_token"]
        user.strava_token_expires_at = token_data["expires_at"]
    return user.strava_access_token


async def fetch_activities(access_token: str, page: int = 1, per_page: int = 200) -> list[dict]:
    """Fetch a page of activities from Strava."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"page": page, "per_page": per_page},
        )
        response.raise_for_status()
        return response.json()


async def fetch_all_activities(access_token: str) -> list[dict]:
    """Fetch ALL activities from Strava (paginated)."""
    all_activities = []
    page = 1
    while True:
        activities = await fetch_activities(access_token, page=page, per_page=200)
        if not activities:
            break
        all_activities.extend(activities)
        page += 1
    return all_activities


async def fetch_activity_detail(access_token: str, activity_id: str) -> dict | None:
    """Fetch detailed activity data (includes description)."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code == 429:  # rate limited
            return None
        response.raise_for_status()
        return response.json()


async def fetch_descriptions_for_activities(
    access_token: str, activity_ids: list[str], batch_size: int = 10, delay: float = 2.0
) -> dict[str, str]:
    """Fetch descriptions for a list of activities, respecting rate limits.

    Returns dict of {activity_id: description}.
    Processes in batches with delays to avoid Strava's 100 req/15min limit.
    """
    descriptions = {}
    for i in range(0, len(activity_ids), batch_size):
        batch = activity_ids[i : i + batch_size]
        for aid in batch:
            detail = await fetch_activity_detail(access_token, aid)
            if detail and detail.get("description"):
                descriptions[aid] = detail["description"]
            elif detail:
                descriptions[aid] = ""
        # Wait between batches to stay under rate limit
        if i + batch_size < len(activity_ids):
            await asyncio.sleep(delay)
    return descriptions


def is_workout_description(description: str) -> bool:
    """Check if a description contains workout-related content."""
    if not description or len(description.strip()) < 10:
        return False
    return bool(WORKOUT_PATTERN.search(description))


def classify_strava_workout_type(strava_type: int | None) -> str | None:
    """Convert Strava's numeric workout_type to our string classification."""
    mapping = {
        0: None,       # default/easy
        1: "race",
        2: "long",
        3: "workout",  # speed/tempo
    }
    return mapping.get(strava_type)


def parse_strava_activity(raw: dict) -> dict | None:
    """Parse a raw Strava activity into our format. Only keeps runs."""
    if raw.get("type") not in ("Run", "TrailRun", "VirtualRun"):
        return None

    distance = raw.get("distance", 0)  # meters
    moving_time = raw.get("moving_time", 0)  # seconds

    avg_pace_per_km = None
    if distance > 0:
        avg_pace_per_km = (moving_time / distance) * 1000  # seconds per km

    strava_wtype = raw.get("workout_type")

    return {
        "external_id": str(raw["id"]),
        "source": "strava",
        "name": raw.get("name", ""),
        "date": raw.get("start_date_local"),
        "distance_meters": distance,
        "duration_seconds": moving_time,
        "elapsed_seconds": raw.get("elapsed_time"),
        "average_pace_per_km": avg_pace_per_km,
        "average_heartrate": raw.get("average_heartrate"),
        "max_heartrate": raw.get("max_heartrate"),
        "elevation_gain": raw.get("total_elevation_gain"),
        "average_cadence": raw.get("average_cadence"),
        "strava_workout_type": strava_wtype,
        "workout_type": classify_strava_workout_type(strava_wtype),
        "suffer_score": raw.get("suffer_score"),
        "pr_count": raw.get("pr_count"),
    }


async def fetch_and_save_single_activity(user: User, activity_id: str, db: Session) -> Activity | None:
    """Fetch a single activity from Strava and upsert into the DB."""
    token = await get_valid_token(user)
    detail = await fetch_activity_detail(token, activity_id)
    if not detail:
        return None

    parsed = parse_strava_activity(detail)
    if parsed is None:  # not a run
        return None

    # Upsert: update if exists, create if new
    existing = db.query(Activity).filter(
        Activity.external_id == parsed["external_id"], Activity.user_id == user.id
    ).first()

    if existing:
        for key, val in parsed.items():
            if key != "external_id" and val is not None:
                setattr(existing, key, val)
        activity = existing
    else:
        activity = Activity(user_id=user.id, **parsed)
        if isinstance(activity.date, str):
            try:
                activity.date = datetime.fromisoformat(activity.date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        db.add(activity)

    # Save description and splits from detail
    if detail.get("description"):
        activity.description = detail["description"]
        activity.has_workout_description = is_workout_description(detail["description"])

    splits_json = parse_splits_from_detail(detail)
    if splits_json:
        activity.splits = splits_json

    db.commit()
    db.refresh(activity)
    return activity


METERS_TO_MILES = 0.000621371
METERS_TO_FEET = 3.28084


def parse_splits_from_detail(detailed: dict) -> str | None:
    """Parse splits from detailed Strava activity into JSON string."""
    splits = detailed.get("splits_standard") or detailed.get("splits_metric")
    if not splits:
        return None

    parsed = []
    for i, split in enumerate(splits, 1):
        dist_m = split.get("distance", 0)
        moving_time = split.get("moving_time", 0)
        dist_miles = dist_m * METERS_TO_MILES
        if dist_miles > 0 and moving_time > 0:
            pace_seconds = moving_time / dist_miles
            mins = int(pace_seconds // 60)
            secs = int(pace_seconds % 60)
            parsed.append({
                "mile": i,
                "pace": f"{mins}:{secs:02d}/mi",
                "pace_seconds": round(pace_seconds, 1),
                "heart_rate": split.get("average_heartrate"),
                "elevation_diff_ft": round(split.get("elevation_difference", 0) * METERS_TO_FEET, 1),
            })

    return json.dumps(parsed) if parsed else None


async def sync_all_to_db(user: User, db: Session) -> dict:
    """
    Full sync: fetch ALL Strava runs, store/update in DB, fetch details with splits.
    Returns summary.
    """
    token = await get_valid_token(user)
    all_raw = await fetch_all_activities(token)

    # Filter to runs only
    runs = [parse_strava_activity(a) for a in all_raw]
    runs = [r for r in runs if r is not None]

    new_count = 0
    updated_count = 0
    detail_count = 0

    for i, parsed in enumerate(runs):
        existing = db.query(Activity).filter(
            Activity.external_id == parsed["external_id"]
        ).first()

        if existing:
            # Update fields
            for key, val in parsed.items():
                if key != "external_id" and val is not None:
                    setattr(existing, key, val)
            updated_count += 1
        else:
            activity = Activity(
                user_id=user.id,
                **parsed,
            )
            # Parse date string
            if isinstance(activity.date, str):
                try:
                    activity.date = datetime.fromisoformat(
                        activity.date.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass
            db.add(activity)
            new_count += 1

        # Commit in batches
        if (i + 1) % 50 == 0:
            db.commit()

    db.commit()

    # Now fetch details (splits + descriptions) for activities that lack them
    # Rate limit: Strava allows 100 req / 15 min, 1000 / day
    activities_needing_detail = (
        db.query(Activity)
        .filter(Activity.user_id == user.id, Activity.splits.is_(None))
        .order_by(Activity.date.desc())
        .all()
    )

    for i, act in enumerate(activities_needing_detail):
        try:
            detail = await fetch_activity_detail(token, act.external_id)
            if detail:
                splits_json = parse_splits_from_detail(detail)
                if splits_json:
                    act.splits = splits_json
                if detail.get("description"):
                    act.description = detail["description"]
                    act.has_workout_description = is_workout_description(detail["description"])
                detail_count += 1
        except Exception:
            pass

        # Rate limit: ~1 req/sec to stay under 100/15min
        if (i + 1) % 10 == 0:
            db.commit()
            await asyncio.sleep(2.0)

    db.commit()

    # Save token back (may have been refreshed)
    db.commit()

    return {
        "total_runs": len(runs),
        "new": new_count,
        "updated": updated_count,
        "details_fetched": detail_count,
    }


async def fetch_all_descriptions(user: User, db: Session) -> dict:
    """Fetch descriptions for ALL activities that don't have one yet.

    This is separate from the full sync — it only hits the detail endpoint
    for activities missing descriptions, regardless of whether they have splits.
    """
    token = await get_valid_token(user)

    # Find activities missing descriptions (NULL only — empty string means already checked)
    missing = (
        db.query(Activity)
        .filter(
            Activity.user_id == user.id,
            Activity.description.is_(None),
        )
        .order_by(Activity.date.desc())
        .all()
    )

    fetched = 0
    found_desc = 0
    errors = 0

    for i, act in enumerate(missing):
        if not act.external_id:
            continue
        try:
            detail = await fetch_activity_detail(token, act.external_id)
            if detail:
                desc = detail.get("description") or ""
                act.description = desc
                if desc:
                    act.has_workout_description = is_workout_description(desc)
                    found_desc += 1
                fetched += 1
        except Exception:
            errors += 1

        # Rate limit: ~10 req then 2s pause to stay under 100/15min
        if (i + 1) % 10 == 0:
            db.commit()
            await asyncio.sleep(2.0)

    db.commit()

    return {
        "activities_checked": len(missing),
        "details_fetched": fetched,
        "descriptions_found": found_desc,
        "errors": errors,
    }
