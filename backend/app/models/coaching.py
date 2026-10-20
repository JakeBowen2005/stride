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
