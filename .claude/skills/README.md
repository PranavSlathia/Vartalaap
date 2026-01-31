# Vartalaap Claude Skills

Context-rich skills for developing the Vartalaap voice bot platform.

## Available Skills

| Skill | Command | Use When |
|-------|---------|----------|
| **Backend** | `/backend` | Creating FastAPI routes, services, middleware |
| **Model** | `/model` | Database models, JSON Schema, migrations |
| **Admin** | `/admin` | Streamlit admin pages, UI components |
| **Voice** | `/voice` | Voice pipeline (STT, LLM, TTS, telephony) |
| **API** | `/api` | CRUD endpoints, OpenAPI generation |

## Skill Summaries

### /backend
- FastAPI route patterns
- Dependency injection
- Background task enqueueing (arq)
- Error handling with HTTP status codes
- Logging (no PII)
- Testing with httpx

### /model
- Schema-first workflow (JSON Schema → Pydantic → SQLModel)
- `datamodel-code-generator` usage
- Alembic migrations
- Repository pattern
- Phone number handling (HMAC hash + AES encryption)

### /admin
- Streamlit page structure
- Authentication with bcrypt
- PII masking (`98XXXX1234` format)
- Metric cards with streamlit-extras
- Config editor with YAML
- Audit logging

### /voice
- Voice pipeline architecture
- Deepgram STT (streaming, Hindi support)
- Groq LLM (streaming, llama-3.1-70b)
- Piper TTS (primary, self-hosted)
- Edge TTS (fallback, feature-flagged)
- Audio resampling (8kHz ↔ 16kHz ↔ 22050Hz)
- Barge-in handling (300ms threshold)
- Language detection

### /api
- fastapi-crudrouter setup
- Auto-generated CRUD endpoints
- Custom business logic endpoints
- Plivo webhooks
- WebSocket audio streaming
- Health checks
- OpenAPI documentation

## Code Generation

All skills reference the code generation workflow:

```
schemas/*.json              # 1. JSON Schema (source of truth)
    ↓ datamodel-codegen
src/schemas/*.py            # 2. Generated Pydantic (DO NOT EDIT)
    ↓ extend
src/db/models.py            # 3. SQLModel tables
    ↓ alembic --autogenerate
migrations/versions/*.py    # 4. Database migrations
    ↓ include in app
src/api/routes/crud.py      # 5. CRUD endpoints (fastapi-crudrouter)
```

## Reference Documents

- **Tech Stack:** `docs/TECH_STACK.md` (v1.2)
- **PRD:** `docs/PRD.md` (v1.2)

## Quick Commands

```bash
# Generate Pydantic from JSON Schema
./scripts/generate.sh

# Create Alembic migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Run API server (dev)
uv run uvicorn src.main:app --reload

# Run Streamlit admin (dev)
uv run streamlit run admin/app.py
```
