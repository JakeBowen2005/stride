# Workout Progression System

> The complete plan for how Stride prescribes, evaluates, and progresses workouts
> across weeks and blocks. Every rule is science-backed with sources cited.
> This is the design document — implementation follows separately.

## Table of Contents

1. [The Core Problem](#the-core-problem)
2. [Design Principles](#design-principles)
3. [Progression Levers](#progression-levers)
4. [Threshold Workout Progression](#threshold-workout-progression)
5. [VO2max / Interval Workout Progression](#vo2max--interval-workout-progression)
6. [Strava Description Integration](#strava-description-integration)
7. [Performance Evaluation Engine](#performance-evaluation-engine)
8. [Week-to-Week Micro-Progression](#week-to-week-micro-progression)
9. [Block-to-Block Macro-Progression](#block-to-block-macro-progression)
10. [Workout Rotation & Variety](#workout-rotation--variety)
11. [Deload Week Workout Selection](#deload-week-workout-selection)
12. [Implementation Plan](#implementation-plan)

---

## The Core Problem

The current system picks workouts via date-seeded rotation from a flat library. This creates
three flaws:

1. **No progression** — the same workout (e.g., 2x10min Hard at 7:00/mi) repeats for weeks
   with no change in volume, pace, or structure.
2. **No evaluation** — when a runner does 6x800m at 5:52/mi and the plan prescribed 4x800m at
   6:00-6:10/mi, the system doesn't notice the runner far exceeded the prescription.
3. **No variety** — workouts don't alternate between time-based and distance-based formats,
   or between different stimulus types within the same category.

All three must be solved together. Progression without evaluation is blind. Evaluation without
progression is useless. Variety without structure is random.

---

## Design Principles

### 1. One Lever at a Time
Never increase both volume AND intensity in the same workout progression step.
If you add reps, hold pace constant. If you increase pace, hold reps constant.
**Source**: Daniels' Running Formula — "manipulate one variable at a time" (Chapter 2);
Bompa & Haff, Periodization (6th ed.) — progressive overload must be applied to one
stimulus dimension per cycle.

### 2. Current Fitness Drives Prescription
Workout paces come from what the runner HAS DONE, not what they want to do.
Strava descriptions are the ground truth. If the runner ran 6x800m at 2:56 avg,
their 800m pace is ~5:52/mi — that's the starting point, not a VDOT table.
**Source**: Canova — "training must be based on what the athlete can do today."

### 3. Small Steps, Frequently
Progression happens in small increments every 2-week block:
- Volume: +1 rep OR +2min per block
- Pace: 5-10 sec/mi faster per block (only after volume is established)
- Rest: 15-30 sec shorter per block (only after pace is established)
**Source**: Seiler (2010) — endurance athletes adapt optimally with ~5% training
load increases; larger jumps increase injury and overtraining risk.

### 4. Never Surprise the Runner
The first workout at any new stimulus should be ACHIEVABLE. Progression earns
the right to harder workouts. Prescribing a workout the runner can't complete
destroys confidence and wastes a training day.
**Source**: Pfitzinger — "the workout should confirm fitness, not test it."

### 5. Alternate Stimulus Types
Within the same category (e.g., threshold), alternate between time-based and
distance-based formats, and between continuous and interval formats:
- Week 1: 2x10min hard (time-based intervals)
- Week 2: 25min continuous tempo (time-based continuous)
- Week 3: 3x2mi threshold (distance-based intervals)
- Week 4: 2x12min hard (time-based intervals, progressed)
**Source**: Canova — "training is not to replace but to ADD"; rotate every
3 weeks within the same physiological target.

---

## Progression Levers

Each workout category has specific levers that can be manipulated.
The order matters — always progress in this sequence:

### Threshold / Tempo Workouts
```
Step 1: Volume (add time or reps)         — FIRST priority
Step 2: Variety (change workout format)    — keeps stimulus fresh
Step 3: Pace (5-10 sec/mi faster)          — ONLY after volume is solid
Step 4: Rest reduction (shorten recovery)  — LAST lever
```

### VO2max / Interval Workouts
```
Step 1: Reps (add 1-2 reps at same pace)  — FIRST priority
Step 2: Rep distance (400 → 600 → 800)    — extends time at VO2max
Step 3: Pace (5 sec/mi faster)             — ONLY if hitting targets easily
Step 4: Rest reduction (15-30 sec less)    — LAST lever
```

### The Golden Rule of Progression
> **If the athlete executed the workout well (hit paces, felt 6-7/10), progress
> the VOLUME lever. If they crushed it (beat paces by 5+sec, felt 8+/10),
> progress the PACE lever. If they struggled (missed paces, felt <=5/10),
> repeat the same workout or regress one step.**

---

## Threshold Workout Progression

### The Threshold Ladder (5K/10K Focus)

Threshold workouts progress through a defined sequence. The plan engine tracks
where the athlete is on the ladder and advances them based on execution.

```
Level 1: 2x10min Hard at TP                      (20min total quality)
Level 2: 20min Continuous Tempo at TP             (20min continuous)
Level 3: 2x12min Hard at TP                      (24min total quality)
Level 4: 3x10min Hard at TP                      (30min total quality)
Level 5: 25min Continuous Tempo at TP             (25min continuous)
Level 6: 2x15min Hard at TP                      (30min total quality)
Level 7: 3x12min Hard at TP                      (36min total quality)
Level 8: 30min Continuous Tempo at TP             (30min continuous)
Level 9: 2x2mi Threshold at TP                   (distance-based switch)
Level 10: 3x2mi Threshold at TP                  (distance-based, higher vol)
Level 11: 2x3mi Threshold at TP                  (longer reps)
Level 12: 20-30-20 Sandwich                      (sustained threshold)
```

#### Progression Rules
- Start at Level 1 for new runners or returning from break
- Start at Level 3-4 for runners with recent threshold workout history
- **Advance 1 level per 2-week block** if execution is good (paces hit, feel >= 6/10)
- **Advance 2 levels** if execution is excellent (paces beaten by 5+ sec, feel >= 8/10)
- **Repeat same level** if execution was mediocre (paces missed or feel <= 5/10)
- **Regress 1 level** if workout was a disaster (DNF, bonked, pain reported)
- **Never advance more than 2 levels in a single block**
- Every 3rd workout should be a FORMAT CHANGE (time → distance or interval → continuous)

#### Time-Based vs Distance-Based Alternation
The ladder alternates between time-based and distance-based formats.
This is intentional — time-based workouts teach effort-based pacing;
distance-based workouts teach pace discipline. Both are necessary.
**Source**: Daniels prescribes both cruise intervals (time-based) and
threshold repeats (distance-based) for the same physiological target.

#### Pace Progression Within the Ladder
- Levels 1-4: Use CURRENT threshold pace
- Levels 5-8: Blend 75% current / 25% goal threshold pace
- Levels 9-12: Blend 50% current / 50% goal threshold pace
- **Pace advance trigger**: when the runner completes a workout 5+ sec/mi
  faster than prescribed AND reports feel >= 7/10, bump prescribed TP by 5 sec/mi
  for the next block

### Threshold Progression Science
- **Daniels**: Threshold pace sits at ~83-88% of VO2max, sustainable for 20-30min.
  Progress by extending time at intensity before increasing intensity itself.
- **Billat (2001)**: Critical velocity (CV) training at 100% CV for 20-30 min
  significantly improved both VO2max and time to exhaustion in trained runners.
- **Research**: 6 weeks of threshold training at CV increased velocity at LT
  by 3.2% and 5K performance by 2.1% (Running Writings analysis).
- **The 30-minute rule**: Total time at threshold should build toward 30-40 min
  per session. Beyond 40 min per session, diminishing returns and excessive fatigue.

---

## VO2max / Interval Workout Progression

### The Interval Ladder (5K/10K Focus)

```
Level 1: 4x800m at IP (2mi total quality)          — intro VO2max
Level 2: 6x400m at SP (1.5mi speed, economy focus) — speed variety
Level 3: 5x800m at IP (2.5mi total quality)        — +1 rep
Level 4: 5x1K at IP (3.1mi total quality)           — longer reps
Level 5: 6x800m at IP (3mi total quality)           — +1 rep again
Level 6: 6x800m + 4x200m (combo session)            — VO2max + speed kicker
Level 7: 8x800m at IP (4mi total quality)            — peak 800m volume
Level 8: 4x1mi at IP (4mi, longer reps)             — sustained VO2max
Level 9: 5x1K at RP (race-pace specific)            — race specificity
Level 10: 5x1200m at RP (race-pace, longer reps)    — peak specificity
Level 11: 6x1K at RP (race-pace volume)             — peak race-pace volume
Level 12: 4x1mi at RP-5sec (faster than race pace)  — confidence builder
```

#### Progression Rules
- Start at Level 1-2 for runners new to structured speed work
- Start at Level 3-5 for runners with recent interval history
- **Advance 1 level per 2-week block** if all reps completed at prescribed pace
- **Skip to next distance-increase level** if runner consistently beats pace by 5+ sec
- **Repeat same level** if runner faded on last 1-2 reps (normal, not a failure)
- **Regress 1 level** if runner couldn't complete the session
- Rest periods: start generous (2min for 800s, 3min for 1K+), tighten later

#### The 200m / 400m Speed Days
Speed work (200m, 400m) is NOT on the same ladder as VO2max work.
It serves a different purpose: running economy and neuromuscular coordination.
- Prescribe 200-400m reps on easy days as strides, or as a workout add-on
- Don't progress these — keep at mile-effort pace with full recovery
- Purpose is to "remind the legs what fast feels like," not build VO2max
**Source**: Daniels, R-pace repetitions; Magness — "short reps maintain
fast-twitch recruitment patterns critical for race-day kick."

#### The Combo Session (Level 6 Example)
The 6x800m + 4x200m combo is a critical pattern:
- The 800s provide the VO2max stimulus (sustained effort above 90% VO2max)
- The 200s at the end develop speed endurance and economy on tired legs
- This mirrors what Jake actually does (Strava shows 6x800 then 4x200)
- Combo sessions should appear every 3rd interval workout

#### VO2max Progression Science
- **Meta-analysis (51 studies, ~1,200 participants)**: Optimal rep duration
  for VO2max improvement is 2-5 minutes. Sweet spot: ~140 seconds (2:20).
  800m at 5:52/mi pace = ~2:55 per rep. Perfect VO2max stimulus.
- **Billat (2001)**: 5x3min at 95% vVO2max with 3min recovery produced
  328 seconds above 90% VO2max — the most efficient protocol tested.
- **Frontiers in Sports (2024)**: Longer intervals (3-5min) dramatically
  outperform short intervals (30sec) for time above 90% VO2max.
  4x3min: 328 sec above 90%. 24x30sec: only 201 sec above 90%.
- **Daniels**: "I-pace should be run at 95-100% VO2max. Total session volume:
  8% of weekly mileage, or 10K, whichever is less." For 25 mpw runner: ~2mi
  of quality. For 50 mpw runner: ~4mi of quality.
- **Key insight**: Adding reps is better than adding pace. 6x800 at 5:52 is
  a bigger VO2max stimulus than 4x800 at 5:42 because total time at VO2max
  is higher. Volume at intensity > intensity at volume.

### Rest Period Progression

Rest is a progression lever, but the LAST one to manipulate:

| Rep Distance | Starting Rest | Intermediate | Advanced |
|-------------|--------------|--------------|----------|
| 400m        | 200m jog (90s) | 200m jog (75s) | 200m jog (60s) |
| 800m        | 2:00 jog | 90s jog | 60-75s jog |
| 1K          | 2:30 jog or 200m walk | 2:00 jog | 90s jog |
| 1200m       | 3:00 jog | 2:30 jog | 2:00 jog |
| Mile        | 3:00-4:00 jog | 3:00 jog | 2:00-2:30 jog |

**Source**: Seiler — "recovery duration determines the proportion of time spent
near VO2max. Shorter rest keeps O2 consumption elevated between reps. But too
short causes form breakdown."

Rule: Only reduce rest after the runner has completed 2+ sessions at the current
rest with good form and paces within 5 sec of target on all reps.

---

## Strava Description Integration

### What We Can Extract

Strava workout descriptions (written by the runner) contain the richest
performance data available. Current pace_calibrator.py parses:

1. **Interval splits**: "6x800 (2:49, 2:55, 2:54, 2:51, 2:53, 2:56)"
2. **Threshold paces**: "2x2 miles threshold (7:02, 6:56)"
3. **200/400m speed**: "4x200 (38, 35, 34, 32)"
4. **Tempo paces**: "25min tempo at 6:45"

### What We Should ALSO Extract (New)

#### A. Workout Pattern Matching
Parse the Strava description to identify WHAT workout the runner actually did:
```
"6x800 then 4x200" → intervals, combo session (800m + 200m)
"2x10 min hard"     → threshold, time-based intervals
"25 min tempo"      → threshold, continuous tempo
"5x1K"              → intervals, 1K repeats
"4x1 mile"          → intervals, mile repeats
"progression run"   → progression (last few miles faster)
```

This tells us:
- Whether they did the PRESCRIBED workout or something different
- What workout format they gravitate toward
- Whether they're ready for the next level on the ladder

#### B. Rep-by-Rep Fade Analysis
Critical for progression decisions. Parse individual split times:
```
6x800: (2:49, 2:55, 2:54, 2:51, 2:53, 2:56)
                                          ↑ slight fade on last rep
```
- **Even or negative splits** → runner handled it well → progress
- **Fade > 5 sec on last 1-2 reps** → borderline → repeat or small progress
- **Progressive fade > 3 sec per rep** → too hard → do NOT progress, consider regress
- **Big positive split** (faster last rep) → runner had more in the tank → progress

**Fade calculation**:
```
avg_first_half = mean(splits[0:n//2])
avg_second_half = mean(splits[n//2:])
fade = avg_second_half - avg_first_half
```
- fade < 3 sec: EXCELLENT execution
- fade 3-6 sec: GOOD execution (normal for hard workouts)
- fade 6-10 sec: FAIR execution (got hard, held on)
- fade > 10 sec: POOR execution (workout was too ambitious)

#### C. Pace vs Prescription Comparison
Compare actual split paces to what was prescribed:
```
Prescribed: 4x800 at 6:00-6:10/mi (2:59-3:03 per 800)
Actual:     6x800 at avg 2:52 (5:46/mi)
Analysis:   +2 reps AND 14 sec/rep faster than prescribed
Decision:   Runner significantly exceeded prescription → recalibrate paces UP
```

#### D. Workout Type Mismatch Detection
When the runner does a different workout than prescribed:
```
Prescribed: 2x10min Hard (threshold)
Actual:     "Lunch Run" at easy pace
Analysis:   Runner swapped hard day for easy day
Decision:   Check feedback — was it fatigue? Schedule conflict?
            Reschedule the threshold to next available easy day.
```

### How Strava Data Flows Into Next Plan

```
1. Runner completes workout → Strava sync pulls activity
2. Parse description → extract splits, workout type, fade analysis
3. Compare to prescription → hit/missed paces, same/different workout
4. Combine with feel rating → objective data + subjective response
5. Calculate progression decision:
   - ADVANCE: hit paces + feel >= 7 + fade < 5 sec
   - HOLD: hit paces + feel 5-6 OR fade 5-8 sec
   - REGRESS: missed paces OR feel <= 4 OR fade > 10 sec
   - RECALIBRATE: beat paces by 10+ sec → update current fitness paces
6. Store progression state → { category, current_level, last_workout, decision }
7. Next plan generation reads progression state → picks next workout on ladder
```

### Pace Recalibration Triggers

The system should recalibrate training paces when:

1. **Interval pace shift**: Runner consistently runs 800s 10+ sec/mi faster
   than prescribed for 2+ sessions → bump interval pace by 5 sec/mi
2. **Threshold pace shift**: Runner completes threshold work 5+ sec/mi faster
   than prescribed with feel >= 7 → bump threshold pace by 5 sec/mi
3. **Easy pace shift**: Runner's average easy pace drops 15+ sec/mi over
   4+ weeks → update easy pace baseline
4. **Race result**: Any race performance updates all derived paces via VDOT

**Conservative recalibration**: Only adjust by 5 sec/mi at a time, even if
data suggests a bigger jump. Gradual pace progression prevents overreaching.
**Source**: Daniels — VDOT updates should happen every 4-6 weeks, not daily.

---

## Performance Evaluation Engine

### The Decision Matrix

After each workout, the system produces one of four decisions:

| Paces Hit? | Feel Rating | Fade | Decision |
|-----------|------------|------|----------|
| Yes (within 5s) | 7-8 | < 5s | **ADVANCE** — progress 1 level |
| Yes (within 5s) | 9-10 | < 3s | **ADVANCE+** — progress 1 level + bump pace 5s |
| Beaten by 5s+ | 8+ | < 5s | **RECALIBRATE** — update paces, advance 1 level |
| Yes (within 5s) | 5-6 | 5-8s | **HOLD** — repeat same workout next time |
| Missed by 5s+ | 5-6 | > 5s | **HOLD** — repeat, but check fatigue context |
| Missed by 10s+ | <= 4 | > 8s | **REGRESS** — drop 1 level, investigate cause |
| DNF / incomplete | any | any | **REGRESS** — drop 1 level, add recovery day |

### Context Modifiers

The raw decision gets adjusted by context:

- **Hot weather (>80F)**: Allow 10-15 sec/mi pace slack before calling it "missed"
  **Source**: Runners Connect — pace slows ~1.5-3% per 10F above 55F
- **High elevation (>4000ft)**: Allow 5-10 sec/mi pace slack
- **Consecutive hard training weeks (3+)**: Hold decisions are preferred over advance
- **Coming off illness/break**: First workout back is always a HOLD regardless of execution
- **Time of day shift**: Morning vs evening performance varies 3-5% (Callard et al., 2000)

### Subjective vs Objective Weight

When feel rating and objective data disagree:

- **Felt great but paces were slow**: Likely external factor (heat, wind, elevation,
  bad GPS). Trust the feel — HOLD, don't regress.
- **Felt terrible but paces were fast**: Possible accumulated fatigue, poor sleep,
  life stress. This is a WARNING — the body performed but at a cost. HOLD,
  don't advance, and watch the next session carefully.
- **Felt great AND paces were fast**: Clear signal to progress. ADVANCE.
- **Felt terrible AND paces were slow**: Clear signal to back off. REGRESS or
  add an extra easy day.

**Source**: Foster (2001) — session RPE (subjective load) is a better predictor
of training adaptation than any single objective metric.

---

## Week-to-Week Micro-Progression

### Within a 2-Week Block

Week 1 and Week 2 of the same block should NOT be identical.

#### Pattern A: Volume Bump
```
Week 1: 2x10min Hard at TP + 6x800m at IP
Week 2: 2x12min Hard at TP + 6x800m + 2x200m at IP/SP
```
Small volume increase in week 2 = natural mini-progression.

#### Pattern B: Format Switch
```
Week 1: 2x10min Hard at TP (time-based) + 6x800m at IP
Week 2: 20min Continuous Tempo at TP (continuous) + 5x1K at IP (longer reps)
```
Different format, same physiological target = variety + continued adaptation.

#### Pattern C: Intensity Touch
```
Week 1: 6x800m at 5:52-6:02/mi + 2x10min Hard at 6:50/mi
Week 2: 6x800m at 5:50-6:00/mi + 2x10min Hard at 6:45/mi
```
Tiny pace bump (2-5 sec) from week 1 to week 2.

### Rules for Within-Block Progression
1. Week 2 is ALWAYS slightly harder than Week 1 (unless Week 1 went badly)
2. The progression is subtle — the runner might not even notice
3. If Week 1 execution was poor (HOLD/REGRESS), Week 2 repeats Week 1 exactly
4. Never change more than one variable between Week 1 and Week 2
5. The threshold day and interval day progress independently

---

## Block-to-Block Macro-Progression

### The 4-Block Cycle (8 Weeks)

Each 4-block cycle (8 weeks) follows a build → build → build → deload pattern:

```
Block 1 (Weeks 1-2):  Establish baseline. Pick starting level on each ladder.
Block 2 (Weeks 3-4):  First progression. Advance 1 level on each ladder.
Block 3 (Weeks 5-6):  Second progression. Advance 1 level + possible pace bump.
Block 4 (Weeks 7-8):  Deload week 1, resume week 2. Consolidate gains.
```

### Macro-Progression Table (5K Example)

| Block | Threshold | Intervals | Notes |
|-------|-----------|-----------|-------|
| 1 | 2x10min at 6:50 | 4x800 at 6:00-6:10 | Establish baseline |
| 2 | 2x12min at 6:50 | 5x800 at 6:00-6:10 | Volume increase |
| 3 | 3x10min at 6:45 | 6x800 at 5:55-6:05 | Volume + pace bump |
| 4 | DELOAD: 2x10min at 6:50 | DELOAD: 4x800 at 6:00 | Absorb, recover |
| 5 | 25min Tempo at 6:45 | 6x800 + 4x200 | Format variety |
| 6 | 2x15min at 6:40 | 5x1K at 5:55-6:05 | Volume + pace |
| 7 | 3x2mi at 6:35 | 8x800 at 5:50-6:00 | Peak volume |
| 8 | DELOAD: 2x2mi at 6:40 | DELOAD: 5x800 at 5:55 | Absorb, recover |

### Key Macro-Progression Rules

1. **Mileage increases 5-10% per block** (total weekly volume)
2. **Workout intensity increases ~5 sec/mi every other block**
3. **Workout volume increases every block** (reps or time)
4. **Deload blocks drop workout volume by ~30%** but maintain 1 quality session
5. **After deload, resume from pre-deload level** (don't restart)
6. **Race-specific workouts appear in blocks 5+** (after base is established)
7. **Pace recalibration happens after every 4th block** (using latest Strava data)

---

## Workout Rotation & Variety

### The 3-Week Rotation Principle

Within each workout category, rotate through 3 distinct formats before repeating.
**Source**: Canova — elite 5000m runners rotate workout themes every 3 weeks to
prevent neural staleness while maintaining the same physiological target.

#### Threshold Rotation Example
```
Block N, Week 1:    Time-based intervals (2x12min Hard)
Block N, Week 2:    Continuous tempo (25min Tempo)
Block N+1, Week 1:  Distance-based intervals (3x2mi Threshold)
Block N+1, Week 2:  Time-based intervals (2x15min Hard) ← back to format 1, progressed
```

#### Interval Rotation Example
```
Block N, Week 1:    800m repeats (6x800m)
Block N, Week 2:    1K repeats (5x1K)
Block N+1, Week 1:  Combo session (6x800 + 4x200)
Block N+1, Week 2:  Mile repeats (4x1mi)
```

### Variety Constraints
- Never repeat the EXACT same workout 3 times in a row
- The same rep distance (e.g., 800m) can repeat if volume/pace changed
- At least 1 time-based and 1 distance-based threshold workout per 4-week cycle
- At least 1 "fun" workout per 4-week cycle (fartlek, progression run, pyramid)
- Long runs already rotate via the existing system (easy, steady finish, etc.)

### Workout Staleness Detection
If the pace_calibrator sees the EXACT same Strava description pattern 3x in a row
(e.g., "6x800" three workouts running), flag it and force a format change.

---

## Deload Week Workout Selection

### Rules
- Drop from 2 workouts to 1
- Pick from the LOWER half of the athlete's current ladder level
- Reduce total quality volume by ~30-40%
- Maintain intensity (pace) — just reduce volume
- The workout should feel "sharp but easy" — leaves the athlete wanting more

### Examples
```
Pre-deload:  3x10min Hard at 6:45 + 6x800 at 5:55-6:05
Deload:      2x10min Hard at 6:45 (single workout, reduced volume)
Post-deload: 25min Continuous Tempo at 6:40 + 6x800 + 4x200 (resume + advance)
```

**Source**: Mujika & Padilla (2003) — optimal taper maintains intensity while
reducing volume by 40-60%. For deload (not taper), 25-30% reduction is sufficient.

---

## Implementation Plan

### Phase 1: Progression State Tracking (Data Model)

Add a new table/model to track workout progression state:

```python
class WorkoutProgression:
    user_id: int
    category: str               # "threshold" or "intervals"
    current_level: int          # position on the ladder (1-12)
    last_workout_date: date
    last_workout_name: str
    last_execution: str         # "advance", "hold", "regress", "recalibrate"
    current_pace_sec: float     # current working pace for this category
    sessions_at_level: int      # how many times they've done this level
    format_rotation: int        # 0, 1, 2 — tracks the 3-format rotation
```

### Phase 2: Enhanced Strava Parsing

Extend pace_calibrator.py with:
1. `evaluate_workout_execution()` — compares actual splits to prescription
2. `calculate_fade()` — rep-by-rep fade analysis
3. `identify_workout_type()` — maps description to workout ladder position
4. `suggest_progression()` — returns ADVANCE/HOLD/REGRESS/RECALIBRATE

### Phase 3: Progression-Aware Plan Engine

Modify plan_engine.py to:
1. Read WorkoutProgression state for the user
2. Use current_level to pick the right workout from the ladder
3. Apply within-block micro-progression (Week 1 vs Week 2 variation)
4. Apply pace adjustments from recalibration events
5. Respect the 3-format rotation counter

### Phase 4: Workout Ladder Definition

Create a new module `workout_ladders.py` that defines:
1. The threshold ladder (12 levels with exact workout specs)
2. The interval ladder (12 levels with exact workout specs)
3. Level-appropriate pace blending (current vs goal)
4. Rest period tables per level
5. Deload variant selection per level

### Phase 5: Post-Workout Evaluation Loop

After Strava sync, automatically:
1. Parse the new activity description
2. Match to the day's prescription
3. Run the evaluation engine
4. Update WorkoutProgression state
5. Store the evaluation for coach feedback context

### Phase 6: Coach Integration

Feed the evaluation data to the LLM coach for:
1. Post-run feedback that references specific splits and fade analysis
2. Explanation of the progression decision ("Your 800s were strong with minimal
   fade — advancing to 5x1K next block")
3. Context-aware encouragement or caution

---

## Appendix A: Jake's Current Starting Points

Based on Strava data from May 2026:

### Interval Ladder
- **Current Level**: ~5 (can do 6x800m at 5:52/mi with 4x200 added)
- **Starting Prescription**: Level 5 — 6x800 at 5:50-6:00/mi
- **Next Progression**: Level 6 — 6x800 + 4x200 combo (already doing this naturally)

### Threshold Ladder
- **Current Level**: ~1-2 (2x2mi threshold at 7:02/6:56 = only recent data point)
- **Starting Prescription**: Level 1 — 2x10min Hard at 6:50/mi
- **Next Progression**: Level 2 — 20min Continuous Tempo at 6:50/mi

### Key Observation
Jake's interval fitness is AHEAD of his threshold fitness. This is common for
runners returning from marathon training — they maintained leg speed but lost
lactate threshold sharpness. The plan should:
1. Progress threshold aggressively (2 levels per block if execution is excellent)
2. Progress intervals normally (1 level per block)
3. Let threshold "catch up" to interval fitness over 4-6 blocks

---

## Appendix B: Science Reference Summary

| Source | Key Finding | Application |
|--------|------------|-------------|
| Daniels (Running Formula) | Progress every 4-6 weeks, one variable at a time | Block-to-block macro-progression |
| Billat (2001) | 5x3min at 95% vVO2max = optimal VO2max stimulus | Interval ladder rep durations |
| Frontiers (2024) | Longer intervals >> short intervals for time at VO2max | Prefer 800m-1K over 200-400m for VO2max |
| Canova | Rotate themes every 3 weeks, "add don't replace" | 3-format rotation principle |
| Seiler (2010) | ~5% load increase per cycle optimal for endurance | Small progression steps |
| Pfitzinger (Faster Road Racing) | 5K requires VO2max AND threshold development in parallel | Dual-ladder system |
| Mujika & Padilla (2003) | Maintain intensity, reduce volume for taper/deload | Deload workout selection |
| Foster (2001) | Session RPE > objective metrics for training load monitoring | Subjective feel weight in decisions |
| Magness (Science of Running) | Short reps maintain neuromuscular patterns | 200-400m as economy work, not VO2max |
| Brad Hudson (Run Faster) | "Adaptive running" — adjust daily based on response | Performance evaluation engine |

---

## Appendix C: Example 8-Week Progression (Jake, Sub-17 5K)

Assuming ~25 mpw start, building to 35 mpw. Intervals on Tuesday, Threshold on Thursday.

### Block 1 (Weeks 1-2)
| Day | Week 1 | Week 2 |
|-----|--------|--------|
| Tue | 6x800m at 5:50-6:00/mi, 90s rest | 6x800m + 4x200m at 5:50-6:00/5:05, 90s/full rest |
| Thu | 2x10min Hard at 6:50/mi, 2min rest | 20min Continuous Tempo at 6:50/mi |

### Block 2 (Weeks 3-4)
| Day | Week 1 | Week 2 |
|-----|--------|--------|
| Tue | 5x1K at 5:50-6:00/mi, 200m jog rest | 6x800m at 5:45-5:55/mi, 90s rest |
| Thu | 2x12min Hard at 6:50/mi, 2min rest | 3x10min Hard at 6:45/mi, 2min rest |

### Block 3 (Weeks 5-6)
| Day | Week 1 | Week 2 |
|-----|--------|--------|
| Tue | 6x800m + 4x200m at 5:45-5:55/5:05, combo | 4x1mi at 5:45-5:55/mi, 3min rest |
| Thu | 25min Continuous Tempo at 6:45/mi | 2x15min Hard at 6:40/mi, 2min rest |

### Block 4 — Deload (Week 7) + Resume (Week 8)
| Day | Week 7 (Deload) | Week 8 (Resume) |
|-----|-----------------|-----------------|
| Tue | 4x800m at 5:50/mi, 2min rest | 8x800m at 5:40-5:50/mi, 90s rest |
| Thu | — (single workout week) | 3x2mi Threshold at 6:35/mi, 0.5mi rest |

Note how each block introduces variety (800m → 1K → combo → mile) while
progressively increasing total quality volume and slightly tightening paces.
