"""Workout progression tracking.

Stores where the athlete is on each workout ladder (threshold, intervals)
and the evaluation history that drives progression decisions.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, Integer, String
from app.database import Base


class WorkoutProgression(Base):
    __tablename__ = "workout_progressions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    category = Column(String, nullable=False)  # "threshold" or "intervals"
    program_key = Column(String(80), nullable=True)
    current_level = Column(Integer, nullable=False, default=1)
    last_workout_date = Column(Date, nullable=True)
    last_workout_name = Column(String, nullable=True)
    last_execution = Column(String, nullable=True)  # advance, hold, regress, recalibrate
    current_pace_sec = Column(Float, nullable=True)  # current working pace (sec/mi)
    sessions_at_level = Column(Integer, nullable=False, default=0)
    format_rotation = Column(Integer, nullable=False, default=0)  # 0, 1, 2
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<WorkoutProgression user={self.user_id} cat={self.category} level={self.current_level}>"
