# Demo programs: full progression review

These simulations start on **October 21, 2026**. Each runner completes the prescribed
work, reports a good 7/10 post-run feel, and approves each new two-week block. Race
programs run through race day. Mileage comparisons run for **24 weeks**, so we can see
both reaching 25 miles/week and the later workout progression. They are demonstrations
of the engine under consistent adherence, not promises of fitness or recovery.

| Program | Full progression | Longest training run | Document |
|---|---|---|---|
| Beginner first 5K | 8.0 → 12.8 mi/week before race week | 5.4 mi | [First 5K](beginner-5k.md) |
| Beginner first marathon | 15.9 → 34.2 mi/week, held to the taper | 13.9 mi | [First marathon](beginner-marathon.md) |
| Beginner build to 25 | 11.1 → 25 mi/week; first reaches 25 in week 19 | 9.3 mi | [Beginner mileage](beginner-mileage.md) |
| Intermediate comparison | Same starting history and goal; reaches 25 in week 19 with faster workout progression | 9.3 mi | [Intermediate mileage](intermediate-mileage.md) |
| Advanced sub-17 5K | No deload in the final peak weeks (see below) | 15 mi | [Sub-17 5K](sub17-5k.md) |
| Advanced sub-3 marathon | Biggest marathon-pace long run 3 weeks out; 2x13min taper threshold | 20 mi | [Sub-3 marathon](sub3-marathon.md) |
| Expert trail 100K | Three-week taper; biggest long run 3 weeks out | 25 mi | [Trail 100K](trail-100k.md) |

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
  clearly longer than any easy day (at least 1.2x, up to its cap). Introductory half/marathon long
  runs may reach 40% (half) / 42% (marathon) of the week, growing about a mile a week from the
  longest recent run, never past ~3 hours. The run after the long run is the week's shortest
  easy run (at most 18% of the week).
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
program.

## Coach-review structure fixes (October 2026)

All seven documents were regenerated after these changes. Weekly volumes are unchanged
except where a down week was removed near a race.

- **No deload near the peak.** A calendar deload due within taper length + 2 weeks of the race
  is suppressed; the block holds the training level instead of building, and the taper absorbs
  the load. Sub-17 5K week 5 is now 50.5 mi (was a 37.5 mi deload); first-marathon week 17
  holds 34.2 mi (was a 25.7 mi down week right before the taper).
- **The week back from a down week** restores volume with one quality session (a demanding
  long run counts as one); the second returns the following week.
- **Longest runs come three weeks out.** The final pre-taper half/marathon week repeats, never
  extends, the longest recent long run. The sub-3 marathon's MP Block Long Run (3x4mi at MP)
  is now in week 3, 22 days out; week 4's long run is an easy 20. The 100K taper is 21 days, so
  its biggest long run (25 mi) is in week 7 and weeks 8–9 taper.
- **Taper sessions keep ~2/3 of the dose** (sub-3 marathon 2x13min threshold, not 2x4min;
  introductory taper efforts 8min instead of 6min of a 12min step). Race week stays light.
- **Race-effort ultra long runs** say easy for the first and last thirds and race effort in the middle.
- **Spike guard for every level.** After a jump in completed mileage, experienced runners also get
  one step of growth, then hold. Race weeks are excluded from spike detection.
- **Volume gap as a decision.** Once build has started, training below half the goal's volume
  target returns an outlook decision (completion goal, later race, or shorter distance).

## What still needs a coaching decision

**The first-marathon demo still has an endurance preparation gap.** It now builds to
about 34 mi/week and a 13.9-mile long run (three weeks out), but that is not equivalent to a
demonstrated marathon-specific long-run buildup. The engine flags the gap within six weeks of
the race, using the outlook's developing long-run milestone (16 miles for a marathon, 10 for a
half). It suggests reviewing a later race or shorter event instead of cramming distance before
taper. This is a Stride review heuristic, not a guarantee of readiness. The goal is not
automatically changed.

## Reproduce the review

From `backend/`:

```sh
venv/bin/python scripts/simulate_demo_program.py beginner-5k --start-date 2026-10-21 --out ../docs/demo-programs/beginner-5k.md
venv/bin/python scripts/simulate_demo_program.py beginner-marathon --start-date 2026-10-21 --out ../docs/demo-programs/beginner-marathon.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --start-date 2026-10-21 --weeks 24 --out ../docs/demo-programs/beginner-mileage.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --experience intermediate --start-date 2026-10-21 --weeks 24 --out ../docs/demo-programs/intermediate-mileage.md
venv/bin/python scripts/simulate_demo_program.py sub17-5k --start-date 2026-10-21 --out ../docs/demo-programs/sub17-5k.md
venv/bin/python scripts/simulate_demo_program.py sub3-marathon --start-date 2026-10-21 --out ../docs/demo-programs/sub3-marathon.md
venv/bin/python scripts/simulate_demo_program.py trail-100k --start-date 2026-10-21 --out ../docs/demo-programs/trail-100k.md
```

Use `--miss-week 4` or `--poor-week 4` with a temporary output path to inspect an interrupted
or poorly recovered program. The first causes a reduced block; the second causes recovery.
`--keep-db /tmp/example.db` retains the disposable simulation database for inspection.
The simulator does not touch the personal database, Garmin or AI.

Verification covers full programs, interrupted and poor-recovery programs, replacement
menu application, duration-based progression, conservative starts, budget/frequency/hard-day
spacing across schedules, and that the three advanced documents match the engine byte-for-byte. The demo/invariant checks are
also exercised with the clock set to every weekday.

## Daily-time comparison (invite beta)

[Time-limited beginner](time-limited-beginner.md) uses the same starting history
and 25 mi/week goal, with Tuesday 30, Thursday 45, Saturday 90 and Sunday 30
minutes available. The engine moves a full quality dose to a roomier easy day
before shortening it, preserves recovery separation, and never makes up unused
miles elsewhere. Full main doses can still earn progression; shortened main doses
cannot. The outlook asks for an availability/goal decision when the finite time
budget cannot support the goal volume. Standard demos without time limits remain
byte-for-byte unchanged after this release, including advanced race programs.

```sh
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --weeks 24 --start-date 2026-10-21 --day-minutes '{"monday":0,"tuesday":30,"wednesday":0,"thursday":45,"friday":0,"saturday":90,"sunday":30}' --out ../docs/demo-programs/time-limited-beginner.md
```
