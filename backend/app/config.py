from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://ved:ved_local_pass@db:5432/ved"
    jwt_secret: str = "change-me-in-env-file"
    jwt_alg: str = "HS256"
    jwt_ttl_hours: int = 12

    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 25

    seed_demo: bool = True
    admin_email: str = "admin@ved.local"
    admin_password: str = "admin123"

    app_name: str = "ВЭД RTP"

    # Communication integrations. Keep real values in `.env`; that file is
    # deliberately ignored by Git and never exposed by the API.
    public_base_url: str = "http://localhost:8090"
    integration_encryption_key: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    gmail_poll_interval_minutes: int = 5


settings = Settings()
