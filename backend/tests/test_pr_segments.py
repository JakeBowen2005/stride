import json

from app.models.activity import Activity
from app.services.analyzer import _extract_segment_time

MI = 1609.34


def test_fast_400_lap_is_not_a_mile_pr():
    # 400m at 75s inside an interval session, with slow recovery jogs around it
    laps = [
        {"distance_miles": 1.5, "duration_seconds": 810},
        {"distance_miles": 0.25, "duration_seconds": 75},
        {"distance_miles": 0.15, "duration_seconds": 90},
        {"distance_miles": 0.25, "duration_seconds": 76},
        {"distance_miles": 0.15, "duration_seconds": 90},
        {"distance_miles": 1.5, "duration_seconds": 810},
    ]
    act = Activity(splits=json.dumps(laps))
    t = _extract_segment_time(act, 1.0)
    assert t is None or t > 300  # never a sub-5:00 "mile"


def test_legacy_mile_splits_still_work():
    splits = [{"mile": i, "pace_seconds": p} for i, p in enumerate([420, 330, 335, 332, 420], 1)]
    act = Activity(splits=json.dumps(splits))
    assert round(_extract_segment_time(act, 3.0)) == 997
