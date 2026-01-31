"""Database session management.

Provides async database connections using SQLModel and aiosqlite.
Uses dependency injection pattern for FastAPI integration.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from src.config import get_settings

# Engine created lazily on first use
_engine = None


def get_engine():
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()

        # Ensure data directory exists for SQLite
        if "sqlite" in settings.database_url:
            db_path = settings.database_url.split("///")[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,  # Log SQL in debug mode
            future=True,
        )
    return _engine


# Async session factory
def get_session_factory():
    """Get async session factory."""
    return sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def init_db() -> None:
    """Initialize database - create all tables.

    Called during application startup.
    In production, use Alembic migrations instead.
    """
    # Import models to register them with SQLModel
    from src.db import models  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db() -> None:
    """Close database connections.

    Called during application shutdown.
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session.

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async_session = get_session_factory()
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for getting async database session.

    Usage in background tasks or scripts:
        async with get_session_context() as session:
            ...
    """
    async_session = get_session_factory()
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Synchronous session for Streamlit admin (which doesn't support async well)
def get_sync_engine():
    """Get synchronous engine for Streamlit admin."""
    from sqlalchemy import create_engine

    settings = get_settings()
    # Convert async URL to sync URL
    sync_url = settings.database_url.replace("+aiosqlite", "")
    return create_engine(sync_url, echo=settings.debug)


def get_sync_session():
    """Context manager for synchronous session (Streamlit admin).

    Usage:
        with get_sync_session() as session:
            ...
    """
    from contextlib import contextmanager

    from sqlalchemy.orm import Session

    @contextmanager
    def _session_scope():
        session = Session(get_sync_engine())
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _session_scope()
