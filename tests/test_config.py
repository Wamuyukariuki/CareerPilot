import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_settings_reject_documented_local_defaults():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            app_env="production",
            secret_key="replace-with-a-random-secret-at-least-32-characters",
            database_url=(
                "postgresql+psycopg://postgres:careerpilot-local-only"
                "@localhost:5432/careerpilot"
            ),
            rate_limit_storage_uri="redis://localhost:6379/0",
        )

    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(
            app_env="production",
            secret_key="a-real-key-that-is-long-enough-for-production-123",
            database_url=(
                "postgresql+psycopg://postgres:careerpilot-local-only"
                "@localhost:5432/careerpilot"
            ),
            rate_limit_storage_uri="redis://localhost:6379/0",
        )


def test_production_settings_accept_configured_services_and_secrets():
    settings = Settings(
        app_env="production",
        secret_key="a-real-key-that-is-long-enough-for-production-123",
        database_url=(
            "postgresql+psycopg://postgres:another-private-password"
            "@localhost:5432/careerpilot"
        ),
        rate_limit_storage_uri="redis://localhost:6379/0",
    )

    assert settings.app_env == "production"
