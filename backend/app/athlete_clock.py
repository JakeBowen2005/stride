"""Athlete calendar dates; UTC remains the clock for sessions, jobs and audit logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, date
from zoneinfo import ZoneInfo

_zone = ContextVar('athlete_timezone', default=None)
_athlete = ContextVar('athlete_identity', default=None)


def athlete_id():return _athlete.get()


def today():
    zone=_zone.get()
    return datetime.now(ZoneInfo(zone)).date() if zone else date.today()


@contextmanager
def athlete_zone(zone,user_id=None):
    token=_zone.set(zone)
    identity=_athlete.set(user_id)
    try:
        yield
    finally:
        _zone.reset(token)
        _athlete.reset(identity)
