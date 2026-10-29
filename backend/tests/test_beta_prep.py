"""Optional error tracking and the beta readiness checklist."""
import sys

from fastapi.testclient import TestClient

from app.main import _init_error_tracking, app


def test_error_tracking_is_off_and_not_imported_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delitem(sys.modules, "sentry_sdk", raising=False)
    assert _init_error_tracking() is False
    assert "sentry_sdk" not in sys.modules


def test_error_tracking_sends_no_athlete_data(monkeypatch):
    import sentry_sdk
    seen = {}
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    assert _init_error_tracking() is True
    assert seen["send_default_pii"] is False and seen["max_request_body_size"] == "never"
    assert seen["include_local_variables"] is False and seen["traces_sample_rate"] == 0
    assert seen["auto_enabling_integrations"] is False


def test_real_init_with_a_dsn_does_not_crash_startup(monkeypatch):
    # sentry-sdk's auto-enabled Starlette integration raised ImportError (jinja2) on Starlette 1.0
    import sentry_sdk
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    try:
        assert _init_error_tracking() is True
    finally:
        sentry_sdk.init(dsn=None, auto_enabling_integrations=False)


def test_a_failing_init_logs_and_keeps_the_app_running(monkeypatch):
    import sentry_sdk
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: (_ for _ in ()).throw(ImportError("boom")))
    assert _init_error_tracking() is False


def test_operations_reports_beta_readiness_without_values(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://secret@example.invalid/1")
    monkeypatch.setenv("STRIDE_BACKUP_S3_BUCKET", "private-bucket-name")
    body = TestClient(app).get("/api/analysis/1/operations").json()
    checks = {c["key"]: c["ready"] for c in body["beta_readiness"]}
    assert checks["error_tracking"] and checks["offsite_backup"] and not checks["accounts"]
    assert "secret" not in str(body) and "private-bucket-name" not in str(body)


def test_other_athletes_do_not_see_the_server_checklist():
    from app.api.analysis import operations
    from app.database import SessionLocal
    from app.models.user import User
    with SessionLocal() as db:
        db.add(User(id=2, name="Tester"))
        db.commit()
        assert operations(2, db)["beta_readiness"] is None
