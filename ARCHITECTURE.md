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
- Block preview and approval ("Approve" / "Make it lighter") before each 2-week block.
- Move / swap / skip a day from the plan, with the no-back-to-back rule re-checked.
- Easy-day effort checks from HR (not just distance), and pace-vs-target on Today.
- A Stride/VDOT race prediction next to Garmin's.
- Push structured workouts to the watch.
