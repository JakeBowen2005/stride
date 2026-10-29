"""Road-race readiness, post-race rest on any weekday, and midweek block starts."""
import json
from datetime import date, datetime, time, timedelta

import time_machine

from app.core.periodization import POST_RACE_REST_DAYS, check_readiness
from app.core.special_weeks import apply_post_race_rest
from app.database import SessionLocal
from app.models.plan import Plan
from app.models.user import Goal, User
from app.services.demo_seed import seed_demo
from tests.season_sim import scenario

TODAY = date(2026, 11, 2)


def test_beginner_marathon_on_15_mpw_is_flagged_before_the_plan_starts():
    result = check_readiness("marathon", TODAY + timedelta(weeks=18), 6.0, 15.0, today=TODAY, experience="beginner")
    assert not result["ready"]
    assert any("Longest run so far is 6.0 mi" in r for r in result["reasons"])
    assert "half before a marathon" in result["suggestion"]


def test_trained_marathoner_and_supported_half_pass():
    assert check_readiness("marathon", TODAY + timedelta(weeks=18), 18.0, 60.0, today=TODAY, experience="advanced")["ready"]
    assert check_readiness("half", TODAY + timedelta(weeks=12), 9.0, 25.0, today=TODAY, experience="intermediate")["ready"]


def _day(offset, type_="easy", miles=5.0, title="Easy Run"):
    return {"date": (date(2027, 3, 13) + timedelta(days=offset)).isoformat(), "type": type_, "title": title,
            "distance_miles": miles, "prescribed": True}


def test_saturday_race_rests_into_the_next_week_and_drops_the_next_long_run():
    race = date(2027, 3, 13)  # a Saturday
    days = [_day(0, "race", 26.2, "RACE DAY")] + [_day(i) for i in range(1, 10)] + [_day(10, "long_run", 12, "Long Run")]
    apply_post_race_rest(days, race, "marathon")
    rest = POST_RACE_REST_DAYS["marathon"]
    assert all(d["distance_miles"] == 0 and d["type"] == "rest" for d in days[1:rest + 1])
    assert days[rest + 1]["distance_miles"] == 5.0
    assert days[10]["type"] == "easy" and days[10]["distance_miles"] <= 5.0
    assert days[0]["type"] == "race"


def test_completed_days_after_the_race_are_never_rewritten():
    race = date(2027, 3, 13)
    ran = _day(1) | {"prescribed": False, "title": "Run (before this plan)"}
    apply_post_race_rest([ran], race, "marathon")
    assert ran["distance_miles"] == 5.0 and ran["title"] == "Run (before this plan)"


def test_midweek_start_keeps_remaining_days_at_normal_size():
    with SessionLocal() as db:
        db.query(Goal).delete()
        db.query(User).delete()
        db.commit()
    wednesday = datetime.combine(TODAY + timedelta(days=2), time(9))
    with time_machine.travel(wednesday, tick=False), SessionLocal() as db:
        preview = json.loads(db.get(Plan, seed_demo(db, scenario("trail-100k"))["preview_id"]).preview_data)
    first, second = preview["weeks"][0]["days"], preview["weeks"][1]["days"]
    easy = lambda days: max(d["distance_miles"] for d in days if d["type"] == "easy" and d.get("prescribed", True))  # noqa: E731
    assert easy(first) <= easy(second) + 0.5


def test_new_athlete_without_history_is_judged_on_reported_volume_only():
    # Onboarding: no synced runs yet. A 30 mpw runner isn't flagged for an unknown long run.
    assert check_readiness("half", TODAY + timedelta(weeks=12), 0.0, 30.0, today=TODAY, experience="intermediate")["ready"]
    assert not check_readiness("marathon", TODAY + timedelta(weeks=12), 0.0, 10.0, today=TODAY, experience="beginner")["ready"]
