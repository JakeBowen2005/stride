from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ProviderCredential(Base):
    __tablename__='provider_credentials'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    kind:Mapped[str]=mapped_column(String(40))
    ciphertext:Mapped[str]=mapped_column(Text)
    scopes:Mapped[str | None]=mapped_column(Text)
    expires_at:Mapped[datetime | None]=mapped_column(DateTime)
    revoked_at:Mapped[datetime | None]=mapped_column(DateTime)


class SyncJob(Base):
    __tablename__='sync_jobs'
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    status:Mapped[str]=mapped_column(String(20),index=True,default='queued')
    full:Mapped[int]=mapped_column(Integer,default=0)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    available_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    lease_until:Mapped[datetime | None]=mapped_column(DateTime,index=True)
    lease_token:Mapped[str | None]=mapped_column(String(64))
    result:Mapped[str | None]=mapped_column(Text)
    error:Mapped[str | None]=mapped_column(String(100))


class BlobDeletion(Base):
    __tablename__='blob_deletions'
    # No FK: erasure removes the athlete before the worker removes the objects.
    id:Mapped[int]=mapped_column(primary_key=True)
    bucket:Mapped[str]=mapped_column(String(255))
    key:Mapped[str]=mapped_column(String(512),unique=True)
