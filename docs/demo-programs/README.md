# Demo programs, run exactly as prescribed

Each file plays one demo athlete's program forward from Oct 21, 2026 to race day (16 weeks for the
mileage goal). The simulated runner completes **every prescribed run exactly**: the right distance,
workouts at the middle of their pace range with matching laps, and a 7/10 feel after hard days.
Every two weeks Stride builds the next block from what was run, and it is approved. That makes
these the plans the engine actually produces, week by week.

| Demo (branch `codex/demo-…`) | Program | Doc |
|---|---|---|
| beginner-5k | First 5K (sub-30), 8 weeks, 3 days/week | [beginner-5k.md](beginner-5k.md) |
| beginner-marathon | First marathon (~4:30), 18 weeks, 4 days/week | [beginner-marathon.md](beginner-marathon.md) |
| beginner-mileage | Build to 25 mi/week, 16 weeks, 4 days/week | [beginner-mileage.md](beginner-mileage.md) |
| sub17-5k | Sub-17 5K, 6 weeks out | [sub17-5k.md](sub17-5k.md) |
| sub3-marathon | Sub-3 marathon, 5 weeks out | [sub3-marathon.md](sub3-marathon.md) |
| trail-100k | Trail 100K, 9 weeks out | [trail-100k.md](trail-100k.md) |

To regenerate after engine changes:

```bash
cd backend && venv/bin/python scripts/simulate_demo_program.py sub3-marathon --out ../docs/demo-programs/sub3-marathon.md
```

## What reading them showed, and what changed (Oct 21, 2026)

The first run of these docs found two engine problems. Both are fixed and the docs are regenerated.

**1. Beginner plans never built. Fixed.** Each block grew from the 4-week average. Beginners deload
every third week, and that average included the deload, so growth netted to about zero (the
beginner marathoner sat at 15 mi/week for 18 weeks).
- **The fix:** after a down week, the next block plans from the **training level**, meaning the
  full-volume weeks. It returns to the pre-deload level, then grows at the usual rate.
- **Safety stays:**
  - a one-off spike is ignored
  - a missed (zero) week still counts as a break
  - the level is capped at 35% above the average
  - fatigue-driven reduce/recovery blocks still start from the average
- **Now:** beginner-marathon builds 15 → 21.5 mi/week in a three-up, one-down rhythm (long run
  4.5 → 6.5 mi), and beginner-mileage builds 11.6 → 14.5.

**2. Structured long runs could never be verified. Fixed.** Marathon-pace, steady and race-effort
long runs existed only as text, so a perfect run still made the next block "hold".
- **The fix:** they now carry numeric prescriptions (easy warmup, then the MP/steady/race-effort
  segments, then cooldown). The block review verifies them from laps like workout reps, and paced
  segments may be at most 10 s/mi slow.
- **Now:** sub3-marathon and trail-100k build every block (0 holds, previously 1 and 3). Workouts
  progress, and marathon-pace long runs stay in the peak.

**Still worth a look:**
- **beginner-marathon reaches race day at about 21 mi/week with a 6.5 mi longest run.** The ramp is
  safe; the goal (a first marathon 18 weeks out from 15 mi/week) is not. The race-readiness check
  should push this athlete to a later race or a half marathon.
- **beginner-5k barely moves (8 → 8.5 mi/week).** At 8 mi/week, a 10% step is smaller than the
  half-mile rounding on three runs.
- **sub17-5k drops to 37.5 mi two weeks before race week** (a deload inside the peak), then
  returns to 51.5.

**What looks right:**
- No back-to-back hard days anywhere.
- Every workout has a purpose plus warmup and cooldown.
- Workouts progress one level at a time.
- Tapers cut volume and keep a short sharpener.
- Race week has a sharpener at least 3 days out.
- Ultra back-to-back weekends are flagged and spaced.
