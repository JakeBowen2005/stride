"""Check every plan change against the athlete's needs and Stride's training philosophy.

Runs on each revised block before it is offered. Two kinds of change:

- ``schedule``: only run days / rest days / long-run day changed. Anything already run
  is untouched, no quality session is added or removed, long runs keep their distance,
  and the week grows by at most the added-day allowance (never more than 10%).
- ``rebuild``: a full regeneration. Workouts may change, but the universal rules hold.

Universal rules (both kinds): no running on rest days, no more run days than the
athlete chose, never two hard days in a row (except flagged ultra back-to-backs),
and easy days stay easy-sized. Returns human-readable problems; empty means it passes.
"""

from collections import Counter

from app.core.plan_validator import MIN_EASY_FLOOR, is_hard
from app.core.schedule_revision import MAX_ADDED_MILES, SchedulePrefs

MAX_SCHEDULE_GROWTH = 0.10  # the 10% rule, as an absolute ceiling for a schedule-only change
TOLERANCE = 0.5


def _quality(days):
    return Counter(d["title"] for d in days if d["type"] in ("workout", "race"))


def review_change(before: list[dict], after: list[dict], prefs: SchedulePrefs, *, kind: str,
                  prior_hard: bool = False) -> list[str]:
    problems: list[str] = []
    flat_after = [d for w in after for d in w["days"]]
    old_days = {d["date"]: d for w in before for d in w["days"]}
    fields = ("type", "title", "distance_miles")
    changed = {d["date"] for d in flat_after
               if d["date"] not in old_days or any(d.get(k) != old_days[d["date"]].get(k) for k in fields)}
    for i, day in enumerate(flat_after):
        if day.get("editable") is False:
            continue
        # A schedule change answers only for what it touched (spacing also for the day after
        # a touched day); a full rebuild answers for every day.
        rebuild = kind != "schedule"
        touched = rebuild or day["date"] in changed
        spacing = touched or (i and flat_after[i - 1]["date"] in changed)
        if touched and day["type"] not in ("rest", "race") and day["day"] in prefs.rest_days:
            problems.append(f"{day['date']}: {day['title']} is on a rest day ({day['day'].title()}).")
        if touched and day["type"] == "easy" and 0 < day["distance_miles"] < MIN_EASY_FLOOR:
            problems.append(f"{day['date']}: an easy run under {MIN_EASY_FLOOR:g} mi isn't worth the trip out the door.")
        previous = flat_after[i - 1] if i else None
        previous_hard = is_hard(previous) if previous else prior_hard
        if spacing and is_hard(day) and previous_hard and not (day.get("b2b") and previous and previous.get("b2b")):
            problems.append(f"{day['date']}: {day['title']} comes straight after another hard day.")
    for week in after:
        runs = sum(d["type"] != "rest" for d in week["days"])
        # Weeks partly in the past keep what was actually run, so only judge what can still change.
        if runs > prefs.days_per_week and any(d.get("editable") for d in week["days"]) and len(week["days"]) == 7:
            problems.append(f"Week {week['week_number']} has {runs} run days; you chose {prefs.days_per_week}.")

    if kind != "schedule":
        return problems
    for old_week, new_week in zip(before, after):
        old_days = {d["date"]: d for d in old_week["days"]}
        for day in new_week["days"]:
            old = old_days.get(day["date"])
            if old and not old.get("editable") and any(old.get(k) != day.get(k) for k in ("type", "title", "distance_miles")):
                problems.append(f"{day['date']}: a day that was already run or locked changed.")
        # Dropping a workout that lost its day is allowed (fail safe); adding one never is.
        added = _quality(new_week["days"]) - _quality(old_week["days"])
        if added:
            problems.append(f"Week {new_week['week_number']}: a schedule change must not add quality sessions "
                            f"({', '.join(added)}).")
        old_long = sorted(d["distance_miles"] for d in old_week["days"] if d["type"] == "long_run")
        new_long = sorted(d["distance_miles"] for d in new_week["days"] if d["type"] == "long_run")
        if old_long != new_long:
            problems.append(f"Week {new_week['week_number']}: long run distance changed on a schedule-only change.")
        old_total = sum(d["distance_miles"] for d in old_week["days"])
        new_total = sum(d["distance_miles"] for d in new_week["days"])
        ceiling = min(old_total * (1 + MAX_SCHEDULE_GROWTH), old_total + MAX_ADDED_MILES) + TOLERANCE
        if new_total > ceiling:
            problems.append(f"Week {new_week['week_number']}: {old_total:g} → {new_total:g} mi is more added "
                            "volume than a schedule change allows.")
    return problems


def summarize_change(before: list[dict], after: list[dict]) -> list[str]:
    """Plain-language 'what changed' lines for the draft review panel."""
    lines = []
    for old_week, new_week in zip(before, after):
        old_total = round(sum(d["distance_miles"] for d in old_week["days"]), 1)
        new_total = round(sum(d["distance_miles"] for d in new_week["days"]), 1)
        old_q, new_q = _quality(old_week["days"]), _quality(new_week["days"])
        quality = ("same workouts" if old_q == new_q else
                   "workouts: " + ", ".join(sorted(old_q.elements())) + " → " + ", ".join(sorted(new_q.elements())))
        runs_old = sum(d["type"] != "rest" for d in old_week["days"])
        runs_new = sum(d["type"] != "rest" for d in new_week["days"])
        days = f"{runs_old} → {runs_new} run days" if runs_old != runs_new else f"{runs_new} run days"
        miles = f"{old_total:g} → {new_total:g} mi" if old_total != new_total else f"{new_total:g} mi"
        lines.append(f"Week {new_week['week_number']}: {miles}, {days}, {quality}.")
    return lines
