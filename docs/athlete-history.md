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
