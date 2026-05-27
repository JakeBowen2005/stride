# Stride — AI-Powered Running Coach

A personal training platform built exclusively for runners. Generates science-based 2-week rolling training plans that adapt based on real performance data from Strava.

Built by Jake Bowen (CS junior at CSUF, 2:58 marathoner, targeting sub-17 5K).

## What It Does

- **Syncs all Strava data** — pulls every run, description, splits, heart rate, cadence
- **Calibrates paces from real workouts** — parses Strava descriptions to extract actual interval times, tempo paces, threshold paces (not theoretical calculations)
- **Generates 2-week rolling plans** — grounded in current fitness, not goal time. Mileage ramps conservatively using headroom-based progression
- **Classifies every run** — workout, long run, easy, recovery based on Strava workout type and description analysis
- **Detects PRs** — scans all activities for best times at 10 standard distances (0.5mi to marathon)
- **Post-run analysis** — tracks feel ratings, shows workout breakdown with average/range calculations
- **Dashboard** — last week's mileage, current goal, next workout, last 7 days of runs
- **History** — all runs with descriptions, workout mini-analysis, filterable by type

## Training Philosophy

Blend of established coaching methodologies:
- **Jack Daniels** — VDOT pacing, interval/tempo/repetition structure
- **Pete Pfitzinger** — Progressive overload, marathon-specific long runs
- **80/20 Running** — ~80% easy, ~20% quality work
- **Canova** — Race-pace specific preparation

Key principles:
- Easy days easy, hard days hard
- Never rush mileage (10% rule, headroom-based ramp)
- Every workout has a purpose
- Plans calibrated from ACTUAL recent workout data, not goal time
- Rolling 2-week blocks (generate → run → analyze → adjust → repeat)

## Tech Stack

### Backend
- **FastAPI** — async Python API
- **SQLAlchemy** — ORM with SQLite (PostgreSQL for production)
- **Strava OAuth2** — full activity sync with token refresh
- **Pace Calibrator** — regex-based parser for workout descriptions
- **Plan Engine** — headroom-based mileage ramp, physiological pace progression

### Frontend
- **Next.js 16** — App Router, React Server Components
- **Tailwind CSS v4** — utility-first styling
- **shadcn/ui** — component library (Radix primitives)
- **Recharts** — data visualization (mileage charts, pace trends)

## Project Structure

```
stride/
├── CLAUDE.md                    # AI coaching instructions & project spec
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Environment settings
│   │   ├── database.py          # SQLAlchemy setup
│   │   ├── models/
│   │   │   ├── user.py          # User + Goal models
│   │   │   └── activity.py      # Activity + PersonalRecord models
│   │   ├── api/
│   │   │   ├── auth.py          # Strava OAuth flow
│   │   │   ├── analysis.py      # Analysis, PRs, activities, classification endpoints
│   │   │   └── plans.py         # Plan generation + goal endpoints
│   │   ├── services/
│   │   │   ├── strava.py        # Strava API integration (sync, descriptions)
│   │   │   ├── analyzer.py      # Athlete analysis, PR detection, classification
│   │   │   └── pace_calibrator.py  # Parse workout descriptions for real paces
│   │   └── core/
│   │       ├── plan_engine.py   # 2-week rolling plan generator
│   │       ├── pacing.py        # VDOT pacing, pace calculations
│   │       └── workouts.py      # Workout library (threshold, intervals, long runs)
│   ├── requirements.txt
│   └── .env                     # Strava API keys (not committed)
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Dashboard (today page)
│   │   ├── plan/page.tsx        # 2-week training plan
│   │   ├── history/page.tsx     # Run history with filters
│   │   ├── settings/page.tsx    # Profile, paces, PRs, connections
│   │   ├── onboarding/page.tsx  # 8-step onboarding flow
│   │   └── activity/[id]/review/page.tsx  # Post-run feel rating
│   ├── components/
│   │   ├── nav.tsx              # Top nav + mobile bottom tabs
│   │   ├── plan-week.tsx        # Week container for plan view
│   │   ├── plan-day.tsx         # Expandable day row with workout details
│   │   ├── run-list.tsx         # Activities grouped by month (with descriptions)
│   │   ├── run-detail-sheet.tsx # Activity detail sheet (with workout analysis)
│   │   ├── charts-wrapper.tsx   # Card wrappers for Recharts
│   │   └── charts/             # Weekly mileage, pace, mileage-over-time charts
│   ├── lib/
│   │   ├── types.ts             # TypeScript types
│   │   ├── format.ts            # Pace/time/distance formatting
│   │   └── utils.ts             # cn() utility
│   └── package.json
└── docs/
    ├── training-principles.md       # Core training methodology
    ├── athlete-profile-jake.md      # Jake's runner profile & history
    ├── 5k-training-science.md       # 5K-specific training science
    ├── 10k-training-science.md      # 10K training science
    ├── half-marathon-training-science.md
    ├── marathon-training-science.md
    ├── marathon-training-notes.md   # Marathon-specific notes
    ├── frontend-plan.md             # Frontend design document
    ├── todo-may27.md                # May 27 feedback & fixes
    ├── changes-may27.md             # May 27 changelog
    └── todo-may28.md                # May 28 plan (Strava full sync)
```

## API Endpoints

### Analysis
- `GET /api/analysis/{user_id}/baseline` — full athlete analysis
- `GET /api/analysis/{user_id}/calibrated-paces` — paces from real workout data
- `GET /api/analysis/{user_id}/activities` — paginated activities with filter (?type=workouts|long_runs|easy)
- `GET /api/analysis/{user_id}/weekly-mileage` — weekly mileage data
- `GET /api/analysis/{user_id}/prs` — personal records
- `POST /api/analysis/{user_id}/full-sync` — sync all Strava data
- `POST /api/analysis/{user_id}/fetch-descriptions` — pull descriptions for activities missing them
- `POST /api/analysis/{user_id}/classify` — classify all activities by type
- `POST /api/analysis/{user_id}/detect-prs` — run PR detection

### Plans
- `POST /api/plans/{user_id}/generate` — generate 2-week training plan
- `GET /api/plans/{user_id}/goal` — get active goal

### Auth
- `GET /api/auth/strava` — Strava OAuth redirect
- `GET /api/auth/strava/callback` — OAuth callback

## Setup

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env with Strava API credentials
echo "STRAVA_CLIENT_ID=your_id" >> .env
echo "STRAVA_CLIENT_SECRET=your_secret" >> .env
echo "STRAVA_REDIRECT_URI=http://localhost:8000/api/auth/strava/callback" >> .env

uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # runs on port 3000 (or 3001 if 3000 is busy)
```

## Current Athlete Data (Jake)

- **465 activities** synced from Strava
- **31 workouts** identified from descriptions
- **28 long runs** (15+ miles or Strava-flagged)
- **10 PRs detected** (0.5mi to marathon)
- **Calibrated paces**: interval ~6:08/mi, tempo ~7:00/mi, easy ~9:15/mi
- **Current fitness**: ~25 mi/week (rebuild phase), peak 70 mi/week
- **Goal**: Sub-17:00 5K (no target date)

## Status

MVP functional. Key features working:
- Strava OAuth + full data sync
- Pace calibration from real workout descriptions
- 2-week plan generation with calibrated paces
- Dashboard, plan, history, settings pages all wired to real API
- Workout classification and PR detection

Next up (May 28):
- Pull full Strava history (all activities ever, not just recent)
- Fetch remaining descriptions (200 activities in Apr-Oct 2025 window)
- Build efficient onboarding flow for new Strava connections
