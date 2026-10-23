"""Auditable, cached model advice. Never itself an authority to change training."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CoachingReview(Base):
    __tablename__ = "coaching_reviews"
    __table_args__ = (UniqueConstraint("user_id", "context_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), nullable=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    context_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    status: Mapped[str] = mapped_column(String(30))  # pending, ready, fallback
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates: Mapped[str] = mapped_column(Text, default="[]")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    applied_candidate_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    athlete_concern: Mapped[str | None] = mapped_column(Text, nullable=True)  # "what isn't working", from Plan options


class CoachingJob(Base):
    __tablename__ = 'coaching_jobs'
    __table_args__ = (UniqueConstraint('user_id', 'activity_id', 'version'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey('activities.id'))
    version: Mapped[str] = mapped_column(String(30), default='sync-v1')
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    review_id: Mapped[int | None] = mapped_column(ForeignKey('coaching_reviews.id'), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CoachingAttempt(Base):
    """Each provider attempt retains its own inputs, including retries with new notes."""
    __tablename__ = 'coaching_attempts'
    __table_args__ = (UniqueConstraint('review_id', 'number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('coaching_reviews.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    input_snapshot: Mapped[str] = mapped_column(Text)
    input_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default='pending')
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
