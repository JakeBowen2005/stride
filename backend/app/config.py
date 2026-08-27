from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    strava_client_id: str
    strava_client_secret: str
    database_url: str = "sqlite:///./stride.db"
    secret_key: str = "stride-dev-secret-key-change-in-production"
    strava_redirect_uri: str = "http://localhost:8000/api/strava/callback"
    strava_webhook_verify_token: str = "stride-webhook-verify"
    strava_webhook_url: str = "http://localhost:8000/api/strava/webhook"
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
