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
- **Garmin Connect** — official Personal API (key-based), date-windowed sync, FIT laps
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
│   └── .env                     # OPENAI_API_KEY, GARMIN_API_KEY etc. (not committed)
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
# 1. One-time: install, then put your Garmin Personal API key in backend/.env as GARMIN_API_KEY=...
#    (create it at https://connect.garmin.com/app/settings/personalApiToken)
cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 2. Start everything (backend + frontend), prints the phone URL
cd .. && ./start.sh
```

- **Computer:** http://localhost:3000
- **Phone (same Wi-Fi):** open the `http://<mac-ip>:3000` URL that `start.sh` prints → Share → **Add to Home Screen**. It opens full-screen like an app.
- **Phone away from home:** install [Tailscale](https://tailscale.com) on the Mac and phone (free) and use the Tailscale URL that `start.sh` prints.
- **AI coach:** add `OPENAI_API_KEY=...` to `backend/.env` (without it, the coach uses template responses). See `docs/ai-call-inventory.md` for exactly what each review sends.

### How Garmin sync works
Stride uses Garmin's official **Connect Personal API** (opened Oct 2026). `GARMIN_API_KEY` in
`backend/.env` is exchanged for a 24-hour bearer token, held in memory only. The API is pull-only
(no webhooks), so Stride syncs when the app opens and checks in the background every
`GARMIN_POLL_MINUTES` (default 15, hourly during `GARMIN_QUIET_HOURS`, default `22-5`); any sync
resets that clock. A check is one request for runs since the newest stored run, with Garmin filtering
non-runs. Only a new run costs more: one FIT download for its laps. Wellness uses three range requests.
The first sync imports your full history. Keys last 30 days to a year. When Garmin rejects the key,
Settings says so; create a new key and update `GARMIN_API_KEY`.
Not available from the Personal API: training readiness, training status, VO2max, Garmin race
predictions and activity notes. Those cards hide themselves.

## Deploying to Render

One always-on Render **Starter** web service (~$7/mo) runs both processes from the root
`Dockerfile`: FastAPI on `127.0.0.1:8000` (private) and the Next.js standalone server on
`$PORT` (public, password-gated). SQLite lives on a 1 GB persistent disk at
`/var/data`. The Garmin poller runs in-process (every 15 minutes, hourly overnight). Config is in `render.yaml`;
the entrypoint is `deploy/start.sh`.

### One-time cut-over

1. **Create the service.** Render dashboard → **New → Blueprint** → pick this repo (branch `main`).
   Enter the `sync: false` secrets when prompted:
   - `STRIDE_PASSWORD`: the app password (if it's empty, every page returns 503 instead of going public)
   - `OPENAI_API_KEY`: the AI coach key (optional; without it the coach uses templates)
   - `GARMIN_API_KEY`: your Garmin Connect Personal API key

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
3. **Garmin.** Nothing to bootstrap: the key is an env var, and tokens are exchanged in memory.
4. **Check it.** Open the `.onrender.com` URL and sign in. Settings should show Garmin connected,
   and a run should appear when you open the app (or within ~15 minutes) after a watch upload. Run `date` in the Render shell; it
   should print Pacific time (`TZ=America/Los_Angeles`; plan logic uses `date.today()`).

### Risks to watch

- **Garmin key expiry.** Personal API keys expire (30 days to 1 year). Garmin emails a reminder;
  rotate `GARMIN_API_KEY` in the Render dashboard and restart.
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

### Storage budget and recovery

The Render blueprint now allocates 5 GB, retains seven local snapshots, and caps
snapshot retention at 512 MiB (`STRIDE_BACKUP_MAX_BYTES`). Existing Render disks
must be resized in the dashboard; a blueprint edit does not prove the live disk
was resized. Backups reserve space for verification and preserve the latest
snapshot when space is insufficient. Operations reports capacity warnings.
Configure the existing encrypted S3 export for off-disk recovery, and verify a
restore with `python -m app.services.backups --restore BACKUP --destination NEW_DB`.
No setting alone proves an offsite backup or a successful recovery.

### Invite-only athlete accounts

Account mode is opt-in: set `STRIDE_ACCOUNTS_ENABLED=true` for both frontend and
backend, `STRIDE_SIGNUP_INVITE_CODE` on the backend, and `STRIDE_PUBLIC_URL` to the
public HTTPS origin. Cookies are Secure by default. Only isolated localhost
previews should set `STRIDE_COOKIE_SECURE=false`. Do not expose the backend on a
public interface. `/auth/register` creates a separate athlete; it never claims
an existing athlete's history. API ownership is checked on the backend even when
someone requests a numeric athlete URL.

Before switching an existing owner to account mode, attach an account locally:
`cd backend && venv/bin/python -m app.services.accounts bootstrap --user-id 1 --email YOUR_EMAIL`.
The command prompts for a password; do not put it in shell arguments. Operator
recovery uses `python -m app.services.accounts recovery --user-id ID`; give the
single-use 30-minute token privately to the athlete, who uses `/auth/reset`.
Email delivery/verification is intentionally not provisioned; registration is
invite-only. Public registration remains a separate deployment decision.

Athletes can change AI consent and timezone, export their own history, or erase
their live account in Settings. Consent is off by default. Erasure does not erase
already-created offsite backups immediately: the operator must define retention
and let those encrypted backups expire. Never enable a shared owner Garmin key
for additional athletes. Garmin multi-user integration still requires Garmin's
approval and the appropriate historical-data entitlement.

### Worker, migrations, and storage deployment

The container runs `python -m app.schema` once before starting the web process,
then starts `python -m app.services.worker` separately. Web replicas use
`SCHEMA_AUTO_UPGRADE=false` and `EMBEDDED_WORKERS=false`. Local development still
supports embedded work. Sync jobs persist per athlete, use leases/retries, and
resume after a worker restart; PostgreSQL claims use row locks with `SKIP LOCKED`.
A schema version marker plus missing columns is treated as drift, not silently
repaired. Future changes require a new Alembic revision; do not edit the frozen
baseline manifest after release. Existing source/data migrations remain separate.

For a larger deployment use a managed PostgreSQL URL (`postgresql+psycopg://…`),
with the provider's encrypted backups and point-in-time recovery enabled. A
PostgreSQL CI service exercises migrations, snapshot transfer, sequence repair,
and concurrent job claims. Cutover procedure:

1. Stop writes; create and restore-verify a SQLite snapshot using the backup CLI.
2. Upgrade a **copy** of that snapshot with the new schema.
3. Run `python -m app.services.database_transfer --source-snapshot COPY --destination-url EMPTY_POSTGRES_URL` in a private operator shell. It reads the snapshot without modifying it, checks counts, and repairs PostgreSQL sequences. The destination must contain no athlete data.
4. Verify login, history, plan, source evidence and backups in staging; then change `DATABASE_URL`. Keep the original database and verified backups for rollback. Never run two writable deployments against separate copies during cutover.

`FIT_BLOB_BUCKET` optionally stores new FIT evidence in private S3 objects,
content-addressed under each athlete. Original inline evidence remains readable.
Configure the bucket's block-public-access, encryption, least-privilege IAM, and
version/lifecycle policy. Database backups alone do not back up external objects.
Exports stream original evidence; account erasure queues idempotent object
removal. Failed SQL transactions may leave unreferenced objects; retain objects
until a separately verified reference/lifecycle cleanup rather than deleting
unreferenced data during ingestion.

`STRIDE_PROVIDER_ENCRYPTION_KEYS` accepts comma-separated Fernet keys (newest first)
for stored owner credentials. Keep keys in a secret manager, separate from database
backups. Rotate by adding the new key while retaining previous keys until stored
credentials are re-encrypted. Generate with `Fernet.generate_key()` from the
`cryptography` library. No provider secret is returned in APIs or exports. The
existing environment owner key remains supported in owner mode only. Separate
athletes cannot reuse it; live Business transport remains disabled pending Garmin
approval and its integration contract. Original FIT uploads work without Garmin.
