"""Real PostgreSQL coverage, run in CI against its disposable service database."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models.user import User
from app.models.operations import SyncJob
from app.schema import upgrade


@pytest.mark.skipif(not os.environ.get('STRIDE_POSTGRES_TEST_URL'),reason='Requires disposable PostgreSQL service')
def test_postgres_upgrade_transfer_and_concurrent_claims(monkeypatch,tmp_path):
    from app.services import sync_jobs
    import app.api.garmin as api
    url=os.environ['STRIDE_POSTGRES_TEST_URL']
    bind=create_engine(url,pool_pre_ping=True)
    # CI owns this database; never use an application DATABASE_URL here.
    with bind.begin() as conn:conn.execute(text('DROP SCHEMA public CASCADE'));conn.execute(text('CREATE SCHEMA public'))
    upgrade(bind);upgrade(bind)
    local=create_engine(f'sqlite:///{tmp_path}/snapshot.db')
    Base.metadata.create_all(local)
    with sessionmaker(bind=local)() as db:
        db.add_all([User(id=1,name='One'),User(id=2,name='Two')]);db.commit()
    from app.services.database_transfer import transfer
    counts=transfer(tmp_path/'snapshot.db',url)
    assert counts['users']==2
    sessions=sessionmaker(bind=bind)
    with sessions() as db:
        for uid in (1,2):sync_jobs.enqueue(uid,db)
    monkeypatch.setattr(sync_jobs,'SessionLocal',sessions)
    gate=Barrier(2)
    seen=[]
    def sync(uid,full):
        seen.append(uid);gate.wait(timeout=10);return {'status':'ok'}
    monkeypatch.setattr(api,'_sync_in_new_session',sync)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(sync_jobs.process_one) for _ in range(2)]
        assert all(f.result(timeout=15) for f in futures)
    assert sorted(seen)==[1,2]
    with sessions() as db:
        assert {j.status for j in db.query(SyncJob)}=={'done'}
        new=User(name='Three');db.add(new);db.commit();assert new.id==3
