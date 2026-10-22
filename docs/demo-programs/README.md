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

## What reading them showed (Oct 21, 2026)

**1. Beginner plans never build (critical).** Each block "builds up to 10%" from the last four
weeks' average. That average includes the deload week, and beginners deload every third week,
so net growth is about zero:
- **beginner-marathon** runs about 15 mi/week with a 4.5 mi long run for 18 weeks, then a full
  marathon. Its longest run is 5 mi.
- **beginner-mileage** stays near 10.5 mi/week for 16 weeks against a 25 mi/week goal.
- **beginner-5k** stays near 8 mi/week.

**2. Structured long runs and climbs can never be verified, so blocks hold (important).**
- Marathon-pace long runs ("10 + 10 MP"), race-effort long runs and run-hike climbs keep their
  structure only as text. `day_prescription` keeps a numeric prescription only for `workout` days,
  and climbs have no pace target.
- The block review counts them as quality sessions it cannot verify, so it decides **hold**.
- **sub3-marathon:** block 2 holds; weeks 3-4 repeat 2x18min and marathon-pace long runs disappear
  in the peak.
- **trail-100k:** the last three blocks all hold, peak weeks repeat 4x7min, and climbs vanish after
  week 3.
- A real runner doing these sessions perfectly would hit the same thing.

**3. A deload lands inside the 5K peak.** sub17-5k drops to 37.5 mi (from 53.5) two weeks before
race week, then goes back up to 51.5 before the race-week taper.

**What looks right:**
- No back-to-back hard days anywhere.
- Every workout has a purpose plus warmup and cooldown.
- sub17-5k progresses cleanly into 5K-pace work (3x2K, 5x1K at goal pace).
- Tapers cut volume and keep a short sharpener.
- Race week has a sharpener at least 3 days out.
- Ultra back-to-back weekends are flagged and spaced.
