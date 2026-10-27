from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.account import AccountSession
from app.models.user import User
from app.services.accounts import digest, issue_session, utcnow


@pytest.fixture
def accounts(monkeypatch):
    monkeypatch.setattr(settings,'accounts_enabled',True)
    monkeypatch.setattr(settings,'signup_invite_code','test-invitation')
    monkeypatch.setattr(settings,'cookie_secure',False)
    return TestClient(app)


def register(client,email='one@example.com'):
    r=client.post('/api/auth/register',json={'name':'Runner','email':email,'password':'a-long-test-password','invite_code':'test-invitation','timezone':'Europe/London','accept_terms':True})
    assert r.status_code==200,r.text
    return r.json()['user_id']


def test_invited_accounts_enforce_ownership_on_every_router(accounts):
    one=register(accounts)
    other=TestClient(app)
    two=register(other,'two@example.com')
    assert one!=two
    assert accounts.get('/api/users/me').json()['id']==one
    for path in [f'/api/users/{two}',f'/api/plans/{two}/current',f'/api/analysis/{two}/activities',f'/api/garmin/status/{two}',f'/api/wellness/{two}',f'/api/coaching/{two}/status']:
        assert accounts.get(path).status_code==403,path
    assert accounts.post('/api/users/onboard',json={'name':'bypass'}).status_code==403
    assert TestClient(app).get('/api/analysis/1/activities').status_code==401
    assert accounts.put('/api/users/me/profile',json={'name':'Changed'},headers={'origin':'https://evil.example'}).status_code==403


def test_sessions_expire_logout_revokes_and_password_recovery_is_single_use(accounts):
    uid=register(accounts)
    token=accounts.cookies.get('stride_account')
    accounts.post('/api/auth/logout')
    accounts.cookies.set('stride_account',token)
    assert accounts.get('/api/auth/me').status_code==401
    with SessionLocal() as db:
        recovery=issue_session(uid,db,kind='recovery');db.commit()
    r=accounts.post('/api/auth/reset',json={'token':recovery,'password':'another-long-password'})
    assert r.status_code==200,r.text
    assert accounts.post('/api/auth/reset',json={'token':recovery,'password':'another-long-password'}).status_code==400
    accounts.cookies.clear()
    assert accounts.post('/api/auth/login',json={'email':'one@example.com','password':'another-long-password'}).status_code==200
    with SessionLocal() as db:
        row=db.get(AccountSession,digest(accounts.cookies.get('stride_account')))
        row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert accounts.get('/api/users/me').status_code==401


def test_registration_is_closed_without_invitation_and_login_is_throttled(accounts,monkeypatch):
    monkeypatch.setattr(settings,'signup_invite_code','')
    assert accounts.post('/api/auth/register',json={'name':'X','email':'x@example.com','password':'a-long-test-password','invite_code':'anything'}).status_code==403
    codes=[accounts.post('/api/auth/login',json={'email':'x@example.com','password':'a-long-test-password'}).status_code for _ in range(9)]
    assert codes[-1]==429


def test_export_and_erasure_only_affect_own_athlete(accounts):
    uid=register(accounts)
    from app.models.activity import Activity
    from datetime import datetime
    with SessionLocal() as db:
        db.add(Activity(user_id=uid,source='manual',name='Mine',date=datetime.now(),distance_meters=3000,duration_seconds=1200))
        db.commit()
    payload=accounts.get('/api/auth/export').json()
    assert payload['tables']['activities'][0]['name']=='Mine'
    assert 'accounts' not in payload['tables']
    assert accounts.post('/api/auth/delete',json={'password':'wrong','confirmation':'DELETE'}).status_code==403
    r=accounts.post('/api/auth/delete',json={'password':'a-long-test-password','confirmation':'DELETE'})
    assert r.status_code==200,r.text
    with SessionLocal() as db:
        assert db.get(User,uid) is None
        assert db.get(User,1) is not None


def test_request_calendar_is_per_athlete_and_ai_consent_is_enforced(accounts):
    import time_machine
    from datetime import datetime,timezone
    uid=register(accounts)
    with time_machine.travel(datetime(2026,10,24,1,tzinfo=timezone.utc),tick=False):
        assert accounts.put('/api/users/me/profile',json={'timezone':'America/Los_Angeles'}).status_code==200
        assert accounts.get('/api/users/me').json()['today']=='2026-10-23'
        assert accounts.put('/api/users/me/profile',json={'timezone':'Asia/Tokyo'}).status_code==200
        assert accounts.get('/api/users/me').json()['today']=='2026-10-24'
        assert accounts.post('/api/coaching/me/review',json={}).status_code==403


def test_registration_requires_and_records_terms(accounts):
    body={'name':'Runner','email':'terms@example.com','password':'a-long-test-password','invite_code':'test-invitation'}
    assert accounts.post('/api/auth/register',json=body).status_code==422
    r=accounts.post('/api/auth/register',json=body|{'accept_terms':True})
    assert r.status_code==200
    from app.database import SessionLocal
    from app.models.account import Account
    with SessionLocal() as db:
        account=db.get(Account,r.json()['user_id'])
        assert account.terms_version and account.terms_accepted_at and account.role=='athlete'
