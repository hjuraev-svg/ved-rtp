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


settings = Settings()
