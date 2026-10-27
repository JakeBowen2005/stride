# Security program (one page)

Status: October 2026. Required before the Garmin Business application (Garmin developer agreement
§5.1(f)–(g); see `docs/multi-user-design.md` §3.2 #10). Owner: Jake Bowen, the only person with
production access.

## Who is on call

- **Jake Bowen**, the operator, at the contact address in `frontend/lib/legal.ts`. There is no second
  on-call person. If Jake is unreachable for more than 24 hours during an incident, the app is paused
  (Render service suspended) rather than left running unattended.

## Secrets and where they live

| Secret | Where | Rotation |
|---|---|---|
| `GARMIN_API_KEY` (Personal API, owner only) | Render env / `backend/.env` locally; never committed | Regenerate in Garmin Connect → Personal API token, update Render, redeploy |
| Garmin OAuth tokens (Business, future) | `provider_credentials`, Fernet-encrypted | Rotate on every refresh; revoke via `DELETE user/registration` |
| `STRIDE_PROVIDER_ENCRYPTION_KEYS` | Render env | Prepend a new key (MultiFernet), redeploy, re-encrypt, then drop the old key |
| `OPENAI_API_KEY` | Render env | Rotate in the OpenAI dashboard; old key revoked immediately |
| `STRIDE_PASSWORD` / account passwords | Render env / Argon2 hashes in `accounts` | Owner password changed on suspicion; users reset via the operator CLI |
| `STRIDE_SIGNUP_INVITE_CODE` | Render env | Change after each invite round |
| S3 backup credentials (if enabled) | Render env | Rotate in AWS IAM; least-privilege bucket policy |

Never paste a secret into an issue, PR, log line or AI prompt. Provider errors are logged by exception
type only (`openai_coach.py`, `garmin_api.py`), never with request or response bodies.

## Revoking access

1. **One athlete:** delete their sessions (`account_sessions`) and provider credentials; for Business,
   call Garmin deregistration.
2. **Everyone:** rotate `STRIDE_PROVIDER_ENCRYPTION_KEYS` so stored tokens can't be decrypted, delete all
   `account_sessions`, and rotate `OPENAI_API_KEY` and the Garmin key or client secret.
3. **Emergency stop:** suspend the Render service. Data stays on the disk and in backups.

## If something goes wrong (breach or exploitable weakness)

1. **Contain** (minutes): suspend the service or the affected route; revoke credentials as above.
2. **Notify Garmin within 24 hours** of discovering any exploitable weakness or breach affecting Garmin
   data: email **security@garmin.com** and call Garmin as the agreement specifies. Record the time.
3. **Assess**: which athletes and which data; preserve logs and a database snapshot before changing anything.
4. **Notify affected athletes** as the law requires (California Civil Code §1798.82 for California residents),
   and update `docs/deployment-recovery.md` with what happened.
5. **Fix and review**: patch, add a test that reproduces the issue, rotate every secret that may have been exposed.

## Baseline controls already in place

HTTPS only; HTTP-only secure session cookies; Argon2 passwords; login throttling; backend ownership checks
on every athlete path (`main.athlete_identity`); same-origin write checks in account mode; Fernet-encrypted
provider credentials; OpenAI calls with `store=False`, no tools and bounded structured output; 6-hourly
backups with a restore drill in `docs/deployment-recovery.md`; no analytics or third-party trackers.

## Review

Re-read this page before each Garmin submission and whenever a new provider, secret or data type is added.
