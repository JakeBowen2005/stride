"""An athlete's plain-language request to rearrange their week, and what came of it.

The feature was removed in Oct 2026 (docs/plain-language-plan-changes.md). The table stays for
history and for this month's AI spend in services/ai_budget."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanChangeRequest(Base):
    __tablename__ = 'plan_change_requests'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('plans.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    request_text: Mapped[str] = mapped_column(Text)
    thread: Mapped[str] = mapped_column(Text, default='[]')  # JSON clarifying Q/A turns
    # clarifying, proposed, no_safe_change, safety, out_of_scope, no_change, applied, declined, undone, stale
    status: Mapped[str] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ai, ai_retry, solver, picker
    safety: Mapped[str] = mapped_column(String(20), default='none')
    proposal: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: understood, constraints, ops, explanation
    rejections: Mapped[str] = mapped_column(Text, default='[]')  # JSON reasons from failed attempts (eval material)
    before_rows: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON {id: snapshot} of touched rows
    after_rows: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_fingerprint: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # provider calls (each counts toward the daily cap)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
