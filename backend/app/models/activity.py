from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # string relationship targets, for type checkers only
    from app.models.user import User


# Garmin Connect's labels for the watch's post-run self-evaluation
GARMIN_FEEL_LABELS = {0: "Very weak", 25: "Weak", 50: "Normal", 75: "Strong", 100: "Very strong"}
GARMIN_EFFORT_LABELS = {1: "Very light", 2: "Light", 3: "Light", 4: "Moderate", 5: "Moderate", 6: "Moderate",
                        7: "Hard", 8: "Hard", 9: "Very hard", 10: "Maximum"}


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
    external_id: Mapped[str | None] = mapped_column(String(100))  # Garmin activity ID (Strava ID on legacy rows)

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
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # for "Garmin <device>" attribution
    vo2max: Mapped[float | None] = mapped_column(Float)
    avg_ground_contact_time: Mapped[float | None] = mapped_column(Float)  # ms
    avg_vertical_oscillation: Mapped[float | None] = mapped_column(Float)  # cm
    calories: Mapped[float | None] = mapped_column(Float)

    # User feedback (post-run)
    feel_rating: Mapped[int | None] = mapped_column(Integer)  # 1-10
    effort_rating: Mapped[int | None] = mapped_column(Integer)
    reported_completion: Mapped[str | None] = mapped_column(String(20))
    feel_notes: Mapped[str | None] = mapped_column(Text)  # free text
    # The watch's own post-run self-evaluation, on Garmin's scales: feel 0/25/50/75/100
    # (very weak .. very strong) and perceived effort 10-100. Stride app ratings win.
    garmin_feel: Mapped[int | None] = mapped_column(Integer)
    garmin_rpe: Mapped[int | None] = mapped_column(Integer)
    garmin_rating_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def watch_feel(self) -> int | None:
        """Garmin feel on Stride's 1-10 feel scale (very weak 2 .. very strong 10)."""
        return None if self.garmin_feel is None else max(1, min(10, round(2 + self.garmin_feel / 12.5)))

    @property
    def watch_effort(self) -> int | None:
        """Garmin perceived effort (10-100) on Stride's 1-10 effort scale."""
        return None if not self.garmin_rpe else max(1, min(10, round(self.garmin_rpe / 10)))

    @property
    def watch_feel_label(self) -> str | None:
        """Garmin's own word for the feel answer, as the Connect app shows it."""
        if self.garmin_feel is None:
            return None
        return GARMIN_FEEL_LABELS[min(GARMIN_FEEL_LABELS, key=lambda k: abs(k - self.garmin_feel))]

    @property
    def watch_effort_label(self) -> str | None:
        """Garmin's own word for perceived effort ("Light" for 2/10)."""
        return None if self.watch_effort is None else GARMIN_EFFORT_LABELS[self.watch_effort]

    @property
    def effective_feel(self) -> int | None:
        """The athlete's own rating: the app answer when given, else the watch's."""
        return self.feel_rating if self.feel_rating is not None else self.watch_feel

    # Onboarding: user-highlighted workouts
    user_highlighted: Mapped[bool] = mapped_column(Boolean, default=False)  # user flagged as representative of fitness
    user_workout_notes: Mapped[str | None] = mapped_column(Text)  # user's description of splits/effort

    # Athlete correction takes precedence over provider mode and pace heuristics.
    activity_kind_override: Mapped[str | None] = mapped_column(String(10), nullable=True)

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


# ── Runs vs walks ───────────────────────────────────────────────
# Watches record a walk as a "treadmill run" if that's the mode picked. A walk is never part of
# the running plan: no mileage, no plan matching, no coaching. It still shows in history, labeled.
WALK_PACE_SEC_PER_MILE = 990  # 16:30/mi: slower than the slowest easy jog Stride prescribes


def is_walk(activity) -> bool:
    override = getattr(activity, "activity_kind_override", None)
    if override:
        return override == "walk"
    subtype = (activity.activity_subtype or "").lower()
    # Running races and outdoor running may include hiking, technical terrain,
    # run/walk or slow recovery. Speed alone is never grounds for exclusion.
    if activity.event_type == "race" or ("run" in subtype and "treadmill" not in subtype):
        return False
    if "walk" in subtype or "hik" in subtype:
        return True
    # Preserve old treadmill/unknown walk labels until the athlete corrects them.
    return activity.workout_type == "walk"


def activity_classification(activity) -> dict:
    miles = (activity.distance_meters or 0) / 1609.34
    slow = bool(miles and activity.duration_seconds and activity.duration_seconds / miles > WALK_PACE_SEC_PER_MILE)
    override = getattr(activity, "activity_kind_override", None)
    walk = is_walk(activity)
    uncertain = not override and slow and (activity.activity_subtype or "") not in {"walking", "hiking"} and activity.event_type != "race"
    reason = ("Athlete-confirmed classification." if override else
              "Provider identifies walking/hiking, or a preserved walk label; you can correct it." if walk else
              "Slow pace can reflect running, hiking or walking. Confirm the activity type; it remains in running load." if uncertain else
              "Running activity; pace does not determine whether it counts.")
    return {"kind": "walk" if walk else "run", "needs_review": uncertain, "reason": reason, "override": override}


def runs_only():
    """Query filter: every activity except walks."""
    from sqlalchemy import or_
    return or_(Activity.workout_type.is_(None), Activity.workout_type != "walk")
