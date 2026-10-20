"""Fit generated weeks to their mileage budget, and validate whole plans.

Used after generation and after every schedule mutation (feedback adjustments),
so the same rules hold everywhere:

- weekly scheduled miles stay within the budget (tolerance below)
- no running on the athlete's rest days (race day excepted)
- never two hard days in a row — across week boundaries and against real hard
  runs completed just before the plan — except an explicitly planned ultra
  back-to-back pair (both days flagged ``b2b``)

Accounting policy: a workout's ``distance_miles`` is its full session total
(warmup + reps + recoveries + cooldown, from the ladder template's
``total_miles``); easy days absorb whatever the budget has left.
"""

from datetime import date, timedelta
from typing import Callable

HARD_TYPES = {"workout", "long_run", "race"}

BUDGET_OVER_TOLERANCE = 0.5  # rounding to the nearest half mile can overshoot this much
BUDGET_UNDER_TOLERANCE = 1.5  # max easy-day length / run days can leave a little unused
MIN_EASY = 3.0
MIN_EASY_FLOOR = 2.0  # used only when the budget can't support 3-mile easy days
MAX_EASY = 10.0  # easy-day cap at normal volume; scales up for high-mileage weeks
MAX_EASY_SHARE = 0.18  # ...to 18% of the week (e.g. 13.5 mi at 75 mpw)
MIN_LONG_SHARE = 0.20  # long run won't be cut below 20% of the week


def _round_half(d: float) -> float:
    return round(d * 2) / 2


def _easy(day: dict, desc: str, miles: float, title: str = "Easy Run") -> None:
    day.update({
        "type": "easy", "title": title, "description": desc,
        "purpose": "Aerobic base building and recovery between hard efforts.",
        "distance_miles": miles, "warmup": None, "cooldown": None,
    })
    day.pop("b2b", None)
    day.pop("prescription", None)


def fit_week_to_budget(
    days: list[dict],
    budget: float,
    easy_desc: str,
    restructure_long: Callable[[float], dict] | None = None,
) -> list[str]:
    """Resize prescribed days so the week totals its budget. Mutates ``days``.

    Days with ``prescribed`` False (already lived, carrying actual miles) and
    races are locked. When the week can't hold its sessions, it gives way in
    order: easy days down to 3 mi → long run down to 20% of the week → the second
    quality session → easy days down to 2 mi → fewer easy days. It never adds
    load beyond the budget to make the numbers look smooth.
    Returns notes describing any compromise.
    """
    notes: list[str] = []
    live = [d for d in days if d.get("prescribed", True) and d["type"] != "race"]
    locked = sum(d["distance_miles"] for d in days if d not in live)

    if live and budget - locked < MIN_EASY_FLOOR:
        for day in live:
            day.update({'type': 'rest', 'title': 'Recovery / Rest',
                        'description': "The week's mileage is already accounted for. Rest and recover.",
                        'purpose': 'Recovery after completed training.', 'distance_miles': 0, 'warmup': None, 'cooldown': None})
            day.pop('prescription', None)
            day.pop('b2b', None)
        return ["No remaining mileage budget: upcoming prescribed days became recovery/rest; completed runs were preserved."]

    def fixed_miles():
        return sum(d["distance_miles"] for d in live if d["type"] in ("workout", "long_run"))

    def easy_days():
        return [d for d in live if d["type"] == "easy"]

    def remaining():
        return budget - locked - fixed_miles()

    def per_easy():
        e = easy_days()
        return remaining() / len(e) if e else 0.0

    # 1. Long run down toward its floor if easy days can't reach 3 mi
    longs = [d for d in live if d["type"] == "long_run" and not d.get("b2b")]
    if easy_days() and per_easy() < MIN_EASY and longs:
        lr = longs[0]
        floor = max(_round_half(budget * MIN_LONG_SHARE), 4.0)
        need = (MIN_EASY - per_easy()) * len(easy_days())
        new = max(floor, _round_half(lr["distance_miles"] - need))
        if new < lr["distance_miles"]:
            lr["distance_miles"] = new
            if restructure_long:
                lr.update(restructure_long(new))
            notes.append(f"Long run shortened to {new:g} mi to fit the weekly budget.")

    # 2. Drop the second quality session
    workouts = [d for d in live if d["type"] == "workout"]
    if easy_days() and per_easy() < MIN_EASY and len(workouts) > 1:
        _easy(workouts[-1], easy_desc, MIN_EASY)
        notes.append("One quality session this week instead of two: the mileage budget can't support both yet.")

    # 3. Fewer easy days if they'd be shorter than 2 mi
    while easy_days() and per_easy() < MIN_EASY_FLOOR and len(easy_days()) > 1:
        d = easy_days()[-1]
        d.update({"type": "rest", "title": "Rest Day", "description": "Rest (keeps the week within its mileage budget).",
                  "purpose": "Recovery.", "distance_miles": 0, "warmup": None, "cooldown": None})
        notes.append("An easy day became rest to keep the week within budget.")

    e = easy_days()
    if e:
        per = per_easy()
        max_easy = max(MAX_EASY, budget * MAX_EASY_SHARE)
        per = min(max(per, MIN_EASY_FLOOR), max_easy)
        each = _round_half(per)
        for d in e:
            d["distance_miles"] = each
        # Repair rounding without adding load: trim the last easy days by half miles
        total = locked + sum(d["distance_miles"] for d in live)
        i = len(e) - 1
        while total > budget + BUDGET_OVER_TOLERANCE and i >= 0:
            if e[i]["distance_miles"] - 0.5 >= MIN_EASY_FLOOR:
                e[i]["distance_miles"] -= 0.5
                total -= 0.5
            else:
                i -= 1

    total = locked + sum(d["distance_miles"] for d in live)
    if total > budget + BUDGET_OVER_TOLERANCE:
        remaining_workouts = [d for d in live if d['type'] == 'workout']
        if remaining_workouts:
            _easy(remaining_workouts[-1], easy_desc, MIN_EASY_FLOOR)
            notes.append("Quality session replaced by easy running: its full prescription cannot fit this week's remaining budget.")
            notes.extend(fit_week_to_budget(days, budget, easy_desc, restructure_long))
            return notes
    if total > budget + BUDGET_OVER_TOLERANCE:
        remaining_longs = [d for d in live if d['type'] == 'long_run']
        if remaining_longs:
            _easy(remaining_longs[-1], easy_desc, MIN_EASY_FLOOR, title='Recovery Run')
            notes.append("Long run replaced by affordable recovery running: completed training leaves too little mileage for its full prescription.")
            notes.extend(fit_week_to_budget(days, budget, easy_desc, restructure_long))
            return notes
    if total < budget - BUDGET_UNDER_TOLERANCE and e:
        notes.append(
            f"Scheduled {total:g} of {budget:g} mi: with this many run days the easy runs would get too long; "
            "add a run day or a double to reach the full budget."
        )
    if total > budget + BUDGET_OVER_TOLERANCE:
        notes.append(
            f"This week's sessions need {total:g} mi but the budget is {budget:g} mi; "
            "consider fewer run days or a lighter week."
        )
    return notes


def is_hard(day: dict) -> bool:
    return day["type"] in HARD_TYPES and day.get("distance_miles", 0) > 0


def enforce_no_back_to_back_hard(
    days: list[dict], easy_desc: str, prior_hard_dates: frozenset[str] | set[str] = frozenset()
) -> list[dict]:
    """Never two hard days in a row. ``days`` may span several weeks; adjacency is by
    date. ``prior_hard_dates`` are ISO dates of real hard runs completed before the
    plan (e.g. yesterday's long run). The only allowed hard pair is an ultra
    back-to-back where both days carry ``b2b``. On conflict the prescribed workout
    is downgraded to easy (fail safe); completed days and races are never touched.
    """
    by_date = {d["date"]: d for d in days}
    for d in sorted(days, key=lambda x: x["date"]):
        if not is_hard(d) or not d.get("prescribed", True):
            continue
        prev_date = (date.fromisoformat(d["date"]) - timedelta(days=1)).isoformat()
        prev = by_date.get(prev_date)
        prev_hard = (prev is not None and is_hard(prev)) or prev_date in prior_hard_dates
        if not prev_hard:
            continue
        if prev is not None and prev.get("b2b") and d.get("b2b"):
            continue  # planned ultra back-to-back pair
        # Downgrade the later prescribed workout; if this day isn't a workout but the
        # previous one is (and is still prescribed), downgrade that instead.
        if d["type"] == "workout":
            victim = d
        elif prev is not None and prev["type"] == "workout" and prev.get("prescribed", True):
            victim = prev
        else:
            continue  # e.g. long run after a completed hard day: leave, validator reports
        _easy(victim, easy_desc, min(victim["distance_miles"], 6.0), title="Easy Run (moved off a hard-day stack)")
        victim["adjustment_reason"] = "Avoids two hard days in a row."
    return days


def validate_plan(
    weeks: list[dict],
    rest_indices: list[int] | None = None,
    prior_hard_dates: frozenset[str] | set[str] = frozenset(),
) -> list[dict]:
    """Return a list of violations ({code, date, message}); empty means valid."""
    problems: list[dict] = []
    rest_indices = rest_indices or []
    all_days = sorted((d for w in weeks for d in w["days"]), key=lambda d: d["date"])
    by_date = {d["date"]: d for d in all_days}

    for w in weeks:
        budget = w.get("budget_miles")
        has_race = any(d["type"] == "race" for d in w["days"])
        scheduled = sum(d["distance_miles"] for d in w["days"])
        if budget is not None and not has_race and scheduled > budget + BUDGET_OVER_TOLERANCE:
            problems.append({"code": "over_budget", "date": w["days"][0]["date"],
                             "message": f"Week {w.get('week_number')}: {scheduled:.1f} mi scheduled vs {budget:.1f} mi budget"})

    for d in all_days:
        if not d.get("prescribed", True):
            continue
        weekday = date.fromisoformat(d["date"]).weekday()
        if weekday in rest_indices and d["type"] not in ("rest", "race") and d["distance_miles"] > 0:
            problems.append({"code": "rest_day_run", "date": d["date"], "message": f"Run scheduled on rest day {d['date']}"})
        if is_hard(d):
            prev_date = (date.fromisoformat(d["date"]) - timedelta(days=1)).isoformat()
            prev = by_date.get(prev_date)
            prev_hard = (prev is not None and is_hard(prev)) or prev_date in prior_hard_dates
            if prev_hard and not (prev is not None and prev.get("b2b") and d.get("b2b")):
                problems.append({"code": "hard_after_hard", "date": d["date"],
                                 "message": f"Hard day {d['date']} directly follows another hard day"})
    return problems
