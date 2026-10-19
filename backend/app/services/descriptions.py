"""Detect whether free-text activity notes describe a workout."""

import re

# Keywords that suggest a description contains workout details
WORKOUT_KEYWORDS = [
    "tempo", "threshold", "interval", "repeat", "rep", "mile repeat",
    "800", "400", "1k", "1600", "fartlek", "progression",
    "race pace", "marathon pace", "mp", "half marathon pace", "hmp",
    "5k pace", "10k pace", "goal pace",
    "warmup", "warm up", "cooldown", "cool down",
    "splits", "split", "negative split",
    "easy then", "then hard", "then fast",
    "x2", "x3", "x4", "x5", "x6", "x7", "x8",
    "2x", "3x", "4x", "5x", "6x", "7x", "8x",
    "workout", "speed work", "track",
    "recovery jog", "jog rest", "rest between",
    "pr", "personal record", "personal best", "pb",
    "race", "raced",
    "sub 3", "sub 17", "sub 18", "sub 19", "sub 20",
    "6:30", "6:00", "5:30", "7:00",  # common pace references
    "miles at", "mile at", "min at", "minutes at",
]



def _keyword_regex(kw: str) -> str:
    # Word boundaries on alphabetic edges so "mp" doesn't match "jump" and
    # "pr" doesn't match "practice"; plural "s" allowed ("reps", "splits").
    pre = r"\b" if kw[0].isalpha() else ""
    post = r"s?\b" if kw[0].isalpha() and kw[-1].isalpha() else ""
    return pre + re.escape(kw) + post


WORKOUT_PATTERN = re.compile(
    "|".join(_keyword_regex(kw) for kw in WORKOUT_KEYWORDS),
    re.IGNORECASE,
)


def is_workout_description(description: str | None) -> bool:
    """Check if a description contains workout-related content."""
    if not description or len(description.strip()) < 10:
        return False
    return bool(WORKOUT_PATTERN.search(description))
