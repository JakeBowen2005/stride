# Stride — Architecture

How the system works today, the trade-offs taken on purpose for a single-athlete
app, and the plan for scaling to many athletes.

## Today (single athlete, self-hosted)

```
 Phone / laptop ──HTTP──▶ Next.js 16 (port 3000, LAN)
                            │ proxy.ts: password gate (cookie)
                            │ /api/* rewrite (same origin, no CORS)
                            ▼
                         FastAPI (127.0.0.1:8000, not exposed)
                            │ SQLAlchemy ─▶ SQLite (WAL)
                            │ asyncio poll loop (15 min, hourly overnight; app-open sync resets it)
                            ▼
                         Garmin Connect Personal API (official, API key → 24h bearer)
                         OpenAI bounded adviser (template fallback when unavailable)
```

| Layer | Responsibility | Key files |
|---|---|---|
| Ingest | Pull runs and laps, merge legacy Strava rows, rebuild lap summaries | `services/garmin.py`, `services/lap_analyzer.py` |
| Wellness | Sleep, HRV, resting HR, body battery, stress (readiness/status/predictions are not in the Personal API) | `services/wellness.py`, `api/wellness.py` |
| Training science | Paces, ladders, periodization, race weeks, ultra rules, readiness gates | `core/plan_engine.py`, `core/periodization.py`, `core/special_weeks.py`, `core/workout_ladders.py` |
| Adaptation | Feedback → ladder progression, fatigue downgrade, reschedule; LLM coach | `api/plans.py`, `core/workout_evaluator.py`, `services/coach.py` |
| UI | Today (readiness + run + recovery trends), Plan, History, Settings | `frontend/app/*`, `frontend/components/home/*` |

### Design choices worth knowing

- **Garmin via the official Personal API.** Garmin opened self-service Personal API keys in
  Oct 2026. `services/garmin_api.py` exchanges `GARMIN_API_KEY` for a 24h bearer token (in memory;
  re-exchanged on 401) and replaced the unofficial `garminconnect` login-as-you scraper. Laps come
  from the activity's FIT file (the API has no `/splits`); lap times are the watch's timer time.
- **Pull-only, so cheap polling.** The Personal API has no webhooks. Incremental sync is one
  date-windowed request (`activityType=running`, newest stored run minus 2 days), and only new runs
  cost a FIT download. Wellness is three range requests. `poll_due` skips background checks when any
  sync ran within `GARMIN_POLL_MINUTES` and drops to hourly in quiet hours.
- **Laps → workout text.** The pace calibrator and evaluator were built to parse
  "6x800 (3:01, ...)" notes. `lap_analyzer` writes that text from Garmin laps
  (structured-workout intensities first, then pace vs. the athlete's easy pace on that
  date), so progression works without typing splits.
- **Merge, don't duplicate.** Legacy Strava rows are matched by start time (±10 min)
  and distance (±5%) and upgraded in place, keeping notes, feel ratings and plan links.
- **Fail safe everywhere.** Readiness gates suggest a stepping-stone race. A hard day
  next to another hard day gets downgraded. Recovery signals only ever suggest easing off.
  Feedback re-submits never re-run plan side effects.
- **One source of paces.** `plan_engine.effective_paces()` feeds both the workouts
  and the pacing guide, so the numbers on screen can't disagree.

### The coaching loop (set goal → block → sessions → evaluation → next block)

| Step | Rule | Code |
|---|---|---|
| Load | Baseline (last four full calendar weeks, empty weeks included; last completed week shown separately) → per-week budgets → long-term destination (e.g. a 75 mpw goal sets the direction and a cap; it is never prescribed all at once). Historical peak sets the default ramp rate, not a ceiling. Advanced mileage builders can repeat a modest increase from a supported recent high instead of restarting from the average. Reaching the destination holds; a lower destination comes down 10%/week. After a down week, growth resumes from the training level (the full-volume weeks), not the deload-dragged average. Spikes and missed weeks keep the average, and fatigue recovery starts from it. | `core/load_policy.py` |
| Fit | Easy days absorb whatever budget is left after the sessions actually placed. The established full-quality path gives way in this order: long run → second quality day → easy-day length → number of easy days. Weeks are never padded to beat last week. That path allows 1 workout on 4 days and none on 3; the introductory path below permits one controlled session on 3 days. Quality stages progress from one session through light support to two substantial goal-specific sessions using completed rep evidence and recovery (`quality_policy.py`, `quality_history.py`). | `core/plan_validator.py`, `core/plan_engine.py` |
| Introductory road training | Beginner/intermediate runners without established full-quality tolerance use a separate `development` duration track: easy bookends around controlled continuous, short-rep and long-rep work. Two consistent running weeks permit introduction; four successful full-dose exposures earn a beginner step, two an intermediate step. Work duration plus recovery does not establish threshold intensity or calibrate pace. A new step holds mileage for its first week; subsequent weekly growth is capped at 10% from repeatable completed volume. Tenth-mile allocation preserves frequency with shorter easy runs. Planned deloads need accumulated quality exposure or mileage growth, not old stable easy history alone. Race-week work is reduced and familiar. Advanced/expert and ultra paths are unchanged. | `core/developmental.py`, `core/load_policy.py`, `core/workout_evaluator.py` |
| Validate | One validator for generation and every later change: budget, rest days, no hard-after-hard across weeks or against real hard runs just before the plan. The only allowed pair is a flagged ultra back-to-back. | `plan_validator.validate_plan` / `enforce_no_back_to_back_hard` |
| Partial weeks | Days before the plan carry real miles (or 0); only the remainder is prescribed. | `generate_plan(completed_by_date, prior_hard_dates)` |
| Evaluate | Version-1 numeric prescriptions/executions for new sessions, legacy text fallback for old rows. Policy `eval-v2`. Per-rep evidence plus every prescribed rep are required to advance or recalibrate. Whole-run averages are weak evidence. Fade is checked before speed. One lever per decision. Decisions are persisted with their evidence. | `core/workout_evaluator.py`, `api/plans._apply_feedback_effects` |
| Adjust | Replacements rebalance unrun, unchanged easy mileage within the same weekly budget; completed runs and long runs stay protected. Explicit actions only ("skip" never reschedules). Reschedules go to future, unrun, non-adjacent easy days, within the weekly budget, or get an explanation. Side effects are claimed atomically, so retries and duplicate submissions apply once. The original prescription is kept. | `api/plans.submit_feedback` |
| Schedule change | Changing run days, rest days or long-run day mid-block is logistics, not new fitness (`mode: "schedule"`). The approved block is kept: workouts, long runs and completed days stay; an added day becomes a short recovery/easy run (preferably after the long run). It is funded by a small experience-based allowance (beginner/comeback 0, intermediate 5%, advanced/expert 8% of the week, max 3 mi), otherwise by trimming easy days. With no room, the day waits for the next block. Removed days drop easy runs first and move their miles. A workout on a new rest day moves to a safe easy day or is dropped. Every changed day is recorded with its reason. | `core/schedule_revision.py`, `api/plans._revise_schedule` |
| Change guard | Every schedule revision is checked before it is offered: no added quality, long runs unchanged, growth ≤ allowance and ≤ 10%, no runs on rest days, no more run days than chosen, easy runs ≥ 2 mi, never hard-after-hard. A failure refuses the change. Full rebuilds report a per-week "what changed" summary against the approved block. | `core/change_guard.py` |
| Structured long runs | Marathon-pace, steady and race-effort long runs carry numeric prescriptions (`long_run_prescription`), and the block review verifies them from laps like workout reps (paced segments ≤10 s/mi slow). A long run shortened to fit a week becomes a plain easy run. | `core/workout_data.py`, `api/plans._assess_previous_block` |
| Approve | Generation (both `/generate` and `/preview`) saves an inactive draft. Approve validates current context and schedule and atomically switches active plan; Make it lighter reduces volume via the existing recovery policy. Changed training/settings require a fresh preview. | `api/plans.approve_draft` |
| Programs | Versioned distance/category ladders with phase-specific content; goal transitions preserve recent demonstrated pace but use the new program’s own level. Numeric work renders its display; calibration is independent by category and requires distinct recent workout days. | `workout_ladders.py`, `workout_data.py`, `pace_calibrator.py` |
| Next block | The previous block (if it ended within a week) is assessed on completed vs planned miles, quality sessions done and feel, giving build / hold / reduce / recovery. Missing feedback isn't a bad rating, and missed miles aren't repaid. Deloads come from completed calendar history (3/4/7/8 sustained loaded weeks for beginner/intermediate/advanced/expert; natural lighter weeks reset the count). Activation is atomic. | `core/block_assessment.py`, `load_policy.deload_due`, `api/plans.generate_training_plan` |
| Explain | The coach runs after the deterministic decision and is given it, so its wording can't contradict what was applied. | `services/coach.py` |

These numbers (ramp rates, 85%/60% completion thresholds, deload cadence, quality
budget) are conservative Stride policy drawn from `docs/training-principles.md`.
They are not universal science. `training-principles.md` allows advanced runners
15–20% per week, while `CLAUDE.md` asks for "slightly faster than 10%". The engine
uses 10–20% depending on how far below a prior peak the athlete is.

Current-block revision preserves the approved date window and locks completed days. Historical weeks retain actual totals; a week already at its revised allowance receives rest, not an impossible retroactive cut. Recent poor feel ratings can trigger recovery before the five-run-day block-assessment minimum. Next-block generation is only offered after completion; revision is a separate explicit action. Preview fingerprints normalize derived completion so a read cannot invalidate approval.

Experience and quality-stage policy: `docs/research/quality-stage-progression.md`. Stages are persisted in the athlete snapshot; adding a second substantial session holds weekly volume until two completed dual weeks.

Personal coaching source provenance and policy mapping: `docs/research/README.md`. Profile edits persist through `/api/users/{id}/profile`, with merged schedule validation; changed settings require a new preview. Time preference changes workout bookends and light support format, not threshold intensity.

Detailed policy numbers, sources and remaining evidence/UI limitations: `docs/coaching-policy-decisions.md`. The default `tempo = threshold * 0.96` remains deliberate; mileage-to-goal-pace blending has been removed because mileage alone does not demonstrate speed.

### Known shortcuts (deliberate for one athlete)

- `user_id` is part of the URL and is `1` in the frontend (`lib/api.ts`). There's no per-user auth;
  the LAN password gate protects the whole app.
- A durable local review-job table plus in-process Garmin locks and asyncio pollers. One uvicorn worker and one service instance are required; this is not a distributed queue.
- SQLite with a small additive migration helper (`database.add_missing_columns`)
  instead of Alembic.
- `analyze_athlete` recomputes from full history on each call (fine at ~600 runs).

## Scaling plan (1 → thousands of athletes)

1. **Auth and tenancy.** Session/JWT auth with a `get_current_user` dependency, and `user_id`
   removed from paths. Every query is scoped to the authenticated user, and the
   `default_user_id` setting is dropped.
2. **Official integrations.** Apply to the Garmin Connect Developer Program (OAuth,
   push/ping webhooks for activities and health) and add Strava OAuth + webhooks as a second
   source. Store per-user tokens encrypted (KMS envelope / Fernet) on `GarminConnection`.
   Screen-scraping thousands of accounts from one IP is neither allowed nor reliable.
3. **Job system.** Webhook → enqueue `sync_user(user_id, since)` on Arq/Celery (Redis)
   or a Postgres-backed queue. Add a per-user lock (advisory lock / `SET NX`), a per-provider
   token-bucket rate limiter, retries with jittered backoff, and a `sync_jobs` status table.
   This replaces the poll loop, the module-level locks and the in-memory job dicts.
4. **Database.** Postgres + Alembic (`render_as_batch` during the SQLite period). Real
   `Date` columns for plan/goal/wellness dates, UTC-aware timestamps plus `User.timezone`
   (per-user "today"), and a `laps` table or JSONB for splits.
5. **Precompute derived data.** Maintain weekly mileage, rolling easy pace, ACWR and
   PRs incrementally on ingest instead of recomputing from full history per request.
6. **LLM cost control.** Run coach calls as queued jobs (202 + poll/SSE). Track per-user
   token usage and cost (usage is already logged) and enforce the monthly budget.
   Treat athlete free text as untrusted prompt input.
7. **Observability.** Structured logs with request IDs, Sentry, and metrics for sync lag
   (watch upload → Stride), provider error/429 rates, queue depth, and LLM tokens and cost.
8. **Frontend.** A typed client generated from OpenAPI (`response_model`s on every route),
   TanStack Query or Server Components for data, error boundaries, and real onboarding
   wired to the backend.

## Product roadmap (from the PM review)

- Automatic post-run coach analysis on sync (splits, HR drift, prescription vs actual),
  before the athlete rates the run.
- Implemented: persisted block preview and approval ("Approve" / "Make it lighter") before each block.
- Implemented: move / replace / skip unrun sessions, with budget, rest preferences and hard-day spacing checked transactionally.
- Easy-day effort checks from HR (not just distance), and pace-vs-target on Today.
- A Stride/VDOT race prediction next to Garmin's.
- Push structured workouts to the watch.


## OpenAI adviser

See [OpenAI coaching](docs/openai-coaching.md). Run feedback and explicit run/block reviews use bounded structured OpenAI Responses output. The model selects only server-authored, prevalidated alternatives; athlete acceptance rechecks freshness, completion locks, schedule and budget, records original prescriptions and commits atomically. Model output never changes fitness or activates plans. Cached reviews, daily attempt limits and explicit fallback preserve deterministic coaching when the provider is unavailable. A synced run, or a comment saved on one, also queues a refresh of the active plan's coach perspective (`coaching_jobs` rows with `plan_id`), run after that run's own review so the block sees the comment and review; unchanged evidence is never re-queued.


## Synced-run jobs, session choices and demos

See [automatic reviews and adaptive choices](docs/adaptive-sessions-and-demos.md). Garmin import transactionally queues recent new/merged runs; a durable local leased worker reviews them after sync/wellness. Feedback remains human evidence. A shared personalized session menu powers athlete replacement and AI IDs, enforcing earned weekly capacity, phase, dose, budgets and actual completed training. Synthetic scenario branches preload isolated databases and frontend copies via start-demo.sh; they never connect to Garmin/OpenAI or the personal database.

## Coaching trust and cloud operations

See [coaching trust hardening](docs/coaching-trust-hardening.md) for activity identity, reversible classification, partial-work evidence, execution-aware block assessment, stale-advice handling and the shared completed-calendar-week workload definition. [Deployment recovery](docs/deployment-recovery.md) covers pre-migration backups, verified restores, scheduled snapshots and optional encrypted offsite export. Settings exposes operational status, and health/readiness have separate endpoints. Existing cookies require sign-in again after the expiring-session upgrade.


## Plain-language plan changes, running hours, multi-user prep (Oct 2026)

- **Plan changes** were built and then removed (Oct 28 2026; see `docs/plain-language-plan-changes.md`).
  Athletes rearrange by hand with **Switch** (`POST /api/plans/{id}/sessions/{date}` with
  `action: switch`; `GET …/switch-targets` previews every same-week day). `_resolve_switch` tries the
  direct swap, shifts a back-to-back long-run pair together, or finds the smallest same-week
  rearrangement (long runs stay put) that passes `_validate_schedule`. Nothing is written until applied.
  Long-run spacing lives in `validate_plan` for every plan.
  Switch applies only with the returned `switch_token`, which binds the exact layout to the plan,
  preferences, activity evidence and athlete date; stale approvals return 409 and the UI reloads choices.
  Taper/race weeks remain reduce-only. `load.rest_date_overrides` persists approved date-specific
  rest exceptions within the block, and validation includes completed long runs before its start.
- **Running hours** (`docs/aerobic-hours.md`): `/analysis/{id}/mileage` returns moving, elapsed and
  planned seconds; `services/aerobic_hours.shadow` records hours budgets and a longest-session guard on
  each new block (`load.shadow_hours`) without enforcing them.
- **AI spend**: `services/ai_budget` prices recorded tokens per model and enforces monthly caps
  (`OPENAI_MONTHLY_BUDGET_USD`, per athlete and owner) on top of the daily attempt limits. AI consent is
  required in every mode, the owner included.
- **Garmin attribution**: `activities.device_name`, "Garmin <device>" on run views, a derived-data line
  on AI reviews, and an attribution field in the export. `/terms` acceptance is recorded at registration.

## Season safety (Oct 28 2026)

- **Post-race rest** (`special_weeks.apply_post_race_rest`, `periodization.POST_RACE_REST_DAYS`): no running for
  1 (5K) to 14 (100 mi) days after the race, on whatever weekday it falls, and no long run or workout in the
  week after that. Only prescribed days change; the week total only goes down.
- **Road long-run caps** (`plan_engine.ROAD_LONG_RUN_CAP`): 5K 15 mi/120 min, 10K 16/135, half 18/150,
  marathon 22/210, whatever share of a big week the long run would otherwise get.
- **Midweek starts** prescribe the remaining days at their normal size (prorated, when that cuts the week by
  more than 10%) and later weeks ramp from that week or the demonstrated level, never from the full week.
- **Road readiness**: `check_readiness` projects the half/marathon long run and volume with the same safe-ramp
  estimate as the goal route (`outlook._weeks_to_grow`) and warns, with an override, when they can't be
  reached before taper.
- **Season simulator** (`tests/season_sim.py`, `tests/test_season_matrix.py`): seeds an athlete, runs every
  prescribed session, and generates and approves each block to race day, then checks season-level rules.
  A subset runs in CI; `STRIDE_SEASON_FULL=1` runs every athlete × distance.
- **Season quality**: introducing a second hard session holds the training level (capped by the last two
  completed weeks), not the deload-dragged 4-week average, so peak no longer drops below build. Marathon
  race-pace long runs stay in build/peak at the `support` stage too. Race week keeps more volume for short
  races (`RACE_WEEK_VOLUME_BY_DISTANCE`, `RACE_WEEK_MAX_EASY`).
