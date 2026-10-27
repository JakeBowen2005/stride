"""Edits an athlete can ask for in plain language, applied and checked deterministically.

The AI (or the rules-only solver) only ever proposes a list of these ops. Stride applies
them here and judges the result with the same rules as every other schedule change, plus
the few this feature needs (``request_violations``). No op adds miles or quality, changes
paces, or touches past, run or race days.

A *day* is a plain dict: ``date``, ``type``, ``title``, ``distance_miles``, ``week_number``,
``editable`` and the content fields below. Pure functions: no database access.
"""

from copy import deepcopy
from datetime import date
from itertools import permutations

from app.core.plan_validator import LONG_RUN_SPACING_DAYS, MIN_EASY_FLOOR, MIN_LONG_SHARE, is_hard
from app.core.time_budget import estimated_minutes
from app.core.workout_data import day_prescription

CONTENT = ("type", "title", "description", "purpose", "distance_miles", "warmup", "cooldown", "prescription", "b2b")
OPS = ("move", "swap", "shorten", "easy", "skip")
REDUCING = {"skip", "easy", "shorten"}
REDUCE_ONLY_PHASES = {"taper", "race_week"}
MAX_OPS = 6
EASY_FROM_HARD_MAX = 6.0  # same as build_options' "make it easy"
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class OpError(ValueError):
    def __init__(self, code: str, day: str | None, message: str):
        super().__init__(message)
        self.reason = {"code": code, "date": day, "message": message}


def _content(day: dict) -> dict:
    return {k: deepcopy(day.get(k)) for k in CONTENT}


def _as_rest(day: dict, title: str, description: str) -> None:
    day.update(type="rest", title=title, description=description, purpose="Recovery.",
               distance_miles=0, warmup=None, cooldown=None, b2b=False)
    day["prescription"] = day_prescription(day | {"prescription": None})


def _as_easy(day: dict, miles: float) -> None:
    day.update(type="easy", title="Easy Run", description="Conversational effort, truly easy.",
               purpose="Recovery instead of quality work.", distance_miles=miles,
               warmup=None, cooldown=None, b2b=False)
    day["prescription"] = day_prescription(day | {"prescription": None})


def _label(day: dict) -> str:
    when = date.fromisoformat(day["date"])
    return f"{DAY_NAMES[when.weekday()].title()} {when.strftime('%b')} {when.day}"


def apply_ops(days: list[dict], ops: list[dict]) -> list[dict]:
    """Return a new day list with ``ops`` applied in order. Raises OpError on a bad op."""
    out = deepcopy(days)
    by_date = {d["date"]: d for d in out}
    if len(ops) > MAX_OPS:
        raise OpError("too_many_ops", None, f"At most {MAX_OPS} changes per request.")
    touched: dict[str, str] = {}

    def editable(when: str | None, role: str) -> dict:
        day = by_date.get(when or "")
        if day is None:
            raise OpError("outside_window", when, f"{when or 'That day'} isn't in the part of your plan that can change.")
        if day["type"] == "race":
            raise OpError("race_locked", when, f"{_label(day)} is race day; it never moves.")
        if not day.get("editable"):
            raise OpError("locked", when, f"{_label(day)} is already run or in the past, so it can't {role}.")
        return day

    def touch(when: str, op: str) -> None:
        # A day changes once, except a swap or move followed by easing or shortening that day.
        previous = touched.get(when)
        if previous and not (previous in {"swap", "move"} and op in {"easy", "shorten", "skip"}):
            raise OpError("touched_twice", when, f"{when} is changed by more than one step.")
        touched[when] = op

    for op in ops:
        kind = op.get("op")
        if kind not in OPS:
            raise OpError("unknown_op", op.get("date"), f"Unknown change '{kind}'.")
        day = editable(op.get("date"), "change")
        if kind in {"move", "swap"}:
            other = editable(op.get("target_date"), "change")
            if other is day:
                raise OpError("same_day", day["date"], "Pick two different days.")
            if day["week_number"] != other["week_number"]:
                raise OpError("cross_week", day["date"],
                              "Sessions stay inside their own week, so missed volume is never crammed into the next one.")
            if kind == "move":
                if day["type"] == "rest":
                    raise OpError("nothing_to_move", day["date"], f"{_label(day)} is already a rest day.")
                if other["type"] not in {"easy", "rest"}:
                    raise OpError("occupied", other["date"], f"{_label(other)} already has {other['title']}; swap them instead.")
                touch(day["date"], kind)
                touch(other["date"], kind)
                other.update(_content(day))
                other["b2b"] = False
                _as_rest(day, "Session moved", f"Moved to {_label(other)} at your request.")
            else:
                touch(day["date"], kind)
                touch(other["date"], kind)
                a, b = _content(day), _content(other)
                day.update(b)
                other.update(a)
                day["b2b"] = other["b2b"] = False
            continue
        touch(day["date"], kind)
        if kind == "skip":
            _as_rest(day, "Session skipped", "Rest at your request.")
        elif kind == "easy":
            if day["type"] not in {"workout", "long_run"}:
                raise OpError("not_hard", day["date"], f"{_label(day)} is already easy.")
            _as_easy(day, min(day["distance_miles"], EASY_FROM_HARD_MAX))
        elif kind == "shorten":
            miles = op.get("miles")
            if miles is None or miles >= day["distance_miles"]:
                raise OpError("not_shorter", day["date"], f"Shortening {_label(day)} must lower its distance.")
            if day["type"] == "workout":
                raise OpError("shorten_workout", day["date"],
                              f"A workout can't be cut part-way; make {_label(day)} easy instead.")
            if day["type"] == "easy" and miles < MIN_EASY_FLOOR:
                raise OpError("too_short", day["date"], f"An easy run under {MIN_EASY_FLOOR:g} mi isn't worth it; skip it instead.")
            if day["type"] == "long_run":
                week_total = sum(d["distance_miles"] for d in days if d["week_number"] == day["week_number"])
                floor = max(4.0, round(week_total * MIN_LONG_SHARE * 2) / 2)
                if miles < floor:
                    raise OpError("too_short", day["date"], f"A long run below {floor:g} mi stops being a long run; make it easy instead.")
            day["distance_miles"] = round(miles * 2) / 2
            if day["type"] == "easy":
                day["prescription"] = day_prescription(day | {"prescription": None})
            elif day["type"] == "long_run":
                # Long runs keep their character; only the distance comes down.
                day["description"] = f"{day['distance_miles']:g} mi at easy long-run effort (shortened at your request)."
                day["prescription"] = day_prescription(day | {"prescription": None, "type": "easy"})
                day["warmup"] = day["cooldown"] = None
    return out


def _minutes(day: dict, easy_pace: float) -> float:
    if day["type"] in {"rest", "race"}:
        return 0.0
    return estimated_minutes(day, easy_pace)


def constraint_problems(after: list[dict], constraints: list[dict], easy_pace: float) -> list[dict]:
    by_date = {d["date"]: d for d in after}
    problems = []
    for c in constraints:
        day = by_date.get(c["date"])
        if day is None:
            continue
        if c["kind"] == "no_run" and day["distance_miles"] > 0 and day["type"] != "race":
            problems.append({"code": "constraint_no_run", "date": c["date"], "message": f"{_label(day)} still has a run, but you can't run that day."})
        elif c["kind"] == "no_hard" and is_hard(day) and day["type"] != "race":
            problems.append({"code": "constraint_no_hard", "date": c["date"], "message": f"{_label(day)} is still a hard day ({day['title']})."})
        elif c["kind"] == "max_minutes" and c.get("minutes") is not None and _minutes(day, easy_pace) > c["minutes"] + 0.5:
            problems.append({"code": "constraint_minutes", "date": c["date"],
                             "message": f"{_label(day)} needs about {round(_minutes(day, easy_pace))} min; you have {c['minutes']}."})
    return problems


def request_violations(before: list[dict], after: list[dict], ops: list[dict], *, phases: dict[int, str],
                       last_long_run: str | None, constraints: list[dict], easy_pace: float,
                       reduce_only: bool = False) -> list[dict]:
    """Rules this feature adds on top of ``_validate_schedule`` (budget, rest days, hard-after-hard, time)."""
    problems: list[dict] = []
    weeks = sorted({d["week_number"] for d in after})
    for week in weeks:
        old = [d for d in before if d["week_number"] == week]
        new = [d for d in after if d["week_number"] == week]
        old_total, new_total = sum(d["distance_miles"] for d in old), sum(d["distance_miles"] for d in new)
        if new_total > old_total + 0.01:
            problems.append({"code": "volume_rose", "date": new[0]["date"],
                             "message": f"Week {week} would go from {old_total:g} to {new_total:g} mi. A life-event change never adds load."})
        quality = lambda days: sum(d["type"] == "workout" for d in days)  # noqa: E731
        if quality(new) > quality(old):
            problems.append({"code": "quality_added", "date": new[0]["date"], "message": f"Week {week} would gain a workout."})
        longest_before = max((d["distance_miles"] for d in old if d["type"] == "long_run"), default=0)
        if any(d["type"] == "long_run" and d["distance_miles"] > longest_before + 0.01 for d in new):
            problems.append({"code": "long_run_grew", "date": new[0]["date"], "message": f"Week {week}'s long run would get longer."})
    if reduce_only or any(phases.get(d["week_number"]) in REDUCE_ONLY_PHASES for d in after
                          if any(o.get("date") == d["date"] or o.get("target_date") == d["date"] for o in ops)):
        moving = [o for o in ops if o["op"] not in REDUCING]
        if moving:
            why = ("You mentioned feeling unwell or hurt, so" if reduce_only else "During the taper and race week")
            problems.append({"code": "reduce_only", "date": moving[0]["date"],
                             "message": f"{why} sessions can only be eased, shortened or skipped, not moved."})
    longs = sorted(d["date"] for d in after if d["type"] == "long_run" and d["distance_miles"] > 0 and not d.get("b2b"))
    if last_long_run:
        longs = [last_long_run] + [d for d in longs if d > last_long_run]
    for a, b in zip(longs, longs[1:]):
        gap = (date.fromisoformat(b) - date.fromisoformat(a)).days
        if gap < LONG_RUN_SPACING_DAYS:
            problems.append({"code": "long_run_spacing", "date": b,
                             "message": f"Only {gap} days between long runs ({a} and {b}); they need at least {LONG_RUN_SPACING_DAYS}."})
    problems.extend(constraint_problems(after, constraints, easy_pace))
    return problems


def hard_adjacency(after: list[dict], prior_hard: set[str]) -> list[dict]:
    """Quick hard-after-hard screen for the solver (the DB validator is still the judge)."""
    by_date = {d["date"]: d for d in after}
    out = []
    for d in after:
        if not is_hard(d):
            continue
        prev = (date.fromisoformat(d["date"]).toordinal() - 1)
        prev_iso = date.fromordinal(prev).isoformat()
        p = by_date.get(prev_iso)
        if (p is not None and is_hard(p) and not (p.get("b2b") and d.get("b2b"))) or (p is None and prev_iso in prior_hard):
            out.append({"code": "hard_after_hard", "date": d["date"], "message": f"{_label(d)} comes straight after another hard day."})
    return out


def _swaps_for(order: list[int]) -> list[tuple[int, int]]:
    """Transpositions that turn identity into ``order`` (position i receives content order[i])."""
    current = list(range(len(order)))
    swaps = []
    for i, want in enumerate(order):
        j = current.index(want)
        if j != i:
            current[i], current[j] = current[j], current[i]
            swaps.append((i, j))
    return swaps


def solve(days: list[dict], constraints: list[dict], *, rest_days: set[str], phases: dict[int, str],
          last_long_run: str | None, prior_hard: set[str], easy_pace: float, reduce_only: bool = False,
          limit: int = 8) -> list[list[dict]]:
    """Rules-only rearrangement for the weeks a request touches. Returns candidate op lists, best first.

    Hard sessions are placed by brute force over the week's open days (a week has at most three,
    so at most a few hundred placements). Score: long run kept at full distance, fewest changed
    days, workouts in their original order, fewest quality sessions dropped. If no placement fits,
    the lowest-priority workout (the later one) is eased and it tries again: fail safe, never stacked.
    """
    by_week: dict[int, list[dict]] = {}
    for d in days:
        by_week.setdefault(d["week_number"], []).append(d)
    affected = sorted({d["week_number"] for d in days if any(c["date"] == d["date"] for c in constraints)})
    if not affected:
        return []
    forbid_hard = {c["date"] for c in constraints if c["kind"] in {"no_hard", "no_run", "prefer_rest"}}
    no_run = {c["date"] for c in constraints if c["kind"] == "no_run"}
    max_minutes = {c["date"]: c["minutes"] for c in constraints if c["kind"] == "max_minutes" and c.get("minutes")}

    per_week: list[list[tuple[tuple, list[dict]]]] = []
    for week in affected:
        week_days = sorted(by_week[week], key=lambda d: d["date"])
        reduce = reduce_only or phases.get(week) in REDUCE_ONLY_PHASES
        open_days = [d for d in week_days if d.get("editable") and d["type"] != "race"
                     and DAY_NAMES[date.fromisoformat(d["date"]).weekday()] not in rest_days]
        options: list[tuple[tuple, list[dict]]] = []
        workouts = [d for d in open_days if d["type"] == "workout"]
        for dropped in range(len(workouts) + 1):
            eased = {d["date"] for d in workouts[len(workouts) - dropped:]}
            hard_idx = [i for i, d in enumerate(open_days) if is_hard(d)]
            soft_idx = [i for i in range(len(open_days)) if i not in hard_idx]
            placements = [tuple(hard_idx)] if reduce else permutations(range(len(open_days)), len(hard_idx))
            for slots in placements:
                # Hard sessions go to ``slots``; easy and rest days fill the rest in their original order.
                order = [None] * len(open_days)
                for src, pos in zip(hard_idx, slots):
                    order[pos] = src
                rest_iter = iter(soft_idx)
                order = [o if o is not None else next(rest_iter) for o in order]
                content = [open_days[i] for i in order]
                blocked = {open_days[pos]["date"] for pos, src in enumerate(content)
                           if is_hard(src) and src["date"] not in eased and open_days[pos]["date"] in forbid_hard}
                if blocked and not reduce:
                    continue  # when moving is allowed, a hard session never lands on a blocked day
                ops = [{"op": "swap", "date": open_days[i]["date"], "target_date": open_days[j]["date"]} for i, j in _swaps_for(list(order))]
                placed = {open_days[pos]["date"]: src for pos, src in enumerate(content)}
                for when, src in placed.items():
                    if is_hard(src) and (src["date"] in eased or when in blocked) and when not in no_run:
                        ops.append({"op": "easy", "date": when})
                for when in sorted(no_run):
                    if when in placed and (placed[when]["distance_miles"] > 0):
                        ops.append({"op": "skip", "date": when})
                    elif when in {d["date"] for d in week_days if d.get("editable")} and when not in placed:
                        ops.append({"op": "skip", "date": when})
                for when, cap in max_minutes.items():
                    src = placed.get(when)
                    if src is None or when in no_run or src["distance_miles"] <= 0:
                        continue
                    miles = round((cap / (easy_pace / 60)) * 2) / 2 - 0.5
                    if is_hard(src) and src["date"] not in eased:
                        continue  # a hard day over the limit fails the check below
                    if miles >= MIN_EASY_FLOOR and src["type"] == "easy" and miles < src["distance_miles"]:
                        ops.append({"op": "shorten", "date": when, "miles": miles})
                    elif _minutes(src, easy_pace) > cap:
                        ops.append({"op": "skip", "date": when})
                ops = [o for o in ops if not (o["op"] == "skip" and placed.get(o["date"], {}).get("type") == "rest")]
                changed = len({o["date"] for o in ops} | {o.get("target_date") for o in ops if o.get("target_date")})
                if reduce and any(o["op"] not in REDUCING for o in ops):
                    continue
                kept_long = any(d["type"] == "long_run" for pos, d in enumerate(content)
                                if open_days[pos]["date"] not in blocked | no_run)
                workout_order = [d["date"] for d in content if d["type"] == "workout" and d["date"] not in eased]
                in_order = workout_order == sorted(workout_order)
                options.append(((0 if kept_long else 1, dropped, changed, 0 if in_order else 1), ops))
        options.sort(key=lambda x: x[0])
        per_week.append(options[:40])

    results: list[tuple[tuple, list[dict]]] = []
    def combine(i: int, score: tuple, ops: list[dict]) -> None:
        if len(results) > 400:
            return
        if i == len(per_week):
            results.append((score, ops))
            return
        for s, o in per_week[i]:
            combine(i + 1, tuple(a + b for a, b in zip(score, s)) if score else s, ops + o)
    combine(0, (), [])
    results.sort(key=lambda x: x[0])
    good: list[list[dict]] = []
    for _, ops in results:
        try:
            after = apply_ops(days, ops) if len(ops) <= MAX_OPS else None
        except OpError:
            continue
        if after is None:
            continue
        if hard_adjacency(after, prior_hard) or request_violations(days, after, ops, phases=phases, last_long_run=last_long_run,
                                                                  constraints=constraints, easy_pace=easy_pace, reduce_only=reduce_only):
            continue
        if ops and ops not in good:
            good.append(ops)
        if len(good) >= limit:
            break
    return good
