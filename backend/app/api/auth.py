"""Account mode is opt-in. Registration requires an operator-issued invitation."""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.database import get_db
from app.models.account import Account, AccountSession, AuthThrottle
from app.models.user import User
from app.services.accounts import COOKIE, PASSWORDS, DUMMY_HASH, digest, issue_session, session_user, utcnow

router = APIRouter(prefix='/api/auth', tags=['accounts'])


def enabled():
    if not settings.accounts_enabled:
        raise HTTPException(404, 'Account mode is not enabled.')


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=100)
    invite_code: str = Field(min_length=1,max_length=256)
    timezone: str = 'America/Los_Angeles'
    ai_consent: bool = False


def throttle(request, email, db):
    from sqlalchemy import text
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    now = utcnow()
    db.execute(delete(AuthThrottle).where(AuthThrottle.expires_at <= now))
    blocked = False
    for key, limit in [(digest('email:'+email), 8),(digest('peer:'+(request.client.host if request.client else 'unknown')),40)]:
        row = db.query(AuthThrottle).filter_by(key=key).with_for_update().first()
        if row is None:
            row = AuthThrottle(key=key, attempts=0, expires_at=now+timedelta(minutes=15))
            db.add(row)
        row.attempts += 1
        blocked |= row.attempts > limit
    db.commit()
    if blocked:
        raise HTTPException(429,'Too many attempts. Try again in 15 minutes.',headers={'Retry-After':'900'})


def set_session(response, user_id, db):
    db.execute(delete(AccountSession).where(AccountSession.expires_at <= utcnow()))
    token = issue_session(user_id, db)
    db.commit()
    response.set_cookie(COOKIE,token,max_age=7*86400,httponly=True,secure=settings.cookie_secure,samesite='lax',path='/')
    response.headers['Cache-Control'] = 'no-store'


@router.post('/register', dependencies=[Depends(enabled)])
def register(data: Registration, request: Request, response: Response, db: Session=Depends(get_db)):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    email = data.email.strip().lower()
    throttle(request,email,db)
    if not settings.signup_invite_code or not secrets.compare_digest(data.invite_code, settings.signup_invite_code):
        raise HTTPException(403,'A valid invitation is required.')
    try:
        ZoneInfo(data.timezone)
    except (ZoneInfoNotFoundError,ValueError):
        raise HTTPException(422,'Choose a valid IANA timezone.')
    try:
        user = User(name=data.name.strip(), timezone=data.timezone, ai_consent=data.ai_consent,days_per_week=3,rest_days='monday,wednesday,friday,sunday',long_run_day='saturday')
        db.add(user); db.flush()
        db.add(Account(user_id=user.id,email=email,password_hash=PASSWORDS.hash(data.password)))
        db.flush()
        set_session(response,user.id,db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Unable to create this account. Try signing in or contact the app owner.')
    return {'user_id':user.id}


@router.post('/login', dependencies=[Depends(enabled)])
def login(data: Credentials, request: Request, response: Response, db: Session=Depends(get_db)):
    email=data.email.strip().lower()
    throttle(request,email,db)
    account=db.query(Account).filter_by(email=email).first()
    valid=PASSWORDS.verify(data.password,account.password_hash if account else DUMMY_HASH)
    if not valid or not account:
        raise HTTPException(401,'Email or password did not match.')
    set_session(response,account.user_id,db)
    return {'user_id':account.user_id}


@router.get('/me', dependencies=[Depends(enabled)])
def me(request: Request, db: Session=Depends(get_db)):
    uid=session_user(request,db)
    if uid is None:
        raise HTTPException(401,'Sign in to continue.')
    user=db.get(User,uid)
    return {'user_id':uid,'timezone':user.timezone,'ai_consent':bool(user.ai_consent)}


@router.post('/logout', dependencies=[Depends(enabled)])
def logout(request: Request,response: Response,db: Session=Depends(get_db)):
    token=request.cookies.get(COOKIE)
    if token:
        db.execute(delete(AccountSession).where(AccountSession.token_hash==digest(token)))
        db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'signed_out':True}


class Reset(BaseModel):
    token: str = Field(min_length=20,max_length=256)
    password: str = Field(min_length=12,max_length=128)


@router.post('/reset', dependencies=[Depends(enabled)])
def reset(data: Reset, request: Request, response: Response, db: Session=Depends(get_db)):
    throttle(request,'recovery:'+digest(data.token),db)
    from app.api.plans import _begin_schedule_write
    _begin_schedule_write(db)
    token=db.query(AccountSession).filter_by(token_hash=digest(data.token),kind='recovery').with_for_update().first()
    if not token or token.expires_at <= utcnow():
        raise HTTPException(400,'Recovery token expired or already used.')
    account=db.get(Account,token.user_id)
    account.password_hash=PASSWORDS.hash(data.password)
    db.execute(delete(AccountSession).where(AccountSession.user_id==account.user_id))
    db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'message':'Password changed. Sign in again on each device.'}


def authenticated(request,db):
    uid=session_user(request,db)
    if uid is None:
        raise HTTPException(401,'Sign in to continue.')
    return uid


@router.get('/export', dependencies=[Depends(enabled)])
def export(request:Request,db:Session=Depends(get_db)):
    import base64,json
    from sqlalchemy import select
    from app.services.account_data import owned_tables
    from app.services.blob_store import read_fit
    from app.models.history import SourceRevision
    from fastapi.encoders import jsonable_encoder
    from starlette.responses import StreamingResponse
    uid=authenticated(request,db)
    def stream():
        yield '{"format":"stride-export-v1","binary_encoding":"base64","tables":{'
        first_table=True
        for table,condition in owned_tables(uid):
            if table.name in {'accounts','account_sessions','provider_credentials'}:continue
            if not first_table:yield ','
            first_table=False
            yield json.dumps(table.name)+':['
            first=True
            for raw in db.execute(select(table).where(condition).execution_options(yield_per=100)).mappings():
                row=dict(raw)
                if table.name=='source_revisions' and row.get('fit_blob_key'):
                    row['fit_bytes']=read_fit(db.get(SourceRevision,row['id']),uid)
                if not first:yield ','
                first=False
                yield json.dumps(jsonable_encoder({k:base64.b64encode(v).decode() if isinstance(v,bytes) else v for k,v in row.items()}))
            yield ']'
        yield '}}'
    return StreamingResponse(stream(),media_type='application/json',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="stride-export.json"'})


class Erasure(BaseModel):
    password:str=Field(max_length=128)
    confirmation:str


@router.post('/delete', dependencies=[Depends(enabled)])
def erase(data:Erasure,request:Request,response:Response,db:Session=Depends(get_db)):
    from app.services.account_data import owned_tables
    uid=authenticated(request,db)
    account=db.get(Account,uid)
    if data.confirmation != 'DELETE' or not PASSWORDS.verify(data.password,account.password_hash):
        raise HTTPException(403,'Confirm DELETE and your current password.')
    from app.models.history import ActivitySource,SourceRevision
    from app.models.operations import BlobDeletion
    keys=db.query(SourceRevision.fit_blob_key).join(ActivitySource,SourceRevision.source_id==ActivitySource.id).filter(ActivitySource.user_id==uid,SourceRevision.fit_blob_key.is_not(None)).all()
    for (key,) in keys:
        if not db.query(BlobDeletion).filter_by(key=key).first():db.add(BlobDeletion(bucket=settings.fit_blob_bucket,key=key))
    db.flush()
    # Core deletes intentionally avoid ORM invalidation hooks recreating revision
    # rows during account removal. Foreign-key order includes indirect children.
    for table,condition in reversed(owned_tables(uid)):
        db.connection().execute(delete(table).where(condition))
    db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'deleted':True,'backup_retention':'Encrypted/offsite backup expiry follows the operator retention policy.'}
