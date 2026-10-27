# Deployment and recovery

The default deployment uses one Render container, SQLite and a persistent disk.
Invite-only accounts, durable workers and PostgreSQL migration support are now
available; see the [deployment settings and cutover commands](../README.md#worker-migrations-and-storage-deployment)
and [invite beta release record](invite-beta-release.md). The snapshot/restore
workflow below applies to SQLite. Managed PostgreSQL needs its own verified
backup and point-in-time recovery configuration.

## Backups before startup changes and while running

The container entrypoint runs `python -m app.services.backups --if-exists
--reason pre-start` **before importing the application**, so an existing database
has a verified snapshot before additive migrations or derived-data rewrites.
Failure to make a usable local snapshot stops startup. Upload imports are checked
for SQLite integrity before replacement; the imported database is also backed up
before migration. Previous raw database files are retained as before.

While the container is running, a separate supervised process takes another
snapshot every six hours. SQLite's online backup API includes committed WAL data
without stopping running requests. Each snapshot is restored to a disposable file;
integrity and all table counts must agree before publication. Files are mode 600,
the backup directory is mode 700. A failed snapshot is not published. The latest
status is written atomically to `STRIDE_BACKUP_DIR/status.json`, including local
and remote success times, restore verification and exception types without payloads.

Settings are environment variables (defaults shown):

| Variable | Default | Purpose |
| --- | --- | --- |
| `STRIDE_BACKUP_DIR` | database directory + `/backups` | Must be on persistent disk; Blueprint uses `/var/data/backups`. |
| `STRIDE_BACKUP_INTERVAL_SECONDS` | `21600` | Interval; minimum 60 seconds. |
| `STRIDE_BACKUP_KEEP` | `28` (Render: `7`) | Maximum verified local snapshots, including startup snapshots. |
| `STRIDE_BACKUP_MAX_BYTES` | `536870912` | Local snapshot byte budget (512 MiB); the latest verified snapshot is preserved. |
| `STRIDE_BACKUP_S3_BUCKET` | unset | Enables optional off-disk export. |
| `STRIDE_BACKUP_S3_PREFIX` | `stride` | Object-key prefix. |
| `STRIDE_BACKUP_S3_KMS_KEY_ID` | unset | Optional KMS key; otherwise S3 AES256 encryption. |

Retention is bounded by both count and bytes, not a promise of seven days:
frequent deploys create extra snapshots and shorten the time covered. Monitor disk space and choose
retention for the real database size. Backup timing depends on the app remaining
running; a suspended or unavailable service cannot create snapshots.

## Off-disk recovery requires external configuration

**This code does not create or configure an S3 bucket or cloud credentials.**
Until `STRIDE_BACKUP_S3_BUCKET` and an IAM credential identity are configured in
Render, backups live on the same Render disk and cannot protect against losing
that disk. The status explicitly reports `remote_configured: false` in that case.

Use a private S3 bucket, block public access, require TLS and encryption in bucket
policy, and grant only `s3:PutObject` on the chosen prefix to the app identity
(plus required KMS permissions if using a customer key). Supply credentials through
the normal AWS environment/IAM chain, never Git or a browser variable. Uploads use
HTTPS and explicitly request `AES256` or `aws:kms` server-side encryption. A failed
export leaves the verified local backup intact and records a warning; startup is
not dependent on S3 availability. Configure a bucket lifecycle policy separately;
the app never deletes remote objects. Keep recovery download access separate from
the app's upload identity. No real bucket upload was part of automated tests.

Render's persistent disk and daily disk snapshots are useful but do not replace
a database-specific, tested backup/restore workflow. See [Render's disk recovery
guidance](https://render.com/docs/disks#restoring-a-custom-database).

## Restore without overwriting the running database

1. Stop the app before any database cut-over. Keep the existing database and its
   WAL/SHM sidecars together as a recovery copy.
2. Select a verified local snapshot, or securely download an off-disk snapshot.
3. Restore into a **new path** with the backend environment:

   ```sh
   cd /app/backend
   python -m app.services.backups --restore /var/data/backups/SELECTED.sqlite3 --destination /var/data/recovered.db
   ```

4. The command refuses an existing destination and verifies integrity/table counts.
   Start an isolated instance against `sqlite:////var/data/recovered.db` with Garmin
   polling and both model keys disabled. Check the athlete, recent runs and active
   plan. Do not reconnect providers during recovery validation.
5. Only after verification, set `DATABASE_URL` to the recovered path or perform a
   controlled file cut-over while stopped. Keep the previous database until the
   restored app has been checked. Code rollback and database recovery are separate.

The CLI never overwrites a live database. The one-time `stride-upload.db` import
is an explicit cut-over mechanism, not a scheduled restore job.

## Shipping and verification

CI builds the actual Docker image, seeds synthetic data with providers disabled,
checks password-gated API access and readiness, replaces the container while
keeping its volume, restores a snapshot to a new file, and verifies the supervisor
exits if the backend dies. These tests use no Garmin, OpenAI, Anthropic or S3 calls.
Backup unit tests also cover uncheckpointed WAL data, corrupt sources, refusal to
overwrite a destination, retention and encrypted upload parameters using mocks.
