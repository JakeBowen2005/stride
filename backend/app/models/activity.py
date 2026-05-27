from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20))  # "strava", "garmin", "manual"
    external_id: Mapped[str | None] = mapped_column(String(50))  # Strava/Garmin activity ID

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

    # Strava metadata
    description: Mapped[str | None] = mapped_column(Text)  # user's notes from Strava
    strava_workout_type: Mapped[int | None] = mapped_column(Integer)  # 0=default, 1=race, 2=long run, 3=workout
    suffer_score: Mapped[float | None] = mapped_column(Float)  # Strava relative effort
    pr_count: Mapped[int | None] = mapped_column(Integer)  # PRs hit on this activity
    has_workout_description: Mapped[bool] = mapped_column(Boolean, default=False)  # flagged as containing workout details

    # Splits (stored as JSON string)
    splits: Mapped[str | None] = mapped_column(Text)  # JSON array of split data

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
