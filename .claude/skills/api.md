# /api - API Endpoints & CRUD Generation

## Context

You are working on **Vartalaap**, a voice bot platform for local Indian businesses.

**Tech Stack Reference:** `docs/TECH_STACK.md` (Section 2, 18.7)
**PRD Reference:** `docs/PRD.md` (Section 9 - Data Models)

## Stack Summary

- **Framework:** FastAPI 0.115.x
- **Validation:** Pydantic v2 (via SQLModel)
- **CRUD Generator:** fastapi-crudrouter 0.8.x
- **OpenAPI:** Auto-generated at `/docs` and `/openapi.json`
- **Async DB:** SQLModel + aiosqlite

## API Structure

```
src/api/
├── __init__.py
├── routes/
│   ├── __init__.py
│   ├── health.py           # Health check
│   ├── plivo_webhook.py    # Plivo call webhooks
│   └── crud.py             # Auto-generated CRUD routers
└── websocket/
    ├── __init__.py
    └── audio_stream.py     # Plivo audio WebSocket
```

## CRUD Generation Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. JSON Schema exists      →   schemas/reservation.json        │
│  2. Pydantic generated      →   src/schemas/reservation.py      │
│  3. SQLModel created        →   src/db/models.py                │
│  4. CRUD router generated   →   src/api/routes/crud.py          │
│  5. OpenAPI auto-updated    →   /docs, /openapi.json            │
└─────────────────────────────────────────────────────────────────┘
```

## fastapi-crudrouter Setup

```python
# src/api/routes/crud.py
from fastapi import APIRouter, Depends
from fastapi_crudrouter import SQLAlchemyCRUDRouter
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.session import get_session
from src.db.models import Reservation, CallLog, CallerPreferences, WhatsappFollowup
from src.schemas.reservation import Reservation as ReservationSchema
from src.schemas.call_log import CallLog as CallLogSchema

# Create main router
router = APIRouter()

# ============================================================
# RESERVATION CRUD
# ============================================================

class ReservationCreate(ReservationSchema):
    """Schema for creating reservations (exclude auto-generated fields)."""
    id: None = None
    created_at: None = None
    updated_at: None = None

class ReservationUpdate(ReservationSchema):
    """Schema for partial updates (all fields optional)."""
    business_id: str | None = None
    party_size: int | None = None
    reservation_date: str | None = None
    reservation_time: str | None = None
    status: str | None = None

reservation_router = SQLAlchemyCRUDRouter(
    schema=ReservationSchema,
    create_schema=ReservationCreate,
    update_schema=ReservationUpdate,
    db_model=Reservation,
    db=get_session,
    prefix="reservations",
    tags=["Reservations"],
    # Security: disable bulk delete
    delete_all_route=False,
)

# Add custom endpoint for availability check
@reservation_router.get("/availability")
async def check_availability(
    date: str,
    time: str,
    party_size: int,
    session: AsyncSession = Depends(get_session),
):
    """Check if a time slot is available."""
    # Custom business logic (not auto-generated)
    # See PRD Section 8.5 for rules
    pass

router.include_router(reservation_router)

# ============================================================
# CALL LOG CRUD (Read-only for admin)
# ============================================================

call_log_router = SQLAlchemyCRUDRouter(
    schema=CallLogSchema,
    db_model=CallLog,
    db=get_session,
    prefix="call-logs",
    tags=["Call Logs"],
    # Read-only: disable create/update/delete
    create_route=False,
    update_route=False,
    delete_one_route=False,
    delete_all_route=False,
)

router.include_router(call_log_router)
```

## Generated Endpoints

For each CRUD router, these endpoints are auto-generated:

| Method | Endpoint | Description | Can Disable |
|--------|----------|-------------|-------------|
| GET | `/{prefix}` | List all (paginated) | - |
| GET | `/{prefix}/{id}` | Get one by ID | - |
| POST | `/{prefix}` | Create new | `create_route=False` |
| PUT | `/{prefix}/{id}` | Full update | `update_route=False` |
| PATCH | `/{prefix}/{id}` | Partial update | Requires `update_schema` |
| DELETE | `/{prefix}/{id}` | Delete one | `delete_one_route=False` |
| DELETE | `/{prefix}` | Delete all | `delete_all_route=False` |

## Adding Custom Endpoints

```python
# Add to the auto-generated router
@reservation_router.post("/{id}/cancel")
async def cancel_reservation(
    id: str,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a reservation (custom business logic)."""
    reservation = await session.get(Reservation, id)
    if not reservation:
        raise HTTPException(404, "Reservation not found")

    reservation.status = "cancelled"
    reservation.updated_at = datetime.utcnow()
    session.add(reservation)
    await session.commit()

    # Audit log
    # ...

    return {"status": "cancelled"}
```

## Health Check Endpoint

```python
# src/api/routes/health.py
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.session import get_session
from src.config import get_settings
import aiohttp

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}

@router.get("/health/detailed")
async def detailed_health(
    session: AsyncSession = Depends(get_session),
):
    """Detailed health check including dependencies."""
    settings = get_settings()
    checks = {}

    # Database
    try:
        await session.exec("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis
    try:
        from arq import create_pool
        redis = await create_pool(settings.redis_settings)
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # External services (don't fail health check)
    checks["deepgram"] = "configured" if settings.deepgram_api_key else "missing"
    checks["groq"] = "configured" if settings.groq_api_key else "missing"
    checks["plivo"] = "configured" if settings.plivo_auth_id else "missing"

    status = "healthy" if checks["database"] == "ok" else "degraded"
    return {"status": status, "checks": checks}
```

## Plivo Webhook Endpoints

```python
# src/api/routes/plivo_webhook.py
from fastapi import APIRouter, Request, Response
from src.services.telephony.plivo import PlivoHandler
from loguru import logger

router = APIRouter(prefix="/plivo", tags=["Plivo Webhooks"])

@router.post("/answer")
async def answer_call(request: Request):
    """Handle incoming call - return Plivo XML."""
    form = await request.form()
    call_uuid = form.get("CallUUID")
    from_number = form.get("From")

    logger.info(f"Incoming call: {call_uuid}")
    # Note: Don't log phone number (PII)

    # Return Plivo XML to connect to WebSocket
    xml = f"""
    <Response>
        <Stream bidirectional="true" keepCallAlive="true">
            wss://{request.url.host}/ws/audio/{call_uuid}
        </Stream>
    </Response>
    """
    return Response(content=xml, media_type="application/xml")

@router.post("/hangup")
async def hangup_callback(request: Request):
    """Handle call hangup."""
    form = await request.form()
    call_uuid = form.get("CallUUID")
    duration = form.get("Duration")

    logger.info(f"Call ended: {call_uuid}, duration={duration}s")
    return {"status": "ok"}
```

## WebSocket Endpoint

```python
# src/api/websocket/audio_stream.py
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from src.core.pipeline import VoicePipeline
from src.core.session import CallSession

async def audio_stream_endpoint(websocket: WebSocket, call_uuid: str):
    """Handle Plivo audio WebSocket stream."""
    await websocket.accept()
    logger.info(f"WebSocket connected: {call_uuid}")

    session = CallSession(call_uuid)
    pipeline = VoicePipeline(...)  # Inject dependencies

    try:
        while True:
            # Receive audio from Plivo
            data = await websocket.receive_bytes()

            # Process through pipeline
            await pipeline.process_audio(session, data)

            # Send response audio back
            if session.has_audio_to_send():
                audio = session.get_audio_chunk()
                await websocket.send_bytes(audio)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {call_uuid}")
        await session.cleanup()
```

## Main App Registration

```python
# src/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.api.routes import health, plivo_webhook, crud
from src.api.websocket.audio_stream import audio_stream_endpoint
from src.db.session import init_db
from src.config import get_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    settings = get_settings()
    await init_db()
    yield
    # Shutdown
    # Cleanup resources

app = FastAPI(
    title="Vartalaap API",
    description="Voice bot platform for local businesses",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router)
app.include_router(plivo_webhook.router, prefix="/api")
app.include_router(crud.router, prefix="/api")

# WebSocket endpoint
app.websocket("/ws/audio/{call_uuid}")(audio_stream_endpoint)
```

## API Documentation

FastAPI auto-generates:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

## Request/Response Patterns

### Pagination
```python
# Auto-handled by fastapi-crudrouter
GET /api/reservations?skip=0&limit=10

# Response includes pagination info
{
    "items": [...],
    "total": 100,
    "skip": 0,
    "limit": 10
}
```

### Filtering
```python
# Add custom filters to CRUD router
@reservation_router.get("/")
async def list_reservations(
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """List reservations with filters."""
    query = select(Reservation)

    if status:
        query = query.where(Reservation.status == status)
    if date_from:
        query = query.where(Reservation.reservation_date >= date_from)
    if date_to:
        query = query.where(Reservation.reservation_date <= date_to)

    result = await session.exec(query)
    return result.all()
```

### Error Responses
```python
from fastapi import HTTPException, status

# Standard error format
{
    "detail": "Reservation not found"
}

# Validation errors (Pydantic)
{
    "detail": [
        {
            "loc": ["body", "party_size"],
            "msg": "ensure this value is greater than 0",
            "type": "value_error.number.not_gt"
        }
    ]
}
```

## Testing API Endpoints

```python
# tests/test_api/test_reservations.py
from ward import test
from httpx import AsyncClient
from src.main import app

@test("GET /api/reservations returns list")
async def _():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/reservations")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

@test("POST /api/reservations creates reservation")
async def _():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/reservations", json={
            "business_id": "himalayan-kitchen",
            "party_size": 4,
            "reservation_date": "2026-02-15",
            "reservation_time": "19:00",
            "customer_name": "Test User",
        })
        assert response.status_code == 201
        assert response.json()["id"] is not None

@test("POST /api/reservations validates party_size")
async def _():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/reservations", json={
            "business_id": "himalayan-kitchen",
            "party_size": 100,  # Exceeds max
            "reservation_date": "2026-02-15",
            "reservation_time": "19:00",
        })
        assert response.status_code == 422  # Validation error
```

## Checklist for New API Endpoint

- [ ] Schema defined (JSON Schema → Pydantic → SQLModel)
- [ ] CRUD router created in `src/api/routes/crud.py`
- [ ] Custom business logic endpoints added
- [ ] Router included in `src/main.py`
- [ ] OpenAPI docs verified at `/docs`
- [ ] Tests written in `tests/test_api/`
- [ ] Error handling returns proper HTTP status codes
- [ ] No PII in logs or error messages
