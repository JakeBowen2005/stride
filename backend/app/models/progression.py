"""Workout progression tracking.

Stores where the athlete is on each workout ladder (threshold, intervals)
and the evaluation history that drives progression decisions.
"""

from datetime import date as date_type, datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, Integer, String
from app.database import Base


class WorkoutProgression(Base):
    __tablename__ = "workout_progressions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    category = Column(String, nullable=False)  # "threshold" or "intervals"
    # Which ladder these levels refer to. Level 5 on the 5K interval ladder
    # (6x800m) is a different workout from level 5 on the marathon one
    # (4x1mi), so a goal change has to re-seed rather than carry the number
    # across.
    distance = Column(String, nullable=False, default="5k")
    current_level = Column(Integer, nullable=False, default=1)
    last_workout_date = Column(Date, nullable=True)
    last_workout_name = Column(String, nullable=True)
    last_execution = Column(String, nullable=True)  # advance, hold, regress, recalibrate
    current_pace_sec = Column(Float, nullable=True)  # current working pace (sec/mi)
    sessions_at_level = Column(Integer, nullable=False, default=0)
    format_rotation = Column(Integer, nullable=False, default=0)  # 0, 1, 2
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<WorkoutProgression user={self.user_id} cat={self.category} dist={self.distance} level={self.current_level}>"
