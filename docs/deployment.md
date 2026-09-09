# Deploying Stride

> Goal: reach the app from your phone and your computer, and have it update
> itself whenever Strava does.
>
> Frontend is already live on Vercel. The backend is the missing half — until
> it is deployed, the Vercel site is talking to `localhost:8000` and shows
> nothing.

---

## Architecture

```
  Strava  ──webhook──►  Railway (FastAPI + Postgres)  ◄──fetch──  Vercel (Next.js)
     ▲                            │                                      ▲
     └────────── OAuth ───────────┘                                      │
                                                          phone / laptop ┘
```

---

## 1. Backend on Railway

### Create the service
1. [railway.app](https://railway.app) -> **New Project** -> **Deploy from GitHub** ->
   select `JakeBowen2005/stride`
2. **Leave Root Directory blank.** Deploy from the repo root.

> **Why not Root Directory = `backend`?**
> `services/coach.py` loads `training-principles.md`, the goal-specific science
> doc and the athlete profile into the LLM system prompt on every call. Those
> live in `docs/`, which is a sibling of `backend/` — setting the root directory
> to `backend` leaves them out of the image entirely. The coach would keep
> answering, just generically, with nothing but a log line to tell you. So the
> build runs from the root (`requirements.txt` there points at backend's) and
> `railway.toml` starts the app with `cd backend && uvicorn ...`.

3. Healthcheck path is already `/health` via the root `railway.toml`.

### Add Postgres
**Do this rather than mounting a volume for SQLite.** SQLite on a container
filesystem survives restarts only if the volume mount is exactly right, and a
single corrupt write loses every activity you have synced.

1. Project → **New** → **Database** → **PostgreSQL**
2. Railway injects `DATABASE_URL` automatically. The app normalises the
   `postgres://` scheme and pins the psycopg 3 driver, so nothing else is needed.

Tables are created on boot (`Base.metadata.create_all` plus `ensure_schema()`
for additive column migrations).

### Environment variables

| Variable | Value | Notes |
|---|---|---|
| `STRAVA_CLIENT_ID` | from strava.com/settings/api | |
| `STRAVA_CLIENT_SECRET` | from strava.com/settings/api | |
| `ANTHROPIC_API_KEY` | from console.anthropic.com | without it the coach falls back to templates |
| `STRAVA_REDIRECT_URI` | `https://<railway-url>/api/strava/callback` | |
| `STRAVA_WEBHOOK_URL` | `https://<railway-url>/api/strava/webhook` | |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | any random string | must match what you use at subscribe time |
| `ALLOWED_ORIGINS` | `https://<your-vercel-url>` | comma-separated; no trailing slash |
| `FRONTEND_URL` | `https://<your-vercel-url>` | where OAuth redirects back to |
| `SECRET_KEY` | any random 32+ chars | |
| `DATABASE_URL` | *(injected by Railway)* | |

`STRIDE_DOCS_DIR` is not needed — `coach.py` searches for the docs directory,
and also honours `STRIDE_DOCS_DIR` if you ever relocate it.

> **Verifying the docs made it.** After the first deploy, check the logs for
> `[coach] WARNING: training doc not found`. Silence means the science docs
> loaded. If you see it, the build context is wrong — check Root Directory is
> blank.

### Point Strava at it
1. strava.com/settings/api → **Authorization Callback Domain**: your Railway
   host (domain only, no scheme or path)
2. Register the webhook once the service is live:
   ```bash
   curl -X POST https://<railway-url>/api/strava/subscribe
   ```
   A 409 means it already exists — that is fine.

---

## 2. Frontend on Vercel

```bash
cd frontend
echo "https://<railway-url>" | vercel env add NEXT_PUBLIC_API_URL production
vercel --prod
```

Without this the deployed site calls `http://localhost:8000` and silently
renders empty. Also worth renaming the Vercel project from `frontend` to
`stride`.

---

## 3. First run

```bash
# 1. Connect Strava — open in a browser, it redirects back to the frontend
open https://<railway-url>/api/strava/connect

# 2. Pull history. Strava's read limit is 100 requests / 15 min, so a full
#    backfill of 500 activities takes several passes. The response tells you
#    whether it stopped early and how much is left.
curl -X POST https://<railway-url>/api/strava/sync/1

# 3. Fill in missing descriptions — this is what pace calibration reads.
#    Re-run every 15 minutes until "rate_limited" comes back false.
curl -X POST https://<railway-url>/api/analysis/1/fetch-descriptions

# 4. Classify and detect PRs
curl -X POST https://<railway-url>/api/analysis/1/classify
curl -X POST https://<railway-url>/api/analysis/1/detect-prs

# 5. Set the goal
curl -X POST https://<railway-url>/api/users/1/goal \
  -H 'Content-Type: application/json' \
  -d '{"goal_type":"race","race_distance":"marathon","target_time_seconds":9900,
       "race_date":"2028-02-06","description":"Sub-2:45 Surf City Marathon"}'

# 6. Generate the plan
curl -X POST https://<railway-url>/api/plans/1/generate
```

---

## Verifying it works

| Check | How |
|---|---|
| Service is up | `GET /health` → `{"status":"ok"}` |
| DB is connected | `GET /api/users/1` returns your profile |
| Strava is linked | `GET /api/analysis/1/baseline` shows real mileage |
| Descriptions landed | `GET /api/analysis/1/calibrated-paces` shows non-empty `data_points` |
| Webhook is live | Upload or edit a Strava run, then check that it appears within a minute |
| Coach has context | Submit feedback; the response should cite specific paces, not generic advice |

---

## Known constraints

- **The Strava rate limiter is process-local.** It holds with a single worker
  (the default). If you ever scale to more than one, the counters need to move
  into Redis or the database or you will get 429s again.
- **No auth.** Every endpoint takes `user_id` in the path and trusts it. Fine
  while it is only you; see `docs/product-vision.md` before sharing the URL.
- **Webhook needs a public URL.** Local development cannot receive them — use
  the manual sync button on the dashboard instead.
