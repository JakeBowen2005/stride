"""Athlete calendar dates; UTC remains the clock for sessions, jobs and audit logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

_zone = ContextVar('athlete_timezone', default=None)
_athlete = ContextVar('athlete_identity', default=None)


def athlete_id():return _athlete.get()


def today():
    zone=_zone.get()
    return datetime.now(ZoneInfo(zone)).date() if zone else date.today()


def day_start_utc():
    """The athlete's local midnight today, as a naive UTC datetime (how timestamps are stored)."""
    zone=_zone.get()
    now=datetime.now(ZoneInfo(zone)) if zone else datetime.now().astimezone()
    midnight=now.replace(hour=0,minute=0,second=0,microsecond=0)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


@contextmanager
def athlete_zone(zone,user_id=None):
    token=_zone.set(zone)
    identity=_athlete.set(user_id)
    try:
        yield
    finally:
        _zone.reset(token)
        _athlete.reset(identity)
