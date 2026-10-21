# Coaching trust and cloud hardening

This change follows the review of PRs 7–14 and preserves PR15's seven-weekday regression suite. Stride remains a single-athlete service: deterministic training rules author prescriptions, model advice explains evidence and selects prevalidated candidates, and the athlete approves changes.

## Activity identity and classification

Every run review uses the requested activity's own laps and metrics. A shakeout does not inherit another run's workout or prescribed-day feedback. Home uses the backend's primary activity ID, and its fallback excludes walks. Detected work carries matched activity IDs. Planned-day feedback is tied to its activity ID. Correcting that activity to a walk archives its feedback, execution and evaluation in an audit history; another run that day cannot inherit them, and already-applied progression is never replayed. Walks cannot enqueue paid running reviews; already queued walks are stopped without a model call. Structured pace calibration also excludes execution records whose activity IDs are no longer eligible runs.

Slow pace alone never creates a walk label. Provider walking/hiking types and explicit athlete corrections take precedence; trail/outdoor running and races recover from legacy pace-only exclusion. Existing treadmill/unknown walk labels are retained for confirmation because they may represent genuine walks. Slow ambiguous activities display their uncertainty and offer Run / Walk / Automatic corrections in History detail. Corrections persist across imports. No speed threshold can establish whether a technical trail effort or beginner run counts. This deliberately replaces the older 16:30/mi automatic exclusion policy.

## Execution, assessment and coaching freshness

See [offline coaching cases](coaching-evaluation-cases.md) for partial/substitution rules, their numerical policy choices and validation limits. Repetition completion, controlled execution, a different session, unknown evidence and mileage adherence have distinct meanings. Unknown subjective feel is never fabricated. Work minutes sum each segment; a mixed ladder is not median rep length times rep count.

Demanding long runs require verified hard-segment execution before they earn quality credit; distance completion alone cannot establish marathon-pace success. Provisional coaching context uses the same progression gates as persisted feedback, including taper and adapted-session holds.

All stale advice, including reviews without suggestions and already-applied reviews, is visibly archived. Review type, model, policy and evidence time are visible. Workout-menu and saved-review GET requests validate alternatives in isolated in-memory trials without SQLite writes or savepoints, so simultaneous page requests do not compete for writer locks. Page views do not refresh a paid stale review; new-run jobs and explicit requests remain bounded by the existing quota. Old model prose is never silently relabeled as a current review. Athlete concerns remain requests to evaluate checked options, not commands granting the model new powers.

## One mileage definition

`services/load_history.completed_week_load` defines the most recently completed Monday–Sunday as the numerator and four completed calendar weeks, including that week, as the denominator. Missing weeks count as zero; current partial weeks and future activities are excluded. Planning and current-fitness baseline use the same full-week definition. Stored plan baselines display their as-of date separately from the latest assessment.

The high/moderate/balanced/below-baseline labels retain Stride's authored 1.5/1.3/0.8 ratio boundaries for trend display. These are not validated injury cutoffs, injury probabilities or permission to increase volume. They do not override the plan's history, recovery, spacing and budget decisions. The full numerator, denominator and dates are exposed so the ratio can be checked.

## Product behavior

The calendar and actual-versus-planned inspector remain. One coaching state distinguishes run synced/review queued, review in progress, current advice, pending approval, applied change, fallback and stale advice. Schedule conflict leads to the actual session Move controls rather than implying the model can reschedule a block through prose. A shared units preference converts dashboard, history, charts, sessions and details; explicitly authored source descriptions retain their labeled units. Saved schedule preferences and latest profile preferences are compared; editing preferences does not silently rewrite an approved block.

Settings exposes sanitized operational status: review queue counts and oldest queued time, verified local backup time and errors, and whether offsite export is configured. No bucket names, keys, table counts, credentials or backup filesystem paths are returned there.

## Deployment

See [backup and recovery](deployment-recovery.md). File-backed SQLite is backed up and restore-verified before application migrations or automatic legacy reclassification, including local/direct uvicorn startup; cloud startup also runs the standalone pre-start backup before importing the app. Cloud supervision runs six-hour backup jobs with local retention and optional encrypted HTTPS S3 export. Missing/corrupt existing database backup fails startup before migration. First startup with no database is permitted.

`/health` and `/livez` are liveness; `/ready` checks the database and frontend `/healthz` performs a bounded backend readiness request. Container CI builds the shipped image and tests authentication, readiness, persistent restart, restore and process supervision with synthetic data and disabled providers. Login has per-client and global attempt limits, signed seven-day sessions and sign-out; rotating the app password invalidates sessions. Existing year-long cookies require sign-in again. This is intentionally single-instance, not multi-user/distributed authentication.

Offsite exports require a private S3 bucket and a scoped IAM identity supplied through deployment secrets. Code and mocked tests cannot create or prove a functioning external recovery destination. Until configured, Settings says so. The daily OpenAI attempt cap bounds request count, not currency spend. Offline context/model-boundary tests are not evidence of live-model factual quality; use the documented case set for explicitly authorized staging evaluations before future model/prompt changes.
