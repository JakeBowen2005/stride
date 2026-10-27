# Multi-user Stride: design

Status: proposal, Oct 26 2026. Oct 27 2026: roadmap items 1–4, AI consent in every mode (5), the
monthly dollar budgets (9) and `accounts.role` (10, partly) are implemented; see `docs/security.md`.
Turning on account mode in Render, the entity decision, invitations, export-zip import, the
Garmin Business transport and the PostgreSQL cutover are still open.
Scope: going from one athlete (Jake, Personal API key) to a small invited group, each with
their own Garmin account. It also reviews the Garmin Business (Starter) application draft.

Read with [ARCHITECTURE.md](../ARCHITECTURE.md) ("Scaling plan"),
[invite-beta-release.md](invite-beta-release.md) and
[deployment-recovery.md](deployment-recovery.md). Line references are to `main` at `875409b`.

## Summary

- **Most of the account layer already exists.** Invite-only registration, Argon2 passwords,
  revocable sessions, backend ownership checks, per-athlete timezones, AI consent, export
  and erasure, durable per-athlete sync jobs and encrypted provider credentials all shipped
  in PRs #35–#39. They are switched off in production: `render.yaml` doesn't set
  `STRIDE_ACCOUNTS_ENABLED`, so the live app still runs in single-password owner mode.
- **The gap is the Garmin transport.** The Personal API key only reads its owner's account.
  Other runners need the Business program: OAuth 2.0 PKCE consent, **push** webhooks, no
  historical backfill on Starter. Stride is pull-only today, so this is a new ingest path,
  not a config change. History for new runners comes from FIT uploads.
- **Recommended order.** (1) Close the policy, terms and attribution gaps that Garmin
  reviewers check. (2) Turn on account mode for Jake alone. (3) Build the OAuth and webhook
  code against the published spec, behind a flag, while the application is reviewed.
  (4) Move to PostgreSQL before the first external Garmin athlete. (5) Invite a handful of
  runners.
- **The application draft is mostly accurate.** Before submitting, fix five things: the
  entity question, a missing Terms of Service, missing Garmin attribution in the UI, a
  privacy-policy line about data Stride doesn't receive, and export/delete being
  unavailable while account mode is off (details in §3).

---

## 1. Connecting other people's Garmin accounts

### 1.1 What the program offers today

Garmin restructured the Connect Developer Program in Oct 2026 into a **Personal** track and a
**Business** track with **Starter** and **Enterprise** tiers ([program overview][overview];
[DC Rainmaker][dcr]; [Hackster][hackster]).

| | Personal (today) | Business Starter (applying) | Business Enterprise |
|---|---|---|---|
| Who | One person, their own data | "Businesses, organizations and other commercial entities" (form text) | Same, larger scale |
| Auth | API key → 24h bearer (`garmin_api.py`) | OAuth 2.0 PKCE, per user ([spec][pkce]) | Same |
| Delivery | Pull only | **Push only** | Push or ping/pull |
| History | Whatever you can pull | **None** | About 1 month+ (backfill) |
| APIs | Activity (JSON + FIT), Health, Women's Health | + Training, Courses | + Golf |
| Users | 1 | "Limited" (DC Rainmaker reports up to 1,000, free) | Unlimited, with support |

Two caveats:
- Between Aug and Oct 2026 new business sign-ups were paused ([Sahha][sahha],
  [Momentum][momentum]). The Starter form is live again, but expect a slow or uncertain answer.
- Third-party guides say the Personal tier omits training readiness, training status and
  VO2max. That matches `wellness.py`. Whether Starter's Health API includes them is
  unconfirmed. Don't promise them.

### 1.2 OAuth 2.0 PKCE (from Garmin's published spec)

From the Garmin OAuth 2.0 PKCE specification PDF on the developer portal ([pkce]):

- **Authorize:** `GET https://connect.garmin.com/oauth2Confirm` with `response_type=code`,
  `client_id`, `code_challenge` (S256 of a 43–128 character verifier), `code_challenge_method=S256`,
  `redirect_uri` and `state`. Preflight (OPTIONS) is not supported, so this is a browser redirect.
- **Token:** `POST https://connectapi.garmin.com/di-oauth2-service/oauth/token`,
  `grant_type=authorization_code`, with the client secret and the code verifier. The response
  carries `access_token` (`expires_in` 86400, so 24 hours), `refresh_token`
  (`refresh_token_expires_in` about 7,776,000 seconds, so 90 days) and a fixed `scope`. Garmin
  recommends refreshing at least 600 seconds early.
- **Refresh:** same endpoint, `grant_type=refresh_token`. **Each refresh returns a new refresh
  token.** Store it atomically, or the next refresh fails.
- **User ID:** `GET https://apis.garmin.com/wellness-api/rest/user/id` returns a stable
  `userId`. The ID survives disconnect and reconnect. Pushes carry it, which is how Stride
  routes a webhook to an athlete.
- **Permissions:** `GET .../wellness-api/rest/user/permissions` returns, for example,
  `ACTIVITY_EXPORT`, `HEALTH_EXPORT`, `WORKOUT_IMPORT`. The user picks permissions on the consent
  screen, and later changes arrive as a permission-change webhook.
- **Deregister:** `DELETE .../wellness-api/rest/user/registration`. The spec says this **must**
  be called whenever Stride offers "Delete my account" or "Disconnect", or whenever the user
  would reasonably believe they are withdrawing consent.

### 1.3 Push delivery (to confirm in the portal docs after approval)

Garmin's Activity API document and integration guides ([openwearables push][owpush];
[openwearables Garmin][owgarmin]) say:

- Each enabled summary type (activities, activity details, activity files, dailies, sleeps,
  HRV, stress, deregistrations, user permission changes) posts JSON to an **HTTPS URL on a
  standard port** that you configure in the portal. One payload can hold several records if
  the watch hasn't synced for days.
- **Answer 200 within seconds and process asynchronously.** Garmin retries non-200 responses
  and timeouts on its own schedule, and data that misses the retry window is lost. Retries
  cause duplicates, so every write must be an idempotent upsert keyed on Garmin's IDs
  (`summaryId`/`activityId`, `userId` + `calendarDate`).
- Activity files arrive as a notification with a callback URL. Stride fetches the FIT file
  with the athlete's bearer token, so a valid token is still needed after the push.

Unverified until we can read the portal docs: payload field names, whether push requests are
signed, FIT callback URL lifetime, and whether manual uploads are flagged. Build the parser
against recorded fixtures, and treat every field as optional.

### 1.4 How this compares with today's code

| Concern | Today (Personal API) | Business |
|---|---|---|
| Credential | `GARMIN_API_KEY` env, or a Fernet-encrypted key in `provider_credentials` (`kind=garmin_personal`), owner only (`provider_connections.py:18-65`) | Per-user access and refresh tokens, Fernet-encrypted, rotated on every refresh |
| Trigger | `worker.schedule_due` polls every `GARMIN_POLL_MINUTES`; app open → `POST /api/garmin/sync/{id}` | Garmin pushes. Stride doesn't poll. "Sync now" only shows the latest receipt |
| Ingest | `services/garmin.sync_garmin` pulls a date window, then a FIT per new run | Webhook inbox → worker → the same upsert/merge code, fed from payloads |
| Laps | FIT download → `laps_from_fit` | Same function, with the FIT bytes fetched from the callback URL |
| Wellness | 3 range requests (`wellness.py`) | Daily, sleep and HRV pushes. Map them into the same `WellnessDay` rows |
| History | First sync walks the full history | Nothing before connect. FIT and export-zip upload instead (§1.6) |
| Disconnect | `POST /api/garmin/disconnect/{id}` wipes the key and tells the user to revoke at Garmin (`api/garmin.py:177`) | Must also call `DELETE /user/registration`, and must handle Garmin-side deregistration pushes |
| Status UI | `business_pending: user_id != default_user_id` | Connected Garmin `userId`, permissions granted, last push received |

### 1.5 Concrete backend changes

**Configuration** (`config.py`): `GARMIN_CLIENT_ID`, `GARMIN_CLIENT_SECRET`,
`GARMIN_BUSINESS_ENABLED` (default false), and `GARMIN_WEBHOOK_SECRET` (a random path segment,
see below). Keep `GARMIN_API_KEY` as the owner's optional Personal transport until Jake
reconnects through OAuth like everyone else.

**Data model** (one Alembic migration; the repo already uses explicit migrations):
- `garmin_connections`: add `garmin_user_id` (unique, indexed), `transport` (`personal` |
  `business`), `permissions` (JSON text), `connected_at`, `deregistered_at` and
  `last_push_at`. The Garmin user ID is pseudonymous and needed in plaintext to route pushes.
- `provider_credentials`: new `kind='garmin_oauth'`. `ciphertext` holds Fernet JSON
  `{access_token, refresh_token, access_expires_at}`, and `expires_at` is the refresh-token
  expiry. The existing `MultiFernet` key rotation (`STRIDE_PROVIDER_ENCRYPTION_KEYS`) works
  unchanged. Change the primary key to `(user_id, provider)` now, so a second provider never
  needs a table rewrite.
- New `oauth_states`: `state_hash`, `user_id`, `code_verifier` (encrypted), `expires_at`
  (10 min), single use.
- New `garmin_inbox`: `id`, `summary_type`, `garmin_user_id`, `payload` (JSON, size-capped),
  `received_at`, `status`, `attempts`, `error`. It records exactly what arrived, survives
  restarts, and makes reprocessing after a parser fix possible. Prune processed rows after 30
  days. The ingested rows and `source_revisions` stay the evidence of record.
- `activities`: store the device model (`deviceName` in the summary, or the FIT `file_id`
  product) for attribution (§3.3).

**Endpoints** (new `api/garmin_oauth.py` and `api/garmin_webhooks.py`):

| Route | Auth | Does |
|---|---|---|
| `GET /api/garmin/oauth/start` | session | Makes the verifier and state, stores them, returns a 302 to `oauth2Confirm` |
| `GET /api/garmin/oauth/callback` | session + state | Exchanges the code, fetches `user/id` and `user/permissions`, encrypts the tokens, upserts the connection. Refuses a Garmin `userId` already linked to another athlete. Redirects to `/settings?garmin=connected` |
| `POST /api/garmin/disconnect/me` | session | Calls `DELETE user/registration` (queued with retry if Garmin is down), then wipes tokens and marks the connection revoked. Existing route, extended |
| `POST /api/webhooks/garmin/{secret}/{summary_type}` | none (see below) | Size check, JSON parse, one insert into `garmin_inbox`, 200. Nothing else |

The webhook needs two routing exceptions, because today everything under `/api/` is
session-gated:
- `main.athlete_identity` (`main.py:151`) rejects `/api/*` without a session. Add an explicit
  `/api/webhooks/` bypass. The handler must never take an athlete ID from the URL.
- `frontend/proxy.ts` returns 401 for `/api/*` without a cookie. Add `api/webhooks` to the
  matcher exclusions, or route webhooks to FastAPI directly.

Without request signing, defend in depth: an unguessable path secret; drop records whose
`userId` matches no active connection (still answer 200); cap body size; parse into
whitelisted fields only; and fetch FIT files only from Garmin hosts, using our own token,
never a URL host taken from the payload without checking it.

**Worker** (`services/worker.py`): add `garmin_inbox.process_one` to the loop next to
`sync_jobs.process_one`. Per record type:
- *Activities / activity details*: running types only (as `sync_garmin` already filters),
  upsert via `ActivitySource(provider='garmin', external_id=summaryId)`. Reuse the
  Strava-row merge and `history_evidence.capture`, then `reanalyze_laps` and
  `coaching_jobs` the same way a sync does (`api/garmin._sync_in_new_session`).
- *Activity files*: fetch the FIT with a valid token, then `laps_from_fit` and
  `capture(source,'fit',…)`. On a 401, refresh once. On expiry, mark the connection
  `needs_reconnect`.
- *Dailies / sleeps / HRV*: map into `WellnessDay`. Extract a shared `parse_day` from
  `wellness.py` so that both transports feed one function.
- *Deregistration*: revoke the credential, set `deregistered_at`, keep training data, and
  show "Garmin was disconnected from Garmin Connect" in the app.
- *Permission change*: store the permissions. If `ACTIVITY_EXPORT` is gone, show a banner
  and stop expecting runs. Without `HEALTH_EXPORT`, recovery inputs are absent; the coaching
  rules already treat missing wellness as no signal.

**Token upkeep**: a daily job refreshes any token whose refresh expiry is under 14 days away,
so an injured runner who doesn't sync for three months stays connected. Take the per-user
lock (PostgreSQL advisory lock, as `sync_jobs.enqueue` already does) around
refresh-and-store, so two workers never race on a rotating refresh token.

**Erasure** (`api/auth.erase`): before deleting rows, enqueue a Garmin deregistration with
the decrypted token. The deregistration row must outlive the user, like `BlobDeletion` does.

**Keep**: `fit_import.py`, `lap_analyzer.py`, the merge logic, coaching jobs, the plan engine.
None of them care where the run came from.

### 1.6 History without backfill

Starter has no backfill. A new runner's plan would otherwise start with an empty baseline, and
`load_policy` needs about four weeks to set a ramp. Three sources, in order of quality:

1. **Garmin "Export your data" archive.** Garmin Connect lets anyone request a full account
   export (a zip that includes the original uploaded FIT files). Add `POST
   /api/analysis/me/import-archive` as a background job: stream the zip, iterate the FIT
   entries (nested zips included), skip non-running sessions, and call the existing
   `import_fit` per file. `import_fit` already deduplicates by SHA-256 and refuses paid
   reviews for historical imports. Bound the work: maximum archive size, maximum entries,
   progress stored on a job row. This is the biggest win and needs no Garmin approval.
2. **Individual FIT upload**, which exists today (`components/fit-import.tsx`).
3. **Self-reported baseline** from onboarding: weekly mileage, PRs, years running. These are
   already collected, and the engine is conservative when evidence is thin.

Later, Enterprise backfill (about 1 month, one day per request, user opt-in per
[openwearables][owgarmin]) can top up the weeks between export and connect.

### 1.7 Phased plan

| Phase | Needs approval? | Work |
|---|---|---|
| A. Before submitting | No | §3 fixes: entity, Terms page, attribution, privacy wording, account mode on in prod |
| B. While under review | No | Migration + OAuth + inbox + worker + token upkeep behind `GARMIN_BUSINESS_ENABLED=false`, tested with fixture payloads and a fake Garmin (`httpx.MockTransport`, as the Personal client tests do). Export-zip import. Webhook bypass in middleware and proxy |
| C. After approval | Yes | Real client ID/secret in Render, portal callback URLs, Jake connects through OAuth and runs both transports side by side for a week (compare activities and laps), record real payloads as fixtures, fix the parser |
| D. First invites | Yes | PostgreSQL cutover (§2.5), invite 3–5 runners, watch inbox lag, failures and token refreshes |
| E. Later | Yes | Training API: push structured workouts (`WORKOUT_IMPORT`; needs the Garmin data-transfer notice, §3.2). Retire the Personal transport |

---

## 2. Users as the core of the system

### 2.1 What already exists

| Piece | Where | State |
|---|---|---|
| Account mode flag | `STRIDE_ACCOUNTS_ENABLED` (`config.py:10`); `proxy.ts` switches gates | Built, **off in prod** |
| Invite registration | `POST /api/auth/register` (`api/auth.py:61`), one shared `STRIDE_SIGNUP_INVITE_CODE` | Built; one code for everyone |
| Passwords and sessions | Argon2 (bounded to 2 concurrent hashes), 7-day opaque cookie, hashed in `account_sessions`, throttled login (`services/accounts.py`, `api/auth.py`) | Built |
| Recovery | Operator CLI `python -m app.services.accounts recovery` prints a 30-min token | Built; no email |
| Ownership | `main.athlete_identity` resolves `me`, rejects any other athlete ID, fails closed for unknown namespaces | Built, tested for two athletes |
| Per-athlete time | `athlete_clock.athlete_zone` ContextVar, `User.timezone` | Built; leaks listed below |
| AI consent | `User.ai_consent` (default false), checked in `api/coaching.py:22,48`, `services/coaching.py:506`, `coaching_jobs.py:40` | Built; skipped in owner mode |
| AI limits | 30 attempts per athlete per local day, 100 global per day (`config.py:22-25`, `services/coaching.py:493-498`) | Built; counts attempts, not dollars |
| Export and erasure | `account_data.owned_tables` walks every table by `user_id` and FK chain; `/api/auth/export`, `/api/auth/delete` | Built; **account mode only**; doesn't deregister at Garmin |
| Durable jobs | `sync_jobs` (one leased row per athlete), `coaching_jobs`, dedicated `python -m app.services.worker` | Built |
| PostgreSQL | Advisory locks in `sync_jobs`, `_begin_schedule_write`, `schema.py`; CI `postgres` job (`.github/workflows/ci.yml:74`); `database_transfer.py` | Built, not deployed |
| Frontend identity | `USER_ID = "me"` (`frontend/lib/api.ts:8`); 24 files use it | Done; no client change needed |

### 2.2 Single-athlete assumptions that must change

`default_user_id` (16 uses outside `config.py`):
- `main.py:77-82`: legacy in-process poll loop for the owner. It only runs when
  `has_api_key()` is true, which is never in account mode. Delete it once account mode is the
  only mode.
- `main.py:185`: owner mode maps every request to athlete 1. This goes away with owner mode.
- `api/garmin.py:36-38,119,151`: status flags (`can_reconnect`, `business_pending`,
  `owner_key_storage_ready`) and owner-only connect/reconnect. These become "is the Personal
  transport enabled for this account" (`accounts.role == 'owner'`), and Business replaces them.
- `services/provider_connections.py:22,24,32,58,60,63`: Personal-key routing. Same change:
  key on credential `kind` plus owner role, not a magic ID.
- `services/worker.py:23`: schedule_due adds the owner when `GARMIN_API_KEY` is set. Polling
  should cover only `transport='personal'` connections. Business athletes are push-driven.

Global and in-process state:
- `services/garmin_api.py:182` module-level `_client` singleton (already refused in account
  mode) and `provider_connections` `lru_cache` clients (keyed per user; fine, but cleared
  only on disconnect).
- `services/garmin.py:52-68`: one global `_sync_lock` and `garmin_io_lock` in owner mode,
  per-athlete in-process lock dicts in account mode. These are process-local, so correct only
  with one worker. On PostgreSQL, rely on the advisory lock plus the leased `sync_jobs` row
  and drop the dicts.
- `api/garmin.py:18`: `_full_sync_jobs` in-memory dict (fallback status). Delete it; the
  durable `SyncJob` already covers this.
- `api/plans.py:1845` `_begin_schedule_write`: on SQLite this is `BEGIN IMMEDIATE`, a
  **database-wide** writer lock, so every athlete's plan write, feedback save, FIT import
  and sync commit queues behind every other one. On PostgreSQL it's already a per-athlete
  advisory lock.
- 33 naive `datetime.now()`/`date.today()` calls outside `athlete_clock`, 18 of them in
  `services/garmin.py` (quiet hours, backoff, last sync), plus `pace_calibrator`, `analyzer`,
  `history_evidence`, `history_cache`, `wellness` and `worker`. Render pins `TZ=America/
  Los_Angeles` (`render.yaml`), so they are all in Jake's local time. Audit each: storage
  timestamps → UTC; athlete-facing "today" → `athlete_clock.today()`. Quiet hours disappear
  for push users.
- Single shared invite code, no email verification, operator-only recovery.
- `POST /api/users/onboard` creates an athlete with no auth. It's fail-closed in account mode
  (the middleware rejects it), but remove it, or fold it into registration.
- `analyze_athlete` recomputes from full history per call (ARCHITECTURE "Known shortcuts").
  That's fine for ~10 athletes and becomes the first CPU hotspot after that.

### 2.3 Recommended data and auth model

Keep the shape that exists. It's sound:

- **`users` is the athlete** (profile, preferences, timezone, consent), and every training
  table hangs off `users.id`. `account_data.owned_tables` depends on that, so every new table
  must carry `user_id` or an FK to a table that does. Add a test asserting this for every
  model.
- **`accounts` is the login identity**, 1:1 with users. Add `role` (`owner` | `athlete`),
  `email_verified_at`, `created_at` and `disabled_at`. "Owner" grants the operator status page
  and the Personal transport, and nothing else. There's no admin read access to other athletes'
  training. If support needs it later, build it as explicit, logged impersonation.
- **Sessions:** keep the opaque, server-revocable cookie. Don't switch to JWT: revocation and
  "sign out everywhere" already work, and the Next.js proxy is same-origin.
- **Invitations:** replace the shared code with an `invitations` table: hashed single-use
  token, optional email, `expires_at`, `created_by`, `used_by`. Add an owner-only "create
  invite link" button.
- **Email:** add a transactional provider (Postmark/Resend) for verification and password
  reset when the group grows past people Jake can text. Until then, the CLI is fine.
- **Remove owner mode.** Bootstrap Jake's account (`python -m app.services.accounts bootstrap
  --user-id 1 --email …`; this preserves data), turn account mode on, and retire
  `STRIDE_PASSWORD` and `default_user_id`. One mode means one set of tests.

### 2.4 Onboarding a new runner

1. Invite link → register (name, email, password; timezone from the browser; AI reviews off
   unless they tick it, with a link to privacy §3).
2. Profile (the existing `/onboarding` page): age, years running, current and peak mileage,
   PRs, days per week, rest days, long-run day, units, workout format.
3. **Connect Garmin** (OAuth). Show the permissions Stride asks for and why. If they skip,
   FIT import and manual logging still work.
4. **Bring your history**: "Request your Garmin export, then upload the zip", plus single-FIT
   upload. Explain that without it, the first block starts from what they told us.
5. Goal → first block **preview** → approve. The engine already handles a thin baseline
   conservatively (invite doc: fresh accounts show an explicit empty baseline).
6. Waiting state on Today: "Your next run will appear here a few minutes after your watch
   syncs with Garmin Connect."

### 2.5 Database: move to PostgreSQL before external Garmin athletes

Recommendation: **yes, at phase D**, not before. Reasons:
- SQLite's single writer (`BEGIN IMMEDIATE`) serializes all athletes. Pushes, worker jobs,
  FIT archive imports and web writes would contend on one lock.
- A Render service with a persistent disk can run only one instance and has downtime on each
  deploy. That's acceptable for Jake, but webhooks during a deploy get failures, and Garmin's
  retry window is outside our control.
- The groundwork exists: advisory locks, `SKIP LOCKED` claims, the CI Postgres job and a
  verified `database_transfer.py`. The remaining work is operational: a Render Postgres
  instance in Oregon, a staged transfer with paused writes, point-in-time recovery, and
  updated backup docs, since `backups.py` is SQLite-specific.
- Then split the web service and `python -m app.services.worker` into two Render services,
  without a disk.

Staying on SQLite is fine for phases A–C and for a few FIT-only invitees.

### 2.6 Per-user AI budget

Today: 30 attempts per athlete per day and 100 globally. At ~$0.025 per review
(`config.py:23` comment), a busy day could cost $2.50 globally, which is too loose for a
~$15/month target with 10 users and too blunt per person.
- Record cost per attempt: tokens × a model price table → `CoachingAttempt.cost_usd`.
- Enforce **monthly** caps in dollars: a per-athlete cap (e.g. $1/month, configurable per
  account, owner higher) and a global cap (`STRIDE_AI_MONTHLY_BUDGET_USD`, e.g. $15). Keep the
  daily attempt limit as a burst guard.
- When a cap is hit, fall back to the deterministic template explanation. It already exists
  for provider outages, so coaching never stops.
- Show "AI reviews used this month" in Settings, and give the owner a global view.
- Require `ai_consent` in every mode, including the owner. Today owner mode skips the check
  (`api/coaching.py:48`).

---

## 3. Review of the Garmin Business application

Sources reviewed: `docs/garmin-developer-application.md` (Jake's main checkout; not yet in
git), `frontend/app/privacy/page.tsx`, `frontend/app/about/page.tsx`, `frontend/lib/legal.ts`,
the Garmin Connect Developer Program Agreement template Rev. B ([agreement][agreement]), the
Garmin API Brand Guidelines v6.30.2025 ([brand][brand]) and the OAuth spec ([pkce]).

### 3.1 What is accurate

- Push-only, no backfill, FIT history: correct, and it matches the program page.
- Pull-only Personal client, FIT laps, deterministic decisions with the AI only explaining
  them, `store=False` on OpenAI calls, Fernet-encrypted credentials, Render in Oregon, export
  and erasure code, invite-only beta: all match the code.
- The AI disclosure is direct and complete. That's the right call, since the form asks about
  "machine learning or AI platforms" by name.
- The API selection (Activity, Health, Training; no Courses or Women's Health) and "0–100
  users" are proportionate.
- The privacy policy covers what Garmin's agreement §15 asks for: notice, lawful basis,
  data-subject rights (access, correction, erasure, export), no sale, and no model training.

### 3.2 Missing or risky (fix before submitting)

1. **Entity.** The agreement's licensee is the organization, and the form is for commercial
   entities. `legal.ts` says "Jake Bowen (Stride)". Choose one: file a California fictitious
   business name (a DBA for a sole proprietorship), or form an LLC. Use exactly that name on
   the form, in `LEGAL.operator` and on the about page. Garmin also licenses the
   **licensee's** name and logo for its own site (§7.1), which is one more reason to use a
   real name.
2. **No Terms of Service.** Agreement §5.3 requires a written agreement with each end user
   that contains protections and limitations of liability for Garmin's benefit, at least as
   protective as Garmin's own. Add `/terms` (public, linked from about, privacy and
   registration) with a liability limitation, a not-medical-advice disclaimer, acceptable use,
   termination, and the Garmin protections. Registration should record acceptance
   (`accounts.terms_accepted_at`, version).
3. **No Garmin attribution in the UI.** The brand guidelines require "Garmin [device model]"
   near the title of every view showing Garmin device data (Today, run sheet, History charts),
   in secondary views, and in exports. Any AI or derived output materially influenced by
   Garmin data needs wording such as "Insights derived in part from Garmin device-sourced
   data". Garmin "reserves the right to review applications for attribution compliance".
   Stride stores no device model today (no `deviceName` anywhere in `backend/app`). Add the
   column, show "Garmin" when unknown, add the line to AI review cards, and add an attribution
   field to the JSON export. This is small, and it's the most visible thing a reviewer can
   check.
4. **Privacy policy lists data Stride doesn't get.** Section 1 says Health includes
   "Garmin's training readiness and load figures". The Personal API doesn't expose readiness
   (`wellness.py:7`), and Starter's Health API isn't confirmed to. List only what is actually
   received. Over-claiming is a mismatch a reviewer can flag.
5. **Export and delete aren't reachable in production.** The policy and the form both say
   "from Settings at any time", but `/api/auth/export` and `/api/auth/delete` return 404 unless
   account mode is on, and prod runs owner mode. Turn on account mode for Jake (§2.3) before
   submitting, or soften the wording until then.
6. **S3 is described as active.** The privacy table lists S3 for backups and FIT files. If
   `STRIDE_BACKUP_S3_BUCKET` and `fit_blob_bucket` aren't set in Render, say "if enabled" or
   remove the row. The draft's own checklist already flags this for the form.
7. **Revenue clause.** Agreement §5.2(e) forbids deriving income from use of the API without
   Garmin's prior written permission. The draft's "planned individual subscription" is honest
   and should stay. Expect to need written permission (or an Enterprise conversation) before
   charging. Don't start billing on a Starter key.
8. **Disconnect wording.** The policy says deletion removes the Garmin connection
   "immediately". Once Business ships, that has to include calling Garmin's deregistration
   endpoint (§1.5), which the spec requires.
9. **Data sent *to* Garmin (Training API).** The agreement requires conspicuous notice with a
   link to the Garmin Connect privacy notice, plus express consent, before uploading user data
   to Garmin. Add that consent step when workout push is built. Until then, the form's
   "would" phrasing is right.
10. **Security obligations.** §5.1(f)–(g) require a security program meeting Garmin's Minimum
    Security Requirements, and notification to security@garmin.com and by phone within 24
    hours of finding an exploitable weakness. Write a one-page `docs/security.md`: who is on
    call, how secrets are rotated, how to revoke tokens, the breach-notification steps.
11. **Contact email.** `legal.ts` uses a personal Gmail. A domain address (e.g. on a domain
    for the about page) reads better and survives a change of hands. It isn't blocking.
12. **Effective date.** The privacy page says Oct 27 2026. Make sure it isn't later than the
    submission date.

### 3.3 What Garmin reviewers will look for

From the agreement, brand guidelines and developer reports:
- A real organization, with a website and privacy policy that describe the same product and
  the same data handling as the form (§4.2 lets Garmin review the application before launch
  and decline it at its discretion).
- Correct OAuth use: never asking for Garmin passwords (§15.8). Stride's Personal-key paste
  box must never be offered to other users. Today it's owner-only (`api/garmin.py:119`). Keep
  it that way.
- Deregistration and permission handling: the delete-registration call, and honoring
  permission changes.
- Attribution on every Garmin-data view, export and AI output.
- Use limited to the stated purpose: "internal business purposes" and display in Stride
  (§4.1(b)), consistent with each user's consent. No resale, ads or competing-product promotion.
- A sensible scope: only the APIs the app uses.

### 3.4 Note on AI and Garmin data

The Rev. B template agreement has no AI-specific clause (searched), and the brand guidelines
*permit* AI use with attribution. A commenter on DC Rainmaker quotes a newer clause barring AI
model use of device-sourced data. Read the agreement presented at approval for any AI or
model-training language before signing. If it forbids sending Garmin data to an AI provider,
keep the deterministic coach for Business users and use AI reviews only on non-Garmin inputs,
or ask Garmin in writing. Stride never trains models, which is the most likely target of such
a clause.

---

## 4. Roadmap

**Small (hours to a day each; no approval needed)**
1. Fix the privacy policy: Health data list, S3 "if enabled", disconnect wording (§3.2 #4, #6).
2. Store the device model and add Garmin attribution to Today, the run sheet, History, AI
   cards and the export (§3.2 #3).
3. Add a `/terms` page, plus terms acceptance at registration (§3.2 #2).
4. Write `docs/security.md` with the 24-hour Garmin notification step (§3.2 #10).
5. Bootstrap Jake's account and turn on account mode in prod. Require AI consent in every mode.
6. Delete dead single-athlete code: `main.garmin_auto_sync`, `_full_sync_jobs`,
   `/api/users/onboard`.

**Medium (days)**
7. Single-use invitation links (`invitations` table, owner button).
8. Garmin export-zip import as a background job (§1.6).
9. Monthly per-user and global AI budgets in dollars, plus usage in Settings (§2.6).
10. `role` on accounts; replace `default_user_id` checks with role and credential kind (§2.2).
11. UTC/athlete-time audit of the 33 naive clock calls.

**Large (a week or more)**
12. Garmin Business transport: migration, OAuth, webhook inbox, worker processors, token
    upkeep, deregistration, fixtures. Built behind a flag, during review (§1.5).
13. PostgreSQL cutover and web/worker split on Render (§2.5).
14. Transactional email for verification and recovery.
15. Training API workout push, with Garmin's data-transfer consent (§3.2 #9).

## 5. Open questions for Jake

1. **Entity:** DBA, LLC, or keep Stride personal (Personal API only) for now? This decides
   whether to submit at all.
2. **Domain:** is there one (for the about page, email and Garmin callback URLs), or is the
   Render subdomain the public URL? Garmin needs stable HTTPS callback URLs.
3. **Is account mode on in Render today** (dashboard env vars beyond `render.yaml`)? Are the S3
   buckets configured?
4. **Who are the first invitees,** how many, and do they all use Garmin? This sets whether
   PostgreSQL is needed before or after the first invite.
5. **AI budget:** is ~$15/month still the global cap? What per-runner cap feels right?
6. **Money:** any plan to charge in the next 12 months? If so, ask Garmin for written
   permission early (§3.2 #7).
7. **Training API:** is pushing workouts to the watch wanted for the first external release,
   or later? Dropping it from the request makes the first review smaller.
8. **Your own data:** move yourself to OAuth once approved (one transport), or keep the
   Personal key alongside it?

## Sources

- Garmin Connect Developer Program overview: <https://developer.garmin.com/gc-developer-program/overview/> [overview]
- Garmin OAuth 2.0 PKCE specification: <https://developerportal.garmin.com/sites/default/files/OAuth2PKCE.pdf> [pkce]
- Garmin Connect Developer Program Agreement (template Rev. B): <https://developerportal.garmin.com/sites/default/files/Garmin%20Connect%20Developer%20Program%20Agreement.pdf> [agreement]
- Garmin API Brand Guidelines v6.30.2025: <https://developer.garmin.com/downloads/brand/Garmin-Developer-API-Brand-Guidelines.pdf> [brand]
- Starter access form: <https://www.garmin.com/en-US/forms/StarterGarminConnectDeveloperAccess/>
- DC Rainmaker, Garmin revamps the Connect Developer API (Oct 2026): <https://www.dcrainmaker.com/2026/10/garmin-connect-api-revamps-connect-developer.html> [dcr]
- Hackster.io, Garmin reopens its Connect Developer Program: <https://www.hackster.io/news/garmin-reopens-its-connect-developer-program-for-fitness-wearable-data-with-new-business-tiers-8d657d04723b> [hackster]
- the5krunner, Garmin Personal API key: <https://the5krunner.com/2026/10/22/garmin-personal-api/>
- Sahha, Garmin paused its developer program: <https://sahha.ai/blog/garmin-developer-program-paused/> [sahha]
- Momentum, Garmin developer program paused: <https://www.themomentum.ai/blog/garmin-developer-program-closed-roadmap> [momentum]
- Open Wearables, Garmin integration: <https://openwearables.io/docs/providers/garmin-api-integration.md> [owgarmin]
- Open Wearables, Garmin push notifications: <https://openwearables.io/blog/garmin-api-push-notifications-how-callback-sync-works> [owpush]

[overview]: https://developer.garmin.com/gc-developer-program/overview/
[pkce]: https://developerportal.garmin.com/sites/default/files/OAuth2PKCE.pdf
[agreement]: https://developerportal.garmin.com/sites/default/files/Garmin%20Connect%20Developer%20Program%20Agreement.pdf
[brand]: https://developer.garmin.com/downloads/brand/Garmin-Developer-API-Brand-Guidelines.pdf
[dcr]: https://www.dcrainmaker.com/2026/10/garmin-connect-api-revamps-connect-developer.html
[hackster]: https://www.hackster.io/news/garmin-reopens-its-connect-developer-program-for-fitness-wearable-data-with-new-business-tiers-8d657d04723b
[sahha]: https://sahha.ai/blog/garmin-developer-program-paused/
[momentum]: https://www.themomentum.ai/blog/garmin-developer-program-closed-roadmap
[owgarmin]: https://openwearables.io/docs/providers/garmin-api-integration.md
[owpush]: https://openwearables.io/blog/garmin-api-push-notifications-how-callback-sync-works
