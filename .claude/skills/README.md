# Vartalaap Claude Skills

Context-rich skills for developing the Vartalaap voice bot platform.

**Before using any skill:** Read `.claude/soul.md` (what this is) and `.claude/roadmap.md` (where it's going).

---

## Available Skills

| Skill | Command | Use When |
|-------|---------|----------|
| **Pipeline** | `/pipeline` | Frame-based pipeline, Silero VAD, streaming LLM→TTS, state machine, interruption handling |
| **Squads** | `/squads` | Agent-as-config, function calling, filler phrases, multi-agent handoffs |
| **Voice** | `/voice` | STT/LLM/TTS services, audio formats, resampling, latency |
| **Backend** | `/backend` | FastAPI routes, dependency injection, middleware, arq tasks |
| **Model** | `/model` | DB models, JSON Schema, Alembic migrations, repositories |
| **Admin** | `/admin` | Streamlit pages, authentication, PII masking, config editor |
| **API** | `/api` | CRUD endpoints, OpenAPI, webhooks, WebSocket |
| **Frontend** | `/frontend` | React 19, TypeScript, Orval codegen, OIDC auth |

---

## Which Skill for Which Work

### Working on the real-time audio path?
→ `/pipeline` (frames, VAD, streaming, state machine)

### Adding a new business or voice bot config?
→ `/squads` (AssistantConfig, provider abstraction)

### Adding a new capability the bot can DO (book, search, etc.)?
→ `/squads` (tool registry, filler phrases, function calling)

### Working on STT/LLM/TTS service internals?
→ `/voice` (Deepgram, Groq, Piper, ElevenLabs, audio formats)

### Building FastAPI routes, background tasks, middleware?
→ `/backend`

### Schema changes, DB models, migrations?
→ `/model`

### Streamlit admin pages?
→ `/admin`

### React/TypeScript frontend?
→ `/frontend`

---

## Skill Detail Summaries

### /pipeline
- Frame-based pipeline architecture (Pipecat-inspired typed frames)
- Silero VAD for interruption detection (replacing energy threshold)
- Streaming LLM-to-TTS: sentence-boundary chunking for 40-60% latency reduction
- State machine: IDLE → LISTENING → THINKING → SPEAKING → INTERRUPTED → FUNCTION_CALLING → TRANSFERRING
- InterruptionFrame propagation pattern
- Connection pooling and per-call setup

### /squads
- AssistantConfig Pydantic model: system_prompt + STT/LLM/TTS configs + tools
- Three-layer provider abstraction (STTConfig, LLMConfig, TTSConfig)
- Tool registry with decorator pattern and filler phrases
- Multi-agent squad definition and context-preserving handoffs
- Language detection for Hindi/English/Hinglish filler selection
- Per-agent endpointing configuration

### /voice
- Deepgram STT: nova-2, language=hi, streaming, utterance_end_ms
- Groq LLM: llama-3.3-70b-versatile, streaming, rate limiter
- Piper TTS: self-hosted, hi_IN-priyamvada-medium, warmup pattern
- ElevenLabs TTS: API-based, higher quality, higher cost
- Edge TTS: feature-flagged fallback
- Audio: 8kHz μ-law ↔ 16kHz PCM ↔ 22.05kHz (Piper output)

### /backend
- FastAPI route patterns and dependency injection
- Background task enqueueing (arq + Redis)
- Error handling with appropriate HTTP status codes
- Loguru structured logging (no PII ever)
- Testing with httpx AsyncClient

### /model
- Schema-first workflow: JSON Schema → Pydantic → SQLModel → Alembic
- `src/schemas/*.py` are generated — NEVER edit, re-run `./scripts/generate.sh`
- Repository pattern in `src/db/repositories/`
- Phone security: HMAC-SHA256 hash + AES-256-GCM encryption
- 90-day auto-purge configured in worker.py

### /admin
- Streamlit page structure and navigation
- bcrypt authentication (single admin user MVP)
- PII masking: `98XXXX1234` format everywhere
- YAML config editor for business settings
- Audit logging for admin actions

### /api
- fastapi-crudrouter auto-generated endpoints
- Plivo webhooks: `/plivo/answer` (returns XML), `/plivo/hangup`
- WebSocket: `/ws/plivo/{call_uuid}` for audio streaming
- OpenAPI export: `python scripts/export_openapi.py`

### /frontend
- React 19 + TypeScript + Vite 7
- Orval codegen from OpenAPI (do not edit `web/src/api/`)
- TanStack Query for server state
- shadcn/ui + Tailwind v4
- react-router v7 (NOT react-router-dom)

---

## Code Generation Workflow

```
schemas/*.json              # Source of truth
    ↓ ./scripts/generate.sh
src/schemas/*.py            # Generated Pydantic (DO NOT EDIT)
    ↓ extend manually
src/db/models.py            # SQLModel tables
    ↓ make migration msg="..."
migrations/versions/*.py    # Alembic migrations
    ↓ python scripts/export_openapi.py
openapi.json                # OpenAPI spec
    ↓ cd web && npm run generate:api
web/src/api/                # Generated TypeScript (DO NOT EDIT)
```

---

## Quick Commands

```bash
# Development
uv run uvicorn src.main:app --reload          # API server
uv run streamlit run admin/app.py             # Admin UI
uv run arq src.worker.WorkerSettings          # Background worker
cd web && npm run dev                         # React frontend

# Voice pipeline testing
uv run python scripts/voice_test.py          # Full pipeline smoke test

# Code generation
./scripts/generate.sh                         # Regenerate Pydantic schemas
python scripts/export_openapi.py             # Re-export OpenAPI spec
cd web && npm run generate:api               # Regenerate TypeScript client

# Database
make migration msg="description"             # Create migration
uv run alembic upgrade head                  # Apply migrations
uv run alembic current                       # Check migration status

# Quality
uv run ruff check .                          # Lint Python
uv run mypy src/                             # Type check Python
cd web && npm run typecheck                  # Type check TypeScript
uv run ward                                  # Run tests
```
