"""Shared pytest fixtures for Vartalaap tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Generator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

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
        "database_url": "sqlite+aiosqlite:///:memory:",
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


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory async SQLite engine for testing."""
    # Import models to register them with SQLModel metadata
    from src.db import models  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for testing."""
    async_session_maker = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session


# =============================================================================
# FastAPI Test Client Fixtures
# =============================================================================

# Shared test engine for API tests
_test_engine = None
_test_session_factory = None


def _get_test_engine():
    """Get or create a shared test engine."""
    global _test_engine
    if _test_engine is None:
        from src.db import models  # noqa: F401

        _test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            future=True,
        )
    return _test_engine


def _get_test_session_factory():
    """Get or create test session factory."""
    global _test_session_factory
    if _test_session_factory is None:
        _test_session_factory = sessionmaker(
            _get_test_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _test_session_factory


async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
    """Override get_session for testing."""
    async with _get_test_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture
def test_client(settings_factory, monkeypatch) -> Generator:
    """FastAPI TestClient with patched settings and in-memory database."""
    import asyncio
    import sys

    from fastapi.testclient import TestClient

    test_settings = settings_factory()

    # Patch get_settings globally before importing anything
    # Need to patch in all modules that import it
    monkeypatch.setattr("src.config.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.services.llm.groq.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.services.stt.deepgram.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.core.pipeline.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.api.websocket.audio_stream.get_settings", lambda: test_settings)
    monkeypatch.setattr("src.api.routes.plivo_webhook.get_settings", lambda: test_settings)

    # Patch init_db to create tables in test engine
    async def mock_init_db():
        from src.db import models  # noqa: F401

        engine = _get_test_engine()
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    # Patch close_db to be a no-op
    async def mock_close_db():
        pass

    # Patch at the db.session module level
    monkeypatch.setattr("src.db.session.init_db", mock_init_db)
    monkeypatch.setattr("src.db.session.close_db", mock_close_db)

    # Remove cached main module to force re-import with patches
    if "src.main" in sys.modules:
        del sys.modules["src.main"]

    # Import and create the app after patching
    # Also patch at the main module level (after import)
    import src.main
    from src.db.session import get_session
    from src.main import create_app

    monkeypatch.setattr(src.main, "init_db", mock_init_db)
    monkeypatch.setattr(src.main, "close_db", mock_close_db)

    app = create_app()

    # Override get_session dependency
    app.dependency_overrides[get_session] = _override_get_session

    with TestClient(app) as client:
        yield client

    # Cleanup: drop all tables after test
    async def cleanup():
        engine = _get_test_engine()
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)

    asyncio.get_event_loop().run_until_complete(cleanup())


@pytest.fixture
def test_client_no_db(settings_factory, monkeypatch) -> Generator:
    """FastAPI TestClient with no database (for testing degraded health)."""
    from fastapi.testclient import TestClient

    test_settings = settings_factory()

    # Patch get_settings globally
    monkeypatch.setattr("src.config.get_settings", lambda: test_settings)

    # Patch init_db to be a no-op
    async def mock_init_db():
        pass

    monkeypatch.setattr("src.db.session.init_db", mock_init_db)

    # Patch close_db to be a no-op
    async def mock_close_db():
        pass

    monkeypatch.setattr("src.db.session.close_db", mock_close_db)

    # Import and create the app after patching
    from src.main import create_app

    app = create_app()

    with TestClient(app) as client:
        yield client
