# Stride — AI-Powered Running Coach

> Working name. Hyper-focused on running. Nothing else.

## Vision

Stride is an AI-powered training platform built exclusively for runners. It generates personalized, science-based training plans that adapt in real-time based on athlete performance data from Garmin and Strava. Unlike Garmin Coach, TrainingPeaks, or Runna, Stride focuses solely on running with deep specificity — real workouts that real competitive runners use, not generic cookie-cutter plans.

The core loop: **Onboard → Sync Data → Set Goal → Generate 2-Week Rolling Plan → Run → Analyze → Adjust → Repeat**

## Core Philosophy

- **Simple but specific.** Running doesn't have to be complicated, but it must be specific to the goal. No "3 rounds of 5 sets of 40-second sprints at 4:12-4:44 pace." Instead: "6x800m at 3:24 (5K goal pace) with 90s jog rest. 1mi warmup, 1mi cooldown."
- **Easy days easy, hard days hard.** Easy runs emphasize conversational effort. Workouts are genuinely difficult and purposeful.
- **Never rush mileage.** Injury prevention through conservative mileage building (10% rule for beginners, slightly faster for experienced). Acute:chronic workload ratio monitoring.
- **Rolling plans, not rigid blocks.** Never generate a full 16-week plan upfront. Generate 2 weeks, analyze how the athlete responds, then generate the next 2 weeks. User confirms each block.
- **Every workout has a why.** The app explains the purpose of each workout ("Today's tempo builds lactate threshold — the key limiter for your half marathon goal").
- **Data-driven coaching tone.** Feels like a knowledgeable coach, but every recommendation is backed by data and exercise science.

## Training Methodology

Blend of established coaching philosophies — not dogmatic about any single one:
- **Jack Daniels** — VDOT pacing, workout structure (intervals, tempo, repetitions)
- **Pete Pfitzinger** — Marathon-specific long runs, progressive overload
- **Hanson** — Cumulative fatigue philosophy for marathon training
- **80/20 Running** — ~80% easy, ~20% quality work
- **Maffetone** — Aerobic base building for beginners
- **Canova** — Specific marathon preparation (race-pace long runs)

### Workout Types Supported
- Easy runs (conversational pace, strides 1-2x/week on easy days)
- Long runs (steady, progressive, or with race-pace segments depending on phase)
- Tempo runs (continuous tempo, cruise intervals)
- Intervals (800m, 1K, 1200m, mile repeats at various paces)
- Threshold work (e.g., 4x10min hard, 2min jog)
- Fartlek
- Hill repeats
- Progression runs
- Recovery runs
- Time trials
- Doubles (AM easy + PM strides) — only for experienced athletes with ambitious goals

### Warmup/Cooldown
Every workout includes a prescribed warmup and cooldown (distance or time-based per user preference).

### Pacing
- Workout paces derived from **goal time** (e.g., sub-17 5K = 5:28/mi pace → intervals slightly faster)
- If athlete struggles with prescribed paces, scale back to current fitness level
- Tempos can be effort-based ("comfortably hard") rather than pace-locked
- Easy runs: prescribe a pace range but emphasize "conversational, truly easy"

### Weekly Structure
- Default template: Mon easy, Tue workout, Wed easy, Thu workout, Fri rest, Sat long run, Sun easy
- **Never back-to-back hard days.** Always easy/rest between workouts and long runs
- Long run can move to Sunday for marathon-focused athletes
- User sets preferred rest days; app can suggest additional rest if fatigue detected

### Periodization
- Competitive athletes with race goals: Base → Build → Peak → Taper (traditional)
- General fitness / beginners: Fluid progression, no rigid phases
- Taper: ~2 weeks for marathon, ~1 week for 5K (auto-calculated from race date)

### Mileage Building
- Beginners: 10% weekly increase rule, strictly enforced
- Experienced runners (50+ mpw history): Can ramp slightly faster but still gradual
- Deload weeks: Every 4th week for amateur runners, every 5-7 weeks for experienced
- Deload = reduced volume, not zero running

### Injury Risk
- Monitor acute:chronic workload ratio
- Flag rapid mileage spikes
- If user reports fatigue/soreness, suggest extra rest or reduced intensity
- Slow build is a core principle — this is a MAJOR differentiator

## Goal Types

Users select from:
1. **Race Goal** — Pick distance (5K, 10K, half marathon, marathon) + target time + race date
2. **Mileage Goal** — Build to X miles/week (e.g., "get to 40 miles per week")
3. **General Fitness** — Start running consistently, no specific target
4. **Return from Injury/Break** — Conservative rebuild plan

Distances supported (Phase 1): 5K, 10K, Half Marathon, Marathon
Distances supported (Phase 2+): 800m, Mile, 50K, 50mi, 100mi

## User Onboarding

1. Basic info: age, estimated times for multiple distances (even rough guesses)
2. Current weekly mileage (or "I'm not running right now")
3. Running history: years running, previous races and times, PRs
4. How many days/week available to run
5. Preferred rest days
6. Preferred units (miles or kilometers)
7. Preferred workout format (time-based or distance-based)
8. Sleep quality input (simple scale)
9. Connect Strava and/or Garmin account (or manual entry option)
10. Select goal from goal types above

## Data Integration

### Strava API
- OAuth2 authentication
- Pull all running activities (ignore other sport types)
- Historical data: pull everything available
- Webhook subscription for automatic sync (preferred)
- Data fields: distance, duration, pace, splits, heart rate, cadence, elevation gain

### Garmin Connect API
- OAuth1.0a authentication
- **Garmin takes priority** if both connected
- Pull all running activities
- Historical data: all available
- Data fields: same as Strava + ground contact time, vertical oscillation, training effect (if available)

### Manual Entry
- For users without a watch
- Log: date, distance, time, effort level (1-10), notes

## Post-Run Analysis

After each run syncs:
1. **Prompt user**: "How did that feel?" — 1-10 scale + optional free text
2. **LLM analyzes**: Did they hit target pace? HR drift? How does subjective feel compare to objective data?
3. **Feedback**: Coach-like response grounded in data ("Your tempo splits were consistent and right on target. HR stayed in zone — solid workout.")
4. **Plan adjustment**: If workout was too hard/easy, or user feels fatigued, adjust upcoming days. Can add rest day, reduce intensity, or modify next workout.

## Weekly Summary

Auto-generated weekly recap:
- Total mileage vs planned
- Workout execution (hit targets or not)
- Trends (improving, maintaining, fatiguing)
- Sleep correlation (if tracked)
- Preview of next week's focus
- Coach-tone insights

## Dashboard & Graphs

### Primary Metric (Hero Number)
**Weekly Mileage** — the first thing you see when opening the app

### Graphs (Priority Order)
1. Weekly mileage over time (bar chart, with planned vs actual)
2. Workout pace vs target pace (scatter/line — are you hitting your marks?)
3. Long run distance progression (line chart)
4. Pace trends over time (easy pace, workout pace)
5. Acute:chronic workload ratio (line chart with danger zone highlighted)

### Daily View
- Today's workout with full description and purpose
- Target paces / effort level
- Warmup and cooldown details
- Upcoming week overview

## Weather Integration

- Pull local weather data
- Adjust pace recommendations for heat/humidity ("It's 95F today — slow your easy pace by 30-45s/mile")
- Note conditions in post-run analysis

## Goal Transitions

The app should handle dramatic goal switches gracefully:
- Detect training type shift (e.g., marathon volume → 5K speed work)
- Generate a transition plan (don't just flip overnight)
- Explain what's changing and why ("You've been training for endurance. We're now shifting to speed — expect shorter runs with more intensity over the next 3-4 weeks")

## Tech Stack

### Backend (Python)
- **FastAPI** — async API framework, fast, modern, great for data processing
- **SQLAlchemy + Alembic** — ORM and migrations
- **PostgreSQL** — primary database (SQLite for local dev initially)
- **Celery + Redis** — background task processing (Strava/Garmin sync, plan generation)
- **Pandas / NumPy** — data analysis, trend calculations, workload ratios

### Frontend
- **Next.js (React)** — web app, App Router
- **Tailwind CSS** — styling
- **shadcn/ui** — component library
- **Recharts or Chart.js** — graphs and data visualization
- **Light mode default** — switchable to dark

### AI / LLM
- **Claude API (Anthropic)** — plan generation, post-run analysis, weekly summaries, plan adjustments
- **Budget cap: ~$15/month** — if exceeded, evaluate switching to Ollama (local LLM)
- Structured prompts with athlete context, training history, and exercise science principles

### Future: Mobile
- React Native or PWA (TBD)
- Offline support for viewing plan (but needs internet for Strava/Garmin sync)

## Project Structure

```
stride/
├── CLAUDE.md                  # This file
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # Settings, env vars
│   │   ├── models/            # SQLAlchemy models
│   │   │   ├── user.py
│   │   │   ├── activity.py
│   │   │   ├── plan.py
│   │   │   └── workout.py
│   │   ├── api/               # API routes
│   │   │   ├── auth.py
│   │   │   ├── activities.py
│   │   │   ├── plans.py
│   │   │   ├── goals.py
│   │   │   └── analysis.py
│   │   ├── services/          # Business logic
│   │   │   ├── strava.py      # Strava API integration
│   │   │   ├── garmin.py      # Garmin API integration
│   │   │   ├── plan_engine.py # Training plan generation
│   │   │   ├── analyzer.py    # Post-run analysis
│   │   │   ├── coach.py       # LLM coaching interface
│   │   │   └── weather.py     # Weather API
│   │   ├── core/              # Training science logic
│   │   │   ├── pacing.py      # Pace calculations, VDOT
│   │   │   ├── workouts.py    # Workout templates
│   │   │   ├── periodization.py
│   │   │   ├── mileage.py     # Mileage ramp logic
│   │   │   └── injury_risk.py # Acute:chronic ratio
│   │   └── utils/
│   ├── tests/
│   ├── alembic/               # DB migrations
│   └── requirements.txt
├── frontend/
│   ├── app/                   # Next.js App Router
│   │   ├── page.tsx           # Dashboard
│   │   ├── onboarding/
│   │   ├── plan/
│   │   ├── activity/
│   │   └── settings/
│   ├── components/
│   │   ├── graphs/
│   │   ├── workout-card/
│   │   └── plan-calendar/
│   ├── lib/
│   └── package.json
└── docs/
    ├── training-philosophy.md # Deep dive on methodology
    ├── api-spec.md            # API documentation
    └── data-model.md          # Database schema
```

## MVP Scope (Phase 1)

The smallest version that delivers value:

1. **Onboarding flow** — Collect user info, running history, PRs, goal selection
2. **Strava OAuth** — Connect and pull historical running data
3. **Athlete assessment** — Analyze imported data to determine baseline fitness
4. **2-week plan generation** — AI generates first training block based on goal + baseline
5. **Daily workout view** — See today's workout with description, paces, warmup/cooldown, and purpose
6. **Post-run sync + analysis** — Auto-sync from Strava, prompt for feel, LLM analyzes
7. **Plan adjustment** — Based on performance, adjust remaining days or generate next 2-week block
8. **Basic dashboard** — Weekly mileage (hero number), workout pace vs target graph, mileage over time graph
9. **Light mode UI** — Clean, simple, running-focused

### What's NOT in Phase 1
- Garmin integration (Phase 2 — Strava is easier to start with)
- Race predictor
- Weather adjustments
- Mobile app
- User accounts / cloud storage (local SQLite + local auth)
- Ultra distance support
- Push workouts to watch
- Coach mode / multi-athlete

## Phase 2 Ideas
- Garmin Connect integration
- Weather-adjusted pace recommendations
- Race time predictor (VDOT-based)
- Cloud database + user accounts (email/password auth)
- Push structured workouts to Garmin watch
- PWA for mobile access

## Phase 3+ Ideas
- Ultra distance support (50K, 50mi, 100mi)
- Nutrition planning for ultras (crew logistics, aid station planning)
- React Native mobile app
- Coach mode (manage multiple athletes)
- Apple Watch / COROS integration
- Advanced analytics (training load modeling, predicted VO2 max trends)
- Comparative analysis ("runners at your level typically...")

## Development Workflow

- **Python 3.12+** for backend
- **Node.js 20+** for frontend
- **Local development**: `uvicorn` (backend) + `next dev` (frontend)
- **Database**: SQLite locally, PostgreSQL for production
- **Git**: feature branches, meaningful commits
- Claude API key stored in `.env` (never committed)

## Key Design Principles

1. **Running only.** No cycling, swimming, gym. If it's not running, it's not in the app.
2. **Coach, not calculator.** Every interaction should feel like talking to a knowledgeable running coach.
3. **Show your work.** Always explain WHY a workout is prescribed.
4. **Respect the athlete.** Let the user approve plan blocks, swap days, adjust preferences.
5. **Fail safe.** When in doubt, prescribe less. An undertrained runner races; an injured runner doesn't.
6. **Light and fast.** The UI should be as fast as interval splits — no bloat, no unnecessary features.

## Founder Context

- **Jake Bowen** — CS junior at CSUF, experienced runner (2:58 marathon, targeting sub-17 5K, future 100-miler)
- 50-70 mpw peak, currently rebuilding to 40-50 mpw
- ~400-500 runs in Garmin
- Frustrated with Garmin Coach's unrealistic pacing and overly complicated workouts
- Wants workouts that look like what real competitive runners actually do
- Building this for himself first, but designed to scale

## Commands

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install
npm run dev  # runs on port 3000
```
