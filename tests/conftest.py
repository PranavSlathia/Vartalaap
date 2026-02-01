"""Shared pytest fixtures for Vartalaap tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.config import Settings


def build_settings(**overrides) -> Settings:
    """Create a Settings object with safe test defaults."""
    base = {
        "groq_api_key": "test-groq-key",
        "deepgram_api_key": "test-deepgram-key",
        "plivo_auth_id": "test-plivo-id",
        "plivo_auth_token": "test-plivo-token",
        "phone_encryption_key": "0" * 64,
        "phone_hash_pepper": "1" * 64,
        "admin_password_hash": "test-admin-hash",
        "session_secret": "test-session-secret",
        "database_url": "sqlite+aiosqlite:///./data/test.db",
        "redis_url": "redis://localhost:6379",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    """Return a factory to build Settings with overrides."""
    return build_settings


@pytest.fixture
def settings(settings_factory: Callable[..., Settings]) -> Settings:
    """Default Settings fixture."""
    return settings_factory()
