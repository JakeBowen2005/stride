# Stride — AI-Powered Running Coach

A personal training platform built exclusively for runners. Generates science-based 2-week rolling training plans that adapt based on real performance data from Garmin Connect.

Built by Jake Bowen (CS junior at CSUF, 2:58 marathoner, targeting sub-17 5K).

## What It Does

- **Syncs all Garmin data automatically** — every run, laps, heart rate, cadence, training effect, VO2max; new watch uploads appear within ~10 minutes (or instantly when you open the app)
- **Reads workouts from your laps** — Garmin laps are turned into workout summaries ("6x800 (3:02, 3:04…)"), so paces calibrate from what you actually ran, with no typing needed
- **Keeps your Strava history** — the 467 runs imported from Strava earlier are matched to their Garmin copies, not duplicated
- **Generates 2-week rolling plans** — grounded in current fitness, not goal time. Mileage ramps conservatively using headroom-based progression
- **Periodizes toward race day** — set a race date and each week is placed in base → build → peak → taper → race week → recovery, with a real taper and race-week sharpener
- **Ultra support (50K–100 mi)** — time-on-feet long runs with fueling targets, back-to-back weekends, hill work for trail/mountain races, and readiness checks that suggest a stepping-stone race when a goal is too big too soon
- **Classifies every run** — workout, long run, easy, recovery based on Garmin event type, training effect, lap analysis, and notes
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
- **Garmin Connect** — `garminconnect` client, background auto-sync loop
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
│   │   │   ├── garmin.py        # Garmin status / sync / full re-import
│   │   │   ├── analysis.py      # Analysis, PRs, activities, classification endpoints
│   │   │   └── plans.py         # Plan generation + goal endpoints
│   │   ├── services/
│   │   │   ├── garmin.py        # Garmin Connect sync (incremental + full, Strava-history merge)
│   │   │   ├── lap_analyzer.py  # Garmin laps → workout summaries
│   │   │   ├── analyzer.py      # Athlete analysis, PR detection, classification
│   │   │   └── pace_calibrator.py  # Parse workout descriptions for real paces
│   │   └── core/
│   │       ├── plan_engine.py   # 2-week rolling plan generator
│   │       ├── pacing.py        # VDOT pacing, pace calculations
│   │       └── workouts.py      # Workout library (threshold, intervals, long runs)
│   ├── requirements.txt
│   ├── garmin_login.py          # one-time Garmin login (saves tokens to .garmin/)
│   └── .env                     # ANTHROPIC_API_KEY etc. (not committed)
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
    ├── ultra-training-science.md    # 50K / 50mi / 100K / 100mi training + how pros train
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
- `POST /api/analysis/{user_id}/full-sync` — re-sync all Garmin data + classify + PRs + analysis
- `POST /api/analysis/{user_id}/classify` — classify all activities by type
- `POST /api/analysis/{user_id}/detect-prs` — run PR detection

### Plans
- `POST /api/plans/{user_id}/generate` — generate 2-week training plan
- `GET /api/plans/{user_id}/goal` — get active goal

### Garmin
- `GET /api/garmin/status/{user_id}` — connection + last sync info
- `POST /api/garmin/sync/{user_id}` — pull new runs (first ever sync pulls full history)
- `POST /api/garmin/full-sync/{user_id}` — re-import all Garmin history in the background

## Setup (run it on your computer + phone)

```bash
# 1. One-time: connect Garmin (type your Garmin login + MFA code in the terminal)
cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python garmin_login.py

# 2. Start everything (backend + frontend), prints the phone URL
cd .. && ./start.sh
```

- **Computer:** http://localhost:3000
- **Phone (same Wi-Fi):** open the `http://<mac-ip>:3000` URL that `start.sh` prints → Share → **Add to Home Screen**. It opens full-screen like an app.
- **Phone away from home:** install [Tailscale](https://tailscale.com) on the Mac and phone (free) and use the Tailscale URL that `start.sh` prints.
- **AI coach:** add `ANTHROPIC_API_KEY=...` to `backend/.env` (without it, the coach uses template responses).

### How Garmin sync works
Garmin's official API is enterprise-only (and closed to new applicants), so Stride uses the
[`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library, which talks to Garmin Connect as you.
`garmin_login.py` saves session tokens to `backend/.garmin/` (git-ignored). Your password is never stored.
The backend polls Garmin every `GARMIN_POLL_MINUTES` (default 10). The first sync imports your full history.
If Garmin ever expires the session, re-run `garmin_login.py`.

## Deploying to Render

One always-on Render **Starter** web service (~$7/mo) runs both processes from the root
`Dockerfile`: FastAPI on `127.0.0.1:8000` (private) and the Next.js standalone server on
`$PORT` (public, password-gated). SQLite and the Garmin tokens live on a 1 GB persistent disk at
`/var/data`. The Garmin poller runs in-process every 10 minutes. Config is in `render.yaml`;
the entrypoint is `deploy/start.sh`.

### One-time cut-over

1. **Create the service.** Render dashboard → **New → Blueprint** → pick this repo (branch `main`).
   Enter the `sync: false` secrets when prompted:
   - `STRIDE_PASSWORD`: the app password (if it's empty, every page returns 503 instead of going public)
   - `OPENAI_API_KEY`: the AI coach key (optional; without it the coach uses templates)
   - `GARMIN_TOKENS_JSON`: the contents of `backend/.garmin/garmin_tokens.json` (see step 3)

   Apply. The first deploy starts with an empty database on the disk.
2. **Copy your data.** Stop `./start.sh` locally so the DB isn't being written, then take a
   consistent snapshot (it includes WAL contents) and upload it over Render SSH. Add your SSH key
   under Account Settings → SSH Keys; the service's **Connect → SSH** shows its address.
   ```bash
   sqlite3 backend/stride.db ".backup /tmp/stride-upload.db"
   scp /tmp/stride-upload.db <service-ssh-address>:/var/data/stride-upload.db
   ```
   Then **Manual Deploy → Restart service**. On boot, `deploy/start.sh` moves
   `stride-upload.db` into place as `stride.db` *before* the backend opens it, and keeps the empty
   first-boot DB as `stride.db.before-import-<time>`. Don't overwrite `stride.db` directly while the
   service is running. Delete `/tmp/stride-upload.db` afterwards: it is your personal health data.
3. **Garmin tokens.** `GARMIN_TOKENS_JSON` is written once to
   `/var/data/.garmin/garmin_tokens.json` (mode 600) on boot, but only if that file doesn't exist.
   After that the disk copy wins, because garminconnect refreshes it. To re-bootstrap, run
   `backend/garmin_login.py` locally, update the secret, delete the file over SSH, and restart.
   You can clear the env var once the file exists.
4. **Check it.** Open the `.onrender.com` URL and sign in. Settings should show Garmin connected,
   and a run should appear within ~10 minutes of a watch upload. Run `date` in the Render shell; it
   should print Pacific time (`TZ=America/Los_Angeles`; plan logic uses `date.today()`).

### Risks to watch

- **Garmin may challenge datacenter IPs.** The tokens were minted on your home network. If Garmin
  flags logins or refreshes from Render's IPs, sync fails with an auth error in the logs and you
  have to re-run `garmin_login.py` and re-bootstrap the tokens. If it keeps happening, sync from
  home and treat Render as read-mostly.
- **Memory.** Starter has 512 MB. Node is capped with `NODE_OPTIONS=--max-old-space-size=192`.
  Watch the Metrics tab. If the service sits above ~450 MB, split the frontend into its own service
  (or move it to Vercel) and point `BACKEND_URL` at the backend. Note that `BACKEND_URL` is baked in
  at build time by the `/api` rewrite.
- **One instance only.** SQLite on a disk means no scaling out and a short downtime on each deploy.

## Current Athlete Data (Jake)

- **465 activities** synced from Strava
- **31 workouts** identified from descriptions
- **28 long runs** (15+ miles or Strava-flagged)
- **10 PRs detected** (0.5mi to marathon)
- **Calibrated paces**: interval ~6:08/mi, tempo ~7:00/mi, easy ~9:15/mi
- **Current fitness**: ~25 mi/week (rebuild phase), peak 70 mi/week
- **Goal**: Sub-17:00 5K (no target date)

## Status

MVP functional, now on Garmin:
- Garmin Connect sync (auto every 10 min + on app open), full history import, Strava-history merge
- Lap-based workout detection feeding pace calibration and the progression ladders
- 2-week plan generation with calibrated paces, feedback loop, Claude Haiku coach
- Installable on phone (Add to Home Screen) via `./start.sh`
