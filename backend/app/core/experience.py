"""Experience describes training background, not a race-time ranking."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExperiencePolicy:
    support_primary_days: int
    dual_primary_days: int
    dual_support_days: int
    stable_weeks: int
    dual_weekly_miles: float
    deload_after: int


EXPERIENCE_POLICIES = {
    'beginner': ExperiencePolicy(2, 4, 4, 8, 25, 3),
    'intermediate': ExperiencePolicy(1, 3, 3, 6, 30, 4),
    'advanced': ExperiencePolicy(0, 2, 2, 4, 30, 6),  # deload every 7th week
    'expert': ExperiencePolicy(0, 2, 1, 4, 30, 7),  # every 8th
}


def experience_policy(level):
    return EXPERIENCE_POLICIES.get(level, EXPERIENCE_POLICIES['beginner'])


def experienced(level):
    return level in {'advanced', 'expert'}
