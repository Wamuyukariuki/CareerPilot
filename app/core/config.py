from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    app_name: str = "CareerPilot"
    app_env: str = "development"
    secret_key: SecretStr = Field(
        default=SecretStr("development-only-key-change-before-deployment-please"),
        min_length=32,
    )
    database_url: str = "sqlite:///./careerpilot.db"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_storage_uri: str = "memory://"
    upload_dir: str = "data/uploads"
    pdf_font_paths: list[str] = []
    max_upload_size_bytes: int = Field(
        default=10 * 1024 * 1024, gt=0, le=25 * 1024 * 1024
    )
    allowed_origins: list[str] = ["http://localhost:5173"]
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.lower() == "production":
            secret_key = self.secret_key.get_secret_value()
            if secret_key.startswith("development-only-") or secret_key == (
                "replace-with-a-random-secret-at-least-32-characters"
            ):
                raise ValueError("SECRET_KEY must be configured in production.")
            if self.database_url.startswith("sqlite"):
                raise ValueError("PostgreSQL must be configured in production.")
            if make_url(self.database_url).password in {
                "careerpilot-local-only",
                "replace-this-local-password",
            }:
                raise ValueError(
                    "POSTGRES_PASSWORD must be changed from the local development default."
                )
            if self.rate_limit_storage_uri.startswith("memory://"):
                raise ValueError("Shared Redis rate-limit storage is required in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
