"""SQLite-native backups, a verified restore path, and optional encrypted S3 export.

This module deliberately does not import the application/database modules: it can
protect the database BEFORE startup migrations or stored-data reclassification.
"""
import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

logger = logging.getLogger("stride.backups")


def database_path(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise ValueError("Backups require a file-backed SQLite DATABASE_URL")
    raw = unquote(urlsplit(url).path)
    # sqlite:///relative.db is relative; sqlite:////absolute.db is absolute.
    raw = raw[1:]
    if not raw or raw == ":memory:":
        raise ValueError("Backups require a file-backed SQLite DATABASE_URL")
    return Path(raw).resolve()


def _readonly(path: Path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def _copy_database(source: Path, target: Path):
    deadline = time.monotonic() + 60

    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup exceeded its time budget")

    with _readonly(source) as src, sqlite3.connect(target) as dest:
        src.backup(dest, pages=256, sleep=0.05, progress=progress)


def verify_database(path: Path) -> dict:
    """Read-only integrity and table-count checks. Never initialize missing files."""
    with _readonly(path) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                for name in sorted(names)}


def restore_new(backup: Path, destination: Path) -> dict:
    """Restore to a NEW path only, then verify. Never overwrite a live database."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("Restore destination must not exist")
    expected = verify_database(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="restore-", suffix=".sqlite3", dir=destination.parent)
    os.close(fd)
    staging = Path(temporary)
    try:
        staging.chmod(0o600)
        _copy_database(backup, staging)
        counts = verify_database(staging)
        if counts != expected:
            raise ValueError("Restored table counts do not match the backup")
        os.link(staging, destination)  # atomic no-overwrite publication
        return counts
    finally:
        staging.unlink(missing_ok=True)


def _atomic_json(path: Path, data: dict):
    fd, name = tempfile.mkstemp(prefix="status-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def upload_s3(path: Path, bucket: str, prefix="stride", kms_key_id=None):
    """TLS transport and explicit server-side encryption; no public ACLs or deletes.

    boto3's normal credential chain supplies an IAM identity. Never serialize or
    log credentials, provider response bodies, or exception messages.
    """
    import boto3
    from botocore.config import Config

    key = "/".join(part for part in (prefix.strip("/"), path.name) if part)
    encryption = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key_id} if kms_key_id else {"ServerSideEncryption": "AES256"}
    client = boto3.client("s3", use_ssl=True, config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 2}))
    with path.open("rb") as body:
        client.put_object(Bucket=bucket, Key=key, Body=body, **encryption)
    return key


def backup_once(source: Path, folder: Path, *, keep=28, reason="scheduled", bucket=None, prefix="stride", kms_key_id=None) -> dict:
    if keep < 1:
        raise ValueError("Keep at least one backup")
    if not source.is_file():
        raise FileNotFoundError("Source database is missing")
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)
    now = datetime.now(timezone.utc).isoformat()
    previous = {}
    status_path = folder / "status.json"
    try:
        previous = json.loads(status_path.read_text())
    except (FileNotFoundError, ValueError):
        pass
    name = "stride-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8] + ".sqlite3"
    backup = folder / name
    # Restore to a disposable path verifies a usable copy, rather than checking
    # only that a file was written. WAL data is included by SQLite's backup API.
    with tempfile.TemporaryDirectory(prefix="verify-", dir=folder) as temp:
        snapshot = Path(temp) / "snapshot.sqlite3"
        snapshot.touch(mode=0o600)
        _copy_database(source, snapshot)
        counts = restore_new(snapshot, Path(temp) / "restored.sqlite3")
        os.link(snapshot, backup)
    # Startup also takes a local-only snapshot through app.main. That must not
    # erase an earlier S3 failure or imply a successful offsite copy was made.
    remote_error = previous.get("last_remote_error_type")
    result = {**previous, "last_local_success": now, "last_backup": name, "restore_verified": True,
              "table_counts": counts, "reason": reason,
              "remote_configured": bool(bucket) or bool(previous.get("remote_configured")),
              "last_local_error_type": None, "last_remote_error_type": remote_error, "last_error_type": remote_error}
    if bucket:
        try:
            result["last_remote_key"] = upload_s3(backup, bucket, prefix, kms_key_id)
            result["last_remote_success"] = now
            result["last_remote_error_type"] = None
            result["last_error_type"] = None
        except Exception as exc:
            result["last_remote_error_type"] = result["last_error_type"] = type(exc).__name__
            logger.warning("Off-disk backup export failed (%s); verified local copy retained", type(exc).__name__)
    _atomic_json(status_path, result)
    # Preserve the snapshot named by status even if the wall clock moved back or
    # several snapshots were taken under a frozen test clock.
    older = sorted((p for p in folder.glob("stride-*.sqlite3") if p != backup), reverse=True)
    for old in older[max(keep - 1, 0):]:
        old.unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="Repeat at the configured interval")
    parser.add_argument("--if-exists", action="store_true", help="Allow a first deployment with no database yet")
    parser.add_argument("--reason", default="scheduled")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps({"integrity": "ok", "table_counts": verify_database(args.verify)}))
        return
    if args.restore:
        if not args.destination:
            parser.error("--restore requires --destination (a new file)")
        print(json.dumps({"restored": True, "table_counts": restore_new(args.restore, args.destination)}))
        return
    source = database_path(os.environ.get("DATABASE_URL", "sqlite:///./stride.db"))
    folder = Path(os.environ.get("STRIDE_BACKUP_DIR", str(source.parent / "backups"))).resolve()
    interval = int(os.environ.get("STRIDE_BACKUP_INTERVAL_SECONDS", "21600"))
    if interval < 60:
        parser.error("STRIDE_BACKUP_INTERVAL_SECONDS must be at least 60")
    if args.loop:
        time.sleep(interval)  # startup already created the pre-migration snapshot
    while True:
        try:
            if source.exists():
                result = backup_once(source, folder, keep=int(os.environ.get("STRIDE_BACKUP_KEEP", "28")), reason=args.reason,
                                     bucket=os.environ.get("STRIDE_BACKUP_S3_BUCKET"),
                                     prefix=os.environ.get("STRIDE_BACKUP_S3_PREFIX", "stride"),
                                     kms_key_id=os.environ.get("STRIDE_BACKUP_S3_KMS_KEY_ID"))
                print(json.dumps({"backup_verified": result["last_backup"], "remote_error": result["last_error_type"]}), flush=True)
            elif not args.if_exists:
                raise FileNotFoundError("Source database is missing")
        except Exception as exc:
            logger.error("Database backup failed (%s)", type(exc).__name__)
            if not args.loop:
                raise SystemExit(1) from None
            folder.mkdir(parents=True, exist_ok=True)
            status_path = folder / "status.json"
            try:
                status = json.loads(status_path.read_text())
            except (FileNotFoundError, ValueError):
                status = {}
            _atomic_json(status_path, {**status, "last_local_error_type": type(exc).__name__, "last_error_type": type(exc).__name__})
        if not args.loop:
            return
        time.sleep(interval)


if __name__ == "__main__":
    main()
