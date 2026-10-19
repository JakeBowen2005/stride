"""Daily Garmin wellness metrics (one row per user per calendar day)."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyWellness(Base):
    __tablename__ = "daily_wellness"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_wellness_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO calendar date
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Heart
    resting_hr: Mapped[float | None] = mapped_column(Float)
    resting_hr_7d_avg: Mapped[float | None] = mapped_column(Float)
    hrv_last_night: Mapped[float | None] = mapped_column(Float)  # ms
    hrv_weekly_avg: Mapped[float | None] = mapped_column(Float)
    hrv_status: Mapped[str | None] = mapped_column(String(20))  # BALANCED, UNBALANCED, LOW, POOR
    hrv_baseline_low: Mapped[float | None] = mapped_column(Float)
    hrv_baseline_high: Mapped[float | None] = mapped_column(Float)

    # Sleep
    sleep_seconds: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    sleep_quality: Mapped[str | None] = mapped_column(String(20))  # EXCELLENT, GOOD, FAIR, POOR
    deep_sleep_seconds: Mapped[float | None] = mapped_column(Float)
    light_sleep_seconds: Mapped[float | None] = mapped_column(Float)
    rem_sleep_seconds: Mapped[float | None] = mapped_column(Float)
    awake_sleep_seconds: Mapped[float | None] = mapped_column(Float)

    # Day
    body_battery_now: Mapped[int | None] = mapped_column(Integer)
    body_battery_wake: Mapped[int | None] = mapped_column(Integer)
    body_battery_high: Mapped[int | None] = mapped_column(Integer)
    body_battery_low: Mapped[int | None] = mapped_column(Integer)
    stress_avg: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    step_goal: Mapped[int | None] = mapped_column(Integer)
    spo2_avg: Mapped[float | None] = mapped_column(Float)
    respiration_avg: Mapped[float | None] = mapped_column(Float)

    # Training
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    readiness_level: Mapped[str | None] = mapped_column(String(20))  # PRIME, HIGH, MODERATE, LOW, POOR
    readiness_feedback: Mapped[str | None] = mapped_column(String(60))
    recovery_time_min: Mapped[int | None] = mapped_column(Integer)
    training_status: Mapped[str | None] = mapped_column(String(40))  # e.g. PRODUCTIVE_3
    acute_load: Mapped[float | None] = mapped_column(Float)
    chronic_load: Mapped[float | None] = mapped_column(Float)
    acwr: Mapped[float | None] = mapped_column(Float)
    load_balance_feedback: Mapped[str | None] = mapped_column(String(40))
    vo2max: Mapped[float | None] = mapped_column(Float)

    # Garmin race predictions (seconds)
    predicted_5k: Mapped[float | None] = mapped_column(Float)
    predicted_10k: Mapped[float | None] = mapped_column(Float)
    predicted_half: Mapped[float | None] = mapped_column(Float)
    predicted_marathon: Mapped[float | None] = mapped_column(Float)
