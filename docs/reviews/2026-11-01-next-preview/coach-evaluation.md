# Why the Nov 2–15 preview is so flat (coach evaluation, Nov 1 2026)

> **Status:** fixes 1–7 built Nov 1 (`tests/test_demonstrated_training.py` uses Jake's block as the
> fixture). The next block now builds to 48 mi/week: 3x8min threshold plus relaxed reps, an 8 mi
> medium-long run, a recovery run after the long run, and a 13.5 mi long run with a steady finish in
> week 1. Fix 8 is replaced by marking previews from older code stale (they no longer cap the rebuild).
> The flat preview Jake saw after #74 deployed was one of these: saved before the deploy.

Jake's two weeks: 40.1 and 45.1 mi, with 3x8min threshold, 6x400m, 2x12min threshold, a 10 mi
long run each week, and an 11 mi midweek day. The preview for the next block was 42.5 mi in both
weeks: 2x6min threshold once a week, five easy days at exactly 5 mi, a 12 mi "Easy Long Run", and
week 2 the same as week 1. A coach wouldn't write that for this athlete.

## Verdict: the preview is honest, and the plan engine is the problem

- **Reproduced** on a disposable copy of `backend/stride.db` (last local sync Oct 27; Oct 28–Nov 1
  filled in from the screenshot), at Nov 1 (provisional) and Nov 2 (final).
- **Same output without the preview code.** Commit `b7db4e0` (the preview) builds the same block
  as the code from before it (`13e5925`, run in a throwaway worktree): 2x6min threshold, flat easy
  days, one quality session, identical weeks. So the preview shows what the old Monday
  "Generate" would have built. It didn't preload anything wrong.
- **42.5 mi = the "training level"**, the average of the last two full weeks (40.1 + 45.1). The
  block was put on **hold**, and hold repeats that volume for both weeks.

The local database doesn't have the exact Render block, so the local run gives 37 mi instead of
42.5. The chain of rules below is the same.

## The chain that produced it

1. **The goal switch reset the workout ladders to level 1.** On Oct 19 the goal became a mileage
   goal (75 mi/week). `_load_progression_state` (`api/plans.py`) makes a fresh
   `ladder-v2:mileage` program at **level 1**, keeping only the pace. The old interval level 7 is
   ignored. Level 1 of the aerobic threshold ladder (`workout_ladders.get_ladder`, `duration = 6`)
   is **2x6min**.
2. **Harder substitutions don't count.** Planned 3x1200m → ran 3x8min threshold. Planned 3mi tempo
   → ran 2x12min threshold. Both are marked "a different session than planned", so:
   - the ladder never moves up (`quality_history`: off-plan sessions are skipped);
   - `block_assessment.assess_block` counts them as **not done**. With fewer than half of quality
     sessions "done", the rule at line ~115 returns **hold**, even with 100%+ of miles run.
3. **Hold forces one quality session.** `quality_policy.select_quality_policy` returns `single`
   whenever `assessment in {'hold','reduce','recovery'}`. The second session (intervals or
   strides support) disappears.
4. **Hold makes week 2 a copy of week 1.** `allow_preview=False` when held, so the week-2 ladder
   step is turned off, and the volume is repeated.
5. **Easy days are split evenly.** `plan_engine._distribute_mileage` divides what's left
   equally over the easy days: 5, 5, 5, 5, 5. There's no medium-long run, no short recovery day
   after the long run, and no variety.
6. **Plain long run.** A mileage goal gets no steady or progression finish, so it's an "Easy Long
   Run" every week.
7. **Long-run evidence is missed.** The "long run completed and recovered" check needs a watch
   feel of 6+ and ≥90% of the planned row's distance. Switched or moved long runs, or runs without
   a watch rating, don't count.

## What the preview commit did get wrong (smaller)

- **The final build is capped at the provisional preview** (`weekly_volume_caps`). As a fail-safe
  that's reasonable. Together with the problems above it also locks in a bad preview: if the
  engine is fixed between Friday and Monday, the final block can't be bigger than the flat
  preview. Recommend: cap only when the provisional projection assumed sessions that then weren't
  run, not always.
- The banner says "assumes the remaining runs are completed" but doesn't say *why* the block is
  held. The hold reasons are in the notes, and the athlete never sees them prominently.

## Recommended fixes (coach view, in order of impact)

1. **Seed ladder levels from demonstrated work.** On a goal switch, and whenever a completed
   threshold or interval session is detected, set the level to at least the highest level whose
   work dose matches what was run under control in the last 6 weeks (2x12min → ~24 min of
   threshold work). Never start an advanced runner at level 1 when they've just run more than that.
2. **A harder same-category substitution is a completed session** for the block decision (hold or
   build), and counts as evidence for the ladder at the dose actually run. An easier one doesn't.
3. **Don't hold a block that was over-completed and felt fine.** If completion is ≥100% and the
   average feel is ≥6.5 with no low feels, build, whatever the quality bookkeeping says.
4. **Hold limits volume, not workouts.** Hold should keep the miles flat but still allow the
   week-2 workout step and the second session the athlete has already earned (one lever at a
   time: volume holds, the workout progresses).
5. **Shape the easy days for experienced runners at ≥35 mi/week**: one medium-long run (about 1.5x
   an easy day, ~15–18% of the week), a short recovery run the day after the long run, and the
   rest spread out, instead of identical days.
6. **Long-run variety for mileage and advanced athletes**: every other week a steady or
   progression finish (the last 2–3 mi at steady pace), the same way race goals already get MP
   finishes.
7. **Long-run evidence**: a long run counts as done if ≥90% of the distance was run on any day
   that week and there's no low feel. A missing watch rating isn't a failure.
8. **Preview cap**: only cap the final block when projected sessions weren't run.

Each needs a regression test using Jake's last block as the fixture (two weeks with harder
substitutions, 85 mi run against 79 planned). The next block should then have two quality
sessions, a threshold dose of at least 2x12min-equivalent, varied easy days, and a modest build.
