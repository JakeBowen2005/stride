from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # string relationship targets, for type checkers only
    from app.models.activity import Activity


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Basic info
    name: Mapped[str | None] = mapped_column(String(100))
    age: Mapped[int | None] = mapped_column(Integer)
    units: Mapped[str] = mapped_column(String(10), default="miles")  # "miles" or "km"
    workout_format: Mapped[str] = mapped_column(String(10), default="distance")  # "distance" or "time"

    # Running background
    years_running: Mapped[float | None] = mapped_column(Float)
    current_weekly_mileage: Mapped[float | None] = mapped_column(Float)
    peak_weekly_mileage: Mapped[float | None] = mapped_column(Float)
    experience_level: Mapped[str | None] = mapped_column(String(20))  # beginner, intermediate, advanced, expert
    # Starting point for someone with no running history: longest continuous run right now,
    # and the Monday it was last set (run/walk progress counts only weeks after it)
    continuous_run_minutes: Mapped[int | None] = mapped_column(Integer)
    continuous_run_set_on: Mapped[str | None] = mapped_column(String(10))  # beginner, intermediate, advanced, expert

    # PRs (stored in seconds)
    pr_5k: Mapped[float | None] = mapped_column(Float)
    pr_10k: Mapped[float | None] = mapped_column(Float)
    pr_half: Mapped[float | None] = mapped_column(Float)
    pr_marathon: Mapped[float | None] = mapped_column(Float)

    # Schedule preferences
    days_per_week: Mapped[int] = mapped_column(Integer, default=6)
    rest_days: Mapped[str | None] = mapped_column(String(50))  # comma-separated: "friday,sunday"
    long_run_day: Mapped[str] = mapped_column(String(10), default="saturday")

    # Relationships
    activities: Mapped[list["Activity"]] = relationship("Activity", back_populates="user")
    goals: Mapped[list["Goal"]] = relationship("Goal", back_populates="user")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Goal type: "race", "mileage", "general", "comeback"
    goal_type: Mapped[str] = mapped_column(String(20))

    # Race goal fields
    race_distance: Mapped[str | None] = mapped_column(String(20))  # 5k, 10k, half, marathon, 50k, 50mi, 100k, 100mi
    target_time_seconds: Mapped[float | None] = mapped_column(Float)
    race_date: Mapped[str | None] = mapped_column(String(20))  # ISO date
    terrain: Mapped[str | None] = mapped_column(String(20))  # road, trail, mountain (ultras)
    elevation_gain_ft: Mapped[float | None] = mapped_column(Float)  # total course climbing

    intent: Mapped[str | None] = mapped_column(String(20))  # performance or completion
    decision: Mapped[str | None] = mapped_column(Text)

    # Mileage goal fields
    target_weekly_mileage: Mapped[float | None] = mapped_column(Float)

    # Description
    description: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", back_populates="goals")
