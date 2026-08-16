"""Configuration validation.

The production hardening validator is a security control, so it gets tests.
"""

from __future__ import annotations

import pytest
from app.core.config import (
    DEV_SECRET_PLACEHOLDER,
    CorsSettings,
    DatabaseSettings,
    Environment,
    ModelSettings,
    SecuritySettings,
    Settings,
)
from pydantic import ValidationError


def _production(**overrides):  # type: ignore[no-untyped-def]
    base = {
        "environment": Environment.PRODUCTION,
        "debug": False,
        "security": SecuritySettings(secret_key="x" * 48),
        "cors": CorsSettings(allow_origins="https://app.example.com"),
        "database": DatabaseSettings(url="postgresql+asyncpg://u:p@db:5432/oia"),
    }
    base.update(overrides)
    return Settings(**base)


def test_production_config_accepts_a_hardened_setup() -> None:
    settings = _production()
    assert settings.environment.is_production_like
    assert settings.docs_url is None


def test_production_rejects_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production(security=SecuritySettings(secret_key=DEV_SECRET_PLACEHOLDER))


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        _production(security=SecuritySettings(secret_key="too-short"))


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _production(debug=True)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="CORS"):
        _production(cors=CorsSettings(allow_origins="*"))


def test_production_rejects_sql_echo() -> None:
    with pytest.raises(ValidationError, match="ECHO"):
        _production(
            database=DatabaseSettings(url="postgresql+asyncpg://u:p@db:5432/oia", echo=True)
        )


def test_development_tolerates_defaults() -> None:
    settings = Settings(environment=Environment.DEVELOPMENT)
    assert settings.docs_url == "/docs"


def test_sync_driver_is_rejected() -> None:
    with pytest.raises(ValidationError, match="async driver"):
        Settings(database=DatabaseSettings(url="postgresql://u:p@db:5432/oia"))


def test_safe_url_hides_credentials() -> None:
    db = DatabaseSettings(url="postgresql+asyncpg://user:sekrit@db:5432/oia")
    assert "sekrit" not in db.safe_url
    assert db.safe_url.endswith("db:5432/oia")


def test_cors_origins_are_parsed_from_a_comma_list() -> None:
    cors = CorsSettings(allow_origins="http://a.test, http://b.test ,")
    assert cors.origins == ["http://a.test", "http://b.test"]


def test_model_routing_maps_task_classes() -> None:
    models = ModelSettings(model_small="small", model_reasoning="big")
    assert models.for_task("small") == "small"
    assert models.for_task("reasoning") == "big"
