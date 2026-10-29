"""Render runs a separate worker; owner connection recovery must work without local .env."""
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.garmin import GarminConnection
from app.models.operations import ProviderCredential, SyncJob
from app.services.accounts import utcnow
from app.services.provider_connections import configured, client_for

client = TestClient(app)


def test_render_missing_key_is_reported_as_owner_setup_not_business_approval(monkeypatch):
    monkeypatch.setattr(settings, 'embedded_workers', False)
    response = client.post('/api/garmin/sync/me')
    assert response.status_code == 409
    assert 'GARMIN_API_KEY in Render' in response.json()['detail']
    assert 'Business' not in response.json()['detail']
    status = client.get('/api/garmin/status/me').json()
    assert not status['api_key_present'] and not status['can_reconnect']
    assert 'Mac' in status['connection_issue']


def test_disconnect_persists_until_explicit_reconnect_then_worker_can_sync(monkeypatch):
    monkeypatch.setattr(settings, 'embedded_workers', False)
    monkeypatch.setattr(settings, 'garmin_api_key', 'render-owner-secret')
    with SessionLocal() as db:
        db.add(GarminConnection(user_id=1, connected=True, last_sync_at=datetime.now()-timedelta(days=3)))
        db.commit()
    assert client.post('/api/garmin/disconnect/me').status_code == 200
    status = client.get('/api/garmin/status/me').json()
    assert not status['api_key_present'] and status['can_reconnect']
    assert 'disconnected' in status['connection_issue']
    assert client.post('/api/garmin/sync/me').status_code == 409
    response = client.post('/api/garmin/reconnect/me')
    assert response.status_code == 200 and response.json()['status'] == 'queued'
    with SessionLocal() as db:
        assert configured(1, db)
        assert db.get(ProviderCredential, 1).ciphertext == ''  # never copy an env secret into SQLite
    assert client_for(1)._key == 'render-owner-secret'
    from app.services import sync_jobs
    import app.api.garmin as garmin
    monkeypatch.setattr(garmin, '_sync_in_new_session', lambda uid, full: {'status':'ok','new':3})
    assert sync_jobs.process_one()
    assert client.get('/api/garmin/status/me').json()['full_sync_job']['result']['new'] == 3


def test_reconnect_clears_stale_auth_backoff_and_retry_delay(monkeypatch):
    monkeypatch.setattr(settings, 'garmin_api_key', 'rotated-render-key')
    with SessionLocal() as db:
        db.add(GarminConnection(user_id=1, connected=False, last_error='Rejected key', backoff_until=datetime.now()+timedelta(hours=1)))
        db.add(SyncJob(user_id=1, status='retry', available_at=utcnow()+timedelta(hours=1), error='GarminAuthError'))
        db.commit()
    assert client.post('/api/garmin/reconnect/me').status_code == 200
    with SessionLocal() as db:
        conn = db.query(GarminConnection).one()
        assert conn.backoff_until is None and conn.last_error is None
        assert db.get(SyncJob, 1).status == 'queued'


def test_other_athletes_cannot_reuse_server_key_and_missing_key_cannot_reconnect(monkeypatch):
    assert client.post('/api/garmin/reconnect/me').status_code == 409
    monkeypatch.setattr(settings, 'garmin_api_key', 'owner-only')
    with SessionLocal() as db:
        db.add(User(id=2, name='Other')); db.commit()
    assert client.post('/api/garmin/reconnect/2').status_code == 409
    with SessionLocal() as db:
        assert not configured(2, db)


def test_manual_sync_reports_backoff_immediately_instead_of_queuing_a_disabled_spinner(monkeypatch):
    monkeypatch.setattr(settings, 'embedded_workers', False)
    monkeypatch.setattr(settings, 'garmin_api_key', 'configured-server-key')
    with SessionLocal() as db:
        db.add(GarminConnection(user_id=1, last_error='Garmin rejected the API key', backoff_until=datetime.now()+timedelta(hours=1)))
        db.commit()
    response = client.post('/api/garmin/sync/me')
    assert response.status_code == 200 and response.json()['status'] == 'backoff'
    assert response.json()['message'] == 'Garmin rejected the API key'
    with SessionLocal() as db:
        assert db.get(SyncJob, 1) is None


def test_in_process_worker_starts_job_loop_inside_api(monkeypatch):
    import asyncio
    from app.services import worker
    started = []

    async def fake_run():
        started.append(True)
        await asyncio.Event().wait()

    monkeypatch.setattr(settings, 'embedded_workers', False)
    monkeypatch.setattr(settings, 'in_process_worker', True)
    monkeypatch.setattr(settings, 'garmin_poll_minutes', 0)
    monkeypatch.setattr(settings, 'openai_auto_reviews', False)
    monkeypatch.setattr(worker, 'run', fake_run)
    with TestClient(app):
        pass
    assert started == [True]
