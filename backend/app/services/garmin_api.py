"""Garmin Connect Personal API client (official, key-based).

Garmin's Personal API (Oct 2026) gives an individual read access to their own
Garmin Connect data with a personal API key created at
https://connect.garmin.com/app/settings/personalApiToken. The key is exchanged
for a bearer token valid for 24h (no refresh tokens: exchange again). Access is
pull-only: there are no webhooks, so Stride still asks for new runs, but one
date-windowed request per check replaces paging through the activity list.

What the Personal API does NOT expose (it 404s): per-activity `/splits`,
training readiness, training status and Garmin race predictions. Laps come from
the activity's original FIT file instead, which is the watch's own record.
"""

import base64
import io
import json
import logging
import threading
import time
import zipfile
from datetime import date

import httpx

from app.config import settings

logger = logging.getLogger("stride.garmin")

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
TOKEN_REFRESH_MARGIN = 3600  # re-exchange when less than an hour remains
METERS_PER_MILE = 1609.34
METERS_TO_FEET = 3.28084


class GarminNotConnected(Exception):
    """No API key configured."""


class GarminAuthError(Exception):
    """The API key was rejected (expired, deleted or mistyped)."""


class GarminRateLimited(Exception):
    """Garmin answered 429."""


def has_api_key() -> bool:
    return bool(settings.garmin_api_key.strip())


def _jwt_expiry(token: str) -> float:
    """Expiry (epoch seconds) from the token's JWT payload; 23h if unreadable."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return time.time() + 23 * 3600


class PersonalApiClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL, http: httpx.Client | None = None):
        if not api_key:
            raise GarminNotConnected("No Garmin API key. Set GARMIN_API_KEY in backend/.env.")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=30)
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    # ── Auth ──
    def _bearer(self, force: bool = False) -> str:
        with self._lock:
            if force or not self._token or self._expires - time.time() < TOKEN_REFRESH_MARGIN:
                r = self._http.post(self._base + TOKEN_PATH, headers={"Authorization": f"ApiKey {self._key}"})
                if r.status_code == 429:
                    raise GarminRateLimited("Garmin token exchange rate-limited")
                if r.status_code in (401, 403):
                    raise GarminAuthError("Garmin rejected the API key (expired or deleted?)")
                r.raise_for_status()
                self._token = r.text.strip()
                self._expires = _jwt_expiry(self._token)
            return self._token

    def _get(self, path: str, params: dict | None = None, *, raw: bool = False, optional: bool = False):
        for attempt in (0, 1):
            r = self._http.get(self._base + path, params=params,
                               headers={"Authorization": f"Bearer {self._bearer(force=attempt == 1)}"})
            if r.status_code == 401 and attempt == 0:
                continue  # token revoked/expired early: exchange once more
            if r.status_code == 429:
                raise GarminRateLimited(f"Garmin rate limit on {path}")
            if r.status_code in (401, 403):
                raise GarminAuthError("Garmin rejected the API token")
            if r.status_code == 404 and optional:
                return None
            r.raise_for_status()
            if raw:
                return r.content
            return r.json() if r.content else None
        return None

    # ── Activities ──
    def search_runs(self, start: int = 0, limit: int = 100, start_date: date | None = None,
                    end_date: date | None = None) -> list[dict]:
        """Running activities (road, trail, treadmill, track...), newest first.

        `activityType=running` is the parent type, so Garmin filters out
        non-runs server-side. Dates are inclusive local calendar dates.
        """
        params = {"start": start, "limit": limit, "activityType": "running"}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        return self._get("/activitylist-service/activities/search/activities", params) or []

    def get_activity(self, activity_id) -> dict | None:
        return self._get(f"/activity-service/activity/{activity_id}")

    def get_fit(self, activity_id) -> bytes:
        """Original FIT evidence, including when it contains no lap messages."""
        blob = self._get(f"/download-service/files/activity/{activity_id}", raw=True, optional=True)
        return _unzip_fit(blob) if blob else b""

    def get_laps(self, activity_id) -> list[dict]:
        """Laps from the original FIT file (the Personal API has no /splits)."""
        return laps_from_fit(self.get_fit(activity_id))

    def display_name(self) -> str | None:
        settings_ = self._get("/userprofile-service/userprofile/settings") or {}
        return settings_.get("displayName")

    # ── Wellness (range endpoints: one request covers many days) ──
    def daily_summaries(self, start: date, end: date) -> list[dict]:
        body = self._get("/usersummary-service/v2/dailysummaries",
                         {"startDate": start.isoformat(), "endDate": end.isoformat()}) or {}
        return body.get("data") or []

    def sleep_range(self, start: date, end: date) -> list[dict]:
        return self._get("/sleep-service/sleep/dailySleepSummariesByDate",
                         {"startDate": start.isoformat(), "endDate": end.isoformat()}) or []

    def hrv_range(self, start: date, end: date) -> list[dict]:
        body = self._get(f"/hrv-service/hrv/daily/{start.isoformat()}/{end.isoformat()}") or {}
        return body.get("hrvSummaries") or []


def _unzip_fit(blob: bytes) -> bytes:
    """The download is a ZIP holding `<id>_ACTIVITY.fit`; tolerate a bare FIT too."""
    if blob[:2] != b"PK":
        return blob
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next((n for n in z.namelist() if n.lower().endswith(".fit")), None)
        return z.read(name) if name else b""


def laps_from_fit(data: bytes) -> list[dict]:
    """Normalize FIT lap messages into Stride's split format (same keys as before)."""
    import fitdecode
    from app.services.lap_analyzer import lap_pace_per_mile

    laps = []
    if not data:
        return laps
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.DISABLED) as reader:
        for frame in reader:
            if not (isinstance(frame, fitdecode.FitDataMessage) and frame.name == "lap"):
                continue
            def value(name):
                return frame.get_value(name, fallback=None)
            distance = value("total_distance") or 0.0
            duration = value("total_timer_time") or value("total_elapsed_time") or 0.0
            hr = value("avg_heart_rate")
            intensity = value("intensity")
            entry = {
                "mile": len(laps) + 1,  # lap number (kept as "mile" for frontend compatibility)
                "distance_m": round(distance, 1),
                "distance_miles": round(distance / METERS_PER_MILE, 2),
                "duration_s": round(duration, 1),
                "duration_seconds": round(duration, 1),
                "heart_rate": round(hr) if hr else None,
                "elevation_diff_ft": round(((value("total_ascent") or 0) - (value("total_descent") or 0)) * METERS_TO_FEET, 1),
                "intensity": str(intensity).upper() if intensity else None,
            }
            pace = lap_pace_per_mile(entry)
            entry["pace_seconds"] = round(pace, 1) if pace else None
            entry["pace"] = f"{int(pace // 60)}:{int(pace % 60):02d}/mi" if pace else "—"
            laps.append(entry)
    return laps


_client: PersonalApiClient | None = None
_client_lock = threading.Lock()


def get_client() -> PersonalApiClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = PersonalApiClient(settings.garmin_api_key.strip())
        return _client


def reset_client():
    global _client
    with _client_lock:
        _client = None
