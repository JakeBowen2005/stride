# Automatic run review, adaptive session choices and synthetic athlete demos

## New Garmin run → automatic review

The Garmin importer enqueues a `CoachingJob` in the same database transaction as each newly stored or legacy-merged run. Only activity dates from today and the prior two calendar days qualify; re-importing history or refreshing summaries does not create duplicate jobs. A successful sync releases these jobs only after its wellness-sync attempt. An interrupted import leaves jobs waiting until a later successful sync.

A local worker runs while the backend is open, independently of the Garmin polling interval. It atomically leases one job, releases the database lock, calls the existing bounded/cached OpenAI review service, then stores completion. The result compares the actual run/laps with its genuine prescription, current goal, recovery and upcoming block. Until the athlete rates the run, subjective feel remains unknown and execution analysis is provisional: no rating, progression change or feedback claim is fabricated.

Completed work never triggers automatic plan mutations. Suggested changes need athlete acceptance. Feedback later triggers a fresh evidence-based review. Opening a plan only normalizes derived completion/matching and does not invalidate a review.

Durability: unique activity/version key, 10-minute recoverable lease with ownership token, three automatic attempts, five-minute retry delay, daily AI quota shared with manual reviews. Quota waits defer until the next UTC day without consuming failure retries. Provider errors cannot roll back imported runs. Manual review stays available after an automatic failure. This is a single-process/local database worker, not a distributed queue service; there are no Garmin webhooks. Default Garmin polling is ten minutes, then the worker starts the queued review shortly afterward. The app displays queued/running/failed states and polls saved results without making extra model calls.

Configuration: `OPENAI_AUTO_REVIEWS=true` (default); false disables the worker and new-job enqueueing. An OpenAI key is required to execute paid work. The existing twelve-attempt UTC daily cap, timeout, token/input ceilings, caching and `store=False` still apply. Automatic reviews add to API usage; a daily call cap is not a dollar budget guarantee.

## Session chooser

Plan → expand an unrun day → Replace → Threshold, Intervals/light speed or Long run. Pick a concrete option and inspect its full prescription, total mileage, bookends and any easy-day reductions before applying.

The backend recomputes the menu from the active goal, phase, experience, eight weeks of actual history, current category pace evidence, recent recovery, progression state, existing week and stored budget. It is deterministic for identical context: it changes with actual training, not random novelty. Missing category pace evidence retains the approved numeric pace rather than speeding up from a display-label change. Warmups, recoveries and cooldowns count in the budget. Modified doses hold the full ladder level (`progression_eligible=False`).

### Menu v2 (`core/session_catalog.py`)

The menu shows **at most three options, each a different shape**: cruise intervals by time, measured threshold reps by distance (1K, 1mi, 1.5mi, 2mi), continuous tempo (minutes or miles), threshold ladders; for intervals short reps (400–600m), 800m–1K reps, long reps (1200m–mile), time-based reps and pyramids. Trail/mountain goals get effort-based hill repeats first (their own `hills` category, so hill laps never calibrate flat interval pace). The athlete's time/distance preference picks which shape comes first; the remaining order rotates by calendar week so the menu varies without randomness.

All options sit inside one **dose band** (minutes of hard work, excluding warmup, recoveries and cooldown):

| | Floor (beginner / intermediate / advanced / expert) | Ceiling |
|---|---|---|
| Threshold | 10 / 15 / 20 / 24 min | 16 / 30 / 40 / 50 min |
| Intervals | 8 / 12 / 15 / 18 min | 12 / 18 / 24 / 30 min |

The top of the band is Daniels' per-session volume guidance (threshold ≈ 10% and I-pace ≈ 8% of weekly mileage, converted to minutes at the athlete's work pace), never below floor + 5 min. Low current volume pulls the floor down so a comeback is not overloaded. Taper and deload weeks keep pace but cut the dose; base weeks keep intervals short. Floors and ceilings are Stride heuristics so that a trained runner never sees a token 2×3min dose; they are not validated safety limits. Examples: an advanced runner at ~40 mi/week sees a 20–30 min threshold band (e.g. 3mi tempo / 3×1mi / 5×5min); a beginner sees 10–16 min.

Unchanged gates: earned single/support/dual stage limits substantial weekly work (support offers up to three light second-stimulus sessions of different families instead of full intervals); phase max-workouts, deload, inexperienced base and ultra back-to-back caps take precedence; a demanding long run or completed quality day consumes a slot; low feel or a failed session removes hard options. Long runs offer up to three durations (60-180 min) of at least 60/75/90 min for beginner/intermediate/advanced and longer than the week's easy runs, capped at 110% of the recent 28-day longest run and 35% of the weekly budget, plus a gated steady finish for established half/marathon athletes. Pace is unchanged by the menu: cruise reps use the broken-threshold pace and continuous tempo the slower tempo pace (deliberate relationship). Menu sessions hold the ladder level (`progression_eligible=False`).

These choices interpret the personal Long Game research plus existing goal/phase/quality policies. They are intentionally explicit product policy and require future longitudinal evaluation; neither a fast PR nor an experience label removes recovery needs.

### Goal pace and specific endurance (menu v3, `core/goal_pace.py`)

Build and peak sessions now look more like the race. **Goal pace is a target, never a prescription by itself.** Every goal-pace session runs at `max(goal pace, demonstrated race pace − 5 s/mi)`. That is one step from what the athlete has shown, and never faster than the goal. Demonstrated race pace comes from calibrated goal-pace reps (`race_pace_<distance>`, two executed sessions as for every other calibrated pace). Without those, it comes from the training paces already in use. These are Stride heuristics after Daniels: 5K ≈ I + 5 s, 10K ≈ T − 10 s, MP ≈ T + 20 s. When the reps are completed and calibrate a faster pace, the next session steps again. Goal-pace reps calibrate only their own distance's race pace. They never move interval or threshold pace, and the feedback path holds instead of recalibrating them. The rule is deterministic: the same evidence always gives the same pace.

| Goal | Where it opens (phase gate) | Sessions |
|---|---|---|
| 5K / 10K | Peak only, not deload | Goal-pace reps (5×1K, 6×1K, 8×800, 3–4×1mi, 3×2K, 2×3K; 10K: up to 8×1K, 5×1mi, 4×2K, 3×3K). The interval ladder in peak is now a 12-level goal-pace ladder instead of generic 800s at I pace. |
| Marathon | Build and peak, not deload | Threshold menu: MP blocks (3×2mi … 2×4mi), continuous MP (4–8mi) and medium-long runs with an MP segment (10–15mi, capped at 25% of weekly volume). Long-run menu: MP-finish and, in peak, MP-block long runs, behind the existing steady-finish gate (two-workout stage, ≥40 mi/week, no other hard day). The plan engine's MP sessions and MP long runs use the same step. |
| Trail/mountain ultras | Power-hike base–peak; downhill build–peak; never taper or deload | Power-hike climbs (6×4min … 3×12min) and climb + fast-descent repeats. Each has a climbing target estimated at ~700 m/h hiking or ~500 m/h running uphill. The plan engine alternates the two by calendar week in build/peak; base keeps short hill repeats. |

Goal-specific shapes lead the menu, at most two of them, so one general shape (threshold, VO2 or hills) is always offered too. They have their own dose bands: goal-pace reps sit between Daniels' T and I caps, marathon pace near Pfitzinger's midweek MP runs, and climbing is measured in time. These bands are Stride heuristics.

**One dosing system.** `quality_policy.secondary_quality` (the controlled second session at the two-workout stage) now picks from the same catalog and `dose_band`. It takes the smallest session that reaches the experience floor, so an advanced runner's secondary threshold is ≥20 minutes, not the old fixed 15–18. Marathoners in build or peak get a continuous MP run on alternate weeks in place of 600s.

Not changed: race-week sharpeners still use exact goal pace, since the race is run at goal pace anyway. Half-marathon MP-finish long runs still use goal HMP as before; a half-marathon step is a follow-up.

Every option is dry-run with its companion budget cuts in rolled-back savepoints through the common validator. A selected ID hashes the full athlete/training/schedule context and proposed changes. POST recomputes it under a write lock: new runs, feedback, goals or schedule edits reject stale choices. Every affected day records its original prescription and adjustment note, then the complete schedule is revalidated and committed atomically. Legacy category-only requests also use the validated menu.

The AI can select IDs from the **same** menu, including earned easy→quality choices. It cannot supply arbitrary pace/reps or bypass the menu limits. The client displays companion mileage cuts before acceptance. No automatic plan activation was added.

## Demo branches

- `codex/demo-sub3-marathon`: advanced runner in sub-three shape, five calendar weeks before race week (about 4–6 weeks out), marathon peak phase.
- `codex/demo-sub17-5k`: advanced sub-17 aspirant, deep in a six-week-to-race 5K build.
- `codex/demo-trail-100k`: experienced trail runner nine weeks from a 100K, with climbing/fueling context and coordinated B2B preparation.

Each branch has the same reviewed application code and its own `demo/default-scenario.json`. Its launcher preloads twelve weeks of **entirely synthetic** activities, approved historical prescriptions, labeled work laps, recovery ratings, PRs, wellness and goal-scoped progression, then generates and approves a fresh block through the real API functions. The fixture history is designed to demonstrate established two-workout tolerance. It is not imported from Jake or another actual person.

### Beginner demo branches

- `codex/demo-beginner-marathon`: first marathon (~4:30), 18 weeks out, 10→16 mi/week history on 4 days in a three-up, one-down rhythm (last week was the down week), easy ~11:00/mi. Base phase, building.
- `codex/demo-beginner-mileage`: mileage goal of 25 mi/week, 8→11 mi/week history on 4 days, easy ~11:30/mi. No race, so the phase is `general`.
- `codex/demo-beginner-5k`: first 5K (~30:00), 8 weeks out, 5→8 mi/week history on 3 days, easy ~12:00/mi, rough 5K PR only.

These use optional scenario keys in `seed_demo`. Omitting them reproduces the three advanced fixtures exactly:

| Key | Default | Meaning |
|---|---|---|
| `goal_type` / `target_weekly_mileage` | `race` / none | `mileage` goals get no race date |
| `days_per_week`, `rest_days`, `long_run_day` | 6, `["sunday"]`, `saturday` | history runs on the non-rest days |
| `workouts` | `true` | `false` = easy-only history: long run ≈30% of the week (never shorter than the other runs), optional `strides` once a week, no workout days or laps |
| `years_running` | 8 | |
| `prs` | all four | partial: only the given PersonalRecord rows / `pr_*` fields |
| `ladder_level` | required | `null` seeds no progression; the plan API starts level 1 with no pace |

The launcher and seed CLI accept any `demo/scenarios/*.json` filename.

Beginner and introductory intermediate road programs now use a separate effort-based
progression (`core/developmental.py`). After two consistent completed weeks, one controlled
session can begin below the old 20 mpw workout gate, including on three-day schedules.
Ten easy / ten controlled / ten easy is the initial pattern; smaller budgets shorten it.
Completed work durations plus recovery earn repeated exposures before extending the dose
or changing its shape. These efforts never calibrate threshold/interval pace. Mileage holds
when a new step is introduced, then grows with the same workout repeated. Run frequency
is preserved with shorter easy days and tenth-mile allocation. Planned deloads require
actual training stress; fatigue still takes priority. Race-week pickups use a familiar,
reduced dose and a short shakeout. Advanced/expert and ultra generation is unchanged.
See [the full programs and review](demo-programs/README.md) for the simulations and limits.

After checking out a branch:

```sh
./start-demo.sh
# Or select any fixture explicitly:
./start-demo.sh sub17-5k
```

Open **http://localhost:3100**. Backend uses **127.0.0.1:8100**. Your regular app can keep running at 3000/8000. A prominent banner identifies synthetic data.

Data lives in `.demo/<scenario>/stride.db`, never `backend/stride.db`. First start automatically seeds it; subsequent starts preserve demo experiments. Dates are anchored to the local day the DB was first created, with no randomness. A separate temporary frontend source/build copy keeps Next's generated files out of the real frontend; each run's copy stays under `.demo/<scenario>/`. Both services bind only loopback. Garmin tokens, polling, AI keys and the AI worker are explicitly disabled by default; the demo has no password because it contains synthetic data and is loopback-only. Real app credentials/config are not copied. Never use `start.sh` to inspect a demo.

To reset, stop the demo, rename its `.demo/<scenario>` directory to a saved name, then run the launcher again. The seed CLI refuses any existing file or the personal DB, including resolved symlinks. No data files or credentials are committed: scenario JSON plus the deterministic loader is the preload.

Backend dependencies/venv and frontend node_modules must already be installed as for normal Stride. Ctrl+C stops only the demo's child processes.

To try the AI features (plain-language plan changes, coach reviews) on a demo, add `--ai`: `./start-demo.sh sub17-5k --ai`. It uses the OpenAI key from `backend/.env`, records AI consent for the synthetic athlete, and the banner shows "AI on". Calls are real and cost money; they count against the demo database's own monthly budget and daily request limit. Run several demos side by side with `--port 3110` (API on port + 5000).

Before shipping plan or settings changes, sweep every scenario for server errors (about 2-3 minutes):

```sh
cd backend && venv/bin/python scripts/sweep_demo_scenarios.py
# a demo you have been playing with (copied, never modified):
venv/bin/python scripts/sweep_demo_scenarios.py --database ../.demo/trail-100k/stride.db
```

It runs ~60 settings and goal changes, session actions (skip, replace, switch) and every switch preview at several clock offsets (mid-block, a week in, after the block ends) and exits non-zero on any 5xx.

## Verification

Tests use temporary databases and mocked providers. Coverage includes importer enqueue/merge/dedup/rollback, sync/wellness ordering, job leases/concurrency/retry/quota, adaptive dose/phase/spacing/earned-capacity gates, final ultra bounds, atomic companion cuts, stale options and derived-match normalization. Each synthetic scenario exercises historical evidence → real generation/approval → a new activity/feedback → revised block/approval. This demonstrates the loop on controlled data; it does not establish long-term training effectiveness.

The marathon fixture exposed an existing easy-pace sampling bug: high-volume athletes' labeled 9–10 mile easy runs were excluded by the 3–8 mile heuristic, leaving shorter workouts as the estimate. Analysis now prefers explicitly easy/recovery activities for recent and historical easy pace, with the legacy heuristic only as fallback. Regression coverage preserves the distinction; workout intensity calibration is unchanged.
