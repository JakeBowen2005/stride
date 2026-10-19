from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stride.db"
    secret_key: str = "stride-dev-secret-key-change-in-production"
    anthropic_api_key: str = ""
    coach_model: str = "claude-haiku-5-5"
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # Garmin Connect — tokens are created once by `python garmin_login.py`
    garmin_tokenstore: str = str(BACKEND_DIR / ".garmin")
    garmin_poll_minutes: int = 10  # auto-sync interval; 0 disables
    default_user_id: int = 1

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
