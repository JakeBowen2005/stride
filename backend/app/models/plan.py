from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (Index("ix_plans_user_active", "user_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    start_date: Mapped[str] = mapped_column(String(20))  # ISO date
    end_date: Mapped[str] = mapped_column(String(20))  # ISO date
    block_number: Mapped[int] = mapped_column(Integer, default=1)
    is_deload: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # JSON-serialized fields
    training_paces: Mapped[str | None] = mapped_column(Text, nullable=True)
    pacing_guide: Mapped[str | None] = mapped_column(Text)  # JSON
    notes: Mapped[str | None] = mapped_column(Text)  # JSON array
    goal_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON
    athlete_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON
    phases: Mapped[str | None] = mapped_column(Text)  # JSON list, one periodization phase per week
    prescribed_from: Mapped[str | None] = mapped_column(String(20))  # local ISO date the plan starts prescribing
    load: Mapped[str | None] = mapped_column(Text)  # JSON LoadPlan: baseline, destination, budgets, reasons
    assessment: Mapped[str | None] = mapped_column(Text)  # JSON BlockAssessment of the previous block

    preview_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_context: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_state: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    planned_workouts: Mapped[list["PlannedWorkout"]] = relationship(
        "PlannedWorkout", back_populates="plan", cascade="all, delete-orphan"
    )


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"
    __table_args__ = (Index("ix_planned_workouts_plan_date", "plan_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(20))  # ISO date
    day_name: Mapped[str] = mapped_column(String(10))  # monday, tuesday, etc.
    week_number: Mapped[int] = mapped_column(Integer)

    feedback_activity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # audit identity, retained after source reclassification
    feedback_history: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Workout prescription
    type: Mapped[str] = mapped_column(String(30))  # easy, workout, long_run, rest
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    distance_miles: Mapped[float] = mapped_column(Float, default=0)
    warmup: Mapped[str | None] = mapped_column(String(200))
    cooldown: Mapped[str | None] = mapped_column(String(200))

    prescription: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution: Mapped[str | None] = mapped_column(Text, nullable=True)
    b2b: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    session_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    moved_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    moved_from: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Matched actual activity
    activity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("activities.id"), nullable=True
    )

    # User feedback on this day
    feel_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-10
    feel_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # user's free-text notes
    pace_assessment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # above, on_target, below, skipped
    # "How hard was it?" (session effort, 1-10) — separate from feel, which is how you felt afterward
    effort_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Athlete-reported completion (JSON: status/reps/minutes, source="self_reported"); never measured evidence
    reported_completion: Mapped[str | None] = mapped_column(Text, nullable=True)
    swapped: Mapped[bool] = mapped_column(Boolean, default=False)
    swap_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_workout_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # what they did if swapped
    coach_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM feedback

    # Deterministic decisions (persisted so UI, coach and reloads agree)
    evaluation: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON WorkoutEvaluation
    adjustment_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # why this day was changed
    original_prescription: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON, before any change
    # Durable dedup: set once when feedback side effects (progression, rescheduling,
    # fatigue downgrade) are applied, so retries/concurrent submits apply them once
    side_effects_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", back_populates="planned_workouts")
