# /backend - FastAPI Backend Development

## Context

You are working on **Vartalaap**, a voice bot platform for local Indian businesses.

**Tech Stack Reference:** `docs/TECH_STACK.md`
**PRD Reference:** `docs/PRD.md`

## Stack Summary

- **Framework:** FastAPI 0.115.x (async-native)
- **Server:** uvicorn 0.34.x
- **WebSocket:** websockets 14.x (Plivo audio streams)
- **Validation:** Pydantic v2 (via SQLModel)
- **Async HTTP:** aiohttp 3.11.x
- **Background Tasks:** arq 0.26.x + Redis
- **Logging:** loguru 0.7.x

## File Structure

```
src/
├── main.py                 # FastAPI app entry, lifespan events
├── config.py               # Pydantic Settings (env vars)
├── logging_config.py       # Loguru setup
├── api/
│   ├── routes/
│   │   ├── health.py       # Health check endpoint
│   │   ├── plivo_webhook.py # Plivo call webhooks
│   │   └── crud.py         # Auto-generated CRUD (fastapi-crudrouter)
│   └── websocket/
│       └── audio_stream.py # Plivo audio WebSocket handler
├── core/
│   ├── pipeline.py         # Voice pipeline orchestration (MANUAL)
│   ├── session.py          # Call session manager (MANUAL)
│   └── context.py          # Conversation context (MANUAL)
├── services/
│   ├── stt/deepgram.py     # Deepgram STT (MANUAL)
│   ├── llm/groq.py         # Groq LLM (MANUAL)
│   ├── tts/piper.py        # Piper TTS (MANUAL)
│   ├── tts/edge.py         # Edge TTS fallback (MANUAL)
│   └── telephony/plivo.py  # Plivo integration (MANUAL)
├── db/
│   ├── models.py           # SQLModel models
│   ├── session.py          # Async DB session
│   └── repositories/       # Data access layer
└── security/
    ├── crypto.py           # AES-256-GCM, HMAC-SHA256 (MANUAL)
    └── auth.py             # Admin authentication
```

## Patterns to Follow

### 1. Route Definition
```python
# src/api/routes/example.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from src.db.session import get_session
from src.schemas.example import ExampleCreate, ExampleResponse
from loguru import logger

router = APIRouter(prefix="/examples", tags=["Examples"])

@router.post("/", response_model=ExampleResponse, status_code=status.HTTP_201_CREATED)
async def create_example(
    data: ExampleCreate,
    session: AsyncSession = Depends(get_session),
) -> ExampleResponse:
    """Create a new example."""
    logger.info(f"Creating example: {data.name}")
    # Implementation
    return result
```

### 2. Dependency Injection
```python
# Common dependencies
from src.config import get_settings, Settings
from src.db.session import get_session

async def get_current_business(
    settings: Settings = Depends(get_settings),
) -> str:
    """Get current business ID (MVP: single tenant)."""
    return settings.default_business_id
```

### 3. Background Task Enqueueing
```python
from arq import create_pool
from src.config import get_settings

async def enqueue_whatsapp(phone_encrypted: str, message: str):
    settings = get_settings()
    redis = await create_pool(settings.redis_settings)
    await redis.enqueue_job("send_whatsapp", phone_encrypted, message)
```

### 4. Error Handling
```python
from fastapi import HTTPException, status

# Use specific HTTP status codes
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Reservation not found"
)

# For validation errors, let Pydantic handle it (422)
# For business logic errors, use 400 or 409
```

### 5. Logging (No PII)
```python
from loguru import logger

# GOOD - No PII
logger.info(f"Call started: call_id={call_id}")
logger.info(f"Reservation created: id={reservation.id}, party_size={reservation.party_size}")

# BAD - Contains PII
logger.info(f"Customer {phone_number} made reservation")  # NEVER DO THIS
```

## Code Generation

### CRUD Endpoints (Auto-generated)
Uses `fastapi-crudrouter` - see `src/api/routes/crud.py`

```python
from fastapi_crudrouter import SQLAlchemyCRUDRouter

reservation_router = SQLAlchemyCRUDRouter(
    schema=ReservationSchema,
    create_schema=ReservationCreate,
    db_model=Reservation,
    db=get_session,
    prefix="reservations",
)
```

### Custom Business Logic (Manual)
Add to repository layer or separate service:

```python
# src/db/repositories/reservations.py
class ReservationRepository:
    async def check_availability(
        self,
        session: AsyncSession,
        business_id: str,
        date: str,
        time: str,
        party_size: int,
    ) -> bool:
        """Check if reservation slot is available."""
        # Business logic from PRD Section 8.5
```

## Testing

```python
# tests/test_api/test_reservations.py
from ward import test
from httpx import AsyncClient

@test("POST /reservations creates valid reservation")
async def _():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/reservations", json={...})
        assert response.status_code == 201
```

## Checklist for New Endpoints

- [ ] Route defined in `src/api/routes/`
- [ ] Router included in `src/main.py`
- [ ] Request/Response schemas in `src/schemas/` (generated or manual)
- [ ] Logging added (no PII)
- [ ] Error handling with proper HTTP status codes
- [ ] Tests in `tests/test_api/`
- [ ] OpenAPI docs verified at `/docs`

## References

- **Latency requirements:** PRD Section 6.1 (P50 < 500ms processing)
- **Reservation rules:** PRD Section 8.5 (configurable business rules)
- **Phone handling:** PRD Section 9.4 (HMAC hash + AES encryption)
- **Consent flow:** PRD Section 15.2 (transcript/WhatsApp consent)
