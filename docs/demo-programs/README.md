# Demo programs: full progression review

These simulations start on **October 21, 2026**. Each runner completes the prescribed
work, reports a good 7/10 post-run feel, and approves each new two-week block. Race
programs run through race day. Mileage comparisons run for **24 weeks**, so we can see
both reaching 25 miles/week and the later workout progression. They are demonstrations
of the engine under consistent adherence, not promises of fitness or recovery.

| Program | Full progression | Longest training run | Document |
|---|---|---|---|
| Beginner first 5K | 8.0 → 12.8 mi/week before race week | 4.9 mi | [First 5K](beginner-5k.md) |
| Beginner first marathon | 15.9 → 34.2 mi/week before taper | 12.0 mi | [First marathon](beginner-marathon.md) |
| Beginner build to 25 | 11.1 → 25 mi/week; first reaches 25 in week 19 | 7.2 mi | [Beginner mileage](beginner-mileage.md) |
| Intermediate comparison | Same starting history and goal; reaches 25 in week 19 with faster workout progression | 7.2 mi | [Intermediate mileage](intermediate-mileage.md) |
| Advanced sub-17 5K | Unchanged from the prior engine | 15 mi | [Sub-17 5K](sub17-5k.md) |
| Advanced sub-3 marathon | Unchanged from the prior engine | 20 mi | [Sub-3 marathon](sub3-marathon.md) |
| Expert trail 100K | Unchanged from the prior engine | 26.5 mi | [Trail 100K](trail-100k.md) |

Messier histories (no laps, harder-than-intended workouts, skipped runs, goal changes) are in [Realistic histories](realistic-histories.md).

## What changed for beginners and introductory intermediates

- **Purposeful quality sooner.** Two consistent completed running weeks can support one
  controlled session per week, even on a three-day schedule. The initial pattern is
  **10min easy → 10min medium-to-hard, controlled effort → 10min easy**. A smaller weekly
  budget shortens the work/bookends. The work should feel around 6/10 effort, with short
  phrases possible and some capacity left at the finish. This effort scale is separate
  from the post-run feel/recovery rating.
- **A progression, not random variety.** Continuous efforts, short intervals and longer
  intervals form a twelve-step track. Beginners earn four successful full-dose exposures
  per step; intermediates earn two. Examples: 10min → 5x2min → 12min → 6x2min → 3x4min →
  15min → 5x3min → 3x5min. Later steps reach 18–20 minutes of work. Reduced, alternative,
  taper and race-week sessions do not earn progression. Labeled work durations plus good
  recovery earn duration exposures; they do not establish threshold intensity or pace.
- **One main change at a time.** Introducing a new step holds mileage in that week.
  The same workout repeats while easy volume can grow in the following week. There is
  no automatic harder workout preview in week two.
- **Mileage increases survive rounding.** Introductory programs use repeatable recent
  completed volume and weekly steps capped at 10%, with tenth-mile allocation. Planned
  down weeks no longer erase the established level. Spikes and missed weeks still
  prevent treating an isolated high week as the new baseline.
- **Consistency before distance floors.** Shorter easy runs preserve the chosen run
  frequency instead of removing days to satisfy a 2–3 mile minimum. Long runs remain at
  least as long as easy days. Introductory half/marathon long runs use 35% of weekly volume.
- **Recovery follows training stress.** In these fixtures, the first planned down week
  is week 5, rather than immediately after week 1. Calendar cadence requires actual
  accumulated quality exposure or sustained mileage growth. Poor recovery can reduce
  training sooner. Stable old easy weeks alone do not force an immediate deload.
- **Race week fits the runner.** Familiar controlled pickups replace the fixed five-mile
  sharpener. The race replaces a normal training day, shakeouts stay short, and unused
  mileage allowance is not forced into the days before the race.
- **Effort is not a guessed threshold pace.** Introductory sessions have numeric durations,
  recoveries and bookends, with effort guidance. Their budgeting pace is explicitly an
  estimate. They never calibrate threshold/interval pace; the athlete-facing pacing guide
  shows easy pace and the goal target rather than guessed workout paces.

Established intermediates with demonstrated full-quality tolerance keep their existing
program. Advanced/expert and ultra programs retain their previous behavior. All three
advanced documents were regenerated at the same date and compared byte-for-byte with the
pre-change outputs; they match. Regression tests preserve that comparison.

## What still needs a coaching decision

**The first-marathon demo still has an endurance preparation gap.** It now builds to
about 34 mi/week and a 12-mile long run, but that is not equivalent to a demonstrated
marathon-specific long-run buildup. The engine flags the gap within six weeks of the
race, using a 16-mile review milestone (8 miles for a half). It suggests reviewing a
later race or shorter event instead of cramming distance before taper. This is a Stride
review heuristic, not a guarantee of readiness. The goal is not automatically changed.

The advanced plans' existing issues, including the sub-17 5K deload near its final peak
and simultaneous changes to volume and quality, are deferred in this change.

## Reproduce the review

From `backend/`:

```sh
venv/bin/python scripts/simulate_demo_program.py beginner-5k --start-date 2026-10-21 --out ../docs/demo-programs/beginner-5k.md
venv/bin/python scripts/simulate_demo_program.py beginner-marathon --start-date 2026-10-21 --out ../docs/demo-programs/beginner-marathon.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --start-date 2026-10-21 --weeks 24 --out ../docs/demo-programs/beginner-mileage.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --experience intermediate --start-date 2026-10-21 --weeks 24 --out ../docs/demo-programs/intermediate-mileage.md
```

Use `--miss-week 4` or `--poor-week 4` with a temporary output path to inspect an interrupted
or poorly recovered program. The first causes a reduced block; the second causes recovery.
`--keep-db /tmp/example.db` retains the disposable simulation database for inspection.
The simulator does not touch the personal database, Garmin or AI.

Verification covers full programs, interrupted and poor-recovery programs, replacement
menu application, duration-based progression, conservative starts, budget/frequency/hard-day
spacing across schedules, and unchanged advanced outputs. The demo/invariant checks are
also exercised with the clock set to every weekday.
