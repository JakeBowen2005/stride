# Stride: project brief for resume writing

> Purpose: give another agent (or a recruiter-facing writer) an accurate, complete picture of
> Stride so it can write resume bullets, a project description, or interview talking points.
> Facts below come from the repository as of 2026-10-21. A "Do not claim" section is at the end.

## One-line summary

**Stride** is a full-stack, AI-assisted running coach web app. It syncs a runner's Garmin data,
builds science-based two-week training plans that adapt to what the athlete actually runs, and
uses a bounded LLM coach to explain each run and suggest pre-validated plan changes.

## Project facts

| Item | Detail |
|---|---|
| Type | Personal project, solo developer (Jake Bowen) |
| Dates | May 2026 to present |
| Status | Deployed and in daily personal use on Render (single athlete) |
| Users | One real athlete (the developer, a 2:58 marathoner) plus six synthetic demo athletes |
| Repo | github.com/JakeBowen2005/stride (public) |
| Size | ~11.5k lines of Python application code, ~4.6k lines of backend tests, ~7.5k lines of TypeScript/TSX |
| Tests | 545 backend tests (pytest) and 19 frontend tests, run in CI on all 7 weekdays (date-independent) |
| API | 37 REST endpoints (FastAPI) |
| Process | 17+ merged pull requests with CI, code review and written PR descriptions |
| Development style | AI-assisted development (Claude Code / Codex agents). Jake set product direction, coaching rules and acceptance criteria, reviewed changes, and tested on his own training data. |

## The problem it solves

Off-the-shelf plans (Garmin Coach, Runna, generic PDFs) prescribe unrealistic paces and
over-complicated workouts, and they don't react to what the runner actually did. Stride's
philosophy: "simple but specific" workouts that real competitive runners use, conservative
mileage building (injury prevention), and every workout explained.

## Tech stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2, Pydantic, SQLite (WAL mode), pandas/NumPy, asyncio background workers
- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Recharts
- **AI:** OpenAI Responses API (gpt-5.4-mini) with Pydantic structured outputs; template fallback when AI is unavailable
- **Data source:** Garmin Connect via the `garminconnect` library (token login, polling sync)
- **Infra:** Docker (multi-stage: Node build plus Python runtime), Render web service with a persistent disk, GitHub Actions CI (lint, type check, tests, production build, container smoke test), Vercel preview builds, optional encrypted S3 backup export (boto3)
- **Quality tooling:** pytest, ruff, ESLint, `tsc --noEmit`, Node test runner

## Architecture (how it fits together)

```
Phone / laptop ──▶ Next.js 16 server (password-gated; proxies /api to the backend)
                       ▼
                    FastAPI (private, same container)
                       ├─ SQLAlchemy ─▶ SQLite on a persistent disk (verified backups)
                       ├─ Garmin poller (every 10 min) + sync on app open
                       └─ OpenAI coach (bounded adviser, daily spend cap, cached by context hash)
```

- One Docker container runs both processes behind a start script that supervises them.
- The training science is **deterministic Python**. The LLM never writes a plan. It can only
  pick from candidate changes that Stride has already validated against budget and safety rules.

## Backend features

**Garmin ingestion and run understanding**
- Imports running activities, laps, HR, cadence, elevation, training effect, VO2max, plus daily wellness (sleep, HRV, resting HR, body battery, readiness, race predictions).
- **Lap analyzer**: turns raw Garmin laps into workout structure (e.g. "3x8min threshold (7:15, 7:09, 6:59/mi) w/ 2min recovery").
  - Merges Garmin auto-lap fragments back into real reps.
  - Distinguishes time reps from distance reps.
  - Detects continuous tempo efforts.
- **Off-plan detection**: recognizes when the athlete ran a different quality session than prescribed (threshold on an interval day) and logs what was actually run. It never mis-scores it as a failure.
- **Activity separation**: walks and secondary runs are never blended into a day's run stats. A day's distance, pace, time and HR come from one primary run.
- Merges legacy Strava-imported rows with Garmin records by start time and distance.

**Training plan engine**
- Rolling **2-week blocks** (generate, preview, approve), never a rigid 16-week plan.
- **Periodization** for race goals (base, build, peak, taper, race week, recovery) counted back from race date. General/mileage goals use fluid progression.
- Supports 5K through 100-mile goals, including ultra-specific rules (time-based long runs, fueling targets, back-to-back weekends, hill work for trail races).
- **Load policy**: baseline from the last four full weeks, conservative weekly budgets (10% rule for beginners), deload weeks, and acute:chronic workload monitoring.
- **Plan validator**: one validator for generation and every edit.
  - weekly mileage budget
  - rest-day preferences
  - never two hard days back-to-back
- **Workout progression ladders** for threshold and interval work, with VDOT-style pacing (Jack Daniels), pace calibration from real lap data, and goal-pace "step" rules for race-specific work.
- **Quality staging**: the athlete earns a second weekly workout only after verified, controlled sessions and good recovery.

**Adaptation loop**
- Post-run feedback (feel 1-10, notes, pace vs. target) drives a deterministic evaluator: advance, hold, regress or recalibrate. It moves one lever at a time and requires per-rep evidence.
- Session controls: replace, move, skip, each re-validated. Replacement menus offer three varied, dose-appropriate options.
- Idempotent side effects: re-submitting feedback never re-applies plan changes.

**AI coach (bounded LLM integration)**
- Grounded context per review:
  - the run's laps and detected reps
  - HR and athlete feedback
  - whether the run matched the plan, with planned vs. run work minutes
  - current calibrated paces
  - a 6-week training summary
  - upcoming sessions with days-from-today
  - relevant coaching research excerpts
- Structured output (Pydantic schema): 3-sentence summary, observations, and suggestions drawn **only** from server-generated candidate IDs.
- Safety and cost controls:
  - context-hash caching (identical context means no new call)
  - a daily call limit
  - stale-review detection
  - prompt-injection guidance (athlete notes are treated as data)
  - no secrets in logs
  - template fallback when AI is unavailable
- Athletes can type "what isn't working" (e.g. "too much volume"). The coach addresses it, but it can't widen the set of allowed changes.
- Evaluated against live data during development. Prompt and context were iterated with input from a running-coach review.

**Reliability and operations**
- Startup migrations (additive column adds). Verified SQLite backups before migrations or reclassification, scheduled retained backups, optional encrypted S3 export, and documented restore.
- Readiness and health endpoints, a container smoke test in CI (auth, persistent restart, restore, process supervision).
- Signed 7-day sessions, login throttling, sign-out. The app fails closed if no password is configured on the host.

## Frontend features

- **Today (Home):**
  - today's run: the plan before it's run, the actual session after (rep paces, HR trend, off-plan tag)
  - an inline collapsible coach review
  - a Garmin readiness strip and recovery metric tiles with 28-day point-to-point trend charts
  - a weekly mileage chart, race predictions, and recent runs labeled by detected workout
- **Plan:**
  - two-week calendar color-coded by session type, with a compact phone view
  - a sticky day inspector (prescription, what you did, feedback, session controls)
  - a single "Plan options" dialog: quick-reason chips plus free text sent to the AI coach, or rebuild lighter / revise / preview the next block
  - a pacing guide, a change log, and a draft approve/discard flow
- **History:** all runs with filters, run detail sheets with lap tables, a mileage-over-time chart.
- **Onboarding and Settings:** goals (race, mileage, general, return from injury), schedule preferences, units, Garmin connection status, backup status.
- Responsive and mobile-first (installable as a PWA via Add to Home Screen). Phone page height was cut about 40% after a design review.

## Notable engineering challenges (good interview stories)

1. **Garmin auto-laps broke workout detection.** An 8-minute rep crossing a mile marker became "1.00 mi + 0.10 mi". The analyzer read this as a 6-rep fartlek, the evaluator scored it as a failed workout, and that single "failure" emptied every replacement menu for two weeks.
   - The fix merges a lap into the rep only when the previous lap ended exactly on an auto-lap marker at a similar pace.
   - Validated against ~120 real activities. Found and fixed regressions on multi-mile reps and short fast reps.
2. **Grounding the LLM.** The first live coach output called a clean threshold session "ambiguous" and suggested an unnecessary change.
   - Fixed by feeding structured rep data, current calibrated paces, days-from-today and planned vs. run work minutes, and by tightening the instructions.
   - The final output correctly identified a progression run at the athlete's threshold pace and recommended no changes.
3. **Budget validation edge case.** Running 1 mile over plan blocked unrelated edits elsewhere in the plan.
   - Fixed with a *net* overrun allowance: extra miles already run don't block edits, but they never create new room.
4. **Not blending activities.** A treadmill walk recorded as a "treadmill run" was merged into the day's workout stats. The fix classifies walks separately and selects one primary run per day.
5. **Date-dependent tests.** The suite failed only on Wednesdays (UTC). Fixed with a frozen-date harness, and CI now runs the backend suite for all 7 weekdays.
6. **Cloud deploy without data loss.** Containerized a two-process app and moved a live SQLite database to a persistent disk with an atomic import-on-boot step and checksum verification.

## Suggested resume bullets (pick 3-5, adjust tone)

- Built **Stride**, a full-stack AI running coach (**FastAPI, Next.js 16, TypeScript, SQLite, Docker**) that syncs Garmin data and generates adaptive two-week training plans; deployed on Render and used daily for personal training.
- Designed a deterministic training engine covering periodization, mileage-budget validation, workout progression ladders and quality staging from 5K to 100 miles, backed by **545 automated tests** run across all seven weekdays in CI.
- Integrated an **OpenAI structured-output coach** grounded in lap-level run data and training history. Constrained it to server-validated plan changes with context-hash caching, daily spend caps and a template fallback.
- Wrote a lap-analysis pipeline that reconstructs workouts from raw Garmin laps (auto-lap merging, time vs. distance reps, off-plan session detection). It fixed misclassified threshold sessions across months of real training data.
- Containerized the app (multi-stage Docker, supervised processes) with persistent storage, verified backups, signed sessions, login throttling and a container smoke test in **GitHub Actions** CI.

## Keywords

Python, FastAPI, SQLAlchemy, Pydantic, SQLite, pandas, asyncio, REST API, Next.js, React,
TypeScript, Tailwind CSS, shadcn/ui, Recharts, OpenAI API, structured outputs, LLM grounding,
prompt engineering, Docker, Render, GitHub Actions, CI/CD, pytest, ESLint, data pipelines,
time-series/fitness data, Garmin, responsive/mobile-first UI, PWA.

## Do not claim (accuracy guardrails)

- **Not multi-user or commercial.** It's single-athlete by design. There are no paying users, no app-store app, and no user-account system beyond a password gate.
- **Not PostgreSQL, Celery or Redis.** CLAUDE.md lists these as the future stack, but production runs on SQLite and in-process asyncio workers.
- **Claude is not the production LLM.** Production coaching uses OpenAI. Claude Code and Codex were used as development tools.
- **No official Garmin API.** It uses the community `garminconnect` library, because Garmin's official API is enterprise-only.
- **The AI doesn't generate plans.** Plans are deterministic. The AI only explains runs and selects from pre-validated changes.
- **No weather integration or race-time predictor model.** Race predictions shown in the app come from Garmin.
- **Cross-training (swim, bike) isn't imported.** Only running activities are synced.

## Final resume material (verified 2026-10-21)

Metrics re-checked against the repo on 2026-10-21:

| Metric | Value | How checked |
|---|---|---|
| Backend tests | 545 | `pytest --collect-only -q tests` |
| Frontend tests | 19 | `test(` calls in `frontend/tests/*.test.mjs` |
| API endpoints | 37 (+ `/`, `/health`, `/ready`) | `@router.*` decorators in `backend/app/api/` |
| Python app code | 11,456 lines | `backend/app/**/*.py` |
| Backend tests code | 4,646 lines | `backend/tests/**/*.py` |
| TypeScript/TSX | 7,525 lines | `frontend/**/*.{ts,tsx}`, excluding `node_modules` / `.next` |
| Pull requests | 17, all merged | `gh pr list --state all` |
| First commit | 2026-05-27 | `git log` |

All the numbers in the brief above were still accurate.

### Project title

**Stride — AI Running Coach** | Python, FastAPI, SQLAlchemy, Next.js 16, React 19, TypeScript, OpenAI API, SQLite, Docker, GitHub Actions *(May 2026 – Present)*

### Resume bullets

- Built and deployed a full-stack running-coach app (FastAPI, Next.js 16, TypeScript, Docker on Render) that syncs Garmin data and generates adaptive two-week training plans through a 37-endpoint REST API; I use it daily for my own training.
- Designed a deterministic training engine (periodization, mileage-budget validation, workout progression ladders, 5K–100-mile goals) that checks every generated plan and every edit through a single validator, covered by 545 pytest tests run for all 7 weekdays in CI.
- Integrated an OpenAI structured-output coach grounded in lap-level run data, limited to selecting from server-validated plan changes, with context-hash caching, a daily call cap and a template fallback.
- Built a lap-analysis pipeline that reconstructs workouts from raw Garmin laps (auto-lap merging, time vs. distance reps, off-plan detection). Validated it on ~120 real activities, which fixed threshold sessions that had been misread as failed fartleks.

### Portfolio / LinkedIn blurb

Stride is a full-stack AI running coach I built for my own training. It syncs my Garmin data, generates science-based two-week plans and adapts them to what I actually run. The plan engine is deterministic, written in Python, with 545 tests behind it. An OpenAI coach explains each run, but it can only choose from changes the server has already checked against mileage and safety rules. It runs as a Dockerized FastAPI + Next.js app on Render, with CI, verified backups and a container smoke test.

### 30-second pitch

"I'm a competitive runner, and the plans from Garmin Coach and similar apps kept giving me unrealistic paces and over-complicated workouts. So I built Stride, a running coach that pulls in my Garmin data and builds two-week training plans that adjust to what I actually ran. The key design choice is that the training science is deterministic Python, backed by 545 tests. The LLM never writes the plan. It explains each run and can only choose from changes my server has already validated for mileage and injury risk. It's FastAPI and Next.js in a Docker container on Render, and I train with it every day."
