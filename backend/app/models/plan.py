from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    start_date: Mapped[str] = mapped_column(String(20))  # ISO date
    end_date: Mapped[str] = mapped_column(String(20))  # ISO date
    block_number: Mapped[int] = mapped_column(Integer, default=1)
    is_deload: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # JSON-serialized fields
    pacing_guide: Mapped[str | None] = mapped_column(Text)  # JSON
    notes: Mapped[str | None] = mapped_column(Text)  # JSON array
    goal_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON
    athlete_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON
    phases: Mapped[str | None] = mapped_column(Text)  # JSON list, one periodization phase per week

    # Relationships
    planned_workouts: Mapped[list["PlannedWorkout"]] = relationship(
        "PlannedWorkout", back_populates="plan", cascade="all, delete-orphan"
    )


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(20))  # ISO date
    day_name: Mapped[str] = mapped_column(String(10))  # monday, tuesday, etc.
    week_number: Mapped[int] = mapped_column(Integer)

    # Workout prescription
    type: Mapped[str] = mapped_column(String(30))  # easy, workout, long_run, rest
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    distance_miles: Mapped[float] = mapped_column(Float, default=0)
    warmup: Mapped[str | None] = mapped_column(String(200))
    cooldown: Mapped[str | None] = mapped_column(String(200))

    # Matched actual activity
    activity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("activities.id"), nullable=True
    )

    # User feedback on this day
    feel_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-10
    feel_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # user's free-text notes
    pace_assessment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # above, on_target, below, skipped
    swapped: Mapped[bool] = mapped_column(Boolean, default=False)
    swap_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_workout_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # what they did if swapped
    coach_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM feedback

    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", back_populates="planned_workouts")
