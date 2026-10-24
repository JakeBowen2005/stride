# Invite beta implementation, October 2026

The five workstreams are implemented as separate PRs. This is an invite-only beta
foundation; live connections for additional Garmin athletes still require an approved
Garmin Business application and its integration contract.

## What changed

1. **Storage reliability and late watch feedback — PR #35.** SQLite snapshots have a
   byte budget, retention pruning and a free-space guard. The Render blueprint requests
   a 5 GB disk and seven snapshots. Recent Garmin details are rechecked so delayed watch
   feel/effort ratings can reach the activity and trigger an updated review.
2. **Feedback and goal decisions — PR #36.** Feedback belongs to the selected activity,
   including doubles, off-plan runs and previous blocks. Only the eligible primary run
   changes current-block progression. Athletes can save completion, later-date or
   shorter-distance goal decisions; replacement blocks still need approval.
3. **Accounts and isolation — PR #37.** Invite-only registration, Argon2 passwords,
   expiring/revocable sessions, single-use recovery, persistent throttling and backend
   ownership checks replace trusting a client user ID. Settings expose timezone, AI
   consent, export and password-confirmed erasure. The existing owner login remains
   available when accounts are disabled.
4. **History operations — PR #38.** Explicit Alembic migrations, a dedicated worker,
   leased/retryable per-athlete sync jobs, encrypted provider credentials, athlete-local
   dates, original FIT import/deduplication/reparse, optional private S3 evidence storage
   and durable blob erasure. A read-only SQLite-to-empty-PostgreSQL transfer tool has
   row-count and sequence checks. Real PostgreSQL CI tests concurrency and migration.
5. **Coaching and training experience — PR #39.** Daily minute limits fit sessions
   without inventing faster paces or cramming displaced miles elsewhere. Full quality
   moves to a suitable roomier day first; a reduced main dose cannot earn progression.
   Introductory run/walk prescriptions retain their numeric running and walking parts.
   Plan cards explain priorities and what earns progression. Finite schedule/goal gaps
   become explicit decisions. History adds cached 4/8/12-week descriptive analysis,
   comparable easy runs and long-run follow-up with evidence IDs and uncertainty. AI
   context receives those facts; global/per-athlete limits, attempt latency/token
   reporting and an offline coach-label evaluation harness support cost and quality
   review. Unlabeled evaluation cases cannot pass.

The final integration also scopes bulk cache invalidation and PostgreSQL scheduling
locks to the affected athlete, preserves FIT deduplication after Garmin reconciliation,
bounds concurrent password hashing, batches due sync scheduling, adds stable history
pagination and removes owner-specific mileage defaults from onboarding.

## Verification

- Disposable SQLite databases only; no personal `backend/stride.db` changes and no live
  Garmin or OpenAI calls.
- Backend full suite, frontend TypeScript/lint/unit tests and production build.
- CI runs the backend suite with every weekday clock, a real PostgreSQL service and a
  container build/smoke test.
- Seven standard demo programs regenerated with start date **2026-10-21** remain
  byte-for-byte identical, including advanced programs. The new
  [time-limited beginner comparison](demo-programs/time-limited-beginner.md) demonstrates
  full-dose scheduling and an explicit goal/availability gap.
- Realistic-history simulations rerun with `--no-laps`, `--hard-from-week 3`,
  `--skip-every`, and a mid-program goal change. The descriptive review is in
  [realistic histories](demo-programs/realistic-histories.md).
- Synthetic mobile browser review covers the plan, history trends, prior-block feedback
  and account settings. Fresh accounts show an explicit empty baseline instead of
  crashing Settings. The mobile sign-out control explicitly submits its form. API tests cover two-athlete isolation, FIT import/reimport,
  export/erasure, session/recovery replay, consent and schedule validation.

## Deployment work that remains external

Use [deployment and recovery](deployment-recovery.md) for commands and rollback details.

- Apply dashboard disk expansion to existing Render services; editing the blueprint does
  not resize a running disk. Configure and restore-test offsite backups separately.
- Set the account feature flag on both services, the exact public URL, a strong invite
  code, encryption keys and HTTPS secure cookies. Bootstrap the existing owner's account
  before inviting anyone. Recovery tokens currently require operator assistance; there
  is no automated email delivery or verified-email flow.
- Provision a private FIT bucket before enabling external evidence storage. PostgreSQL
  requires a staged transfer, paused writes, restored-data validation and a deliberate
  cutover. No live database migration, bucket provisioning or infrastructure resize was
  performed by this work.
- Obtain Garmin Business approval. Additional athletes can import original FIT files in
  the meantime; the owner's Personal API key is never shared across accounts.
- Have a running coach label the evaluation corpus and review actual opt-in AI output
  before claiming its coaching quality is validated. Current automated checks establish
  data/decision validity, not independent coaching judgment.

## Before the first invitation

Restore a backup into staging; run migrations; register two disposable athletes; prove
that neither can read or mutate the other's history, jobs or plans; import and reimport
one FIT file; test recovery/session revocation and export/erasure; verify timezone dates;
review a schedule-limited plan and a goal decision; confirm worker retries and AI consent;
then invite a small group and monitor failed jobs, latency, token use and storage growth.
