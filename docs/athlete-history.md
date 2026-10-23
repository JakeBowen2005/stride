# Athlete history and analysis

## Ingestion and evidence

Garmin discovery and FIT enrichment have separate completion states. A completed
history scan means the available summary pages were checked; it does not promise
that every day was recorded or that every FIT was available.

- Activity IDs stay stable through matching. Provider aliases live in
  `activity_sources`; original summaries and FIT bytes are content-addressed,
  immutable `source_revisions`. Original manual/Strava values are retained before
  upgrading a row. Athlete feedback and classification overrides are preserved.
- FIT evidence lives in its own SQLite table so existing consistent database
  backups include it. This deliberately favors recoverability over an additional
  file/object-store deployment. Monitor database size before extracting blobs to
  external storage; never embed them in dashboard/model responses.
- Routine scans refresh changed summary measurements. A weekly summary-only
  reconciliation discovers old late uploads and corrections. Explicit full sync
  refreshes existing FITs as well. Missing timestamps fail rather than assigning
  a historical run today's date.
- Failed enrichment persists attempts, sanitized errors and retry times. Each
  routine sync retries at most ten old pending sources independently of the
  discovery dates, with exponential backoff and five attempts. Exhausted sources
  are marked unavailable; explicit full sync can retry them.
- Manual placeholders match only an unambiguous same-day distance within 5%.
  Ambiguous doubles remain separate, preserving the athlete report for resolution.
- Evidence changes enqueue revision-specific automatic coaching only for recent
  runs. Pending older versions are superseded. Importing years of history never
  queues years of paid reviews or replays past progression effects.
- `schema_migrations` records transactional data upgrades after additive schema
  creation. Existing rows are adopted as **legacy snapshots**, never fabricated
  original Garmin payloads. Startup's existing backup precedes migration.

All regression tests use disposable databases, fake clients and a minimal FIT
fixture with distinct timer/elapsed times. No Garmin or model credentials are
needed. Original summary payloads retain local/UTC metadata when supplied;
canonical `Activity.date` remains the existing local training-calendar timestamp.

## Derived facts and caches

`GET /api/analysis/{user_id}/history` exposes an observed historical profile:
current completed weeks, up to three non-overlapping sustained four-week blocks,
long-run evidence and recording gaps. Historical capacity is explicitly separate
from current fitness. Every block references real activity IDs; absent weeks are
unknown recording coverage, not a claim that the athlete rested.

Activity edits dirty their affected calendar dates; moving a run dirties both
old and new dates. The next materialization rebuilds those daily facts and folds
weekly facts from them. Athlete input revisions invalidate persistent historical
and baseline snapshots. Feedback, wellness, goals, profile and schedule edits
also invalidate dependent analysis. Rollbacks roll back invalidation. Bulk ORM
edits conservatively invalidate all facts because they bypass per-object history.
Snapshot keys include calculation version and local as-of date, so midnight and
algorithm updates cannot silently reuse yesterday's interpretation. Read-only
schedule trials never flush or populate caches. The explicit analysis endpoints
serialize cache materialization with the existing SQLite write mechanism.

Wellness records immutable range responses and independent endpoint coverage.
One historical chunk of at most 28 days is attempted per sync after the initial
recent import, working backward to the first stored activity. An empty successful
response records access without inventing measurements; partial endpoint failure
does not advance the common history cursor. Corrected resting HR recalculates the
following seven days' derived baseline. History does not imply that the athlete
wore a compatible device for that entire interval.
