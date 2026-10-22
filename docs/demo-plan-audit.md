# Demo plan audit against Stride's principles (Oct 21 2026)

Every demo deploy branch (`codex/demo-*`) was merged up to main (`c58444f`), so each now runs
the current engine with its own demo athlete. Each scenario was seeded through the real engine on a
disposable database. Its two-week block was then checked against the core principles, which come
from `CLAUDE.md`, `training-principles.md` and `ARCHITECTURE.md`.

## The core principles, condensed

1. **Mileage and consistency first.** Build volume before intensity. No workouts until the base supports them.
2. **Easy days easy, hard days hard.** About 80% of miles are easy; workouts are genuinely hard and purposeful.
3. **Never two hard days in a row.** The only exception is a flagged ultra back-to-back weekend.
4. **Progress slowly.** Ramp limits by experience: about 10% for beginners, 15-20% for advanced. Deload every 3-4 weeks for beginners and every 5-7 for experienced runners, reducing volume 20-30%. Change one lever at a time, and never raise mileage and intensity in the same week.
5. **Every workout has a why.** Each one has a purpose, a target pace or effort, and a warmup and cooldown.
6. **Simple but specific.** "6x800m at 2:34-2:39 with 1:30 jog", not rounds and sets.
7. **Adapt to the response.** Feel plus objective data drive adjust, hold or regress, and the athlete approves changes.
8. **More specific as the race nears.** Base → build → peak → taper → race week.
9. **The long run is sacred.** About 25-30% of the week for 5K/10K and 25-35% for half/marathon, and never the shortest run.
10. **Fail safe.** When in doubt, prescribe less.

## Results

All six plans pass the invariant matrix (`tests/test_plan_invariants_matrix.py`): budgets, rest days, hard-day spacing, ramp, deload cadence and taper shape. They also have no back-to-back hard days, every workout has a purpose plus warmup and cooldown, and every title is short.

| Demo | Baseline | Weeks | Quality | Long run | Verdict |
|---|---|---|---|---|---|
| beginner-5k | 7.5 mpw | 8.0 → 6.0 (deload) | none: base first (P1) | 3.0 → 2.0 mi | ✅ after fix (see below) |
| beginner-marathon | 15.4 | 16.7 → 11.0 (deload) | none | 5.0 → 3.5 (30-32%) | ✅ |
| beginner-mileage | 10.8 | 11.6 → 8.5 (deload) | none | 3.0 / 3.0 | ✅, see note 2 |
| sub17-5k | 46.8 | 49 → 51 (+4%) | tempo; then 6x800+4x200 and 2x15min | 13.5 → 14.5 (28%) | ✅ |
| sub3-marathon | 60.8 | 60.5 → 67 (+10%) | cruise intervals; 2x18min threshold | 19 easy → 20 with 10 at MP | ✅, see note 3 |
| trail-100k | 60.5 | 64 → 67.5 (+12%, expert) | run-hike climbs; 3x8min threshold | 22.5; then back-to-back 13 + 23.5 | ✅, see note 4 |

## Fixed in this change

- **The long run could be the shortest run of the week.** In the beginner-5K deload week, a 5.6 mi budget over three runs left easy days at the 2-mile floor. The rebalancing loop then gave up, leaving a 1.5 mi "long run", but still added a note claiming the long run was "not shorter than the easy days". Now the loop:
  1. uses the half-mile rounding tolerance, or
  2. folds an easy day into the long run, keeping the same total.

  The note appears only when it's true. Regression test: `test_low_volume_long_run_is_never_shorter_than_an_easy_day`.
- **The deload note told beginners to "keep 1 quality workout"** when their plan has none. It now says every run stays easy when there's no workout.

## Judgement calls to decide (not changed)

1. **Deloads at very low volume.** All three beginners deload in week 2 after 4-8 steady weeks (5.5-6 mpw for the first-5K athlete). This follows the principle's cadence, but at 6-8 mpw there's little load to absorb. The goal's minimum mileage (P1 table: 10-15 mpw to finish a 5K) isn't even reached yet. Option: skip or soften deloads while the baseline is below the goal's minimum.
2. **beginner-mileage week 2 drops from 4 to 3 run days** to keep easy runs at least 2 mi in an 8.1 mi deload. Consistency (P1) argues for keeping frequency and shortening runs instead.
3. **sub3-marathon week 2 raises mileage 10% and adds a 10-mile marathon-pace long run.** That's race-specific and right for the peak phase (P8, Pfitzinger/Canova), but it bends "never raise mileage and intensity in the same week" (P4). Option: hold volume flat in the week a marathon-pace long run is introduced.
4. **trail-100k warmups read "16.5min easy".** Time-based warmups should round to 5 minutes (P6, simple): "15min easy".
