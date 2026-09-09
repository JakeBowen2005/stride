# Code Review + Goal Change — September 9, 2026

> Companion to `2026-09-09-handoff.md`. That doc describes the system as
> designed; this one records what a review found, what was changed, and what
> is still open.
>
> Trigger: goal changed from **sub-17 5K** to **sub-2:45 marathon, Feb 2028**.

---

## The headline finding

The marathon workout library in `core/workouts.py` was dead code.

`plan_engine._pick_workout_progressive()` falls back to the old rotation
library only when `progression_state` is absent — but `_load_progression_state()`
creates a row for every user on first call, so state is *never* absent.
Every workout therefore came from `workout_ladders.py`, which contained only
`THRESHOLD_LADDER_5K` and `INTERVAL_LADDER_5K`, and `get_ladder()` ignored its
`distance` argument entirely.

Net effect: switching the goal to a marathon would have produced a 5K training
plan with marathon pace numbers stapled on. `3x2mi at threshold` — the single
workout that built the 2:58 — could not be prescribed at all.

Only long runs read the distance-aware library, which is why the marathon long
runs looked right and nothing else did.

---

## Changes made

### Marathon support

| Change | File |
|---|---|
| Added `THRESHOLD_LADDER_MARATHON` (2x2mi → 3x2mi → 2x3mi → 4x2mi → 3x3mi → MP blocks) | `core/workout_ladders.py` |
| Added `INTERVAL_LADDER_MARATHON` (1K/mile/1.5mi reps; VO2max as maintenance, not the main course) | `core/workout_ladders.py` |
| `get_ladder()` now routes by distance; added `ladder_length()`, `max_level()` | `core/workout_ladders.py` |
| `determine_starting_level()` is distance-aware — 6x800m is level 5 on the 5K ladder, level 3 on the marathon one | `core/workout_evaluator.py` |
| Progression rows carry a `distance` column; changing goal distance re-seeds both ladders from recent Strava history instead of reusing a level number that now means a different workout | `models/progression.py`, `api/plans.py` |
| Added `ensure_schema()` — additive column migrations, since there is no Alembic and `create_all()` won't ALTER an existing table | `database.py`, `main.py` |

### Pacing correctness

**Tempo and threshold were inverted.** `tempo = threshold * 0.96` made
continuous tempo *faster* than threshold, and the ladder then subtracted
another 10 sec/mi for broken reps. `training-principles.md` says the opposite:
broken reps with rest are ~10 sec/mi faster than a continuous tempo. Now
`tempo_pace = threshold_pace + 10`, and the ladder's `{tp_fast}` lands exactly
on threshold.

**`race_pace` was nonsense for a marathon goal.** The calibrator estimates it as
`interval_pace * 1.05` — i.e. from 800m splits. That is roughly 5K effort. Any
ladder level referencing race pace would have prescribed 5K reps labelled
"marathon pace". `race_pace` is now the goal pace whenever a goal exists.

**Goal-derived paces are distance-aware.** New `GOAL_PACE_OFFSETS` table:
threshold is 27 sec/mi *faster* than marathon pace but 30 sec/mi *slower* than
5K pace. The old code applied a single marathon-shaped offset to everything.

**Longer reps now get slower paces.** `interval_pace` is anchored on 800m
splits (what the calibrator parses most often), so each ladder level carries a
`rep_adjust_sec`: 1K +5, mile +12. Previously 4x1mi was prescribed at 800m
repeat pace — for Jake that meant mile repeats at 5:42 when his real mile
repeats are 6:06-6:24.

**Goal-pace work is gated.** New `_mp_is_realistic()`: race-pace workouts are
withheld until goal pace is at least 15 sec/mi slower than current threshold.
Prescribing 6:17 MP reps while threshold sits at 6:35 asks for a workout harder
than the threshold session it exists to support. When gated, the plan says so
in its notes and substitutes steady-effort work.

**Blend clamp.** Weekly mileage is a weak fitness proxy, and an ambitious goal
dragged the inferred paces well past anything demonstrated. Goal-blended
threshold and interval paces are now capped at 20 sec/mi faster than the
effort-derived baseline per block. Real Strava splits override this entirely —
measured beats inferred.

### Bugs fixed

**Deload never fired.** `wk_is_deload = is_deload and wk == 0 and not current_week_overlap`,
but week 0 always starts on Monday of the current week, so `current_week_overlap`
was always true. No deload week had ever been generated. Now the block picks
the first week that isn't already underway.

**The threshold ladder could not mathematically advance.** With no parseable
rep splits (every time-based and continuous session), the evaluator compared
the *whole run's* average pace — warmup, cooldown and recovery jogs included —
against the prescribed rep pace. That reads ~90 sec/mi slow no matter how well
the reps went, so `pace_diff <= 5` was unreachable and every threshold session
returned HOLD or REGRESS forever. The evaluator now tracks `pace_confidence`
and judges effort-only sessions on feel and completion.

**2mi/3mi rep splits weren't parsed at all.** `extract_splits_from_description()`
handled 200m through 1 mile. `3x2 miles (6:36,6:36,6:20)` — the staple marathon
threshold workout — produced nothing. Added `_extract_long_rep_paces()`.

**Peak long runs ignored the weekly mileage budget.** `run_type: peak_fixed`
entries carry a hardcoded `total_miles`, so a 19mi MP sandwich could land in a
deload week and blow the target by 12 miles. Now filtered against the week's
actual allocation, and excluded from deload weeks entirely.

**Deload weeks barely deloaded.** `_distribute_mileage()` mapped workout days to
`[wo1, wo2]` positionally. A deload week places only the threshold session, so
`wo1_miles` read 0 and the whole workout allocation was re-spent on easy days.
A "deload" came out 62.5mi against a 63mi build week. Now 50.5mi.

**Deload kept the wrong session.** It kept whichever workout was placed first —
the VO2max session. A deload keeps controlled aerobic work; speed work is the
first thing to drop. Now keeps the threshold/MP session.

**`weekly_avg()` over-reported mileage.** It divided total miles by the span
between the first and last run *inside* the window, not the window length. Two
weeks off followed by one 40mi week reported as "40 mpw" instead of 10 — and
that number feeds the mileage ramp directly. Now a fixed denominator.

**ACWR wasn't ACWR.** It compared a 4-week average to a 12-week average, which
smooths away exactly the one-week spike the ratio exists to detect. Now the
standard 7-day vs rolling 28-day.

**Strava rate limiting was ~6x over the limit.** The sync fired 10 requests
back to back then slept 2 seconds — roughly 600 requests per 15 minutes against
a 100-request limit. The resulting 429s were swallowed by `except Exception: pass`,
so a "successful" sync silently left hundreds of activities with no description,
which is precisely the data the pace calibrator reads. Added a real token
bucket (90 per 15 min, 900 per day), a `StravaRateLimited` exception, and
progress reporting so a partial sync says how much is left.

**`sync_all_to_db` matched activities by `external_id` alone**, without a
`user_id` filter — a cross-user collision waiting to happen.

**Webhook processed inline.** Strava expects a 200 within 2 seconds and retries
otherwise. Now returns immediately and processes in a `BackgroundTask` on its
own DB session, and re-runs classification so a new run is typed without a
manual re-classify.

**OAuth callback returned JSON**, leaving the athlete on a raw JSON page at the
end of the flow. Now redirects to `settings.frontend_url`.

**Coach docs path breaks on Railway.** `DOCS_DIR` resolved to `<repo>/docs`,
but the deploy sets the service root to `backend/`, so every science doc loaded
as `""` — the coach kept answering, just with none of its training context and
no error. Now checks several locations, honours `STRIDE_DOCS_DIR`, and warns
when a doc is missing.

**Workout category detection missed every marathon workout name.**
`_detect_workout_category()` only knew 5K titles. `MP Pace Run — 4mi`,
`3x2mi Threshold` and `Progressive 8mi` all returned `None`, which skipped
evaluation entirely. Rewritten, checking threshold patterns first so `3x2mi`
isn't misread as interval work.

### Progression

The evaluator now returns `advance_steps`. Two levels are granted when the
athlete beats the prescribed pace by 5+ sec/mi at feel 9-10 with no fade — the
"experienced rebuilder" case `training-principles.md` describes, but derived
from evidence rather than an athlete-type label. Level ceilings come from the
actual ladder length instead of a hardcoded 12.

A session cut short by 2+ reps now HOLDs regardless of how fast the completed
reps were.

### Docs

`athlete-profile-jake.md` — which is injected into every coach LLM call —
retargeted to the 2:45 marathon: gap analysis, the volume and threshold numbers
2:45 actually requires, a proposed 17-month sequencing, and the marathon ladder
starting positions. The stale May 2026 fitness snapshot is now explicitly
marked stale, deferring to the analyzer at generation time.

### New

`backend/scripts/set_goal.py` — set the active goal directly against the DB,
with a warning when the distance change invalidates progression levels.

---

## Verification

Third-party deps are not installed in the review environment, so the app was
not booted. What *was* verified:

- All 26 backend modules parse; every internal `from app.X import Y` resolves
- `plan_engine.generate_plan()` exercised directly across five scenarios
  (rebuild / deep build / calibrated paces / deload block / peak block)
- `workout_evaluator.evaluate_workout()` unit-checked on real Strava
  description formats from Jake's log

**Not verified: anything touching the database, the API, Strava, or the LLM.**

---

## Still open

1. **No tests.** `backend/tests/` contains one empty `__init__.py`. The plan
   engine and evaluator are pure functions with no I/O — they are trivially
   testable and are exactly where a silent wrong answer costs the most.
2. **No auth; `user_id` is hardcoded to `1`** in six frontend files.
3. **No medium-long midweek run.** At 65mpw the engine spreads easy days
   evenly at 8-9mi. Pfitzinger's midweek 10-13mi is a marathon staple and is
   currently absent.
4. **No taper logic.** `goal.race_date` is stored but never read by the plan
   engine. The 3-week taper in `marathon-training-science.md` is not implemented.
5. **No periodization phase.** Base/build/peak/specific is documented but the
   engine has no concept of where in a cycle it is — only a block number.
6. **Settings page is read-only.** No way to change goal, rest days, days per
   week, or edit a prescribed workout from the UI.
7. **No weekly summary endpoint** (Priority 2 in the handoff).
8. **`lib/api.ts` is dead code** — every path in it is a route that does not
   exist on the backend.
9. **Timezone handling.** Activity dates are Strava's `start_date_local` parsed
   as if UTC. SQLite silently drops the offset so it works by accident; Postgres
   will not be so forgiving.
10. **Backend still not deployed.** Nothing in this review changes that.

---

# Part 2 — Backend build-out (same day)

Context that changed the priorities: Jake has **not run in ~6-8 weeks** (lifting
and jiu jitsu daily, occasional unstructured runs), plans to start building
miles around **November 2026**, and to train seriously from **early 2027**.
Race target confirmed as **Surf City Marathon, Huntington Beach, February 2028**.

## The ramp was broken at zero

`ceiling = min(peak * 0.9, current * 1.5)` collapses when current mileage is
near zero. Measured before the fix:

| Current mpw | Week 1 target |
|---|---|
| 0.0 | **0.0 mi** |
| 1.5 | 2.2 mi |
| 4.0 | 6.0 mi |

An athlete at zero was handed an empty week. Replaced with an **absolute-step
return ramp** (`_return_to_running_targets`): anchored on training history
rather than on recent mileage, capped at 30% of established peak for the whole
return phase, with a step size that shrinks as volume returns so it hands off
smoothly to the percentage ramp at 12 mpw instead of jumping at the seam.

From zero, Jake now gets 13.0mi across 3 runs in week one, 14.5 across 4 in
week two. All easy. No quality until ~28 mpw.

## Periodization and taper

New `app/core/periodization.py`. `goal.race_date` was stored but never read —
there was no taper at all.

- Phase per week from weeks-to-race: base / build / specific / taper / race week
- Marathon taper is 3 weeks at 80% / 60% / 40% of recent peak (PMC 2021: strict
  3-week tapers associated with finishes 2.6% faster); half 2 weeks, 5K/10K 1
- **Frequency and intensity are maintained, only volume drops** — Bosquet's
  meta-analysis is unambiguous that cutting training days tapers worse
- Race day itself is generated: the day before becomes a 2mi shakeout, two days
  before becomes rest
- Taper-specific workouts, because ladder levels carry a fixed `total_miles` —
  a level-8 threshold session is 12.5 miles whether you are 12 weeks out or 6
  days out. The two weekly slots get different sessions (short and sharp
  Tuesday, race pace Thursday).

Measured taper from 68 mpw: **68 → 50 → 35 → 22.5 + race**.

## Volume gates

Tests caught the engine prescribing an **11-mile workout inside a 20-mile
week** — 55% of the week in one session, and longer than that week's long run.
Three fixes:

- `QUALITY_MILEAGE_FLOOR` is distance-aware. Marathon quality work needs 28 mpw
  (advanced) / 34 (other); 5K needs 18 / 20. The smallest marathon threshold
  rung is 7.5 miles, so the floor has to be higher.
- Second weekly workout requires 40 mpw for marathon/half, 28 for 5K/10K
- `_fit_workout_to_week` walks down the ladder until the session fits the
  week's budget, and returns `None` — leaving the day easy — if nothing does
- When only one quality session fits, endurance goals get the threshold
  session, not the VO2max one

## Plan editing

Principle 4 — respect the athlete. All warn on principle violations, none refuse.

```
PATCH /api/plans/{user_id}/days/{date}          partial edit
POST  /api/plans/{user_id}/days/{date}/swap     swap two days' prescriptions
POST  /api/plans/{user_id}/days/{date}/skip     turn a day into rest
POST  /api/plans/{user_id}/days/{date}/reroll   different session, same stimulus
```

## Weekly summary

`GET /api/plans/{user_id}/weekly-summary?week_start=YYYY-MM-DD`

New `app/services/summary.py`. Planned vs actual mileage, workout execution,
feel trend, trailing 4-week comparison, per-run detail. **The numbers are
computed in Python; the LLM only interprets them.** Deterministic template
fallback when no API key is set.

## Deployment hardening

- **Timezone.** Strava's `start_date_local` is local wall-clock time suffixed
  with `Z`. Parsing that `Z` as UTC produced tz-aware values that SQLite
  silently truncated (working by accident) and that Postgres would store
  shifted by the athlete's offset — runs landing on the wrong day, breaking
  plan-to-activity matching. Now parsed to naive local via
  `parse_local_datetime()`. `utcnow()` comparisons switched to local to match.
- **Portable date filtering.** `func.date(x)` is a SQLite builtin Postgres
  lacks. The first fix — `cast(x, Date)` — is valid SQL but SQLite has no DATE
  type, so NUMERIC affinity turned `2026-09-07 07:00:00` into the integer
  `2026` and every comparison matched nothing. *The integration tests caught
  this.* Now half-open datetime ranges, which work identically on both and can
  use an index.
- **Postgres URL + driver.** Railway hands out `postgres://`; SQLAlchemy 2.x
  only accepts `postgresql://`. Normalised, psycopg 3 dialect pinned,
  `pool_pre_ping` enabled so idle-dropped connections reconnect.
- **Experience classification.** Required >365 days of history, so six months
  at 48 mpw classified as "beginner" and capped the ramp at 10%/week. Now
  judged on demonstrated volume first, history length second.

## Tests

**136 tests, all passing.** `pytest.ini` + `tests/conftest.py`;
`requirements-dev.txt` added.

| File | Count | Covers |
|---|---|---|
| `test_plan_engine.py` | 47 | ramp, structure, deload, pacing, taper, gating |
| `test_workout_evaluator.py` | 33 | split parsing, fade, progression decisions |
| `test_ladders.py` | 34 | all 4 distances x 2 categories render correctly |
| `test_api_integration.py` | 22 | full loop against a real DB |

Every test in `test_plan_engine.py` corresponds to a bug that actually shipped.

Two bugs were found *by* the tests during this session: the 11-mile workout in
a 20-mile week, and the SQLite `CAST` regression above.

## Also

- `docs/product-vision.md` — the four-step end state: sign up, sync, set goal,
  plan builds. Everything else inferred from data.
- `docs/deployment.md` — full Railway + Vercel walkthrough with verification steps.
- `backend/scripts/set_goal.py` — set the goal from the CLI.

## Verified

The backend now boots. 33 routes register. The integration suite exercises the
real API against a real database: seed → analyze → set goal → generate → edit →
feedback → summary → switch goal distance → regenerate.

**Still not verified:** anything touching live Strava or the Anthropic API.
Both are exercised only through their fallback paths.
