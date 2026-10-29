# Beta runbook: inviting other athletes

Stride runs in **owner mode** today: one `STRIDE_PASSWORD`, one athlete, and Garmin through your Personal API
key. This runbook switches Render to **account mode** so invited testers get their own login and data. Settings →
Operational status shows a "Ready for other athletes" checklist that turns green as each step lands. The checklist
reports yes/no only, never values.

Garmin sync for testers needs Garmin Business approval. Until then, testers upload FIT files exported from Garmin
Connect (Settings → Garmin), or start without history. **Never share your Personal API key with other athletes.**

All steps below are changes in the Render dashboard or AWS console. Stride's code doesn't make them for you.

## 1. Before you start
- Merge and deploy `main`. Check that Settings → Operational status shows a recent verified local backup.
- Download a fresh snapshot for safekeeping (`docs/deployment-recovery.md` → Restore).

## 2. Error tracking (Sentry, free tier)
1. Create a Sentry project (platform: Python / FastAPI) and copy its DSN.
2. Render → stride → Environment: add `SENTRY_DSN` = the DSN. Optional: `STRIDE_ENV=production`.
3. Save and redeploy.

What it sends: unhandled backend errors with the stack trace. It doesn't send request bodies (run comments), cookies,
IP or user data, or local variables. Tracing is off. With no DSN, Sentry isn't even imported, so it costs no memory.
The frontend isn't covered yet.

## 3. S3: FIT files and offsite backups
1. AWS → S3 → create a **private** bucket (e.g. `stride-data-<random>`, region us-west-2).
   - Block all public access.
   - Default encryption SSE-S3.
   - Versioning on.
   - Add a lifecycle rule to expire `stride/` backup snapshots after 35 days.
2. IAM → create a user `stride-render` with **only** this inline policy (replace the bucket name):
   ```json
   {"Version":"2012-10-17","Statement":[
     {"Effect":"Allow","Action":["s3:PutObject","s3:GetObject","s3:DeleteObject"],
      "Resource":"arn:aws:s3:::stride-data-XXXX/*"},
     {"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::stride-data-XXXX"}]}
   ```
   Create an access key for it.
3. Render → Environment:

| Variable | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | the `stride-render` key |
| `AWS_DEFAULT_REGION` | the bucket's region |
| `FIT_BLOB_BUCKET` | bucket name. New FIT files go to S3; existing ones stay readable from the database. |
| `STRIDE_BACKUP_S3_BUCKET` | bucket name. Every scheduled verified backup is also uploaded. |

4. Redeploy. After the next backup interval (6 h), or a restart, Settings should show "Offsite export: configured"
   and a last successful offsite export time.

## 4. Account mode
1. Generate secrets on your Mac:
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(12))"
   ```
2. Render → Environment:

| Variable | Value |
|---|---|
| `STRIDE_PROVIDER_ENCRYPTION_KEYS` | the Fernet key (keep a copy in your password manager; losing it loses saved credentials) |
| `STRIDE_SIGNUP_INVITE_CODE` | the invite code (give it only to testers) |
| `STRIDE_PUBLIC_URL` | `https://<your-service>.onrender.com` (or your domain) |

   Keep `STRIDE_PASSWORD` for now. Don't set `STRIDE_ACCOUNTS_ENABLED` yet.
3. Redeploy, then attach your login to your existing athlete (your training data is preserved). In Render →
   Shell:
   ```bash
   cd /app/backend && python -m app.services.accounts bootstrap --user-id 1 --email you@example.com
   ```
   It prompts for a 12–128 character password. Tested Oct 28 on a copy of your database: the account attaches to athlete
   1 and all 582 runs stay. The schema must be current, which Render's startup already ensures.
4. Render → Environment: `STRIDE_ACCOUNTS_ENABLED=true`. Redeploy. Sign in with the email and password.
5. Check: Today, Plan and History show your data; Settings shows the checklist; Garmin still syncs (your
   Personal API key stays owner-only).

**Locked out?** In Render → Shell:
```bash
python -m app.services.accounts recovery --user-id 1
```
It prints a single-use 30-minute recovery token.

**Rollback:** remove `STRIDE_ACCOUNTS_ENABLED` (or set it to `false`) and redeploy. Owner mode with `STRIDE_PASSWORD`
works again; accounts stay in the database for next time.

## 5. Inviting testers (3–5 to start)
- Send each tester the app URL and the invite code. They register and accept `/terms`, then set a goal in onboarding.
- They upload FIT files from Garmin Connect (Activities → ⋯ → Export Original) in Settings to build history, or start
  from reported mileage.
- AI reviews need each tester's AI consent. Spend is capped per athlete (`OPENAI_ATHLETE_MONTHLY_BUDGET_USD`, default
  $1) and app-wide (`OPENAI_MONTHLY_BUDGET_USD`, default $15).
- Watch Render → Logs for `Memory rss=` lines (every 10 minutes) and Sentry for errors in the first week.

## 6. When Garmin Business is approved
Garmin OAuth and push webhooks replace FIT uploads for testers. That's a separate build; see
`docs/multi-user-design.md`.
