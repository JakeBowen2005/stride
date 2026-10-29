from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    accounts_enabled: bool = Field(default=False, validation_alias="STRIDE_ACCOUNTS_ENABLED")
    signup_invite_code: str = Field(default="", validation_alias="STRIDE_SIGNUP_INVITE_CODE")
    cookie_secure: bool = Field(default=True, validation_alias="STRIDE_COOKIE_SECURE")
    public_app_url: str = Field(default="", validation_alias="STRIDE_PUBLIC_URL")
    schema_auto_upgrade: bool = True
    embedded_workers: bool = True
    # Render: run the durable job loop inside the API process (saves a second ~150MB Python
    # process on a 512MB instance) while manual syncs still go through the queue.
    in_process_worker: bool = Field(default=False, validation_alias="STRIDE_IN_PROCESS_WORKER")
    provider_encryption_keys: str = Field(default="", validation_alias="STRIDE_PROVIDER_ENCRYPTION_KEYS")
    fit_blob_bucket: str = ""
    fit_blob_prefix: str = "stride"
    database_url: str = "sqlite:///./stride.db"
    openai_api_key: str = ""
    openai_coach_model: str = "gpt-5.4-mini"
    openai_coach_global_daily_limit: int = 100
    # Per athlete, per local day. A run review is ~30k input / ~500 output tokens (~$0.025 on
    # gpt-5.4-mini), so 30 is at most ~$0.75/day; cached (unchanged) reviews never count.
    openai_coach_daily_limit: int = 30
    openai_coach_timeout_seconds: float = 35
    openai_auto_reviews: bool = True
    # Plain-language plan changes: a slim ~3k-token request, so a separate, smaller cap
    # (docs/plain-language-plan-changes.md §3). Empty model = use openai_coach_model.
    # Monthly dollar caps (docs/multi-user-design.md §2.6); daily attempt limits stay as a burst guard.
    openai_monthly_budget_usd: float = 15.0  # app-wide; the owner's allowance is reserved inside it
    openai_athlete_monthly_budget_usd: float = 1.0
    openai_owner_monthly_budget_usd: float = 10.0
    allowed_origins: str = "http://localhost:3000,http://localhost:3001"

    # Garmin Connect Personal API key (connect.garmin.com/app/settings/personalApiToken).
    # Pull-only API: Stride checks for new runs when the app opens and on this interval.
    garmin_api_key: str = ""
    garmin_poll_minutes: int = 15  # background check interval; 0 disables
    garmin_quiet_hours: str = "22-5"  # local hours checked only hourly (nobody uploads runs at 2am)
    default_user_id: int = 1

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
