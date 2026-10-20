"""Workout library — real workouts that real runners use.

Marathon-first design. Intervals favor 1K and mile reps for marathon training.
Long runs use run_type field — the plan engine generates specific mile breakdowns.
Workouts rotate via date-seeded picker in plan_engine.
"""

from app.core.pacing import format_pace, pace_range


def get_workout_library(paces: dict, distance: str, current_mileage: float = 0) -> dict:
    rp = paces["race_pace"]
    tp = paces.get("tempo_pace", rp * 1.08)
    ip = paces.get("interval_pace", rp * 0.95)
    ep_low = paces["easy_pace_low"]
    ep_high = paces["easy_pace_high"]
    sp = paces.get("strides_pace", rp * 0.85)
    thrp = paces.get("threshold_pace", tp)
    stp = paces.get("steady_pace", ep_low * 0.90)
    # MP workouts use the goal-pace step (demonstrated pace moving toward goal MP,
    # core/goal_pace.py), never a jump to goal pace; threshold if there is no goal
    grp = paces.get("specific_pace") or paces.get("goal_race_pace") or thrp
    grp_label = format_pace(grp)
    # Extended rep pace: slightly faster than threshold (~10sec), used for 1.5mi reps
    ext_rep = thrp - 10
    # Interval range: ip = baseline target, ipf = feeling-good/pushing pace
    ipf = paces.get("interval_pace_fast", ip - 10)
    ip_range = f"{format_pace(ipf)}-{format_pace(ip)}"

    easy_range = pace_range(ep_low, ep_high)

    workouts = {
        "threshold": [],
        "intervals": [],
        "tempo": [],
        "long_run": [],
        "easy": [],
        "recovery": [],
        "progression": [],
    }

    # === EASY ===
    workouts["easy"].extend([
        {"name": "Easy Run",
         "structure": f"Run at {easy_range}/mi. Truly easy — if in doubt, slow down.",
         "purpose": "Aerobic base building, recovery between hard efforts.",
         "warmup": None, "cooldown": None, "total_miles": None},
        {"name": "Easy Run + Strides",
         "structure": f"Run easy at {easy_range}/mi. Last 10 min: 4-6x20sec strides at {format_pace(sp)}/mi with full recovery between.",
         "purpose": "Maintain leg speed and neuromuscular coordination on easy days.",
         "warmup": None, "cooldown": None, "total_miles": None},
    ])

    # === RECOVERY ===
    workouts["recovery"].append({
        "name": "Recovery Run",
        "structure": f"2-4 miles at {format_pace(ep_high)}/mi or slower. No ego.",
        "purpose": "Blood flow for recovery without adding stress.",
        "warmup": None, "cooldown": None, "total_miles": 3.0,
    })

    # =================================================================
    # THRESHOLD — Marathon/Half
    # =================================================================
    if distance in ("marathon", "half"):
        workouts["threshold"].extend([
            # Distance reps
            {"name": "2x2mi Threshold",
             "structure": f"2x2mi at {format_pace(thrp)}/mi with 0.5mi easy jog rest.",
             "purpose": "Builds lactate threshold. Manageable volume for building fitness.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 7.5, "min_mpw": 0},
            {"name": "3x2mi Threshold",
             "structure": f"3x2mi at {format_pace(thrp)}/mi with 0.5mi easy jog rest.",
             "purpose": "The staple threshold workout. Critical for marathon performance.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 11.0, "min_mpw": 35},
            {"name": "2x3mi Threshold",
             "structure": f"2x3mi at {format_pace(thrp)}/mi with 1mi easy float between.",
             "purpose": "Longer reps build ability to hold threshold for extended periods.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 11.0, "min_mpw": 40},
            {"name": "4x2mi Threshold",
             "structure": f"4x2mi at {format_pace(thrp)}/mi with 0.5mi jog rest. Negative split.",
             "purpose": "Peak threshold volume. 8 miles at threshold — massive stimulus.",
             "warmup": "2mi easy", "cooldown": "1mi easy",
             "total_miles": 12.5, "min_mpw": 45},
            # Continuous MP pace runs — use goal race pace
            {"name": "MP Pace Run — 3mi",
             "structure": f"3mi continuous at goal MP ({grp_label}/mi). Controlled — can push if feeling good but don't force it.",
             "purpose": "Intro marathon pace work. Teaches the body to hold race rhythm.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 7.0, "min_mpw": 25},
            {"name": "MP Pace Run — 4mi",
             "structure": f"4mi continuous at goal MP ({grp_label}/mi). Controlled and steady — lock into rhythm.",
             "purpose": "Extended marathon pace work. Building toward longer sustained efforts.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 8.0, "min_mpw": 30},
            {"name": "MP Pace Run — 5mi",
             "structure": f"5mi continuous at goal MP ({grp_label}/mi). This is a hard workout — stay controlled.",
             "purpose": "Sustained marathon pace. Builds confidence holding rhythm.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 9.0, "min_mpw": 35},
            {"name": "MP Pace Run — 6mi",
             "structure": f"6mi continuous at goal MP ({grp_label}/mi). Mentally and physically demanding — stay disciplined.",
             "purpose": "Peak marathon pace session. Simulates a chunk of race day.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 10.0, "min_mpw": 40},
            # Combo
            {"name": "2x2mi Threshold + 2x10min Tempo",
             "structure": f"2x2mi at {format_pace(thrp)}/mi with 0.5mi jog, then 2x10min at {format_pace(tp)}/mi with 2min jog.",
             "purpose": "Threshold volume with tempo kicker. Faster work on tired legs.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 10.5, "min_mpw": 30},
        ])

    # =================================================================
    # THRESHOLD — Marathon only (peak workouts)
    # =================================================================
    if distance == "marathon":
        workouts["threshold"].append(
            {"name": "3x3mi at MP",
             "structure": f"3x3mi at goal MP ({grp_label}/mi) with 0.5mi jog rest. 9 miles at race pace — this is a hard day.",
             "purpose": "Peak marathon-specific volume. Only prescribe after athlete has proven they can hold MP for 4-5mi in workouts and long runs.",
             "warmup": "2mi easy", "cooldown": "1mi easy",
             "total_miles": 13.0, "min_mpw": 50, "requires_mp_readiness": True},
        )

    # =================================================================
    # THRESHOLD — 5K/10K
    # =================================================================
    if distance in ("5k", "10k"):
        workouts["threshold"].extend([
            {"name": "2x10min Hard",
             "structure": f"2x10min at {format_pace(tp)}/mi with 2min jog rest.",
             "purpose": "Intro threshold work. Builds lactate clearance.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 5.5, "min_mpw": 0},
            {"name": "3x10min Hard",
             "structure": f"3x10min at {format_pace(tp)}/mi with 2min jog rest.",
             "purpose": "Builds lactate threshold — key limiter for 5K and 10K.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 25},
            {"name": "25min Continuous Tempo",
             "structure": f"25min at {format_pace(tp)}/mi. One continuous effort.",
             "purpose": "Teaches your body to clear lactate at a sustained pace.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 30},
            {"name": "20-30-20 Sandwich",
             "structure": f"20min easy at {easy_range}/mi, 30min hard at {format_pace(tp)}/mi, 20min easy.",
             "purpose": "Sustained threshold with built-in warmup/cooldown.",
             "warmup": "Built into workout", "cooldown": "Built into workout",
             "total_miles": 8.0, "min_mpw": 35},
        ])

    # =================================================================
    # INTERVALS
    # Marathon/Half: 1K and mile reps FIRST (most important for MP work)
    # 5K/10K: 800s and 400s first
    # =================================================================
    if distance in ("marathon", "half"):
        workouts["intervals"].extend([
            # 1K and mile reps first — most valuable for marathon
            {"name": "5x1K",
             "structure": f"5x1K at {ip_range}/mi with 200m jog rest.",
             "purpose": "Kilometer repeats build speed endurance. Faster end if feeling good.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 25},
            {"name": "4x1mi",
             "structure": f"4x1mi at {ip_range}/mi with 3min jog rest.",
             "purpose": "Mile repeats build sustained speed. Controlled, not all-out.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 9.0, "min_mpw": 30},
            {"name": "5x1K + 2mi Threshold",
             "structure": f"5x1K at {ip_range}/mi with 400m jog, then 2mi continuous at {format_pace(thrp)}/mi.",
             "purpose": "VO2max stimulus with threshold finish. Running fast on tired legs.",
             "warmup": "2mi easy", "cooldown": "1mi easy",
             "total_miles": 10.0, "min_mpw": 35},
            {"name": "6x800m",
             "structure": f"6x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "Develops VO2max. Hard but controlled.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 25},
            {"name": "5x1mi",
             "structure": f"5x1mi at {ip_range}/mi with 3min jog rest. Negative split.",
             "purpose": "5 miles total at interval pace — serious speed endurance.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 10.0, "min_mpw": 40},
            {"name": "4x1.5mi",
             "structure": f"4x1.5mi at {format_pace(ext_rep)}/mi with 3min jog rest. Think of this as an easier threshold day.",
             "purpose": "Extended reps at near-threshold effort — marathon-specific endurance.",
             "warmup": "2mi easy", "cooldown": "2mi easy",
             "total_miles": 10.5, "min_mpw": 40},
            {"name": "8x800m",
             "structure": f"8x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "High-volume VO2max. Extra reps build endurance at speed.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 7.5, "min_mpw": 35},
            {"name": "4x800m",
             "structure": f"4x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "Intro VO2max — short enough to maintain form.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 5.0, "min_mpw": 0},
            {"name": "6x400m Fast",
             "structure": f"6x400m at {format_pace(sp)}/mi with 200m jog rest.",
             "purpose": "Speed maintenance. Keeps fast-twitch fibers sharp.",
             "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy",
             "total_miles": 5.0, "min_mpw": 20},
        ])
    else:
        # 5K/10K — 800s and 400s more prominent
        workouts["intervals"].extend([
            {"name": "4x800m",
             "structure": f"4x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "Intro VO2max work.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 5.0, "min_mpw": 0},
            {"name": "6x800m",
             "structure": f"6x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "Develops VO2max. Hard but controlled.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 25},
            {"name": "6x400m Fast",
             "structure": f"6x400m at {format_pace(sp)}/mi with 200m jog rest.",
             "purpose": "Pure speed development. Improves running economy.",
             "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy",
             "total_miles": 5.0, "min_mpw": 20},
            {"name": "5x1K",
             "structure": f"5x1K at {ip_range}/mi with 200m jog rest.",
             "purpose": "Kilometer repeats. Faster end if feeling good.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 6.5, "min_mpw": 25},
            {"name": "4x1mi",
             "structure": f"4x1mi at {ip_range}/mi with 3min jog rest.",
             "purpose": "Sustained race pace practice.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 8.0, "min_mpw": 30},
            {"name": "8x400m Fast",
             "structure": f"8x400m at {format_pace(sp)}/mi with 200m jog rest.",
             "purpose": "Extended speed session. Top-end speed and economy.",
             "warmup": "1.5mi easy + 4 strides", "cooldown": "1.5mi easy",
             "total_miles": 5.5, "min_mpw": 25},
            {"name": "8x800m",
             "structure": f"8x800m at {ip_range}/mi with 90sec jog rest.",
             "purpose": "High-volume VO2max work.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 7.5, "min_mpw": 35},
            {"name": "5x1mi",
             "structure": f"5x1mi at {ip_range}/mi with 3min jog rest. Negative split.",
             "purpose": "5 miles at race pace — race-specific fitness and confidence.",
             "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
             "total_miles": 9.0, "min_mpw": 40},
        ])

    # === TEMPO ===
    workouts["tempo"].append({
        "name": "2x16min Tempo",
        "structure": f"2x16min at {format_pace(tp)}/mi with 5min easy jog between.",
        "purpose": "Sustained effort that builds lactate threshold.",
        "warmup": "1.5mi easy", "cooldown": "1.5mi easy",
        "total_miles": 7.0, "min_mpw": 25,
    })

    # === PROGRESSION ===
    workouts["progression"].append({
        "name": "Progressive Run",
        "structure": f"Start at {format_pace(ep_low)}/mi, gradually increase each mile. Last 2mi at {format_pace(tp)}/mi.",
        "purpose": "Teaches pace awareness and builds confidence finishing strong.",
        "warmup": "Built into workout", "cooldown": "1mi very easy",
        "total_miles": 7.0, "min_mpw": 25,
    })

    # =================================================================
    # LONG RUNS — run_type field drives specific structure in plan_engine
    # =================================================================
    workouts["long_run"].append({
        "name": "Easy Long Run", "run_type": "easy",
        "purpose": "Builds aerobic endurance, capillary density, and fat-burning efficiency.",
        "min_mpw": 0,
    })

    if distance in ("marathon", "half"):
        workouts["long_run"].extend([
            {"name": "Steady Finish Long Run", "run_type": "steady_finish",
             "purpose": "Teaches finishing strong on tired legs. Controlled — not a workout.",
             "min_mpw": 30},
            {"name": "MP Finish Long Run", "run_type": "mp_finish",
             "purpose": "Marathon-specific endurance. Running race effort on tired legs.",
             "min_mpw": 40},
            {"name": "Steady Sandwich Long Run", "run_type": "sandwich",
             "purpose": "Sustained steady effort sandwiched between easy. Pacing discipline.",
             "min_mpw": 35},
        ])

    # =================================================================
    # LONG RUNS — Marathon only, peak block (advanced, 55+ mpw)
    # Fixed structures — these are the real marathon long runs
    # =================================================================
    if distance == "marathon":
        stp_label = format_pace(stp)
        workouts["long_run"].extend([
            {"name": "MP Block Long Run", "run_type": "peak_fixed",
             "structure": f"5mi easy, then 3x4mi at goal MP ({grp_label}/mi) with 1mi float between, 1mi cooldown.",
             "purpose": "Accumulates massive marathon pace volume. Peak long run workout.",
             "total_miles": 20.0, "min_mpw": 55},
            {"name": "10 + 8 MP Long Run", "run_type": "peak_fixed",
             "structure": f"10mi easy at {easy_range}/mi, then 8mi at goal MP ({grp_label}/mi). Stay controlled — this is a race simulation.",
             "purpose": "Simulates the back half of a marathon on tired legs.",
             "total_miles": 18.0, "min_mpw": 55},
            {"name": "10 + 10 MP Long Run", "run_type": "peak_fixed",
             "structure": f"10mi easy at {easy_range}/mi, then 10mi at goal MP ({grp_label}/mi). The ultimate marathon long run.",
             "purpose": "20 miles with half at race pace. Peak confidence builder.",
             "total_miles": 20.0, "min_mpw": 60},
            {"name": "10 + 9 MP Long Run", "run_type": "peak_fixed",
             "structure": f"10mi easy at {easy_range}/mi, then 9mi at goal MP ({grp_label}/mi). Stay disciplined the whole way.",
             "purpose": "Race simulation — 9 miles at MP on tired legs builds mental toughness.",
             "total_miles": 19.0, "min_mpw": 58},
            {"name": "Steady to MP Long Run", "run_type": "peak_fixed",
             "structure": f"5mi easy at {easy_range}/mi, 5mi at steady ({stp_label}/mi), then 10mi at goal MP ({grp_label}/mi).",
             "purpose": "Progressive build from easy to steady to race pace. Teaches pacing discipline over 20 miles.",
             "total_miles": 20.0, "min_mpw": 60},
            {"name": "Sandwich MP Long Run", "run_type": "peak_fixed",
             "structure": f"4mi easy at {easy_range}/mi, 4mi at steady ({stp_label}/mi), 4mi easy, then 7mi at goal MP ({grp_label}/mi).",
             "purpose": "Mixed effort long run. Steady block primes the legs for the MP finish.",
             "total_miles": 19.0, "min_mpw": 55},
        ])

    if distance in ("5k", "10k"):
        workouts["long_run"].extend([
            {"name": "Long Run with Pickups", "run_type": "easy",
             "purpose": "Adds neuromuscular stimulus without making it a workout.",
             "min_mpw": 25},
            {"name": "Progressive Long Run", "run_type": "steady_finish",
             "purpose": "Builds aerobic endurance with a quality finish.",
             "min_mpw": 35},
        ])

    # Filter by current mileage
    if current_mileage > 0:
        for category in workouts:
            workouts[category] = [
                w for w in workouts[category]
                if current_mileage >= w.get("min_mpw", 0)
            ]

    return workouts
