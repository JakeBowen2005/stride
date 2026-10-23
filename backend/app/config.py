from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stride.db"
    openai_api_key: str = ""
    openai_coach_model: str = "gpt-5.4-mini"
    openai_coach_daily_limit: int = 12
    openai_coach_timeout_seconds: float = 35
    openai_auto_reviews: bool = True
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # Garmin Connect Personal API key (connect.garmin.com/app/settings/personalApiToken).
    # Pull-only API: Stride checks for new runs when the app opens and on this interval.
    garmin_api_key: str = ""
    garmin_poll_minutes: int = 15  # background check interval; 0 disables
    garmin_quiet_hours: str = "22-5"  # local hours checked only hourly (nobody uploads runs at 2am)
    default_user_id: int = 1

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
