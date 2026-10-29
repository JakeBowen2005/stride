from app.athlete_clock import today as athlete_today
"""2-week rolling plan generator.

Key principles:
- Mileage progression within a demonstrated-load budget
- Mileage ramp rate accounts for headroom (current vs peak)
- Category paces change from execution evidence, not mileage or goal time
- Workout variety via date-seeded rotation
- Long runs have specific mile breakdowns (not just "steady finish")
- Marathon-first design: everything builds toward race day
"""

from datetime import date, timedelta

from app.core.pacing import format_pace, goal_paces, pace_range
from app.core.workout_data import long_run_prescription, race_pace_miles
from app.core.workouts import get_workout_library
from app.core.goal_pace import with_specific_pace
from app.core.session_catalog import ultra_vert_session
from app.core.workout_ladders import get_workout_at_level, get_deload_workout, get_week2_variant
from app.core.experience import experienced
from app.core import developmental
from app.core.quality_policy import select_quality_policy, light_speed_support, format_bookends
from app.core.load_policy import plan_load, race_pace_step
from app.core.periodization import NO_DELOAD_BEFORE_TAPER_WEEKS, WeekPhase, is_ultra, plan_phases, protects_peak, weeks_before_taper
from app.core.plan_validator import enforce_no_back_to_back_hard, fit_week_to_budget, validate_plan
from app.core.special_weeks import (
    back_to_back_day,
    build_race_week,
    apply_post_race_rest,
    hill_session,
    ultra_long_run,
)


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DEFAULT_WORKOUT_DAYS = [1, 3]
DEFAULT_LONG_RUN_DAY = 5
# Longest single run by road goal (miles, minutes at easy pace): Daniels caps the long run
# near 150 min; 5K/10K need endurance support, not marathon-length runs.
ROAD_LONG_RUN_CAP = {"5k": (15, 120), "10k": (16, 135), "half": (18, 150), "marathon": (22, 210)}
DEFAULT_REST_DAY = 6


def calculate_plan_params() -> dict:
    """Calculate start_date, end_date, and num_weeks for a plan.

    ALL plans start from Monday of the current week:
      - Mon-Wed (weekday <= 2): 2 weeks (rest of this week + 1 full week)
      - Thu-Sun (weekday >= 3): 3 weeks (rest of this week + 2 full weeks)
    Days before today in the current week show as non-prescribed.
    """
    today = athlete_today()
    weekday = today.weekday()  # 0=Mon, 6=Sun

    # Start from Monday of current week
    start_date = today - timedelta(days=weekday)
    if weekday <= 2:  # Mon-Wed
        num_weeks = 2  # rest of this week + 1 full week
    else:  # Thu-Sun
        num_weeks = 3  # rest of this week + 2 full weeks
    end_date = start_date + timedelta(days=num_weeks * 7 - 1)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "num_weeks": num_weeks,
        "first_prescribe_date": today,
    }


def _round_half(d: float) -> float:
    """Round distance to nearest 0.5 mile."""
    return round(d * 2) / 2


def _round_pace(seconds: float) -> float:
    """Round pace to nearest 5 seconds."""
    return round(seconds / 5) * 5


def generate_plan(
    goal_type: str,
    goal_distance: str | None,
    target_time_seconds: float | None,
    current_weekly_mileage: float,
    peak_weekly_mileage: float,
    experience_level: str,
    days_per_week: int,
    rest_days: list[str],
    long_run_day: str,
    easy_pace_seconds: float,
    current_workout_paces: dict | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    num_weeks: int = 2,
    first_prescribe_date: date | None = None,
    block_number: int = 1,
    progression_state: dict | None = None,
    race_date: date | None = None,
    terrain: str | None = None,
    target_weekly_mileage: float | None = None,
    assessment: str | None = None,
    completed_by_date: dict[str, float] | None = None,
    prior_hard_dates: set[str] | None = None,
    reported_mileage: float | None = None,
    allow_preview: bool = True,
    deload_is_due: bool | None = None,
    completed_weeks: list[float] | None = None,
    fatigue_recovery: bool = False,
    workout_format: str = 'distance',
    weekly_run_days: list[int] | None = None,
    recent_long_run_miles: float = 0,
    quality_evidence: dict | None = None,
    previous_quality_stage: str | None = None,
    continuous_run_minutes: int | None = None,
    run_walk_weeks: list[int] | None = None,  # run days per completed week since the starting point was set
    previous_block: dict | None = None,
    day_time_budgets: dict[str,int] | None = None,
    race_weeks: list[bool] | None = None,  # aligned with completed_weeks: weeks that held a race
    recent_race_pace_miles: float = 0,  # most race-pace miles in a recently completed long run
) -> dict:
    """Generate a block.

    deload_is_due comes from completed training history (load_policy.deload_due);
    when None, the legacy block-number cadence is used.

    current_weekly_mileage is the demonstrated baseline (4-week average of completed
    runs). completed_by_date carries real miles already run on days of the block that
    are before first_prescribe_date, so a midweek plan only prescribes what's left.
    prior_hard_dates are ISO dates of real hard runs just before the plan, so the
    first prescribed day can't stack on yesterday's long run.
    """
    completed_by_date = completed_by_date or {}
    prior_hard_dates = set(prior_hard_dates or ())
    if start_date is None:
        today = athlete_today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start_date = today + timedelta(days=days_until_monday)

    if end_date is None:
        end_date = start_date + timedelta(days=num_weeks * 7 - 1)

    # Race-date periodization: phase per week (base/build/peak/taper/race week/recovery)
    phases = plan_phases(start_date, num_weeks, goal_type, goal_distance, race_date)
    developing = developmental.uses_developmental(experience_level, goal_type, goal_distance)
    development_state = (progression_state or {}).get('development', {})
    evidence = quality_evidence or {}
    # Established intermediates keep their demonstrated full-quality program;
    # the introductory path must not reset a trained runner to ten minutes.
    if (experience_level == 'intermediate' and current_weekly_mileage >= 25
            and evidence.get('primary_successes', 0) >= 4 and not development_state.get('last_completed_level')):
        developing = False

    # Deloads land on the first full week that hasn't started yet (a deload label on a
    # week that's already half run would be a deload in name only)
    fpd = first_prescribe_date or athlete_today()
    deload_week = None
    due = _is_deload_block(block_number, experience_level) if deload_is_due is None else deload_is_due
    if developing:
        # Old easy fixture/history weeks alone do not force an immediate down
        # week. Count performed quality exposures since the last lighter week.
        due = due and developmental.deload_supported(completed_weeks or [], evidence, fpd)
    peak_hold = False  # a due deload was suppressed because the taper is close
    if due:
        for w in range(num_weeks):
            wk_start = start_date + timedelta(days=7 * w)
            if (wk_start > fpd or (wk_start == fpd and not completed_by_date)) and phases[w].phase in ("general", "base", "build", "peak"):
                if protects_peak(phases[w], goal_distance):
                    peak_hold = True
                    continue
                deload_week = w
                break
    if deload_week is not None:
        peak_hold = False
    is_deload = deload_week is not None

    load = plan_load(
        baseline=current_weekly_mileage,
        peak=peak_weekly_mileage,
        experience=experience_level,
        goal_type=goal_type,
        num_weeks=num_weeks,
        target_weekly_mileage=target_weekly_mileage,
        assessment=assessment,
        deload_week=deload_week,
        reported_mileage=reported_mileage, completed_weeks=completed_weeks,
        developmental=developing, previous_block=previous_block, race_weeks=race_weeks,
    )
    if peak_hold:
        # The taper absorbs the accumulated load; until it starts, hold the training
        # level rather than add growth on top of a streak that would have earned a deload.
        hold_at = load.training_level or current_weekly_mileage
        load.weekly_budgets = [round(min(b, hold_at), 1) for b in load.weekly_budgets]
        if load.mode == 'build':
            load.mode = 'hold'
        load.reasons.append(f'Deload suppressed: the taper starts within {NO_DELOAD_BEFORE_TAPER_WEEKS} weeks and is the '
                            f'recovery. Holding {hold_at:g} mi/week until then instead of building.')
    # Volume that sessions are sized from (the baseline, or the starting load when
    # there's no usable history)
    sizing_mileage = max(current_weekly_mileage, load.weekly_budgets[0]) if load.weekly_budgets else current_weekly_mileage

    goal_pace_data = None
    if goal_type == "race" and goal_distance and target_time_seconds:
        goal_pace_data = goal_paces(goal_distance, target_time_seconds) or None

    current_paces = _build_current_paces(
        easy_pace_seconds, current_workout_paces,
        goal_pace_data=goal_pace_data,
        current_mileage=current_weekly_mileage,
    )

    # Goal-pace target for race-specific work, stepped from the paces workouts use
    current_paces["specific_pace"] = with_specific_pace(
        effective_paces(current_paces, progression_state), goal_distance)["specific_pace"]

    # Ultras use the marathon library for road-style sessions (threshold, long-run variety)
    lib_distance = "marathon" if is_ultra(goal_distance) else (goal_distance or "5k")
    workout_lib = get_workout_library(current_paces, lib_distance, sizing_mileage)

    include_workouts = _should_include_workouts(
        sizing_mileage, goal_type, experience_level
    )
    holding = assessment in {'hold', 'reduce', 'recovery'} or fatigue_recovery
    run_walk = [developmental.run_walk_stage(continuous_run_minutes, run_walk_weeks, w, holding) if developing else None
                for w in range(num_weeks)]
    if developing:
        include_workouts = developmental.ready_for_workout(completed_weeks or [], weekly_run_days or [],
                                                         sizing_mileage, evidence, assessment, fatigue_recovery)
    workouts_per_week = _workouts_per_week(sizing_mileage, experience_level)
    quality = select_quality_policy(goal_type, experience_level, days_per_week,
                                    completed_weeks or [], weekly_run_days or [],
                                    recent_long_run_miles, assessment, fatigue_recovery, quality_evidence)
    workouts_per_week = min(workouts_per_week, quality.sessions)
    if quality.stage == 'support':
        workouts_per_week = 2
    run_walk_ahead = 0  # block weeks so far with at least two run/walk sessions
    if run_walk[0] is not None:
        include_workouts = False  # earn continuous running before any workout
    if developing:
        workouts_per_week = 1
        from app.core.quality_policy import QualityPolicy
        quality = QualityPolicy('single', 'One controlled effort workout each week, with easy bookends. Earn longer work through completed durations and recovery; keep the other runs easy.', quality.criteria, quality.evidence)
    adding_hard_session = quality.stage == 'dual' and (quality_evidence or {}).get('dual_weeks',0) < 2
    if adding_hard_session and (quality_evidence or {}).get('dual_weeks',0) < 2:
        # Change intensity distribution first; don't increase weekly volume too.
        # Demonstrated volume is the training level (a deload week drags the 4-week
        # average under it), but never more than was actually run in the last two weeks.
        recent = (completed_weeks or [current_weekly_mileage])[-2:]
        anchor = min(max(current_weekly_mileage, load.training_level or 0), max(recent))
        load.weekly_budgets = [min(b,anchor) for b in load.weekly_budgets]
        load.mode = 'hold'
        load.reasons.append('Introducing a second substantial session: hold demonstrated weekly volume while testing recovery.')
    if goal_type == 'mileage' or adding_hard_session:
        allow_preview = False

    rest_indices = sorted(set([DAY_NAMES.index(d) for d in rest_days if d in DAY_NAMES]+[DAY_NAMES.index(d) for d,v in (day_time_budgets or {}).items() if d in DAY_NAMES and v==0]))
    long_run_idx = DAY_NAMES.index(long_run_day)

    # Same rounded range everywhere (easy days, long runs, pacing guide)
    easy_range = pace_range(current_paces["easy_pace_low"], current_paces["easy_pace_high"])

    def restructure_long(miles: float) -> dict:
        if developing:
            return {'title': 'Easy Long Run', 'description': f'{miles:g}mi easy at {easy_range}/mi. Conversational the entire time.',
                    'purpose': 'Build aerobic endurance and durable time on feet.', 'prescription': None}
        lr = _long_run_structure(miles, "easy", current_paces)
        # A shortened long run is a plain easy run: drop any structured (MP/steady) prescription.
        return {"title": lr["title"], "description": lr["description"], "purpose": lr["purpose"], "prescription": None}

    easy_desc_all = (
        "Conversational effort the entire time. Should be able to hold a full conversation — "
        f"if you can't, slow down. ({easy_range}/mi or slower)"
    )

    prorated: dict[int, float] = {}  # week index → its midweek-prorated total

    def compose_week(wk, wk_target, long_cap, wk_workouts, wk_is_deload, returning):
        """Build one week at a weekly target: sessions, already-run days, then fit to the budget."""
        wk_num, wk_start, wk_phase = wk + 1, start_date + timedelta(days=wk * 7), phases[wk]
        notes = []
        week_days = _build_week(
            week_num=wk_num, start_date=wk_start, block_start=start_date,
            target_mileage=wk_target, days_per_week=days_per_week,
            rest_indices=rest_indices, long_run_idx=long_run_idx,
            easy_pace=easy_pace_seconds, current_paces=current_paces,
            workout_lib=workout_lib, include_workouts=include_workouts and wk_workouts > 0,
            num_workouts=wk_workouts,
            goal_distance=goal_distance,
            current_mileage=current_weekly_mileage, is_deload=wk_is_deload,
            progression_state=progression_state,
            phase=wk_phase, terrain=terrain, target_time_seconds=target_time_seconds,
            max_workout_miles=max(5.0, wk_target * 0.30),
            allow_preview=allow_preview, program_distance=goal_distance or goal_type,
            light_second=quality.light_second and wk_workouts > 1,
            workout_format=workout_format,
            quality_stage='single' if returning and quality.stage == 'dual' else quality.stage,
            experience=experience_level,
            developing=developing,
            first_prescribe_date=fpd,
            long_cap=long_cap,
        )

        week_days = [d for d in week_days if d['date'] <= end_date.isoformat()]
        # Days before the plan starts prescribing already happened: they carry the
        # real miles run (0 if none), never a hypothetical prescription.
        for d in week_days:
            if first_prescribe_date and date.fromisoformat(d["date"]) < first_prescribe_date:
                actual = round(completed_by_date.get(d["date"], 0.0), 2)
                d.update({
                    "prescribed": False,
                    "type": "easy" if actual > 0 else "rest",
                    # Never present a hypothetical prescription for a day that already happened
                    "title": "Run (before this plan)" if actual > 0 else "No run logged",
                    "description": None, "purpose": None,
                    "distance_miles": actual,
                    "warmup": None, "cooldown": None,
                })
                d.pop("b2b", None)
            else:
                d["prescribed"] = True

        locked_miles = sum(d['distance_miles'] for d in week_days if not d.get('prescribed', True))
        run_weekdays = [i for i in range(7) if i not in rest_indices]
        open_weekdays = [i for i in run_weekdays if wk_start + timedelta(days=i) >= fpd]
        if (run_weekdays and 0 < len(open_weekdays) < len(run_weekdays) and wk_phase.phase != 'race_week'
                and locked_miles + wk_target * len(open_weekdays) / len(run_weekdays) < wk_target * .9):
            # A midweek start prescribes the rest of the week at its normal size; it never
            # crams the whole week's target into the days that are left.
            wk_target = round(locked_miles + wk_target * len(open_weekdays) / len(run_weekdays), 1)
            prorated[wk] = wk_target
            notes.append("This week started midweek: the remaining days are planned at their normal size, "
                         "not squeezed to reach the full weekly total.")
        if not any(d.get('prescribed', True) for d in week_days):
            wk_target = locked_miles
        elif locked_miles > wk_target:
            notes.append("This week's completed mileage already exceeds the new target; remaining training is recovery/rest, not mileage to repay.")
            wk_target = locked_miles
        load.weekly_budgets[wk] = wk_target
        if not any(d["type"] == "race" for d in week_days):
            if developing:
                notes.extend(developmental.fit_week(week_days, wk_target, easy_desc_all, restructure_long, long_cap))
            else:
                notes.extend(fit_week_to_budget(week_days, wk_target, easy_desc_all, restructure_long))
        return week_days, wk_target, notes

    # Build all weeks
    weeks = []
    longest_long = recent_long_run_miles  # the long-run step grows from the longest recent run
    recent_race_pace = recent_race_pace_miles  # race-pace long-run work already absorbed
    fit_notes: list[str] = []
    for wk in range(num_weeks):
        wk_num = wk + 1
        wk_start = start_date + timedelta(days=wk * 7)
        wk_target = load.weekly_budgets[wk]
        wk_phase = phases[wk]
        wk_is_deload = wk == deload_week
        if developing and wk > 0 and phases[wk - 1].phase == 'recovery':
            # A future post-race recovery week is not evidence for compounding
            # another growth step. First return to the demonstrated level.
            wk_target = min(wk_target, load.training_level or current_weekly_mileage)
        if developing and include_workouts and load.mode == 'build' and wk == 0:
            level = development_state.get('current_level', 1)
            # A newly earned dose/shape is the week's progression. Mileage can
            # grow next week while the same workout is repeated.
            if development_state.get('last_completed_level') != level:
                wk_target = min(wk_target, load.planning_anchor or current_weekly_mileage)
                load.weekly_budgets = [round(min(b, wk_target * (1 + load.rate) ** min(i, 2)), 1)
                                       for i, b in enumerate(load.weekly_budgets)]
                load.reasons.append('New controlled-workout step: repeat demonstrated volume in week one, then build easy mileage while repeating the dose.')
        if run_walk[0] is not None:
            # Run/walk sessions are prescribed by time. Size the week so every chosen run
            # day survives (a tiny mileage baseline must not turn the week into all rest);
            # each run day is rewritten as a ~25-30 minute run/walk below.
            wk_target = max(wk_target, days_per_week * 2.0)
        if wk_phase.volume_multiplier is not None:
            # Taper / race week / post-race recovery: scale from current volume, no ramp
            wk_target = round(max(current_weekly_mileage, 10) * wk_phase.volume_multiplier, 1)
            if developing:
                wk_target = round((load.training_level or current_weekly_mileage) * wk_phase.volume_multiplier, 1)

        covered_days = max(0, min(7, (end_date - wk_start).days + 1))
        if covered_days < 7:
            wk_target = round(wk_target * covered_days / 7, 1)
        load.weekly_budgets[wk] = wk_target

        wk_workouts = min(workouts_per_week, 1) if wk_is_deload else workouts_per_week
        # First week back from a down week: volume returns, but with one quality session
        # (a demanding long run counts as one); the second returns the week after.
        returning = wk == deload_week + 1 if deload_week is not None else (wk == 0 and load.after_down_week)
        if returning:
            wk_workouts = min(wk_workouts, 1)
        if fatigue_recovery and wk_start <= fpd <= wk_start + timedelta(days=6):
            wk_workouts = 0
        if wk_phase.max_workouts is not None:
            wk_workouts = min(wk_workouts, wk_phase.max_workouts)
        if wk_phase.phase == "base" and not experienced(experience_level):
            wk_workouts = min(wk_workouts, 1)

        long_cap = None
        if developing and goal_distance in developmental.LONG_RUN_SHARE:
            long_cap = developmental.long_run_cap(wk_target, longest_long, easy_pace_seconds)
        if goal_distance in ROAD_LONG_RUN_CAP:
            # A share of a big week is not a 5K/10K/half long run: cap miles and time.
            cap_miles, cap_minutes = ROAD_LONG_RUN_CAP[goal_distance]
            road_cap = _round_half(min(cap_miles, cap_minutes * 60 / easy_pace_seconds))
            long_cap = min(long_cap, road_cap) if long_cap is not None else road_cap
        if (goal_distance in {'half', 'marathon'} and longest_long > 0
                and weeks_before_taper(wk_phase, goal_distance) == 1):
            # The longest run comes three weeks out; the last pre-taper week repeats, never extends, it.
            long_cap = min(long_cap or longest_long, longest_long)
        week_days, wk_target, notes = compose_week(wk, wk_target, long_cap, wk_workouts, wk_is_deload, returning)
        race_pace = max([race_pace_miles(d) for d in week_days if d['type'] == 'long_run'], default=0)
        # "Flat" is the week before: the previous plan week, or the last completed week.
        previous = weeks[-1]['budget_miles'] if weeks else (completed_weeks or [0])[-1]
        hold_at = max(previous, load.training_level or current_weekly_mileage)
        if (not developing and not is_ultra(goal_distance) and wk_phase.phase in ('build', 'peak')
                and race_pace_step(race_pace, recent_race_pace)
                and any(d.get('prescribed', True) for d in week_days) and wk_target > hold_at + 0.5):
            # One lever at a time: the new race-pace long run is this week's progression,
            # so volume repeats the week before it and grows again the week after.
            held = round(hold_at, 1)
            week_days, wk_target, notes = compose_week(wk, held, long_cap, wk_workouts, wk_is_deload, returning)
            race_pace = max([race_pace_miles(d) for d in week_days if d['type'] == 'long_run'], default=0)
            load.reasons.append(f'Week {wk_num} adds {race_pace:g} mi at race pace in the long run: holding '
                                f'{held:g} mi/week that week, then building again.')
        if wk in prorated:
            # Later weeks grow from what this week actually prescribes (or the baseline),
            # not from the full week it would have been.
            ramp_from = max(prorated[wk], current_weekly_mileage, load.training_level or 0, load.planning_anchor or 0)
            for later in range(wk + 1, num_weeks):
                load.weekly_budgets[later] = min(load.weekly_budgets[later],
                                                 round(ramp_from * (1 + load.rate) ** (later - wk), 1))
        rest_notes = apply_post_race_rest(week_days, race_date, goal_distance)
        if rest_notes:
            notes.extend(rest_notes)
            wk_target = round(min(wk_target, sum(d['distance_miles'] for d in week_days)), 1)
            load.weekly_budgets[wk] = wk_target
        fit_notes.extend(notes)
        recent_race_pace = max(recent_race_pace, race_pace)
        longest_long = max([longest_long] + [d['distance_miles'] for d in week_days if d['type'] == 'long_run'])

        if run_walk[0] is not None:
            # Preview the next step only after a block week that actually had sessions:
            # a first week with nothing left to run must not skip step one.
            run_walk[wk] = developmental.run_walk_stage(continuous_run_minutes, run_walk_weeks,
                                                       run_walk_ahead, holding)
        if run_walk[wk] is not None:
            for d in week_days:
                if d.get('prescribed', True) and d['type'] in {'easy', 'long_run', 'recovery'} and d['distance_miles'] > 0:
                    developmental.run_walk_day(d, run_walk[wk], easy_pace_seconds, long=d['type'] == 'long_run')
            load.weekly_budgets[wk] = round(sum(d['distance_miles'] for d in week_days), 1)
            if sum(d.get('prescribed', True) and d['title'].startswith('Run/Walk') for d in week_days) >= 2:
                run_walk_ahead += 1

        weeks.append({
            "week_number": wk_num,
            "budget_miles": wk_target,  # intended load
            "target_mileage": round(sum(d["distance_miles"] for d in week_days), 1),  # scheduled
            "phase": wk_phase.to_dict(),
            "quality_sessions": sum(d['type']=='workout' and d.get('prescribed',True) for d in week_days),
            "days": week_days,
        })
    from app.core.time_budget import fit_availability
    availability_notes=fit_availability(weeks,day_time_budgets,easy_pace_seconds,developing=developing,prior_hard_dates=prior_hard_dates)
    if availability_notes:
        load.weekly_budgets=[w['target_mileage'] for w in weeks]
        if load.training_level is not None:load.training_level=min(load.training_level,max(load.weekly_budgets))

    # Whole-plan safety pass: hard-day separation across week boundaries and against
    # real hard runs just before the plan, then report anything still violated.
    enforce_no_back_to_back_hard([d for w in weeks for d in w["days"]], easy_desc_all, prior_hard_dates)
    for w in weeks:
        w["target_mileage"] = round(sum(d["distance_miles"] for d in w["days"]), 1)
        w["quality_sessions"] = sum(d["type"]=="workout" and d.get("prescribed",True) for d in w["days"])
    violations = validate_plan(weeks, rest_indices, prior_hard_dates)

    plan = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "block_number": block_number,
        "is_deload": is_deload,
        "weeks": weeks,
        "pacing_guide": _pacing_guide(easy_range, effective_paces(current_paces, progression_state)),
        "training_paces": effective_paces(current_paces, progression_state),
        "notes": list(load.reasons) + [quality.reason] + availability_notes,
        "quality_policy": quality.to_dict(),
        "phases": [w["phase"] for w in weeks],
        "load": load.to_dict() | {"deload_week": deload_week},
        "violations": violations,
    }
    if run_walk[0] is not None:
        plan['notes'].insert(0, 'Run/walk start: sessions are prescribed by time, not distance. The running share grows one '
                                'step per week you run; continuous 20-minute runs come before any workout.')
    if developing:
        # No introductory session prescribes threshold/VO2 pace. Keep guessed
        # fallback paces out of the athlete-facing guide for this program.
        plan['pacing_guide'] = {'easy': easy_range}
    for note in fit_notes:
        if note not in plan["notes"]:
            plan["notes"].append(note)

    for wp in phases:
        for note in wp.notes:
            if note not in plan["notes"]:
                plan["notes"].append(note)

    if developing and goal_type == 'race' and goal_distance in {'half', 'marathon'} and race_date:
        weeks_left = (race_date - fpd).days / 7
        from app.core.outlook import LONG_RUN_TARGETS
        long_target = LONG_RUN_TARGETS[goal_distance][0]
        if weeks_left <= 6 and recent_long_run_miles < long_target:
            remaining = max(0, round(weeks_left))
            plan['notes'].append(f'Endurance preparation gap: recent longest run is {recent_long_run_miles:g} mi with {remaining} week{"s" if remaining != 1 else ""} to the {goal_distance}. '
                                 f'Review a later race or a shorter event if a {long_target:g}-mile long run cannot be built and recovered from before taper. Do not cram missed endurance into the final weeks.')

    if goal_pace_data and not goal_pace_data.get("is_ultra"):
        plan["pacing_guide"]["goal_race_pace"] = format_pace(goal_pace_data["race_pace"])
        plan["notes"].append(
            f"Workouts are paced off CURRENT fitness, progressing toward goal. "
            f"Goal race pace ({format_pace(goal_pace_data['race_pace'])}/mi) is the target."
        )

    if is_deload:
        has_quality = any(d["type"] == "workout" for w in plan["weeks"] for d in w["days"])
        plan["notes"].append(
            "Deload week — reduced volume so your body can absorb the training. "
            + ("Keep 1 quality workout, stay sharp, but let the fatigue dissipate. " if has_quality
               else "Every run stays easy and conversational. ")
            + "You'll come back stronger next block."
        )

    if not include_workouts:
        plan["notes"].append(
            f"Building base mileage first. Currently at {current_weekly_mileage:.0f} mpw — "
            f"focus on easy miles and gradually increasing distance."
        )

    return plan


def _pacing_guide(easy_range: str, paces: dict) -> dict:
    """Same numbers the workouts print (see workout_ladders.get_workout_at_level)."""
    tempo = paces["tempo_pace"]
    return {
        "easy": easy_range,
        "steady": format_pace(paces["steady_pace"]),
        "tempo": format_pace(tempo),  # continuous tempo
        "threshold_reps": format_pace(paces.get("broken_threshold_pace", tempo - 10)),  # broken threshold reps
        "intervals": f"{format_pace(paces['interval_pace_fast'])}-{format_pace(paces['interval_pace'])}",
    }


def _build_current_paces(
    easy_pace: float,
    workout_paces: dict | None,
    goal_pace_data: dict | None = None,
    current_mileage: float = 0,
) -> dict:
    """Conservative easy-pace defaults, overridden only by category evidence.

    Goal pace is retained separately for explicitly eligible race-specific work.
    Volume alone never moves threshold/interval training to a goal-time estimate.
    """
    # Base paces from easy pace
    base_threshold = easy_pace * 0.77

    # Mileage and an aspirational goal are not evidence of pace fitness.
    threshold = base_threshold
    ultra = bool(goal_pace_data and goal_pace_data.get("is_ultra"))

    # Workouts are written from tempo_pace: continuous tempo at tempo_pace, broken
    # threshold reps ~10s/mi faster (workout_ladders tp_fast). `threshold` is only the
    # base it's derived from, so the pacing guide shows tempo, not this number.
    tempo = threshold * 0.96
    steady = threshold + 25           # ~25sec slower than threshold, near MP range

    interval = easy_pace * 0.67

    # Round all paces to nearest 5 seconds
    threshold = _round_pace(threshold)
    tempo = _round_pace(tempo)
    interval = _round_pace(interval)
    interval_fast = _round_pace(interval - 10)  # feeling-good end of range
    steady = _round_pace(steady)

    # Goal race pace for MP workouts and long runs (None if no goal set)
    grp = _round_pace(goal_pace_data["race_pace"]) if goal_pace_data and goal_pace_data.get("race_pace") and not ultra else None

    if workout_paces:
        return {
            "race_pace": _round_pace(workout_paces.get("race_pace", workout_paces.get("interval_pace", interval))),
            "interval_pace": _round_pace(workout_paces.get("interval_pace", interval)),
            "interval_pace_fast": _round_pace(workout_paces.get("interval_pace", interval) - 10),
            "tempo_pace": _round_pace(workout_paces.get("tempo_pace", tempo)),
            "threshold_pace": _round_pace(workout_paces.get("threshold_pace", threshold)),
            "broken_threshold_pace": _round_pace(workout_paces.get("threshold_pace", tempo - 10)),
            "steady_pace": _round_pace(workout_paces.get("steady_pace", steady)),
            "easy_pace_low": _round_pace(easy_pace * 0.95),
            "easy_pace_high": _round_pace(easy_pace * 1.05),
            "long_run_pace": _round_pace(easy_pace),
            "strides_pace": _round_pace(workout_paces.get("strides_pace", easy_pace * 0.55)),
            "goal_race_pace": grp,
            # Calibrated goal-pace rep evidence per distance (pace_calibrator)
            **{k: v for k, v in workout_paces.items() if k.startswith("race_pace_")},
        }

    return {
        "race_pace": interval,
        "interval_pace": interval,
        "interval_pace_fast": interval_fast,
        "tempo_pace": tempo,
        "threshold_pace": threshold,
        "broken_threshold_pace": tempo - 10,
        "steady_pace": steady,
        "easy_pace_low": _round_pace(easy_pace * 0.95),
        "easy_pace_high": _round_pace(easy_pace * 1.05),
        "long_run_pace": _round_pace(easy_pace),
        "strides_pace": _round_pace(easy_pace * 0.55),
        "goal_race_pace": grp,
    }


def _is_deload_block(block_number: int, experience: str) -> bool:
    """Determine if this block should be a deload.

    First deload comes after the initial adaptation phase:
      Advanced: first deload at block 4, then every 3rd block after (7, 10, 13...)
      Intermediate: first deload at block 3, then every 2nd block after (5, 7, 9...)
      Beginner: first deload at block 3, then every 2nd block after (5, 7, 9...)

    Push through initial soreness, then deload once in a groove.
    """
    if block_number <= 2:
        return False

    if experienced(experience):
        # First deload at block 4, then every 3rd block after
        if block_number == 4:
            return True
        return block_number > 4 and (block_number - 4) % 3 == 0
    else:
        # First deload at block 3, then every 2nd block after
        if block_number == 3:
            return True
        return block_number > 3 and (block_number - 3) % 2 == 0


def _should_include_workouts(current_mileage: float, goal_type: str, experience: str) -> bool:
    if goal_type == "comeback":
        return False
    if experience == "beginner" and current_mileage < 15:
        return False
    if current_mileage < 20:
        return False
    return True


def _workouts_per_week(current_mileage: float, experience: str) -> int:
    if current_mileage < 20:
        return 1
    return 2


# ── Long run structure generator ────────────────────────────────

def _long_run_structure(total_miles: float, run_type: str, paces: dict) -> dict:
    """Generate specific mile breakdown for long runs.

    Returns title + description with exact mile splits, not vague percentages.
    """
    easy_range = pace_range(paces["easy_pace_low"], paces["easy_pace_high"])
    steady = format_pace(paces["steady_pace"])
    grp = paces.get("goal_race_pace")
    # Marathon-pace segments step toward goal MP from demonstrated pace (core/goal_pace.py).
    mp = paces.get("specific_pace") or grp
    if mp and grp and mp > grp:
        mp_label = f"MP step ({format_pace(mp)}/mi, goal {format_pace(grp)}/mi)"
    else:
        mp_label = f"goal MP ({format_pace(mp)}/mi)" if mp else f"steady ({steady}/mi)"
    total = _round_half(total_miles)
    easy_ref = paces.get("long_run_pace") or paces["easy_pace_high"]

    if run_type == "easy":
        return {
            "title": "Easy Long Run",
            "description": f"{total}mi easy at {easy_range}/mi. Conversational the entire time.",
            "purpose": "Builds aerobic endurance, capillary density, and fat-burning efficiency.",
        }

    elif run_type == "steady_finish":
        # Steady portion: 2mi at 10-11mi, 3mi at 12-14mi, 4mi at 15+
        if total <= 11:
            hard = 2.0
        elif total <= 14:
            hard = 3.0
        else:
            hard = 4.0
        easy_mi = _round_half(total - hard)
        description = f"{easy_mi}mi easy at {easy_range}/mi, then {hard}mi at steady effort ({steady}/mi)."
        return {
            "title": "Steady Finish Long Run",
            "description": description,
            "purpose": "Teaches finishing strong on tired legs. Controlled — not a workout.",
            "prescription": long_run_prescription([("easy", easy_mi), ("steady", hard, paces["steady_pace"])], description, easy_ref),
        }

    elif run_type == "mp_finish":
        # MP finish: 3mi at 12-14mi, 4mi at 15-16mi, 5mi at 17+
        if total <= 14:
            hard = 3.0
        elif total <= 16:
            hard = 4.0
        else:
            hard = 5.0
        easy_mi = _round_half(total - hard)
        description = f"{easy_mi}mi easy at {easy_range}/mi, then {hard}mi at {mp_label}. Controlled — don't force it."
        return {
            "title": "MP Finish Long Run",
            "description": description,
            "purpose": "Marathon-specific endurance. Running race effort on tired legs — the key long run workout.",
            "prescription": long_run_prescription([("easy", easy_mi), ("race_pace" if mp else "steady", hard, mp or paces["steady_pace"])], description, easy_ref),
        }

    elif run_type == "sandwich":
        # Easy / steady / easy — roughly equal thirds
        third = _round_half(total / 3)
        middle = _round_half(total - third * 2)
        description = f"{third}mi easy at {easy_range}/mi, {middle}mi at steady ({steady}/mi), {third}mi easy to finish."
        return {
            "title": "Steady Sandwich Long Run",
            "description": description,
            "purpose": "Sustained steady effort sandwiched between easy. Builds pacing discipline over distance.",
            "prescription": long_run_prescription([("easy", third), ("steady", middle, paces["steady_pace"]), ("easy", third)], description, easy_ref),
        }

    elif run_type == "mp_block":
        # Sets of 3mi at MP with 1mi float between
        sets = max(int(total // 4), 2)
        mp_total = sets * 3
        float_total = sets - 1
        wu = _round_half((total - mp_total - float_total) / 2)
        cd = _round_half(total - mp_total - float_total - wu)
        description = f"{wu}mi easy, then {sets}x3mi at {mp_label} with 1mi float ({easy_range}/mi) between sets, {cd}mi easy."
        blocks = [part for _ in range(sets) for part in (("race_pace" if mp else "steady", 3, mp or paces["steady_pace"]), ("easy", 1))][:-1]
        return {
            "title": "MP Block Long Run",
            "description": description,
            "purpose": "Accumulates massive marathon pace volume. Peak long run workout.",
            "prescription": long_run_prescription([("easy", wu)] + blocks + [("easy", cd)], description, easy_ref),
        }

    # Fallback
    return {
        "title": "Easy Long Run",
        "description": f"{total}mi easy at {easy_range}/mi.",
        "purpose": "Aerobic endurance.",
    }


# ── Week builder ────────────────────────────────────────────────

def _build_week(
    week_num: int, start_date: date, block_start: date,
    target_mileage: float, days_per_week: int, rest_indices: list[int],
    long_run_idx: int, easy_pace: float, current_paces: dict,
    workout_lib: dict, include_workouts: bool, num_workouts: int,
    goal_distance: str | None, current_mileage: float,
    is_deload: bool = False,
    progression_state: dict | None = None,
    phase: WeekPhase | None = None,
    terrain: str | None = None,
    target_time_seconds: float | None = None,
    max_workout_miles: float | None = None,
    allow_preview: bool = True,
    program_distance: str | None = None,
    light_second: bool = False,
    workout_format: str = 'distance',
    quality_stage: str = 'single',
    experience: str = 'intermediate',
    developing: bool = False,
    first_prescribe_date: date | None = None,
    long_cap: float | None = None,
) -> list[dict]:
    phase = phase or WeekPhase(phase="general")
    easy_range = pace_range(current_paces["easy_pace_low"], current_paces["easy_pace_high"])
    easy_desc = f"Conversational effort the entire time. Should be able to hold a full conversation — if you can't, slow down. ({easy_range}/mi or slower)"

    if phase.race_date and goal_distance:
        days = build_race_week(
            start_date, phase, goal_distance, target_time_seconds,
            target_mileage, rest_indices, current_paces,
            developing=developing, development_state=(progression_state or {}).get('development'),
            days_per_week=days_per_week, include_workouts=include_workouts,
        )
        return enforce_no_back_to_back_hard(days, easy_desc)

    ultra = is_ultra(goal_distance)
    trail = terrain in ("trail", "mountain")
    run_days = [i for i in range(7) if i not in rest_indices]

    while len(run_days) > days_per_week:
        protected = {long_run_idx, 1, 3}
        for candidate in reversed(run_days):
            if candidate not in protected:
                run_days.remove(candidate)
                break
        else:
            for candidate in reversed(run_days):
                if candidate != long_run_idx:
                    run_days.remove(candidate)
                    break

    day_assignments = {}
    for i in range(7):
        if i not in run_days:
            day_assignments[i] = "rest"
        elif i == long_run_idx:
            day_assignments[i] = "long"
        else:
            day_assignments[i] = "easy"

    # Ultra back-to-back weekend: reserve the day next to the long run before placing
    # workouts, so no quality session lands beside the pair (prefer the day after)
    b2b_idx = None
    if ultra and phase.back_to_back:
        for cand in (long_run_idx + 1, long_run_idx - 1):
            if (0 <= cand < 7 and day_assignments.get(cand) == "easy"
                    and abs((cand - start_date.weekday()) % 7 - (long_run_idx - start_date.weekday()) % 7) == 1):
                b2b_idx = cand
                break
        if b2b_idx is not None:
            day_assignments[b2b_idx] = "b2b"
    hard_block = {i for i in (long_run_idx, b2b_idx) if i is not None}
    if b2b_idx is not None:
        num_workouts = min(num_workouts,1)  # paired ultra long runs already add substantial stress

    long_wo = _pick_long_run(workout_lib, include_workouts, week_num, current_mileage, block_start)
    # Race-pace long runs are the marathon's key session: any established quality stage
    # (two substantial sessions, or one plus light support) keeps them in build and peak.
    structured_stages = {'dual', 'support'} if goal_distance == 'marathon' else {'dual'}
    if not (goal_distance in {'half','marathon'} and phase.phase in {'build','peak'} and quality_stage in structured_stages):
        long_wo = None
    elif goal_distance == 'marathon' and phase.phase == 'peak':
        before = weeks_before_taper(phase, goal_distance)
        if before == 1:
            # The final pre-taper long run stays aerobic: the biggest marathon-pace
            # session belongs three weeks out so it is absorbed before race day.
            long_wo = None
        elif before == 2 and include_workouts:
            long_wo = _biggest_mp_long_run(workout_lib, current_mileage) or long_wo
    if long_wo and (long_wo.get('run_type') not in {None,'easy'} or long_wo.get('structure')):
        # A demanding long run spends one of the substantial-stimulus slots.
        num_workouts = min(num_workouts,1)

    # Quality budget (80/20): with few run days, hard days would dominate the week.
    # 5+ run days allow two workouts, 4 allow one, 3 or fewer allow none (the long
    # run is the week's quality).
    num_workouts = min(num_workouts, max(0, len(run_days) - (2 if developing else 3)))

    # Single-quality-session weeks (base, taper) use threshold for longer races,
    # race-specific intervals for 5K/10K
    single_threshold = (num_workouts == 1 or light_second or (quality_stage=='dual' and goal_distance not in {'5k','10k'})) and goal_distance not in ("5k", "10k")

    workout1 = None
    workout2 = None
    if include_workouts:
        preferred_workout_days = [1, 3] + [i for i in range(7) if i not in (1, 3)]  # prefer Tue/Thu; honor availability
        placed = 0
        for wd in preferred_workout_days:
            if developing and first_prescribe_date and start_date + timedelta(days=(wd-start_date.weekday()) % 7) < first_prescribe_date:
                continue
            if placed >= num_workouts:
                break
            if any(abs(wd - h) == 1 for h in hard_block):
                continue  # never right next to the long run / back-to-back pair
            if wd in run_days and day_assignments.get(wd) == "easy":
                placed += 1
                if developing:
                    from app.core.workout_ladders import program_key
                    level = (progression_state or {}).get('development', {}).get('current_level', 1)
                    workout1 = developmental.workout(level, easy_pace, target_mileage,
                        program=program_key(program_distance or goal_distance), phase=phase.phase,
                        reduced=is_deload or phase.phase in {'taper', 'recovery'})
                    if workout1:
                        day_assignments[wd] = 'workout_speed'
                    else:
                        placed -= 1
                        break
                elif placed == 1 and single_threshold:
                    day_assignments[wd] = "workout_threshold"
                    workout2 = _pick_workout_progressive(
                        workout_lib, "threshold", week_num, block_start,
                        current_paces, program_distance or goal_distance or "general",
                        is_deload, progression_state,
                        max_miles=max_workout_miles, allow_preview=allow_preview,
                        current_mileage=current_mileage, phase_name=phase.phase,
                    )
                elif placed == 1 and ultra and trail and phase.phase in ("base", "build", "peak"):
                    # Trail/mountain ultras: hills replace track intervals early in the week
                    day_assignments[wd] = "workout_speed"
                    workout1 = ultra_vert_session(phase.phase, goal_distance, terrain, current_paces, experience,
                                                  current_mileage, start_date, is_deload) or hill_session(phase.phase)
                elif placed == 1:
                    # Intervals (hard speed work) early in the week
                    day_assignments[wd] = "workout_speed"
                    workout1 = _pick_workout_progressive(
                        workout_lib, "intervals", week_num, block_start,
                        current_paces, program_distance or goal_distance or "general",
                        is_deload, progression_state,
                        max_miles=max_workout_miles, allow_preview=allow_preview,
                        current_mileage=current_mileage, phase_name=phase.phase,
                    )
                elif quality_stage == 'dual' and ultra and trail and phase.phase in {'base','build','peak'}:
                    day_assignments[wd] = "workout_speed"
                    workout1 = ultra_vert_session(phase.phase, goal_distance, terrain, current_paces, experience,
                                                  current_mileage, start_date, is_deload) or hill_session(phase.phase)
                elif quality_stage == 'dual' and goal_distance not in {'5k','10k'}:
                    day_assignments[wd] = "workout_speed"
                    from app.core.quality_policy import secondary_quality
                    workout1 = secondary_quality(effective_paces(current_paces, progression_state),
                                                 program_distance or 'mileage', phase.phase,
                                                 week_num, current_mileage, experience=experience,
                                                 deload=is_deload)
                elif light_second:
                    support = light_speed_support(current_paces, workout_format, week_start=start_date, terrain=terrain)
                    # Legacy slots are positional; preserve a short-race primary
                    # interval session already occupying workout1.
                    if workout1 is not None:
                        day_assignments[wd] = "workout_threshold"
                        workout2 = support
                    else:
                        day_assignments[wd] = "workout_speed"
                        workout1 = support
                else:
                    # Threshold later in the week
                    day_assignments[wd] = "workout_threshold"
                    workout2 = _pick_workout_progressive(
                        workout_lib, "threshold", week_num, block_start,
                        current_paces, program_distance or goal_distance or "general",
                        is_deload, progression_state,
                        max_miles=max_workout_miles, allow_preview=allow_preview,
                        current_mileage=current_mileage, phase_name=phase.phase,
                    )

                hard_block.add(wd)

    workout1 = format_bookends(workout1, current_paces, workout_format)
    workout2 = format_bookends(workout2, current_paces, workout_format)
    wo1_miles = _round_half(workout1["total_miles"]) if workout1 and workout1.get("total_miles") else 0
    wo2_miles = _round_half(workout2["total_miles"]) if workout2 and workout2.get("total_miles") else 0

    mileage_dist = _distribute_mileage(
        target_mileage, day_assignments, goal_distance,
        wo1_miles=wo1_miles, wo2_miles=wo2_miles,
        developing=developing, long_cap=long_cap,
    )

    strides_placed = False
    days = []

    for offset in range(7):
        day_date = start_date + timedelta(days=offset)
        i = day_date.weekday()
        assignment = day_assignments[i]
        day_name = DAY_NAMES[i]

        if assignment == "rest":
            days.append(_rest_day(day_date, day_name))

        elif assignment == "b2b":
            days.append(None)  # filled once the main long run exists (it may come later in the week)

        elif assignment == "long" and ultra:
            days.append(ultra_long_run(day_date, goal_distance, target_mileage, phase, current_paces, terrain))

        elif assignment == "long":
            distance = mileage_dist.get('long', target_mileage * .28) if developing else _round_half(mileage_dist.get("long", target_mileage * 0.28))

            if long_wo and long_wo.get("structure") and long_wo.get("total_miles", distance) <= distance * 1.15:
                # Peak fixed-structure long runs — use as-is (only when they fit this week)
                day = {
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": long_wo["name"],
                    "description": long_wo["structure"],
                    "purpose": long_wo["purpose"],
                    "distance_miles": long_wo.get("total_miles", distance),
                    "warmup": None, "cooldown": None,
                }
                if long_wo.get("parts"):
                    # The written structure as numbers, so the marathon-pace work can be verified.
                    target = {"mp": ("race_pace", current_paces.get("goal_race_pace") or current_paces["steady_pace"]),
                              "steady": ("steady", current_paces["steady_pace"])}
                    day["prescription"] = long_run_prescription(
                        [("easy", miles) if kind == "easy" else (target[kind][0], miles, target[kind][1])
                         for kind, miles in long_wo["parts"]], long_wo["structure"],
                        current_paces.get("long_run_pace") or current_paces["easy_pace_high"])
                days.append(day)
            elif long_wo and long_wo.get("run_type"):
                lr = _long_run_structure(distance, long_wo["run_type"], current_paces)
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": lr["title"],
                    "description": lr["description"],
                    "purpose": lr["purpose"],
                    "distance_miles": distance,
                    "warmup": None, "cooldown": None,
                    **({"prescription": lr["prescription"]} if lr.get("prescription") else {}),
                })
            else:
                lr = _long_run_structure(distance, "easy", current_paces)
                days.append({
                    "date": day_date.isoformat(), "day": day_name,
                    "type": "long_run",
                    "title": lr["title"],
                    "description": lr["description"],
                    "purpose": lr["purpose"],
                    "distance_miles": distance,
                    "warmup": None, "cooldown": None,
                })

        elif assignment == "workout_speed":
            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "workout",
                "title": workout1["name"],
                "description": workout1["structure"],
                "purpose": workout1["purpose"],
                "distance_miles": wo1_miles,
                "prescription": workout1.get("prescription"),
                "warmup": workout1.get("warmup", "1.5mi easy"),
                "cooldown": workout1.get("cooldown", "1.5mi easy"),
            })

        elif assignment == "workout_threshold":
            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "workout",
                "title": workout2["name"],
                "description": workout2["structure"],
                "purpose": workout2["purpose"],
                "distance_miles": wo2_miles,
                "prescription": workout2.get("prescription"),
                "warmup": workout2.get("warmup", "1.5mi easy"),
                "cooldown": workout2.get("cooldown", "1.5mi easy"),
            })

        else:  # easy
            distance = _round_half(mileage_dist.get(f"easy_{i}", target_mileage * 0.12))
            title = "Easy Run"
            desc = easy_desc
            purpose = "Aerobic base building and recovery between hard efforts."

            if not strides_placed and include_workouts:
                strides_placed = True
                title = "Easy Run + Strides"
                sp = format_pace(current_paces["strides_pace"])
                desc = f"Conversational effort the whole run — easy means easy. After the run: 4-6x20sec strides at {sp}/mi with full recovery walk between. ({easy_range}/mi or slower)"
                purpose = "Aerobic base + maintain leg speed and neuromuscular coordination."

            days.append({
                "date": day_date.isoformat(), "day": day_name,
                "type": "easy", "title": title,
                "description": desc, "purpose": purpose,
                "distance_miles": distance,
                "warmup": None, "cooldown": None,
            })

    if b2b_idx is not None:
        main_offset = (long_run_idx - start_date.weekday()) % 7
        second_offset = (b2b_idx - start_date.weekday()) % 7
        main = days[main_offset]
        days[second_offset] = back_to_back_day(
            start_date + timedelta(days=second_offset), main, current_paces, terrain, before_main=second_offset < main_offset,
        )
        # Explicitly mark the planned pair: the only hard-after-hard the validator allows
        main["b2b"] = True
        days[second_offset]["b2b"] = True

    # Easy-day sizing happens in generate_plan via fit_week_to_budget, which accounts
    # for every session actually placed (ultra long runs are sized by time).
    return enforce_no_back_to_back_hard(days, easy_desc)


def _rest_day(day_date: date, day_name: str) -> dict:
    return {
        "date": day_date.isoformat(), "day": day_name,
        "type": "rest", "title": "Rest Day",
        "description": "Full rest. Recovery is when your body adapts and gets stronger.",
        "purpose": "Physical and mental recovery.",
        "distance_miles": 0, "warmup": None, "cooldown": None,
    }


def _distribute_mileage(
    target: float, assignments: dict, goal_distance: str | None,
    wo1_miles: float = 0, wo2_miles: float = 0,
    developing: bool = False,
    long_cap: float | None = None,
) -> dict:
    if goal_distance in ("marathon", "half"):
        long_pct = developmental.LONG_RUN_SHARE[goal_distance] if developing else 0.30
    else:
        long_pct = 0.28

    distribution = {}

    wo_keys = [k for k, v in assignments.items() if v.startswith("workout")]
    wo_totals = [wo1_miles, wo2_miles]
    total_workout_miles = 0
    for idx, k in enumerate(wo_keys):
        wo_dist = wo_totals[idx] if idx < len(wo_totals) else 0
        distribution[f"workout{idx + 1}"] = wo_dist
        total_workout_miles += wo_dist

    distribution["long"] = round(target * long_pct, 1) if developing else _round_half(target * long_pct)
    if long_cap is not None:
        distribution["long"] = min(distribution["long"], long_cap)

    remaining = target - total_workout_miles - distribution["long"]
    easy_days = [k for k, v in assignments.items() if v == "easy"]

    if easy_days:
        per_easy = remaining / len(easy_days) if remaining > 0 else 3.0
        for d in easy_days:
            distribution[f"easy_{d}"] = max(per_easy, 3.0)

    return distribution


def effective_paces(current_paces: dict, progression_state: dict | None) -> dict:
    """Paces actually used in workouts: base paces with any ladder recalibration
    applied. The pacing guide uses this too, so the two can never disagree."""
    paces = dict(current_paces)
    for category, state in (progression_state or {}).items():
        pace = state.get("current_pace_sec")
        if not pace:
            continue
        if category == "intervals":
            paces["interval_pace"] = pace
            paces["interval_pace_fast"] = pace - 10
        elif category == "threshold":
            paces["tempo_pace"] = pace
            paces["broken_threshold_pace"] = pace - 10
    return paces


def _pick_workout_progressive(
    workout_lib: dict, category: str, week_num: int, block_start: date,
    current_paces: dict, goal_distance: str,
    is_deload: bool, progression_state: dict | None,
    max_miles: float | None = None,
    allow_preview: bool = True,
    current_mileage: float | None = None,
    phase_name: str | None = None,
) -> dict:
    """Pick a workout using the progression ladder if state exists,
    falling back to the old rotation system if not.

    max_miles caps the full session (warmup + work + cooldown) at what the week's
    budget can hold: a high ladder level on a low-mileage week steps down the ladder
    for this prescription (the athlete's stored level is unchanged).
    """
    if not progression_state or category not in progression_state:
        progression_state = {category: {"current_level": 1, "last_execution": "insufficient"}}

    state = progression_state[category]
    level = state.get("current_level", 1)

    paces = effective_paces(current_paces, progression_state)

    def at(lvl: int) -> dict:
        return get_workout_at_level(category, lvl, paces, goal_distance, phase_name or "general")

    if is_deload:
        return get_deload_workout(category, level, paces, goal_distance, phase_name or "general")

    # Week 2 previews the next level only when the athlete's last result allows it
    preview = (allow_preview and week_num % 2 == 0 and phase_name not in ("taper", "race_week", "recovery")
               and state.get("last_execution") not in ("hold", "regress", "insufficient"))
    wo = get_week2_variant(category, level, paces, goal_distance, phase_name or "general") if preview else at(level)
    if max_miles:
        lvl = level + (1 if preview else 0)
        while (wo.get("total_miles") or 0) > max_miles and lvl > 1:
            lvl -= 1
            wo = at(lvl)
    return wo


def _eligible(w: dict, current_mileage: float | None, goal_distance: str | None, phase_name: str | None) -> bool:
    """Library readiness metadata: min_mpw, and marathon-pace sessions only for a
    marathon goal at ≥ their mileage during build/peak."""
    if current_mileage is not None and current_mileage < w.get("min_mpw", 0):
        return False
    if w.get("requires_mp_readiness"):
        return goal_distance == "marathon" and phase_name in ("build", "peak")
    return True


def _pick_workout(workout_lib: dict, category: str, week_num: int,
                  start_date: date = None, deload: bool = False,
                  current_mileage: float | None = None, goal_distance: str | None = None,
                  phase_name: str | None = None) -> dict:
    """Pick a workout, rotating across blocks via start_date seed.

    Week 1 and week 2 within the same block always get different workouts.
    The block_seed shifts each 2-week block so workouts rotate over time.
    On deload: pick from the lighter workouts (lower total_miles).
    """
    options = [w for w in workout_lib.get(category, []) if _eligible(w, current_mileage, goal_distance, phase_name)]

    if not options:
        options = [w for w in (workout_lib.get("threshold", []) or workout_lib.get("tempo", []))
                   if _eligible(w, current_mileage, goal_distance, phase_name)]

    if not options:
        return {
            "name": "Tempo Run",
            "structure": "25min at threshold effort.",
            "purpose": "Builds lactate threshold.",
            "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
            "total_miles": 6.5,
        }

    if deload:
        # Pick from shorter workouts only — keep it under 9mi total
        light = [w for w in options if w.get("total_miles", 6) <= 8.5]
        if light:
            options = light
        else:
            sorted_opts = sorted(options, key=lambda w: w.get("total_miles", 6))
            options = sorted_opts[:2]

    if start_date:
        block_seed = start_date.toordinal() // 14  # seed per 2-week block
    else:
        block_seed = 0

    # Week 1 gets index N, week 2 gets index N+1 — always different
    idx = (block_seed + week_num - 1) % len(options)
    return options[idx]


def _biggest_mp_long_run(workout_lib: dict | None, current_mileage: float) -> dict | None:
    """The eligible long run with the most marathon-pace miles (fixed structures first)."""
    options = [o for o in (workout_lib or {}).get("long_run", []) if current_mileage >= o.get("min_mpw", 0)]
    fixed = [o for o in options if o.get("parts")]
    if fixed:
        return max(fixed, key=lambda o: (sum(m for kind, m in o["parts"] if kind == "mp"), o.get("total_miles", 0)))
    return next((o for o in options if o.get("run_type") == "mp_finish"), None)


def _pick_long_run(
    workout_lib: dict | None, include_workouts: bool,
    week_num: int, current_mileage: float,
    start_date: date = None,
) -> dict | None:
    """Pick long run type. Week 1 = easy, Week 2 = quality (rotated)."""
    if not workout_lib or not include_workouts:
        return None

    options = workout_lib.get("long_run", [])
    if not options:
        return None

    # Week 1 = always easy long run
    if week_num % 2 == 1:
        return options[0]

    # Week 2 = rotate through quality options (skip the easy one at index 0)
    quality = [o for o in options[1:] if current_mileage >= o.get("min_mpw", 0)]
    if not quality:
        return options[0]

    if start_date:
        block_seed = start_date.toordinal() // 7
    else:
        block_seed = 0
    idx = block_seed % len(quality)
    return quality[idx]
