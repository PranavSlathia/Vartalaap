"""FastAPI application entry point.

Vartalaap - Voice bot platform for local Indian businesses.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import (
    business,
    call_logs,
    crud,
    health,
    knowledge,
    metrics,
    plivo_webhook,
    reviews,
    voice,
)
from src.api.websocket.audio_stream import audio_stream_endpoint, call_registry
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
    - Close active call sessions
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
    # Close all active call sessions
    await call_registry.close_all()

    # Close database
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

    # Health check routes
    app.include_router(health.router, tags=["Health"])

    # Plivo webhook routes
    app.include_router(plivo_webhook.router, prefix="/api", tags=["Plivo"])

    # CRUD routes for reservations
    app.include_router(crud.router, prefix="/api", tags=["CRUD"])

    # Knowledge base CRUD routes
    app.include_router(knowledge.router, prefix="/api", tags=["Knowledge"])

    # Call logs routes
    app.include_router(call_logs.router, prefix="/api", tags=["Call Logs"])

    # Transcript reviews routes (QA agent system)
    app.include_router(reviews.router, prefix="/api", tags=["Reviews"])

    # Business settings routes
    app.include_router(business.router, tags=["Business"])

    # Metrics endpoint for Prometheus scraping
    app.include_router(metrics.router, tags=["Observability"])

    # Voice testing routes
    app.include_router(voice.router, prefix="/api", tags=["Voice"])

    # WebSocket endpoint for audio streaming
    @app.websocket("/ws/audio/{call_id}")
    async def audio_ws(websocket: WebSocket, call_id: str):
        """WebSocket endpoint for Plivo audio streaming."""
        await audio_stream_endpoint(websocket, call_id)

    # Serve voice test UI
    @app.get("/voice")
    async def voice_ui():
        """Serve the voice testing UI."""
        static_path = Path(__file__).parent / "api" / "static" / "voice.html"
        return FileResponse(static_path, media_type="text/html")

    return app


# Application instance
app = create_app()
