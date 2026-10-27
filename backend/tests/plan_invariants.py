"""Running-rule invariants every generated plan must satisfy.

`assert_plan_invariants(plan, ...)` takes the dict `generate_training_plan` returns
(or a stored `Plan.preview_data`) and checks it against the coaching rules in
CLAUDE.md, using the production policy functions as the source of truth:

- `plan_validator.validate_plan`: weekly budget, no runs on rest days, no hard day
  directly after another hard day (except a flagged ultra ``b2b`` pair)
- ramp: no week schedules more than the demonstrated load (the 4-week average, or after a
  down week the training level, never above a week actually run) grown by
  `load_policy.ramp_rate`, and no week grows more than that rate over the week
  before it (a week may always return to the demonstrated load after a lighter one)
- deloads: a deload week appears exactly when `load_policy.deload_due` says one is
  due for the completed weeks, on the first eligible full week, and is actually lighter
- taper: from the first taper week through race week, weekly volume never rises
- race week: at most one workout (a sharpener ≥3 days before the race), a short
  shakeout the day before, then race day; nothing hard after it
- intensity distribution: roughly 80/20 easy by work-segment miles (see EASY_SHARE_MIN)
- one lever at a time: a week whose long run introduces race-pace work, or grows it by
  `load_policy.RACE_PACE_STEP_MILES`, doesn't also raise volume over the week before it

Race-day miles are not training load, so they are left out of ramp, taper and
80/20 totals. Days with ``prescribed`` False are already-run history and are only
counted, never judged.
"""

from datetime import date, timedelta

from app.core.load_policy import DELOAD_FACTOR, deload_due, race_pace_step, ramp_rate
from app.core.periodization import is_ultra
from app.core.workout_data import race_pace_miles
from app.core.plan_validator import BUDGET_OVER_TOLERANCE, is_hard, validate_plan

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Plans round every day to the nearest half mile, so a week can land half a mile
# above its exact policy number; the validator allows the same.
MILES_TOLERANCE = BUDGET_OVER_TOLERANCE

# 80/20 by mileage. Hard miles are a workout's *work* segments from its structured
# prescription (reps x rep distance, or rep time at the segment's pace); warmup,
# cooldown and jog recoveries are easy running. A workout without a structured
# prescription counts as hard for its whole distance. Long runs count as easy
# aerobic volume. The floor is 75% easy per fully prescribed training week: 80/20
# with five points of slack for half-mile rounding and two-session weeks near the
# dual-quality volume threshold. Race weeks are excluded: their shape (sharpener,
# shakeout, race) is checked separately and their low volume makes shares noisy.
EASY_SHARE_MIN = 0.75
MI = 1609.34
FALLBACK_WORK_PACE = 360  # sec/mi, for a timed rep with no pace on it (counts it generously)

PRE_TAPER = {"general", "base", "build", "peak"}
TAPERING = {"taper", "race_week"}


def _training_miles(week: dict) -> float:
    return sum(d["distance_miles"] for d in week["days"] if d["type"] != "race")


def _full_week(week: dict) -> bool:
    return len(week["days"]) == 7


def _fully_prescribed(week: dict) -> bool:
    return _full_week(week) and all(d.get("prescribed", True) for d in week["days"])


def work_miles(day: dict) -> float:
    """Miles at workout intensity in a day: its work segments, else the whole day."""
    if day["type"] != "workout":
        return 0.0
    p = day.get("prescription") or {}
    if p.get("evidence_source") == "effort_guidance" or not p.get("segments"):
        return day["distance_miles"]
    miles = 0.0
    for s in p["segments"]:
        pace = s.get("pace_range_sec_per_mile")
        if s.get("distance_meters"):
            miles += s["reps"] * s["distance_meters"] / MI
        elif s.get("duration_seconds"):
            miles += s["reps"] * s["duration_seconds"] / ((pace["fast"] + pace["slow"]) / 2 if pace else FALLBACK_WORK_PACE)
    return min(miles, day["distance_miles"])


def _phase(week: dict) -> str:
    return (week.get("phase") or {}).get("phase", "general")


def plan_invariant_violations(
    plan: dict,
    *,
    rest_days: list[str] | None = None,
    completed_weeks: list[float] | None = None,
    prior_hard_dates: frozenset[str] | set[str] = frozenset(),
    recent_race_pace_miles: float | None = None,
) -> list[str]:
    """Every rule the plan breaks, as readable strings. Empty means it conforms.

    rest_days defaults to the plan's athlete snapshot. completed_weeks (oldest →
    newest full calendar weeks, as the API feeds `deload_due`) enables the deload
    cadence check; without it only the deload week's shape is checked.
    recent_race_pace_miles (the most race-pace miles in a recently run long run) enables
    the one-lever check on the first week; later weeks compare against earlier ones.
    """
    weeks = plan["weeks"]
    load = plan.get("load") or {}
    athlete = plan.get("athlete") or {}
    goal = plan.get("goal") or {}
    if rest_days is None:
        rest_days = (athlete.get("schedule_preferences") or {}).get("rest_days", [])
    rest_indices = [DAY_NAMES.index(d) for d in rest_days if d in DAY_NAMES]
    problems: list[str] = []

    # 1. The production validator: budget, rest days, hard-after-hard.
    for v in validate_plan(weeks, rest_indices, prior_hard_dates):
        problems.append(f"validator {v['code']} on {v['date']}: {v['message']}")

    # 2. Ramp rate.
    baseline = float(load.get("baseline") or 0)
    experience = athlete.get("experience_level", "beginner")
    rate = ramp_rate(baseline, float(athlete.get("peak_weekly_mileage") or 0), experience, goal.get("type") or "race")
    # After a down week the policy grows from the training level (the full-volume weeks), not the
    # deload-dragged average. Checked independently: never above a week actually run, never more
    # than 35% over the average.
    level = min(float(load.get("training_level") or 0), baseline * 1.35)
    if completed_weeks:
        level = min(level, max(completed_weeks[-4:]))
    anchor = max(baseline, float(load.get("planning_anchor") or 0), level)
    if load.get("mode") == "start":  # no usable history: the policy's starting load is the anchor
        anchor = max(anchor, *(load.get("weekly_budgets") or [0]))
    ceiling = anchor * (1 + rate)
    developmental = bool(load.get('developmental'))
    for w in weeks:
        if developmental:
            ceiling = anchor * (1 + min(rate, .10)) ** min(w['week_number'], 2)
        locked = sum(d["distance_miles"] for d in w["days"] if not d.get("prescribed", True))
        if _training_miles(w) > max(ceiling, locked) + MILES_TOLERANCE:
            problems.append(f"ramp: week {w['week_number']} schedules {_training_miles(w):.1f} mi, above "
                            f"{anchor:.1f} x (1 + {rate:.0%}) = {ceiling:.1f}")
    for a, b in zip(weeks, weeks[1:]):
        if not (_fully_prescribed(b) and _full_week(a)):
            continue
        reference = max(_training_miles(a), anchor)
        if _training_miles(b) > reference * (1 + rate) + MILES_TOLERANCE:
            problems.append(f"ramp: week {b['week_number']} ({_training_miles(b):.1f} mi) grows more than "
                            f"{rate:.0%} over max(week {a['week_number']}, baseline) = {reference:.1f}")

    # 3. Deload cadence and shape.
    deload_week = load.get("deload_week")
    if completed_weeks is not None:
        due, _ = deload_due(completed_weeks, experience)
        if developmental:
            from app.core.developmental import deload_supported
            dates = [date.fromisoformat(d['date']) for w in weeks for d in w['days'] if d.get('prescribed', True)]
            evidence = (plan.get('quality_policy') or (athlete.get('quality_policy') or {})).get('evidence', {})
            due = due and deload_supported(completed_weeks, evidence, min(dates))
        if (plan.get("assessment") or {}).get("decision") in ("reduce", "recovery"):
            due = False  # a reduced block already is the lighter block
        eligible = [i for i, w in enumerate(weeks) if _fully_prescribed(w) and _phase(w) in PRE_TAPER]
        expected = eligible[0] if due and eligible else None
        if deload_week != expected:
            problems.append(f"deload: deload_due={due} for completed weeks {completed_weeks} ({experience}) "
                            f"expects deload week index {expected}, plan has {deload_week}")
    if deload_week is not None and 0 <= deload_week < len(weeks):
        w = weeks[deload_week]
        deload_anchor = anchor if developmental else baseline
        if w["budget_miles"] > deload_anchor * DELOAD_FACTOR + MILES_TOLERANCE:
            problems.append(f"deload: week {w['week_number']} budget {w['budget_miles']} is not "
                            f"≤ {DELOAD_FACTOR:.0%} of baseline {baseline}")
        if sum(d["type"] == "workout" for d in w["days"]) > 1:
            problems.append(f"deload: week {w['week_number']} keeps more than one quality session")
        for after in weeks[deload_week + 1:]:
            if _training_miles(after) > deload_anchor + MILES_TOLERANCE and _phase(after) in PRE_TAPER:
                problems.append(f"deload: week {after['week_number']} jumps past baseline right after the deload")

    # 4. Taper: volume never rises from the first taper week through race week.
    for a, b in zip(weeks, weeks[1:]):
        if _phase(b) in TAPERING and _phase(a) in TAPERING | PRE_TAPER:
            if b["budget_miles"] > a["budget_miles"] + MILES_TOLERANCE:
                problems.append(f"taper: week {b['week_number']} ({_phase(b)}) budget {b['budget_miles']} "
                                f"rises over week {a['week_number']} ({_phase(a)}) {a['budget_miles']}")
            if _fully_prescribed(a) and _fully_prescribed(b) and _training_miles(b) > _training_miles(a) + MILES_TOLERANCE:
                problems.append(f"taper: week {b['week_number']} schedules {_training_miles(b):.1f} mi, "
                                f"more than week {a['week_number']} ({_training_miles(a):.1f})")

    # 5. Race week shape.
    for w in weeks:
        if _phase(w) != "race_week":
            continue
        races = [d for d in w["days"] if d["type"] == "race"]
        if len(races) != 1:
            if any(not d.get("prescribed", True) for d in w["days"]) or not _full_week(w):
                continue  # race already behind us or outside this block
            problems.append(f"race week {w['week_number']}: expected one race day, found {len(races)}")
            continue
        race_day = date.fromisoformat(races[0]["date"])
        by_date = {date.fromisoformat(d["date"]): d for d in w["days"]}
        before = [d for d in w["days"] if date.fromisoformat(d["date"]) < race_day and d.get("prescribed", True)]
        hard_before = [d for d in before if is_hard(d)]
        if len(hard_before) > 1 or any(d["type"] != "workout" for d in hard_before):
            problems.append(f"race week {w['week_number']}: only one sharpener may precede the race, got "
                            f"{[(d['date'], d['type']) for d in hard_before]}")
        for d in hard_before:
            if (race_day - date.fromisoformat(d["date"])).days < 3:
                problems.append(f"race week {w['week_number']}: sharpener {d['date']} is closer than 3 days to the race")
        # The sharpener belongs on the last run day ≥3 days out, if that day is still ahead.
        slot = next((race_day - timedelta(days=k) for k in range(3, 7)
                     if (race_day - timedelta(days=k)).weekday() not in rest_indices
                     and race_day - timedelta(days=k) in by_date), None)
        if slot and by_date[slot].get("prescribed", True) and by_date[slot]["type"] != "workout" \
                and not by_date[slot].get("adjustment_reason"):
            problems.append(f"race week {w['week_number']}: no sharpener on {slot} (≥3 days before the race)")
        eve = by_date.get(race_day - timedelta(days=1))
        if eve and eve.get("prescribed", True) and eve["type"] != "rest":
            if eve["type"] != "easy" or eve["distance_miles"] > 3 or "shakeout" not in eve["title"].lower():
                problems.append(f"race week {w['week_number']}: day before the race should be a short shakeout, "
                                f"got {eve['type']} '{eve['title']}' {eve['distance_miles']} mi")
        for d in w["days"]:
            if date.fromisoformat(d["date"]) > race_day and (is_hard(d) or d["distance_miles"] > 3):
                problems.append(f"race week {w['week_number']}: {d['date']} after the race must be rest or a short jog")

    # 6. 80/20 easy share per fully prescribed training week.
    for w in weeks:
        total = _training_miles(w)
        if not _fully_prescribed(w) or _phase(w) == "race_week" or total <= 0:
            continue
        hard = sum(work_miles(d) for d in w["days"])
        if (total - hard) / total < EASY_SHARE_MIN:
            problems.append(f"80/20: week {w['week_number']} is {(total - hard) / total:.0%} easy "
                            f"({hard:.1f} of {total:.1f} mi at workout intensity); floor is {EASY_SHARE_MIN:.0%}")

    # 7. One lever at a time: a new or materially longer race-pace long run holds volume.
    if not developmental and not is_ultra(goal.get("distance")):
        absorbed = recent_race_pace_miles
        for i, w in enumerate(weeks):
            race_pace = max([race_pace_miles(d) for d in w["days"] if d["type"] == "long_run"], default=0)
            if i == 0:
                previous = (completed_weeks or [0])[-1] if absorbed is not None else None
            else:
                previous = weeks[i - 1]["budget_miles"]
            if (previous is not None and _phase(w) in {"build", "peak"} and race_pace_step(race_pace, absorbed or 0)
                    and w["budget_miles"] > max(previous, float(load.get("training_level") or 0), baseline) + MILES_TOLERANCE):
                problems.append(f"one lever: week {w['week_number']} adds {race_pace:g} mi at race pace in the long run "
                                f"and raises volume to {w['budget_miles']} over {previous}")
            absorbed = max(absorbed or 0, race_pace)
    return problems


def assert_plan_invariants(plan: dict, **kwargs) -> None:
    problems = plan_invariant_violations(plan, **kwargs)
    assert not problems, "plan breaks running rules:\n  " + "\n  ".join(problems)
