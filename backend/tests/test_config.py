"""Configuration system tests."""

from __future__ import annotations

from app.core.config import Environment, Settings


def test_settings_defaults_and_nested():
    settings = Settings()
    assert settings.app_name
    assert settings.api_v1_prefix.startswith("/")
    # Nested subsystems are constructed.
    assert settings.rate_limit.user_requests >= 1
    assert settings.ollama.primary_model
    assert "PERSON" in settings.safety.pii_entities


def test_cors_origins_parsed_from_csv(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    settings = Settings()
    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_environment_enum(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    settings = Settings()
    assert settings.environment == Environment.PRODUCTION
    assert settings.is_production is True
