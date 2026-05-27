# Athlete Profile — Jake Bowen

> This file captures training patterns, preferences, and insights specific to Jake.
> The plan generator should reference this when creating personalized plans.

## Current PRs
- **5K**: 18:22 (Jun 2025) — 5:55/mi
- **10K**: 44:52 (Oct 2025) — 7:25/mi (likely not a true race effort based on pace)
- **Half Marathon**: 1:29:27 (Oct 2025) — 6:48/mi
- **Marathon**: 2:58:42 (Feb 2026) — 6:46/mi

## Current Status (May 2026)
- Rebuilding after post-marathon break
- Currently ~19-25 mpw, 4-5 runs/week
- Targeting sub-17 5K (need to drop from 18:22 → 16:59 = 83 seconds)
- After 5K goal: 100-miler (future)
- Easy pace currently ~9:06-9:09/mi, trail runs ~12:00+ with elevation
- 160 spm cadence, easy HR ~143
- Now fully locked in on sub-17 goal

## Recent Workout Paces (May 2026 — Current Fitness)
These define WHERE the athlete IS, not where they want to be:
- **800m repeats**: 3:03 → 2:56 (last rep) = ~6:06-5:52/mi pace
- **200m repeats**: 38 sec = ~5:04/mi pace (short burst speed exists)
- **2x2mi threshold**: 7:02, 6:56/mi with 2mi float rest
- **5x1K**: 3:44-3:57 = ~6:00-6:22/mi with 200m walk rest (~2:00-2:15)
- **Trail run**: 7mi at 12:41 avg, last 2mi at 7:25 on tired legs, 900ft elevation gain

### Current Fitness Paces (for plan generation)
- **Threshold/tempo**: ~6:30-6:45/mi (not all-out, sustainable hard)
- **800m interval**: ~2:56-3:03 (5:52-6:06/mi)
- **1K interval**: ~3:44-3:57 (6:00-6:22/mi)
- **200m speed**: ~38sec (5:04/mi)
- **Easy**: 9:00-10:00/mi
- **Goal 5K race pace**: 5:28/mi (NOT current ability — target to build toward)

## Core Training Belief: Mileage & Consistency Above All

**This is the #1 principle of the entire plan generator.**

- Mileage and consistency are the single greatest predictors of performance at every distance
- You cannot shortcut volume. Sub-3 marathon on 25-30 mpw is not realistic. Jake aimed for 50, realized he needed more, peaked at 70
- Fast 5K? Need lots of miles. Fast marathon? Even more miles. Ultra? Even more
- Consistency over months matters more than any single workout
- The plan generator must ALWAYS prioritize building sustainable mileage before adding intensity
- A runner doing 50 easy miles per week will outperform a runner doing 30 miles with fancy workouts

### Mileage Targets by Goal (Guidelines)
- Sub-20 5K: 30-40 mpw minimum
- Sub-17 5K: 45-55+ mpw
- Sub-3:00 marathon: 50-70 mpw (Jake's range)
- Sub-1:30 half: 45-60 mpw
- 100-miler: 60-80+ mpw with back-to-back long runs

## Training Patterns That Work
- **Responds well to threshold repeats** (2mi reps are the sweet spot)
- **Negative splits** — naturally gets faster through workouts
- **Needs structured long runs** — not just easy miles
- **Float/jog rest preferred** over standing rest (0.25mi or 1mi jog)
- **Warmup/cooldown always included** — typically 2mi each
- **7 runs per week at peak** — can handle high frequency
- **Peaked at 70 mpw** — body handled it well
- **50-65 mpw is the sustainable training zone**

## Pacing Principles

### Easy Runs
- **Easy should actually be easy** — the emphasis is on conversational effort, not a specific pace number
- Should be able to hold a full conversation the entire time. If you can't talk, slow down.
- Pace is secondary to effort — include a range as reference but don't obsess over it
- Currently ~9:00-10:00/mi

### Steady Pace
- At peak marathon shape, steady was **~7:30/mi**
- Should be **within a minute of goal MP** — not the midpoint of easy and threshold
- Progresses down as threshold progresses down
- Used for steady portions of long runs and sandwich runs

### Threshold Pace
- Starts conservative based on current fitness (easy pace * 0.77 ≈ 7:00 from 9:06 easy)
- **Progresses toward goal** as mileage builds — blends from base toward (goal MP - 25sec/mi)
- At peak marathon shape: 6:30/mi or faster for sub-3 goal
- **Round all workout paces to nearest 5 seconds** — no need for false precision

### Extended Reps (1.5mi reps)
- **4x1.5mi is NOT an interval workout** — it's an easier threshold day
- Pace should be slightly faster than threshold (~10sec below threshold)
- At peak shape: ~6:30 or below, but probably not faster than 6:15
- Think of it as threshold with 1-2 more reps at slightly faster pace

### MP Pace Runs
- **Use the exact goal race pace** (e.g., 6:52/mi for sub-3 marathon)
- Should say "controlled — can push if feeling good but don't force it"
- Everything should revolve around the goal race pace
- The code should be general — works for any goal, not hardcoded for sub-3

### Long Run Pacing
- First few weeks of building: long runs should be all easy
- **After 6+ weeks of building**: long runs should start including miles at goal MP
- Steady finish, MP finish, sandwich — all should reference goal race pace
- Long runs are where marathon-specific fitness is built

### Peak Marathon Long Runs (marathon only, advanced, 55-60+ mpw)
These are the real marathon long runs for the final 2 months of a training cycle:
- **10 + 8 MP** (18mi): 10mi easy, 8mi at goal MP — race simulation
- **10 + 9 MP** (19mi): 10mi easy, 9mi at goal MP — mental toughness builder
- **10 + 10 MP** (20mi): 10mi easy, 10mi at goal MP — the ultimate marathon long run
- **Steady to MP** (20mi): 5mi easy, 5mi steady, 10mi at goal MP — progressive build
- **Sandwich MP** (19mi): 4mi easy, 4mi steady, 4mi easy, 7mi at goal MP — mixed effort
- **MP Block** (20mi): 5mi easy, 3x4mi at goal MP with 1mi float, 1mi cooldown — massive MP volume
- These are fixed-structure workouts — exact mile breakdowns, not dynamically generated
- Only appear when mileage is 55-60+ mpw and the athlete has been building for a while

### Interval Pace
- **Progresses toward goal** as mileage builds, just like threshold
- **Always show a pace range** for 1mi reps and below (800m, 1K, 1mi)
- Range = ~10sec window. Faster end is "feeling good/pushing," slower end is baseline target
- Example: "5:55-6:05/mi" — hit 5:55 if legs feel great, 6:05 is perfectly fine
- Gives the athlete flexibility based on how they feel that day
- 1.5mi reps are NOT interval pace — they're near-threshold (see Extended Reps above)
- 400m reps stay at strides pace (pure speed), no range needed

### 3x3mi Workout
- This is a **marathon pace workout**, not threshold
- 9 miles at goal MP is brutal enough — no need to go faster
- Peak marathon-specific volume workout, use sparingly
- **Do NOT prescribe unless** the athlete has shown they can hold MP for 4-5mi in workouts and long runs
- Gate behind 50+ mpw AND a `requires_mp_readiness` flag (checks workout/long run history)

### General Pace Rules
- All workout paces rounded to nearest 5 seconds
- Paces derive from current fitness, not goal — but progress toward goal over time
- Both threshold AND interval pace progress as mileage builds
- Strides: short bursts at ~5:00/mi effort, not timed precisely

## Training Preferences
- Workouts should be simple and specific (no complicated sets)
- Easy days truly easy — conversational effort above all
- Hard days genuinely hard
- No back-to-back hard days
- Prefers distance-based workouts but open to time-based
- Units: miles
- **Workout days: Tuesday and Thursday**
- Long run: Saturday
- **Rest day: Sunday** (user preference for now, should be configurable later)
- No pace zones — easy should be easy, hard should be hard
- Strides 1-2x per week on easy days
- **Warmup and cooldown always included and counted in total distance**
  - Typical warmup: 1-1.5mi easy (or 10-15min)
  - Typical cooldown: 1-1.5mi easy (or 10-15min)
  - Total workout distance = warmup + main set + cooldown
- **Two workouts per week is fine**, but one can be lighter (threshold effort, not all-out)
  - Example: Tue = lighter threshold session, Thu = harder interval/speed session
  - Or: Tue = harder session, Thu = lighter tempo/threshold

## Known Weaknesses to Address for Sub-17 5K
- Goal race pace (5:28/mi) is faster than anything sustained in training yet
- BUT 200m speed (5:04/mi) and 800m speed (5:52/mi) show the raw speed EXISTS
- Gap is in SUSTAINING speed, not reaching it — need to extend speed endurance
- Has massive aerobic engine from marathon training, needs to sharpen it for 5K
- 10K PR (44:52) seems soft — likely has sub-40 fitness based on marathon
- Key development path: current 800m pace (5:52) → extend that to 3.1 miles

## Deload Weeks

- **Deload is 1 week only**, never 2 — the second week of the block goes right back to building
- **Advanced**: first deload at block 4 (week 7), then every 3rd block after (~6 weeks: week 13, 19, 25...)
- **Beginner/Intermediate**: first deload at block 3 (week 5), then every 2nd block after (~4 weeks: week 9, 13, 17...)
- **Reasoning**: push through initial adaptation/soreness first, then deload once athlete is in a groove
- **Triggered by block number**, not automatic timer
- **Mileage reduction**: ~25% cut from current weekly mileage for the deload week
- **Workouts**: drop from 2 to 1. Keep it quality but lighter — MP Pace Run 3-4mi or 2x2mi threshold, nothing over ~8.5mi total
- **Long run**: doesn't have to be all easy. Can still include steady or light MP finish (e.g., 8mi easy + 3mi at MP)
- **Purpose**: let the body absorb training, dissipate fatigue, come back stronger
- **Not a rest week** — still running, still sharp, just reduced volume
- **Week 2 resumes from pre-deload mileage** with a slight bump — don't restart the ramp
- **Future**: user-reported fatigue (bad sleep, soreness, feeling off) can trigger an early deload

## What Doesn't Work
- Overly complicated workouts (e.g., "3 rounds of 5 sets of 40sec sprints")
- Garmin Coach style pacing (too aggressive mileage ramps, weird structures)
- Standing rest (prefers jog/float recovery)
- Plans that are too far in advance (prefers 2-week rolling blocks)
