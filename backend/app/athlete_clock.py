"""Athlete calendar dates; UTC remains the clock for sessions, jobs and audit logs."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, date
from zoneinfo import ZoneInfo

_zone = ContextVar('athlete_timezone', default=None)


def today():
    zone=_zone.get()
    return datetime.now(ZoneInfo(zone)).date() if zone else date.today()


@contextmanager
def athlete_zone(zone):
    token=_zone.set(zone)
    try:
        yield
    finally:
        _zone.reset(token)
