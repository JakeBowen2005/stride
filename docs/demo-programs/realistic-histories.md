# Realistic histories: when training differs from the simulation

The [demo programs](README.md) assume perfect adherence. This page runs the same engine
through the messier histories real runners produce. Every run uses a disposable database
and starts on **October 21, 2026**. Reproduce with the commands at the bottom.

| Scenario | What the runner does | What Stride does | Verdict |
|---|---|---|---|
| No lap data | Beginner mileage builder; no watch laps, so they report "did it all" and effort 6/10 in the feedback form | Identical to the lap-recorded program (11.1 → 23.8 mi/week over 16 weeks; 10min → 5x2min → 12min) | Self-reported completion is enough for effort-based introductory sessions. It is stored as `self_reported` evidence and never calibrates a pace. |
| Harder than intended | From week 3, every controlled workout is reported at 8/10 effort (target ~6) | The 10-minute dose holds (two 8/10 sessions in a row step it down, with a "6/10 is slower than you think" cue), while easy volume keeps building, 14.8 → 25 mi/week | Fixed after the coach review: workout effort sets the workout's dose, not the athlete's easy volume. One effort rule with or without laps: ≤7 can advance, 8 holds, ≥9 steps back. |
| Inconsistent schedule | Beginner 5K; skips every 4th scheduled run | Volume holds near 8 mi/week instead of growing; workout progression still advances on sessions completed | Correct fail-safe: missed runs are not made up, and growth waits for consistency. |
| Inconsistent, marathon | Beginner marathon; skips every 4th scheduled run | Holds about 16.8 mi/week. Before the coach review it shrank every block (17.5 → 4 mi/week) because holds were anchored to a 4-week average that already contained the skips | Fixed: holds anchor to the last block's planned volume; a second interrupted block in a row stops shrinking and suggests fewer run days. The outlook now requires a goal decision; athletes can save a completion goal, later race or shorter distance. The current approved block stays in place until they review and approve its replacement. |
| Goal change | Mileage builder switches to a 10K, 16 weeks out, in week 5 | Next block switches to race periodization (Base). Volume and the workout step carry over; no reset to zero, no sudden jump | Correct transition. |
| Advanced, no laps, skips | Sub-3 marathon; no laps and every 5th run skipped | Peak → taper → race week run as planned; threshold ladders hold because unverified sessions can't advance | Correct. Pace ladders require measured laps. |
| Missed week / poor week | Existing `--miss-week` and `--poor-week` flags | Reduced block / recovery block | Unchanged (see README). |

New since this review: athletes with **no running history at all** no longer get an error.
With a stated starting point ("how long can you run without stopping?"), under 20 minutes
starts a run/walk on-ramp (1 min run / 2 min walk × 8 → … → 15 min / 1 min × 2), one
step per week with running. A missed week restarts the step from their stated ability.
No workouts are prescribed until continuous running is established.

## Reproduce

From `backend/` (`--out` to a temporary path):

```sh
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --weeks 16 --no-laps --start-date 2026-10-21 --out /tmp/nolaps.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --weeks 16 --hard-from-week 3 --start-date 2026-10-21 --out /tmp/hard.md
venv/bin/python scripts/simulate_demo_program.py beginner-5k --skip-every 4 --start-date 2026-10-21 --out /tmp/skip.md
venv/bin/python scripts/simulate_demo_program.py beginner-mileage --weeks 12 --goal-change-week 5 --goal-change-to 10k --start-date 2026-10-21 --out /tmp/goal.md
venv/bin/python scripts/simulate_demo_program.py sub3-marathon --skip-every 5 --no-laps --start-date 2026-10-21 --out /tmp/sub3.md
```
