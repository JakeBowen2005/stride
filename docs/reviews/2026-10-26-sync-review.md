# Garmin and recent PR review — October 26, 2026

Reviewed merged PRs #42–#46: comment-driven watch feedback, mileage/efficiency history, one-lever marathon progression and rounded bookends, dusk/daybreak UI, and normalized demo laps. Read the backend and frontend diffs, exercised the real provider and local app, and ran the test suites.

## Findings repaired

- Worker-backed sync responses mean queued/running, not success. The UI now polls durable completion, handles terminal errors, distinguishes backoff and partial wellness, and cancels polling on unmount. A bounded wait points to Settings if work remains pending.
- The global navigation now owns app-open/foreground sync on every page. Successful sync emits the refresh event even for corrections or wellness-only updates. History now refreshes its activities and derived charts on that event.
- Connection health requires a verified connection. Saving a replacement encrypted key clears old expiry, authentication backoff, and failed-job delay. Full-history import failures are displayed and its completion refreshes views.
- Wellness refresh used only today/yesterday after an outage. Its recent range now covers the missed interval (bounded to 28 days), while independent historical backfill continues. Failed streams report partial completion and are not cached as a fresh successful refresh.
- PR #44 inferred completed marathon-pace long-run work from any activity on that date. Load progression now requires medium/high-confidence lap matching, full work completion, and target pace; skipped, moved and substituted sessions do not earn that credit.

## Local recovery

The local backend was stopped and its database was still on the older schema. Made a SQLite backup before applying the existing migrations, confirmed successful authenticated activity/sleep/HRV/summary responses, and imported three missing runs plus wellness. Today and History visibly show the recovered activities and the stale-wellness banner is gone. Personal data, credentials and recovery snapshots stay outside Git.

This verifies the local installation; it does not establish the status of a separately hosted deployment. Pull-based background sync requires an awake, running backend/worker (or an always-on deployment).

## Validation

Added regression coverage for queued/retrying/failed/cancelled syncs, partial wellness, missed-day recovery, replacement credentials, and verified marathon-pace work. TypeScript, frontend unit tests, lint and production build pass. Backend full suite and CI cover existing coaching, plan, history, account isolation, container and database behavior. UI checked against real local data in Today and History.
