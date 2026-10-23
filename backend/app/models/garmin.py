"""Garmin Connect connection + sync state (one row per user)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GarminConnection(Base):
    __tablename__ = "garmin_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_new_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    full_sync_done: Mapped[bool] = mapped_column(Boolean, default=False)
    full_repair_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime)
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime)  # set after a Garmin 429
