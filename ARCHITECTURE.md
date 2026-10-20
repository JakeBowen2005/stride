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
                            │ asyncio poll loop (every 10 min)
                            ▼
                         Garmin Connect (garminconnect library, token login)
                         Claude Haiku (coach feedback)
```

| Layer | Responsibility | Key files |
|---|---|---|
| Ingest | Pull runs and laps, merge legacy Strava rows, rebuild lap summaries | `services/garmin.py`, `services/lap_analyzer.py` |
| Wellness | Sleep, HRV, resting HR, body battery, readiness, training status, VO2max, race predictions | `services/wellness.py`, `api/wellness.py` |
| Training science | Paces, ladders, periodization, race weeks, ultra rules, readiness gates | `core/plan_engine.py`, `core/periodization.py`, `core/special_weeks.py`, `core/workout_ladders.py` |
| Adaptation | Feedback → ladder progression, fatigue downgrade, reschedule; LLM coach | `api/plans.py`, `core/workout_evaluator.py`, `services/coach.py` |
| UI | Today (readiness + run + recovery trends), Plan, History, Settings | `frontend/app/*`, `frontend/components/home/*` |

### Design choices worth knowing

- **Garmin via `garminconnect`, not the official API.** Garmin's Connect Developer
  Program is enterprise-only and closed to new applicants. The library logs in once
  (`garmin_login.py`, MFA supported), and only the session token is saved, never the password.
- **Polling, not webhooks.** Webhooks are only offered through the official program. The
  backend polls every `GARMIN_POLL_MINUTES`, and the app also syncs when it opens or comes
  back to the foreground. Incremental sync stops at the first known activity, and wellness
  data is throttled to one refresh per 20 minutes.
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
| Load | Baseline (last four full calendar weeks, empty weeks included; last completed week shown separately) → per-week budgets → long-term destination (e.g. a 75 mpw goal sets the direction and a cap; it is never prescribed all at once). Historical peak sets the default ramp rate, not a ceiling. Advanced mileage builders can repeat a modest increase from a supported recent high instead of restarting from the average. Reaching the destination holds; a lower destination comes down 10%/week. | `core/load_policy.py` |
| Fit | Easy days absorb whatever budget is left after the sessions actually placed. When a week can't hold its sessions it gives way in this order: long run → second quality day → easy-day length → number of easy days. Weeks are never padded to beat last week. 4 run days allow 1 workout; 3 allow none. General goals get 1 threshold session; quality stages progress from one session through light support to two substantial goal-specific sessions using completed rep evidence and recovery (`quality_policy.py`, `quality_history.py`). | `core/plan_validator.py`, `core/plan_engine.py` |
| Validate | One validator for generation and every later change: budget, rest days, no hard-after-hard across weeks or against real hard runs just before the plan. The only allowed pair is a flagged ultra back-to-back. | `plan_validator.validate_plan` / `enforce_no_back_to_back_hard` |
| Partial weeks | Days before the plan carry real miles (or 0); only the remainder is prescribed. | `generate_plan(completed_by_date, prior_hard_dates)` |
| Evaluate | Version-1 numeric prescriptions/executions for new sessions, legacy text fallback for old rows. Policy `eval-v2`. Per-rep evidence plus every prescribed rep are required to advance or recalibrate. Whole-run averages are weak evidence. Fade is checked before speed. One lever per decision. Decisions are persisted with their evidence. | `core/workout_evaluator.py`, `api/plans._apply_feedback_effects` |
| Adjust | Replacements rebalance unrun, unchanged easy mileage within the same weekly budget; completed runs and long runs stay protected. Explicit actions only ("skip" never reschedules). Reschedules go to future, unrun, non-adjacent easy days, within the weekly budget, or get an explanation. Side effects are claimed atomically, so retries and duplicate submissions apply once. The original prescription is kept. | `api/plans.submit_feedback` |
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
- In-process locks and an asyncio loop instead of a job queue. This is correct for one uvicorn worker only.
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

See [OpenAI coaching](docs/openai-coaching.md). Run feedback and explicit run/block reviews use bounded structured OpenAI Responses output. The model selects only server-authored, prevalidated alternatives; athlete acceptance rechecks freshness, completion locks, schedule and budget, records original prescriptions and commits atomically. Model output never changes fitness or activates plans. Cached reviews, daily attempt limits and explicit fallback preserve deterministic coaching when the provider is unavailable.
