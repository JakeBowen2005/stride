"""Smallest safe change to an approved block when only the athlete's schedule changes.

Changing run days, rest days or the long-run day is a logistics change, not new
fitness. Rebuilding the block from scratch would also reshuffle its workouts, so
instead the approved block is kept and only the affected days move:

- workouts, long runs and anything already run stay exactly as approved
- a NEW run day gets a short recovery/easy run, preferably the day after the long run
- the added day is funded by a small, experience-based allowance (none for beginners
  or comebacks) and otherwise by splitting existing easy days; with no room, the day
  is left for the next block, which is rebuilt with the new day count
- a NEW rest day drops its easy run (miles move to other easy days) or moves its
  workout to a safe easy day; fewer run days drop the shortest easy days first
- a new long-run day swaps the long run with that day's easy run when it stays safe

The result is checked by ``core.change_guard`` before it is offered to the athlete.
"""

from dataclasses import dataclass, field

from app.core.plan_validator import MAX_EASY, MIN_EASY, MIN_EASY_FLOOR, _round_half, is_hard

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Extra weekly volume an added run day may bring, as a share of the week's planned miles.
# Beginners and comebacks add none: their new day is made by splitting existing easy runs.
ADDED_DAY_ALLOWANCE = {"beginner": 0.0, "comeback": 0.0, "intermediate": 0.05, "advanced": 0.08, "expert": 0.08}
MAX_ADDED_MILES = 3.0  # per week, whatever the experience
RECOVERY_MIN, RECOVERY_MAX = MIN_EASY_FLOOR, 4.0
SESSION_FIELDS = ("type", "title", "description", "purpose", "distance_miles", "warmup", "cooldown", "prescription", "b2b")


@dataclass
class SchedulePrefs:
    days_per_week: int
    rest_days: list[str]
    long_run_day: str

    @classmethod
    def from_dict(cls, data: dict | None) -> "SchedulePrefs":
        data = data or {}
        return cls(int(data.get("days_per_week") or 6),
                   sorted(d.strip().lower() for d in data.get("rest_days") or [] if d and d.strip()),
                   (data.get("long_run_day") or "saturday").lower())


@dataclass
class Revision:
    weeks: list[dict]
    changes: list[dict] = field(default_factory=list)  # {date, before, after, reason}
    notes: list[str] = field(default_factory=list)


def _label(day: dict) -> str:
    return "Rest" if day["type"] == "rest" else f"{day['title']} ({day['distance_miles']:g} mi)"


def _rest(day: dict) -> None:
    day.update(type="rest", title="Rest Day", description="Full rest.", purpose="Recovery.",
               distance_miles=0, warmup=None, cooldown=None, prescription=None, b2b=False)


def _easy(day: dict, miles: float, title: str, easy_desc: str) -> None:
    day.update(type="easy", title=title, description=easy_desc,
               purpose="Easy aerobic running that adds frequency without adding stress.",
               distance_miles=miles, warmup=None, cooldown=None, prescription=None, b2b=False)


def _hard_neighbour(days: list[dict], index: int, prior_hard: bool) -> bool:
    before = is_hard(days[index - 1]) if index > 0 else prior_hard
    after = is_hard(days[index + 1]) if index + 1 < len(days) else False
    return before or after


def _spread(miles: float, receivers: list[dict]) -> float:
    """Hand out freed miles in half-mile steps to the shortest easy days. Returns what didn't fit."""
    miles = _round_half(miles)
    while miles >= 0.5 and receivers:
        open_days = [d for d in receivers if d["distance_miles"] + 0.5 <= MAX_EASY]
        if not open_days:
            break
        target = min(open_days, key=lambda d: (d["distance_miles"], d["date"]))
        target["distance_miles"] += 0.5
        miles -= 0.5
    return miles


def revise_for_schedule(weeks: list[dict], old: SchedulePrefs, new: SchedulePrefs, *, experience: str | None,
                        easy_desc: str, prior_hard: bool = False) -> Revision:
    """Return the revised weeks. Day dicts need: date, day, type, title, distance_miles, editable.

    Only ``editable`` days (future, not yet run, not already moved) are ever changed.
    """
    import copy

    original_weeks = weeks
    weeks = copy.deepcopy(weeks)
    rev = Revision(weeks=weeks)
    allowance_share = ADDED_DAY_ALLOWANCE.get((experience or "intermediate").lower(), 0.05)

    def change(day: dict, before: str, reason: str):
        rev.changes.append({"date": day["date"], "before": before, "after": _label(day), "reason": reason})

    for w_index, week in enumerate(weeks):
        days = week["days"]
        editable = [d for d in days if d.get("editable")]
        if not editable:
            continue
        prior = prior_hard if w_index == 0 else is_hard(weeks[w_index - 1]["days"][-1])
        easy_pool = lambda exclude=(): [d for d in editable if d["type"] == "easy" and d["day"] not in new.rest_days
                                        and d not in exclude]

        # 1. The long run follows its new day when that is a plain easy/rest day and stays safe.
        if new.long_run_day != old.long_run_day:
            long_run = next((d for d in editable if d["type"] == "long_run"), None)
            target = next((d for d in editable if d["day"] == new.long_run_day and d["type"] in ("easy", "rest")), None)
            if long_run and target:
                saved = {k: long_run.get(k) for k in SESSION_FIELDS}, {k: target.get(k) for k in SESSION_FIELDS}
                lr_before, target_before = _label(long_run), _label(target)
                long_run.update(saved[1]); target.update(saved[0])
                if _hard_neighbour(days, days.index(target), prior):
                    long_run.update(saved[0]); target.update(saved[1])
                    rev.notes.append(f"Kept the {target['date']} week's long run on {old.long_run_day.title()}: moving it "
                                     f"to {new.long_run_day.title()} would put two hard days back to back.")
                else:
                    change(target, target_before, f"Long run moved to {new.long_run_day.title()}.")
                    change(long_run, lr_before, f"Long run moved to {new.long_run_day.title()}.")

        # 2. New rest days: easy miles move to other easy days; a workout moves to a safe easy day.
        for day in [d for d in editable if d["day"] in new.rest_days and d["type"] != "rest"]:
            before = _label(day)
            if day["type"] in ("workout", "race", "long_run"):
                def safe(slot):
                    # The vacated day becomes rest, so it never counts as a hard neighbour.
                    i = days.index(slot)
                    neighbours = [days[j] for j in (i - 1, i + 1) if 0 <= j < len(days) and days[j] is not day]
                    return not any(is_hard(n) for n in neighbours) and not (i == 0 and prior)
                slot = next((s for s in easy_pool() if safe(s)), None)
                if slot is None:
                    _rest(day)
                    change(day, before, f"{day['day'].title()} is now a rest day and no safe day was left this week, "
                                        "so this session is dropped rather than squeezed next to another hard day.")
                    continue
                slot_before, freed = _label(slot), slot["distance_miles"]
                slot.update({k: day.get(k) for k in SESSION_FIELDS})
                _rest(day)
                change(slot, slot_before, f"Moved from {day['day'].title()}, now a rest day.")
                change(day, before, f"{day['day'].title()} is now a rest day.")
                _spread(freed, easy_pool())
            else:
                freed = day["distance_miles"]
                _rest(day)
                change(day, before, f"{day['day'].title()} is now a rest day; its miles moved to other easy days.")
                _spread(freed, easy_pool())

        # 3. Fewer run days: drop the shortest editable easy days.
        while sum(d["type"] != "rest" for d in days) > new.days_per_week:
            candidates = easy_pool()
            if not candidates:
                rev.notes.append(f"Week {week['week_number']} keeps {sum(d['type'] != 'rest' for d in days)} run days: "
                                 "only workouts and the long run are left to change.")
                break
            day = min(candidates, key=lambda d: (d["distance_miles"], d["date"]))
            before, freed = _label(day), day["distance_miles"]
            _rest(day)
            change(day, before, "Fewer run days this week; its miles moved to other easy days.")
            _spread(freed, easy_pool())

        # 4. More run days: a short easy/recovery run, funded by a small allowance, then by splitting easy days.
        planned = sum(d["distance_miles"] for d in days)
        extra_left = min(_round_half(planned * allowance_share), MAX_ADDED_MILES)
        easy_days = [d for d in days if d["type"] == "easy"]
        average_easy = sum(d["distance_miles"] for d in easy_days) / len(easy_days) if easy_days else MIN_EASY
        while sum(d["type"] != "rest" for d in days) < new.days_per_week:
            open_days = [d for d in editable if d["type"] == "rest" and d["day"] not in new.rest_days]
            if not open_days:
                break

            def preference(d):
                i = days.index(d)
                after_long = i > 0 and days[i - 1]["type"] == "long_run"
                after_hard = i > 0 and is_hard(days[i - 1])
                return (not after_long, not after_hard, d["date"])
            day = min(open_days, key=preference)
            i = days.index(day)
            target = min(max(_round_half(average_easy * 0.6), RECOVERY_MIN), RECOVERY_MAX)
            from_allowance = min(target, extra_left)
            needed = target - from_allowance
            donors = sorted([d for d in easy_pool() if d is not day], key=lambda d: -d["distance_miles"])
            while needed >= 0.5:
                donor = next((d for d in donors if d["distance_miles"] - 0.5 >= MIN_EASY), None)
                if donor is None:
                    break
                donor["distance_miles"] -= 0.5
                needed -= 0.5
                donors.sort(key=lambda d: -d["distance_miles"])
            miles = target - needed
            if miles < RECOVERY_MIN:
                # Give the shaved miles back: an extra day isn't worth more mileage than the athlete can absorb.
                _spread(miles - from_allowance, [d for d in easy_pool() if d is not day])
                rev.notes.append(f"Week {week['week_number']}: no room for another run day without adding more "
                                 "mileage than is safe. The next block is built with your new day count.")
                break
            extra_left -= from_allowance
            before = _label(day)
            after_long = i > 0 and days[i - 1]["type"] == "long_run"
            _easy(day, miles, "Recovery Run" if i > 0 and is_hard(days[i - 1]) else "Easy Run", easy_desc)
            change(day, before, "Added run day: short and easy" + (" the day after the long run." if after_long else "."))
        week["target_mileage"] = round(sum(d["distance_miles"] for d in days), 1)

    # Easy days that gave or took miles to keep the week level are changes too.
    recorded = {c["date"] for c in rev.changes}
    original = {d["date"]: d for w in original_weeks for d in w["days"]}
    for day in (d for w in weeks for d in w["days"]):
        old_day = original[day["date"]]
        if day["date"] not in recorded and any(day.get(k) != old_day.get(k) for k in SESSION_FIELDS):
            shorter = day["distance_miles"] < old_day["distance_miles"]
            rev.changes.append({"date": day["date"], "before": _label(old_day), "after": _label(day),
                                "reason": "Shortened to make room for the added run day." if shorter
                                else "Lengthened to keep the week's miles after a day became rest."})
    rev.changes.sort(key=lambda c: c["date"])
    return rev
