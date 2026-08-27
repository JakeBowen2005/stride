# Stride Training Principles

> Universal principles that govern ALL plan generation across every distance.
> This is the foundation the plan engine reads before generating any plan.

## Principle 1: Mileage & Consistency Are King

Nothing matters more than total weekly volume sustained over time. A runner doing 50 easy
miles per week will beat a runner doing 30 miles with fancy workouts every time.

- Build mileage BEFORE adding intensity
- A new runner should spend 4-8 weeks just building easy volume before any workouts
- An experienced runner returning from a break needs 2-4 weeks of easy running to rebuild
- The plan generator should NEVER add hard workouts to a week where the mileage base isn't sufficient

### Minimum Mileage Guidelines by Goal
| Goal | Minimum Weekly Avg | Target Weekly Avg |
|------|-------------------|-------------------|
| Finish a 5K | 10-15 mpw | 15-20 mpw |
| Sub-25 5K | 15-20 mpw | 25-30 mpw |
| Sub-20 5K | 25-30 mpw | 35-45 mpw |
| Sub-17 5K | 40-45 mpw | 50-60 mpw |
| Sub-1:45 half | 25-30 mpw | 35-45 mpw |
| Sub-1:30 half | 35-40 mpw | 45-55 mpw |
| Sub-3:30 marathon | 30-40 mpw | 45-55 mpw |
| Sub-3:00 marathon | 45-50 mpw | 55-70 mpw |
| 100-miler finish | 50-60 mpw | 60-80+ mpw |

## Principle 2: Easy Days Easy, Hard Days Hard

- ~80% of weekly mileage should be at easy/conversational effort
- Easy pace = conversational, no huffing. Prescribe a pace range but emphasize FEEL
- Hard workouts should be genuinely challenging — not moderate, not "comfortably hard"
- The workout should have a clear purpose and a clear target effort

## Principle 3: No Back-to-Back Hard Days

- Always separate workouts and long runs with easy/rest days
- Standard week: Easy, WORKOUT, Easy, WORKOUT, Rest, LONG RUN, Easy
- This is non-negotiable for injury prevention

## Principle 4: Progressive Overload (Slowly)

### Mileage Ramp Rates
| Experience | Weekly Increase | Deload Frequency |
|-----------|----------------|------------------|
| Beginner (< 1yr) | Max 10% per week | Every 3rd-4th week |
| Intermediate (1-3yr) | Max 10-15% per week | Every 4th week |
| Advanced (3yr+) | Max 15-20% per week | Every 5th-7th week |

- Deload week = reduce volume by 20-30%, maintain some intensity
- After injury/break: start at 50% of previous volume, rebuild over 3-4 weeks
- NEVER increase mileage AND intensity in the same week

### Workout Progression (One Lever at a Time)
Workouts progress through defined ladders — NOT random rotation. Each 2-week block
advances the athlete ONE level on the ladder if execution was good.

**Progression levers (in order)**:
1. **Volume** — add reps or time (e.g., 2x10min → 2x12min, or 4x800 → 5x800)
2. **Variety** — change workout format (time-based ↔ distance-based, intervals ↔ continuous)
3. **Pace** — 5-10 sec/mi faster (ONLY after volume is established)
4. **Rest reduction** — 15-30 sec shorter recovery (LAST lever to pull)

Never increase more than one lever per block. Never increase volume AND pace in the same
workout. Source: Daniels — "manipulate one variable at a time."

### Threshold Pace Differentiation
Broken threshold intervals (with rest) should be prescribed ~10 sec/mi FASTER than
continuous tempo runs. The rest between reps allows the athlete to sustain a harder effort.
- **Continuous tempo** (20min, 25min, 30min): standard threshold pace (e.g., 6:50/mi)
- **Broken intervals** (2x10min, 3x12min, 2x2mi): ~10 sec/mi faster (e.g., 6:40/mi)
- **Distance intervals** (2x2mi, 3x2mi, 2x3mi): also faster — rest enables harder pace

This mirrors real coaching practice: "2x10min with rest, you can push harder than a
straight 20min tempo." The pace differential is built into the ladder templates.

### Experience-Based Progression Rate
Not all athletes progress at the same rate. The system should identify athlete type from
data and adjust accordingly:

| Athlete Type | Indicators | Progression Rate |
|-------------|-----------|-----------------|
| Experienced rebuilder | Strong PRs, high peak mileage history, currently low mileage | Fast — 2 levels/block for lagging categories |
| Experienced steady | Consistent mileage, recent race results | Normal — 1 level/block |
| Intermediate | 1-3 years running, moderate PRs | Normal — 1 level/block |
| Beginner | <1 year, no race history | Conservative — hold at each level for 2+ blocks |

**Key insight**: An athlete with a 2:58 marathon and 70 mpw peak who is currently at 25 mpw
is NOT a beginner. Their body remembers the fitness. They should progress threshold work
aggressively (2 levels/block) because the aerobic base exists — it just needs reactivating.
Interval work progresses normally since speed takes longer to rebuild.

See `docs/workout-progression-system.md` for the complete ladder definitions and rules.

## Principle 5: Every Workout Has a Purpose

When prescribing a workout, always include:
1. **The workout** (what to do)
2. **The purpose** (why you're doing it — what physiological system it targets)
3. **Target paces/effort** (specific numbers or effort descriptions)
4. **Warmup and cooldown** (always included, distance or time based)

## Principle 6: Workouts Should Be Simple

Good: "6x800m at 5K pace with 90sec jog rest"
Bad: "3 rounds of 5 sets of 40sec sprints between 4:12-4:44 pace"

Runners should be able to remember the workout without checking their phone mid-run.

## Principle 7: Adapt Based on Response

- The plan is a suggestion, not a law
- If a runner bombs a workout, investigate (fatigue? life stress? sleep?)
- If a runner crushes workouts consistently, consider progressing faster
- Post-run feel rating (1-10) + objective data = adjustment decisions
- Never blindly follow the plan if the runner is struggling

### Strava-Informed Evaluation
After each workout syncs from Strava, the system evaluates:
1. **Did they hit the prescribed paces?** (parse splits from description)
2. **Did they fade?** (compare first-half vs second-half split averages)
3. **Did they do the prescribed workout?** (match description to prescription)
4. **How did they feel?** (1-10 rating from feedback)

This produces a decision: ADVANCE (progress next workout), HOLD (repeat),
REGRESS (step back), or RECALIBRATE (update training paces from new data).

If the runner beats prescribed paces by 10+ sec/mi for 2+ sessions, bump
training paces by 5 sec/mi. Always adjust conservatively — 5 sec at a time.
See `docs/workout-progression-system.md` for the full evaluation matrix.

## Principle 8: Race-Specific Training Gets More Specific Over Time

Early in a training block: general fitness, base building
Middle: introduce race-specific workouts
Late: highly specific to goal race demands
Taper: reduce volume, maintain sharpness

## Principle 9: Long Run Is Sacred

- The weekly long run is the most important single run of the week
- For 5K/10K: long run = 25-30% of weekly mileage
- For half/marathon: long run = 25-35% of weekly mileage
- Long runs should NOT always be easy — they should evolve with the training phase
- But recovery long runs (pure easy) should alternate with quality long runs

## Principle 10: Injury Prevention Over Performance

- When in doubt, prescribe LESS
- An undertrained runner can still race; an injured runner cannot
- Monitor acute:chronic workload ratio — flag anything above 1.3
- If a runner reports pain (not soreness), immediately reduce load
- Extra rest days > pushing through fatigue
