"""Recovery tests only ever create disposable SQLite databases."""
import json
import os
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.services.backups import backup_once, database_path, restore_new, upload_s3, verify_database


def test_online_backup_contains_committed_wal_and_restores_without_overwriting(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY, notes TEXT)")
        db.commit()
        db.execute("INSERT INTO runs(notes) VALUES ('committed in WAL')")
        db.commit()
        result = backup_once(source, tmp_path / "backups")
        assert result["restore_verified"] and result["table_counts"] == {"runs": 1}
        assert result["remote_configured"] is False
        backup = tmp_path / "backups" / result["last_backup"]
        destination = tmp_path / "restored.db"
        assert restore_new(backup, destination) == {"runs": 1}
        with sqlite3.connect(destination) as restored:
            assert restored.execute("SELECT notes FROM runs").fetchone()[0] == "committed in WAL"
        with pytest.raises(FileExistsError):
            restore_new(backup, destination)
        assert backup.stat().st_mode & 0o777 == 0o600


def test_backup_retention_and_remote_failure_preserve_verified_local_data(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE runs(id INTEGER)")
    folder = tmp_path / "backups"
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: (_ for _ in ()).throw(TimeoutError("secret payload")))
    for _ in range(3):
        result = backup_once(source, folder, keep=2, bucket="test-bucket")
    assert len(list(folder.glob("stride-*.sqlite3"))) == 2
    assert result["last_error_type"] == "TimeoutError"
    assert result["last_local_success"] and result["restore_verified"]
    assert "secret payload" not in (folder / "status.json").read_text()
    assert verify_database(folder / result["last_backup"]) == {"runs": 0}


def test_s3_upload_requests_tls_and_server_side_encryption(tmp_path, monkeypatch):
    calls = []
    path = tmp_path / "backup.sqlite3"
    path.write_bytes(b"synthetic snapshot")
    def client(service, **kwargs):
        assert service == "s3" and kwargs["use_ssl"] is True
        def put(**args):
            calls.append({**args, "Body": args["Body"].read()})
        return types.SimpleNamespace(put_object=put)
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "botocore.config", types.SimpleNamespace(Config=lambda **args: args))
    assert upload_s3(path, "synthetic", "athlete") == "athlete/backup.sqlite3"
    upload_s3(path, "synthetic", "", "kms-test-key")
    assert calls[0]["ServerSideEncryption"] == "AES256"
    assert calls[1]["ServerSideEncryption"] == "aws:kms" and calls[1]["SSEKMSKeyId"] == "kms-test-key"
    assert calls[0]["Body"] == b"synthetic snapshot"


def test_refuse_missing_corrupt_and_non_sqlite_sources(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_once(tmp_path / "missing.db", tmp_path / "backups")
    assert not (tmp_path / "missing.db").exists()
    corrupt = tmp_path / "bad.db"
    corrupt.write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError):
        restore_new(corrupt, tmp_path / "output.db")
    assert not (tmp_path / "output.db").exists()
    for url in ("postgres://somewhere/db", "sqlite:///:memory:"):
        with pytest.raises(ValueError):
            database_path(url)
    assert database_path("sqlite:////var/data/stride.db") == Path("/var/data/stride.db").resolve()


def test_verified_status_survives_remote_failure_and_failed_restore_is_not_published(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE runs(id INTEGER)")
    folder = tmp_path / "backups"
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: "prefix/verified.sqlite3")
    first = backup_once(source, folder, bucket="synthetic")
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: (_ for _ in ()).throw(ConnectionError()))
    second = backup_once(source, folder, bucket="synthetic")
    assert second["last_remote_success"] == first["last_remote_success"]
    assert json.loads((folder / "status.json").read_text())["last_error_type"] == "ConnectionError"
    monkeypatch.setattr("app.services.backups.restore_new", lambda *a: (_ for _ in ()).throw(ValueError()))
    before = list(folder.glob("stride-*.sqlite3"))
    with pytest.raises(ValueError):
        backup_once(source, folder)
    assert list(folder.glob("stride-*.sqlite3")) == before


def test_cli_protects_legacy_database_without_importing_or_migrating_app(tmp_path):
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE legacy_runs(id INTEGER)")
        db.execute("INSERT INTO legacy_runs VALUES (1)")
    folder = tmp_path / "backups"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{source}", "STRIDE_BACKUP_DIR": str(folder),
           "STRIDE_BACKUP_S3_BUCKET": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "app.services.backups", "--reason", "pre-start"], env=env, cwd=backend_dir, check=True, capture_output=True)
    assert verify_database(source) == {"legacy_runs": 1}  # no app tables added before the backup
    status = json.loads((folder / "status.json").read_text())
    assert status["reason"] == "pre-start" and status["restore_verified"]
    restored = tmp_path / "from-cli.db"
    subprocess.run([sys.executable, "-m", "app.services.backups", "--restore", str(folder / status["last_backup"]),
                    "--destination", str(restored)], env=env, cwd=backend_dir, check=True, capture_output=True)
    assert verify_database(restored) == {"legacy_runs": 1}


def test_local_startup_snapshot_cannot_hide_failed_offsite_export(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE runs(id INTEGER)")
    folder = tmp_path / "backups"
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: "verified/key")
    first = backup_once(source, folder, bucket="synthetic")
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: (_ for _ in ()).throw(TimeoutError()))
    backup_once(source, folder, bucket="synthetic")
    # The direct application startup path deliberately performs no network call.
    local = backup_once(source, folder, reason="before-app-migration")
    assert local["remote_configured"] is True
    assert local["last_remote_success"] == first["last_remote_success"]
    assert local["last_remote_error_type"] == local["last_error_type"] == "TimeoutError"
    assert local["last_local_error_type"] is None and local["restore_verified"]
    monkeypatch.setattr("app.services.backups.upload_s3", lambda *a: "verified/key")
    recovered = backup_once(source, folder, bucket="synthetic")
    assert recovered["last_remote_error_type"] is None and recovered["last_error_type"] is None
