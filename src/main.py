"""FastAPI application entry point.

Vartalaap - Voice bot platform for local Indian businesses.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health
from src.config import get_settings
from src.db.session import close_db, init_db
from src.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Startup:
    - Initialize logging
    - Initialize database

    Shutdown:
    - Close database connections
    """
    settings = get_settings()

    # Startup
    setup_logging(
        level=settings.log_level,
        enable_file=settings.is_production,
    )

    # Only auto-create tables in development
    # Production should use: alembic upgrade head
    if not settings.is_production:
        await init_db()

    yield

    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Vartalaap API",
        description="Voice bot platform for local Indian businesses",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])

    # Future routers:
    # app.include_router(plivo_webhook.router, prefix="/api", tags=["Plivo"])
    # app.include_router(crud.router, prefix="/api", tags=["CRUD"])
    # app.websocket("/ws/audio/{call_uuid}")(audio_stream_endpoint)

    return app


# Application instance
app = create_app()
