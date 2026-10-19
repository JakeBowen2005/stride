from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # string relationship targets, for type checkers only
    from app.models.user import User


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_user_date", "user_id", "date"),
        # One row per provider activity — sync upserts rely on this
        Index("ux_activities_user_source_external", "user_id", "source", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20))  # "garmin", "manual" ("strava" = legacy imports)
    external_id: Mapped[str | None] = mapped_column(String(50))  # Garmin activity ID (Strava ID on legacy rows)

    # Core run data
    name: Mapped[str | None] = mapped_column(String(200))
    date: Mapped[datetime] = mapped_column(DateTime)
    distance_meters: Mapped[float] = mapped_column(Float)  # always stored in meters
    duration_seconds: Mapped[float] = mapped_column(Float)  # moving time in seconds
    elapsed_seconds: Mapped[float | None] = mapped_column(Float)  # total elapsed time

    # Pace (stored as seconds per meter for easy conversion)
    average_pace_per_km: Mapped[float | None] = mapped_column(Float)  # seconds per km

    # Heart rate
    average_heartrate: Mapped[float | None] = mapped_column(Float)
    max_heartrate: Mapped[float | None] = mapped_column(Float)

    # Elevation
    elevation_gain: Mapped[float | None] = mapped_column(Float)  # meters

    # Cadence
    average_cadence: Mapped[float | None] = mapped_column(Float)  # steps per minute

    # Notes + legacy Strava metadata (kept for historical imports)
    description: Mapped[str | None] = mapped_column(Text)  # user's notes, or a workout summary built from Garmin laps
    strava_workout_type: Mapped[int | None] = mapped_column(Integer)  # legacy: 0=default, 1=race, 2=long run, 3=workout
    suffer_score: Mapped[float | None] = mapped_column(Float)  # Strava relative effort
    pr_count: Mapped[int | None] = mapped_column(Integer)  # PRs hit on this activity
    has_workout_description: Mapped[bool] = mapped_column(Boolean, default=False)  # flagged as containing workout details

    # Splits / laps (stored as JSON string). Garmin rows store laps, which may not be 1 mile each.
    splits: Mapped[str | None] = mapped_column(Text)  # JSON array of split data

    # Garmin metrics
    event_type: Mapped[str | None] = mapped_column(String(30))  # "race", "training", ...
    activity_subtype: Mapped[str | None] = mapped_column(String(40))  # running, trail_running, treadmill_running...
    aerobic_training_effect: Mapped[float | None] = mapped_column(Float)
    anaerobic_training_effect: Mapped[float | None] = mapped_column(Float)
    training_effect_label: Mapped[str | None] = mapped_column(String(40))
    training_load: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    avg_ground_contact_time: Mapped[float | None] = mapped_column(Float)  # ms
    avg_vertical_oscillation: Mapped[float | None] = mapped_column(Float)  # cm
    calories: Mapped[float | None] = mapped_column(Float)

    # User feedback (post-run)
    feel_rating: Mapped[int | None] = mapped_column(Integer)  # 1-10
    feel_notes: Mapped[str | None] = mapped_column(Text)  # free text

    # Onboarding: user-highlighted workouts
    user_highlighted: Mapped[bool] = mapped_column(Boolean, default=False)  # user flagged as representative of fitness
    user_workout_notes: Mapped[str | None] = mapped_column(Text)  # user's description of splits/effort

    # Workout classification
    workout_type: Mapped[str | None] = mapped_column(String(30))  # easy, tempo, interval, long, recovery, etc.

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="activities")


class PersonalRecord(Base):
    __tablename__ = "personal_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    distance_label: Mapped[str] = mapped_column(String(50))  # "1 Mile", "5K", "Half Marathon", etc.
    distance_miles: Mapped[float] = mapped_column(Float)
    time_seconds: Mapped[float] = mapped_column(Float)
    pace_per_mile: Mapped[float] = mapped_column(Float)  # seconds per mile
    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("activities.id"), nullable=True)
    strava_activity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
