import io
import json
import struct
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, inspect
from app.main import app
from app.database import SessionLocal
from app.config import settings
from app.models.activity import Activity
from app.models.user import User
from app.models.history import ActivitySource,SourceRevision
from app.models.operations import SyncJob,ProviderCredential
from app.services.accounts import utcnow
from app.services import sync_jobs


def running_fit():
    from fitdecode.utils import compute_crc
    # session: running, start time (FIT epoch), distance, timer and elapsed time
    fields=bytes([5,1,0,2,4,0x86,9,4,0x86,8,4,0x86,7,4,0x86])
    definition=bytes([0x40,0,0])+struct.pack('<H',18)+bytes([5])+fields
    record=bytes([0])+struct.pack('<BIIII',1,1161604800,500000,1800000,1900000)
    data=definition+record
    header=struct.pack('<BBHI4s',12,0x10,100,len(data),b'.FIT')
    body=header+data
    return body+struct.pack('<H',compute_crc(body))


def test_upload_retains_real_fit_deduplicates_and_rejects_invalid_data():
    client=TestClient(app)
    body=running_fit()
    a=client.post('/api/analysis/1/import-fit',content=body)
    assert a.status_code==200,a.text
    assert client.post('/api/analysis/1/import-fit',content=body).json()['duplicate'] is True
    with SessionLocal() as db:
        assert db.query(Activity).count()==1
        assert db.query(SourceRevision).one().fit_bytes==body
        assert db.query(Activity).one().duration_seconds==1800
    assert client.post('/api/analysis/1/import-fit',content=b'broken').status_code==422
    assert client.post('/api/analysis/1/import-fit',content=b'x',headers={'content-length':str(11*1024**2)}).status_code==413


def test_object_evidence_is_private_hashed_and_reprocessable(monkeypatch):
    from app.services.history_evidence import source_for,capture
    from app.services.blob_store import read_fit
    monkeypatch.setattr(settings,'fit_blob_bucket','private-test')
    objects={}
    def put(**kw):
        assert kw['ServerSideEncryption']=='AES256'
        objects[kw['Key']]=kw['Body']
    fake=SimpleNamespace(put_object=put,get_object=lambda **kw:{'Body':io.BytesIO(objects[kw['Key']])})
    monkeypatch.setattr('app.services.blob_store._client',lambda:fake)
    with SessionLocal() as db:
        a=Activity(user_id=1,source='manual',date=datetime.now(),distance_meters=5000,duration_seconds=1800)
        db.add(a);db.flush()
        source=source_for(a,'fit_upload','one',db)
        capture(source,'fit',db,blob=running_fit());db.commit()
        row=db.query(SourceRevision).one()
        assert row.fit_bytes is None and row.fit_blob_key
        assert read_fit(row,1)==running_fit()
        import pytest
        with pytest.raises(ValueError):read_fit(row,2)
        objects[row.fit_blob_key]=b'corrupt'
        with pytest.raises(ValueError,match='checksum'):read_fit(row,1)


def test_sync_jobs_survive_restart_retry_and_recover_expired_leases(monkeypatch):
    import app.api.garmin as api
    with SessionLocal() as db:
        sync_jobs.enqueue(1,db,True)
        assert sync_jobs.enqueue(1,db,True)['state']=='running'
        assert db.query(SyncJob).count()==1
    calls=[]
    monkeypatch.setattr(api,'_sync_in_new_session',lambda uid,full:calls.append((uid,full)) or {'status':'ok'})
    assert sync_jobs.process_one()
    assert not sync_jobs.process_one()
    assert calls==[(1,True)]
    with SessionLocal() as db:
        sync_jobs.enqueue(1,db)
        row=db.get(SyncJob,1);row.status='running';row.lease_until=utcnow()-timedelta(seconds=1);db.commit()
    assert sync_jobs.process_one()
    assert len(calls)==2


def test_encrypted_provider_credentials_never_fall_back_to_owner(monkeypatch):
    from cryptography.fernet import Fernet
    from app.services.provider_connections import cipher,client_for
    from app.services.garmin_api import GarminNotConnected
    import pytest
    monkeypatch.setattr(settings,'provider_encryption_keys',Fernet.generate_key().decode())
    monkeypatch.setattr(settings,'accounts_enabled',True)
    monkeypatch.setattr(settings,'garmin_api_key','owner-secret-must-not-be-shared')
    with SessionLocal() as db:
        db.add(User(id=2,name='Other'));db.commit()
        db.add(ProviderCredential(user_id=1,kind='garmin_personal',ciphertext=cipher().encrypt(b'private-owner-key').decode()));db.commit()
        assert 'private-owner-key' not in db.get(ProviderCredential,1).ciphertext
    with pytest.raises(GarminNotConnected):client_for(2)
    assert client_for(1)._key=='private-owner-key'


def test_athlete_calendar_uses_saved_timezone():
    import time_machine
    from app.athlete_clock import athlete_zone,today
    with time_machine.travel(datetime(2026,10,24,1,tzinfo=timezone.utc),tick=False):
        with athlete_zone('America/Los_Angeles'):assert today().isoformat()=='2026-10-23'
        with athlete_zone('Asia/Tokyo'):assert today().isoformat()=='2026-10-24'


def test_explicit_schema_upgrade_preserves_legacy_rows_and_is_repeatable(tmp_path):
    from app.schema import upgrade,check
    bind=create_engine(f'sqlite:///{tmp_path}/legacy.db')
    with bind.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY,name VARCHAR(100))'))
        conn.execute(text("INSERT INTO users VALUES (1,'Existing athlete')"))
    upgrade(bind);upgrade(bind);check(bind)
    with bind.connect() as conn:
        assert conn.execute(text('SELECT name FROM users WHERE id=1')).scalar()=='Existing athlete'
        assert 'timezone' in {c['name'] for c in inspect(conn).get_columns('users')}
        assert 'provider_credentials' in inspect(conn).get_table_names()


def test_current_schema_marker_does_not_hide_missing_columns(tmp_path):
    from app.schema import upgrade,check
    import pytest
    bind=create_engine(f'sqlite:///{tmp_path}/drift.db')
    upgrade(bind)
    with bind.begin() as conn:conn.execute(text('ALTER TABLE users DROP COLUMN timezone'))
    with pytest.raises(RuntimeError,match='Schema drift'):check(bind)


def test_imported_fit_only_matches_precise_time_not_another_same_day_run():
    from app.services.garmin import _find_legacy_match
    stamp=datetime(2026,10,23,7)
    with SessionLocal() as db:
        row=Activity(user_id=1,source='manual',external_id='fit-'+'a'*64,date=stamp,distance_meters=5000,duration_seconds=1800)
        db.add(row);db.commit()
        parsed={'date':stamp+timedelta(hours=5),'distance_meters':5000,'duration_seconds':1800}
        assert _find_legacy_match(1,parsed,db) is None
        parsed['date']=stamp
        assert _find_legacy_match(1,parsed,db).id==row.id


def test_fit_upload_dedup_survives_garmin_identity_merge():
    from app.services.fit_import import import_fit
    with SessionLocal() as db:
        first=import_fit(1,running_fit(),db)
        row=db.get(Activity,first['activity_id']);row.source='garmin';row.external_id='provider-identity';db.commit()
        repeated=import_fit(1,running_fit(),db)
        assert repeated['duplicate'] and repeated['activity_id']==first['activity_id']
        assert db.query(Activity).count()==1


def test_replacement_garmin_key_clears_expiry_backoff_and_failed_job(monkeypatch):
    from cryptography.fernet import Fernet
    from app.models.garmin import GarminConnection
    from app.services.provider_connections import client_for, configured
    monkeypatch.setattr(settings, 'provider_encryption_keys', Fernet.generate_key().decode())
    with SessionLocal() as db:
        db.add(ProviderCredential(user_id=1, kind='garmin_personal', ciphertext='expired',
                                  expires_at=utcnow()-timedelta(days=1)))
        db.add(GarminConnection(user_id=1, connected=False, last_error='Rejected key',
                                backoff_until=datetime.now()+timedelta(hours=1)))
        db.add(SyncJob(user_id=1, status='retry', available_at=utcnow()+timedelta(hours=1)))
        db.commit()
    key = 'replacement-private-key-for-testing'
    response = TestClient(app).post('/api/garmin/connect/1', json={'api_key':key})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert configured(1, db)
        assert db.get(ProviderCredential, 1).expires_at is None
        conn = db.query(GarminConnection).filter_by(user_id=1).one()
        assert conn.backoff_until is None and conn.last_error is None and not conn.connected
        assert db.get(SyncJob, 1).status == 'cancelled'
    assert client_for(1)._key == key
