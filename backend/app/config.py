from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    strava_client_id: str
    strava_client_secret: str
    database_url: str = "sqlite:///./stride.db"
    secret_key: str = "stride-dev-secret-key-change-in-production"
    strava_redirect_uri: str = "http://localhost:8000/api/strava/callback"

    model_config = {"env_file": ".env"}


settings = Settings()
