"""Provider evidence is separate from the stable activity and athlete feedback."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActivitySource(Base):
    __tablename__ = 'activity_sources'
    __table_args__ = (UniqueConstraint('user_id', 'provider', 'external_id'),
                      Index('ix_source_retry', 'user_id', 'enrichment_status', 'next_retry_at'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    activity_id: Mapped[int] = mapped_column(ForeignKey('activities.id'), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(100))
    summary_hash: Mapped[str | None] = mapped_column(String(64))
    enrichment_status: Mapped[str] = mapped_column(String(20), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(100))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fit_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    parser_version: Mapped[str | None] = mapped_column(String(30))


class SourceRevision(Base):
    __tablename__ = 'source_revisions'
    __table_args__ = (UniqueConstraint('source_id', 'content_hash'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('activity_sources.id'), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))  # summary, fit, legacy
    payload: Mapped[str | None] = mapped_column(Text)
    # Content-addressed evidence kept in a separate table, covered by existing DB backups.
    fit_blob_key: Mapped[str | None] = mapped_column(String(512))
    fit_sha256: Mapped[str | None] = mapped_column(String(64))
    fit_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class HistoryCoverage(Base):
    __tablename__ = 'history_coverage'
    __table_args__ = (UniqueConstraint('user_id', 'stream', 'start_date', 'end_date'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    stream: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))  # checked, failed; never proves watch wear
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AthleteRevision(Base):
    __tablename__ = 'athlete_revisions'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class DirtyDay(Base):
    __tablename__ = 'history_dirty_days'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)


class DailyFact(Base):
    __tablename__ = 'history_daily_facts'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(30))


class AnalysisSnapshot(Base):
    __tablename__ = 'analysis_snapshots'
    __table_args__ = (UniqueConstraint('user_id', 'kind', 'cache_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    cache_key: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WellnessRevision(Base):
    __tablename__ = 'wellness_revisions'
    __table_args__ = (UniqueConstraint('user_id', 'stream', 'start_date', 'end_date', 'content_hash'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    stream: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
