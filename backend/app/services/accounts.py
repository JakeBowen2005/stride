"""Invite-only accounts, Argon2 passwords and server-revocable session tokens."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from pwdlib import PasswordHash
from app.models.account import AccountSession

COOKIE = 'stride_account'
_PASSWORDS = PasswordHash.recommended()


class LimitedPasswords:
    # Bound Argon2 memory use even if several web requests arrive together.
    def __init__(self):
        import threading
        self.slots=threading.BoundedSemaphore(2)
    def _run(self,method,*args):
        from fastapi import HTTPException
        if not self.slots.acquire(timeout=1):
            raise HTTPException(429,'Sign-in is busy. Try again shortly.')
        try:return getattr(_PASSWORDS,method)(*args)
        finally:self.slots.release()
    def hash(self,value):return self._run('hash',value)
    def verify(self,value,encoded):return self._run('verify',value,encoded)


PASSWORDS=LimitedPasswords()
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_session(user_id, db, *, kind='session'):
    token = secrets.token_urlsafe(32)
    db.add(AccountSession(token_hash=digest(token), user_id=user_id, kind=kind,
                          expires_at=utcnow()+timedelta(days=7) if kind == 'session' else utcnow()+timedelta(minutes=30)))
    return token


def session_user(request, db):
    token = request.cookies.get(COOKIE)
    row = db.get(AccountSession, digest(token)) if token else None
    return row.user_id if row and row.kind == 'session' and row.expires_at > utcnow() else None


def main():
    import argparse
    import getpass
    from app.database import SessionLocal
    from app.models.account import Account
    parser = argparse.ArgumentParser(description='Owner-only local account bootstrap and recovery. Never sends email.')
    parser.add_argument('action', choices=['bootstrap', 'recovery'])
    parser.add_argument('--user-id', type=int, required=True)
    parser.add_argument('--email')
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.action == 'bootstrap':
            from app.models.user import User
            if not db.get(User,args.user_id) or db.get(Account,args.user_id):
                parser.error('Athlete must exist and must not already have an account.')
            if not args.email:
                parser.error('--email required')
            password = getpass.getpass('New account password (at least 12 characters): ')
            if not 12 <= len(password) <= 128:
                parser.error('Password length must be 12–128 characters.')
            db.add(Account(user_id=args.user_id,email=args.email.strip().lower(),password_hash=PASSWORDS.hash(password),
                           role='owner',created_at=utcnow()))
            db.commit()
            print('Account attached to the existing athlete. Training data was preserved.')
        else:
            if not db.get(Account,args.user_id):
                parser.error('Account not found.')
            token = issue_session(args.user_id,db,kind='recovery')
            db.commit()
            print('Single-use recovery token (expires in 30 minutes):',token)


if __name__ == '__main__':
    main()
