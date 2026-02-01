# Tech Stack Selection
# Vartalaap - Voice Bot Platform for Local Businesses

**Product Name:** Vartalaap (वार्तालाप - "conversation" in Hindi)

**Version**: 1.2
**Date**: February 1, 2026
**Python Version**: 3.12.x

---

## Quick Reference

```
Python 3.12 + FastAPI + SQLModel + Piper/EdgeTTS(fallback) + Deepgram + Groq + Plivo
Docker + Caddy + supervisord + Redis (arq for tasks+cron) + SQLite
Codegen: datamodel-codegen (schemas) + fastapi-crudrouter (CRUD) + alembic (migrations)
```

---

## 1. Core Runtime

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Language** | Python | 3.12.x | Latest stable, performance improvements, better typing |
| **Package Manager** | uv | 0.5.x | 10-100x faster than pip, modern, Rust-based |
| **Virtual Env** | uv (built-in) | - | uv manages venvs natively |

### Installation
```bash
# Install uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init voice-bot
cd voice-bot
uv python install 3.12
uv venv --python 3.12
```

---

## 2. Web Framework & API

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Framework** | FastAPI | 0.115.x | Async-native, auto OpenAPI docs, Pydantic integration |
| **ASGI Server** | uvicorn | 0.34.x | Fast, production-ready, FastAPI recommended |
| **WebSocket** | websockets | 14.x | Production-grade, reconnection handling, Plivo streams |

### Dependencies
```toml
# pyproject.toml
[project]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "websockets>=14.0",
]
```

---

## 3. Database Layer

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Database** | SQLite | 3.x (stdlib) | Simple, no server, sufficient for MVP |
| **ORM** | SQLModel | 0.0.22+ | Pydantic + SQLAlchemy, type-safe, FastAPI native |
| **Migrations** | Alembic | 1.14.x | SQLAlchemy ecosystem, version control for schema |
| **Async Driver** | aiosqlite | 0.20.x | Async SQLite access for non-blocking queries |

### Dependencies
```toml
[project]
dependencies = [
    "sqlmodel>=0.0.22",
    "alembic>=1.14.0",
    "aiosqlite>=0.20.0",
]
```

### Future Migration Path
```
MVP: SQLite (single file, zero config)
 ↓
Scale: PostgreSQL + asyncpg (when concurrent calls needed)
```

---

## 4. Voice Pipeline

### 4.1 Speech-to-Text (STT)

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Provider** | Deepgram | API v1 | Free tier 100hrs, streaming, good Hindi |
| **SDK** | deepgram-sdk | 3.x | Official Python SDK |

```toml
[project]
dependencies = [
    "deepgram-sdk>=3.7.0",
]
```

### 4.2 Text-to-Speech (TTS)

**Primary: Piper** (self-hosted, fast)
| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Engine** | Piper | 2024.x | CPU-friendly, fast inference, Hindi voices |
| **Python Wrapper** | piper-tts | 1.2.x | Official Python bindings |

**Fallback: Edge TTS** (cloud, excellent quality) ⚠️ **FEATURE-FLAGGED**
| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Engine** | Edge TTS | API | Microsoft's free TTS, excellent Hindi |
| **Python Client** | edge-tts | 6.x | Async, easy to use |

**MP3 Decoding (Edge TTS output)**  
Edge TTS streams MP3 audio. Decoding requires one of:
- **pydub + ffmpeg** (recommended, most reliable)
- **miniaudio** (pure Python, bundled decoders)
- **soundfile** with MP3-enabled libsndfile (system-dependent)

> ⚠️ **Warning:** Edge TTS uses Microsoft's unofficial/consumer endpoint (same as
> Edge browser's "Read Aloud" feature). It can throttle, rate-limit, or change without
> notice. **Treat as feature-flagged fallback only.** For production reliability:
> - Use Piper as primary (self-hosted, no external dependency)
> - Edge TTS as optional fallback (enabled via `EDGE_TTS_ENABLED=true`)
> - Consider paid TTS (Azure Speech, Google Cloud TTS) for SLA guarantees

```toml
[project]
dependencies = [
    "piper-tts>=1.2.0",
    "edge-tts>=6.1.0",  # Feature-flagged fallback
    "pydub>=0.25.1",    # MP3 decode (requires ffmpeg)
    "miniaudio>=1.59",  # MP3 decode (pure Python)
]
```

### 4.3 Language Model (LLM)

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Provider** | Groq | API | Free tier, fastest inference |
| **Model** | llama-3.3-70b-versatile | - | Best quality on free tier |
| **SDK** | groq | 0.13.x | Official Python SDK |

```toml
[project]
dependencies = [
    "groq>=0.13.0",
]
```

### 4.4 Telephony

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Provider** | Plivo | API v1 | Cheaper than Twilio, good India support |
| **SDK** | plivo | 4.x | Official Python SDK |

```toml
[project]
dependencies = [
    "plivo>=4.55.0",
]
```

---

## 5. Audio Processing

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **File I/O** | soundfile | 0.12.x | Read/write WAV, FLAC, etc. |
| **Resampling** | soxr | 0.5.x | High-quality resampling (libsoxr bindings) |
| **NumPy** | numpy | 2.x | Audio data manipulation |
| **Recording/Playback** | sounddevice | 0.5.x | **Dev-only** - local mic testing |

```toml
[project]
dependencies = [
    "soundfile>=0.12.0",
    "soxr>=0.5.0",
    "numpy>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "sounddevice>=0.5.0",  # Local mic testing only
]
```

> **Note:** `sounddevice` requires PortAudio and a physical audio device. On headless
> VPS/Docker it often fails and isn't needed—telephony audio streams via WebSocket,
> not local hardware. Keep it dev-only for local testing with microphone.

### Audio Format Notes
```
Plivo incoming:  8kHz/16kHz, mono, μ-law/PCM
Deepgram input:  16kHz recommended
Piper output:    22050Hz typically
Plivo outgoing:  Resample to match incoming
```

---

## 6. Background Tasks & Scheduling

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Task Queue** | arq | 0.26.x | Async-native, Redis-backed, lightweight |
| **Redis Client** | redis[hiredis] | 5.x | Fast, async support, hiredis for speed |

```toml
[project]
dependencies = [
    "arq>=0.26.0",
    "redis[hiredis]>=5.0.0",
]
```

### Scheduling Strategy

**arq handles both tasks AND cron jobs** - no need for APScheduler.

```python
# src/worker.py
from arq import cron

class WorkerSettings:
    functions = [send_whatsapp_followup, process_transcript]

    # Built-in cron scheduling (runs in arq worker)
    cron_jobs = [
        # Daily 3 AM: purge records older than 90 days
        cron(purge_old_records, hour=3, minute=0),
        # Every hour: retry failed WhatsApp sends
        cron(retry_failed_whatsapp, minute=0),
    ]
```

> **Why not APScheduler?** Running both arq + APScheduler risks double-execution
> of scheduled jobs in multi-instance deployments. arq's built-in `cron_jobs`
> uses Redis for coordination.
>
> ⚠️ **Cron Job Concurrency Warning:** arq does NOT guarantee "exactly once"
> execution across multiple workers. If you run multiple worker instances, each
> may independently trigger the same cron job. For MVP with a single worker, this
> is fine. For multi-worker deployments, either:
> - Run a **dedicated cron worker** (single instance with `cron_jobs`, others without)
> - Implement explicit distributed locking (Redis `SET NX EX`) in job functions
> - Use a dedicated scheduler service (not arq) that enqueues to arq workers

### Redis Setup (Docker)
```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
```

### 6.1 Transcript Analysis Agent System

**Purpose:** Internal QA tooling for reviewing call transcripts and identifying improvement opportunities.

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Agent Framework** | CrewAI | 0.86.x | Production-ready, Groq-native, structured outputs |
| **LLM Integration** | langchain-groq | 0.2.x | Connect CrewAI to Groq models |
| **Tools** | crewai-tools | 0.17.x | Built-in agent capabilities |

```toml
[project]
dependencies = [
    "crewai>=0.86.0,<1",
    "crewai-tools>=0.17.0,<1",
    "langchain-groq>=0.2.0,<1",
]
```

#### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 Transcript Review Crew                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ QA Reviewer  │  │  Classifier  │  │   Improver   │  │
│  │    Agent     │→ │    Agent     │→ │    Agent     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  Agent Roles:                                           │
│  • QA Reviewer: Rate quality (1-5), identify issues     │
│  • Classifier: Categorize by root cause                 │
│  • Improver: Generate actionable suggestions            │
│                                                         │
│  Issue Categories:                                      │
│  • knowledge_gap    - Missing knowledge base info       │
│  • prompt_weakness  - LLM prompt needs improvement      │
│  • ux_issue         - User experience friction          │
│  • stt_error        - Speech-to-text misrecognition     │
│  • tts_issue        - Text-to-speech quality            │
│  • config_error     - Business configuration problem    │
└─────────────────────────────────────────────────────────┘
```

#### Data Models

```python
# src/db/models.py

class TranscriptReview(SQLModel, table=True):
    """QA review of a call transcript by AI agents."""
    id: str = Field(primary_key=True)
    call_log_id: str = Field(foreign_key="call_logs.id", index=True)
    business_id: str = Field(index=True)
    quality_score: int = Field(ge=1, le=5)  # Internal rating
    issues_json: str | None  # JSON array of issues
    suggestions_json: str | None  # JSON array of suggestions
    has_unanswered_query: bool = False
    has_knowledge_gap: bool = False
    has_prompt_weakness: bool = False
    has_ux_issue: bool = False
    agent_model: str = "llama-3.3-70b-versatile"
    review_latency_ms: float | None
    reviewed_at: datetime
    reviewed_by: str = "agent"  # or admin username

class ImprovementSuggestion(SQLModel, table=True):
    """Actionable suggestions from reviews."""
    id: str = Field(primary_key=True)
    review_id: str = Field(foreign_key="transcript_reviews.id")
    business_id: str = Field(index=True)
    category: IssueCategory
    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)
    priority: int = Field(ge=1, le=5)
    status: SuggestionStatus = "pending"  # pending/implemented/rejected
```

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/reviews` | GET | List reviews for a business |
| `/api/reviews/stats` | GET | Review statistics and trends |
| `/api/reviews/{id}` | GET | Get specific review |
| `/api/reviews/analyze` | POST | Trigger analysis for a call |
| `/api/reviews/suggestions` | GET | List improvement suggestions |
| `/api/reviews/suggestions/{id}` | PATCH | Update suggestion status |

#### Worker Integration

```python
# src/worker.py

async def analyze_transcript_quality(ctx, call_id: str) -> None:
    """Background job to analyze call transcript with AI agents."""
    from src.services.analysis import TranscriptAnalysisCrew

    async with get_session_context() as session:
        call_log = await session.get(CallLog, call_id)
        if not call_log or not call_log.transcript:
            return

        crew = TranscriptAnalysisCrew()
        result = await crew.analyze_transcript(call_log.transcript)

        # Store review and suggestions...

class WorkerSettings:
    functions = [
        send_whatsapp_followup,
        process_transcript,
        generate_call_summary,
        analyze_transcript_quality,  # NEW
    ]
```

#### Usage

```bash
# Queue analysis for a specific call
curl -X POST "http://localhost:8000/api/reviews/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"call_log_id": "abc-123"}'

# List pending suggestions
curl "http://localhost:8000/api/reviews/suggestions?business_id=himalayan_kitchen&status=pending"

# Mark suggestion as implemented
curl -X PATCH "http://localhost:8000/api/reviews/suggestions/xyz-456" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"status": "implemented"}'
```

> **Note:** This is internal QA tooling for admins, not real-time or caller-facing.
> Analysis runs asynchronously via arq worker to avoid blocking API requests.

---

## 7. Configuration & Environment

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Settings** | pydantic-settings | 2.x | Type-safe, env var support, FastAPI native |
| **YAML Parsing** | PyYAML | 6.x | Business config files |
| **Env Files** | Docker env_file | - | Container-level, parity across envs |

```toml
[project]
dependencies = [
    "pydantic-settings>=2.5.0",
    "pyyaml>=6.0.0",
]
```

### Settings Structure
```python
# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    groq_api_key: str
    deepgram_api_key: str
    plivo_auth_id: str
    plivo_auth_token: str

    # Security
    phone_encryption_key: str  # 64 hex chars
    phone_hash_pepper: str     # 32+ bytes
    admin_password_hash: str

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/vartalaap.db"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # TTS
    piper_model_path: str | None = None
    piper_voice: str = "hi_IN-female-medium"
    edge_tts_voice: str = "hi-IN-SwaraNeural"
    tts_target_sample_rate: int = 8000

    # Feature Flags
    edge_tts_enabled: bool = False  # Enable Edge TTS fallback (unofficial API)
```

---

## 8. Security & Cryptography

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Crypto** | cryptography | 44.x | AES-256-GCM, well-audited, industry standard |
| **Password Hashing** | bcrypt | 4.x | Admin password hashing |
| **Secrets** | secrets (stdlib) | - | Secure random generation |

```toml
[project]
dependencies = [
    "cryptography>=44.0.0",
    "bcrypt>=4.2.0",
]
```

---

## 9. HTTP Client

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **HTTP Client** | aiohttp | 3.11.x | Mature async, WebSocket support, production-ready |
| **Connection Pooling** | Built-in | - | aiohttp handles this |

```toml
[project]
dependencies = [
    "aiohttp>=3.11.0",
]
```

---

## 10. Admin Interface

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Framework** | Streamlit | 1.41.x | Quick Python UI, good for admin panels |
| **Extras** | streamlit-extras | 0.4.x | Enhanced components (metrics, cards) |
| **Auth** | streamlit-authenticator | 0.3.x | Session-based auth |

```toml
[project]
dependencies = [
    "streamlit>=1.41.0",
    "streamlit-extras>=0.4.0",
    "streamlit-authenticator>=0.3.0",
]
```

---

## 11. Development Tools

### 11.1 Code Quality

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Linter + Formatter** | Ruff | 0.8.x | All-in-one, extremely fast |
| **Type Checker** | mypy | 1.14.x | Static type analysis |
| **Pre-commit** | pre-commit | 4.x | Git hooks automation |

```toml
[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.14.0",
    "pre-commit>=4.0.0",
]
```

### Ruff Config
```toml
# pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = false
warn_return_any = true
warn_unused_ignores = true
```

### 11.2 Testing

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Framework** | ward | 0.68.x | Modern, descriptive tests |
| **Async Testing** | pytest-asyncio | 0.24.x | ward uses pytest plugins |
| **Coverage** | coverage | 7.x | Code coverage reporting |
| **Mocking** | unittest.mock | stdlib | Built-in mocking |

```toml
[project.optional-dependencies]
dev = [
    "ward>=0.67.0",
    "pytest-asyncio>=0.24.0",
    "coverage>=7.0.0",
]
```

### 11.3 Logging

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Logger** | loguru | 0.7.x | Simple, colorful, structured |

```toml
[project]
dependencies = [
    "loguru>=0.7.0",
]
```

### Loguru Config
```python
# src/logging_config.py
from loguru import logger
import sys

logger.remove()  # Remove default handler

# Console (dev)
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG",
    colorize=True,
)

# File (prod)
logger.add(
    "logs/vartalaap_{time:YYYY-MM-DD}.log",
    rotation="100 MB",
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
    level="INFO",
)
```

---

## 12. Infrastructure

### 12.1 Containerization

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Container** | Docker | 27.x | Containerization |
| **Orchestration** | docker-compose | 2.x | Multi-container setup |

### Docker Setup
```dockerfile
# Dockerfile
# Pin Python and uv versions for reproducibility
FROM python:3.12.8-slim AS base

WORKDIR /app

# Install system deps for audio (no PortAudio needed - telephony uses WebSocket)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv - pin specific version for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (--frozen ensures uv.lock is used exactly)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/
COPY config/ ./config/

# Run
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **Reproducibility Notes:**
> - Python image pinned to `3.12.8-slim` (update quarterly)
> - uv pinned to `0.5.14` (update when needed, test first)
> - `uv.lock` committed to git ensures exact dependency versions
> - `--frozen` flag prevents uv from updating the lock file

### docker-compose.yml
```yaml
version: "3.9"

services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config
    depends_on:
      - redis
    restart: unless-stopped

  admin:
    build:
      context: .
      dockerfile: Dockerfile.admin
    ports:
      - "8501:8501"
    env_file:
      - .env.production
    volumes:
      - ./data:/app/data
    depends_on:
      - api
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

  worker:
    build: .
    command: uv run arq src.worker.WorkerSettings
    env_file:
      - .env.production
    depends_on:
      - redis
    restart: unless-stopped

volumes:
  redis_data:
```

### 12.2 Reverse Proxy

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Proxy** | Caddy | 2.x | Auto HTTPS, simple config |

### Caddyfile
```caddyfile
# Main API domain
vartalaap.yourdomain.com {
    # API endpoints
    handle /api/* {
        reverse_proxy api:8000
    }

    # WebSocket for Plivo audio streams
    handle /ws/* {
        reverse_proxy api:8000
    }

    # Default - API docs
    handle {
        reverse_proxy api:8000
    }
}

# Admin panel on subdomain (avoids Streamlit static asset/WebSocket path issues)
admin.vartalaap.yourdomain.com {
    reverse_proxy admin:8501
}
```

> **Note:** Streamlit requires its own subdomain because it serves static assets
> and WebSocket connections at root-relative paths (`/_stcore/*`, `/static/*`).
> Proxying under `/admin/*` breaks these unless you configure `server.baseUrlPath`,
> which has known issues. A subdomain is the cleanest solution.

### 12.3 Process Manager

| Tool | Choice | Version | Purpose |
|------|--------|---------|---------|
| **Process Manager** | supervisord | 4.x | Manage processes inside containers |

```ini
# supervisord.conf (if not using docker-compose)
[supervisord]
nodaemon=true

[program:api]
command=uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
autostart=true
autorestart=true
stdout_logfile=/var/log/api.log

[program:worker]
command=uv run arq src.worker.WorkerSettings
autostart=true
autorestart=true
stdout_logfile=/var/log/worker.log
```

---

## 13. Complete Dependency List

### pyproject.toml
```toml
[project]
name = "vartalaap"
version = "0.1.0"
description = "Voice bot platform for local businesses"
requires-python = ">=3.12,<3.13"
dependencies = [
    # Web Framework
    "fastapi>=0.115.0,<0.116",
    "uvicorn[standard]>=0.34.0,<0.35",
    "websockets>=14.0,<15",

    # Database
    "sqlmodel>=0.0.22,<0.1",
    "alembic>=1.14.0,<2",
    "aiosqlite>=0.20.0,<0.21",

    # Voice Pipeline
    "deepgram-sdk>=3.7.0,<4",
    "piper-tts>=1.2.0,<2",
    "edge-tts>=6.1.0,<7",  # Feature-flagged fallback
    "groq>=0.13.0,<1",
    "plivo>=4.55.0,<5",

    # Audio Processing
    "soundfile>=0.12.0,<0.13",
    "soxr>=0.5.0,<0.6",
    "numpy>=2.0.0,<3",

    # Background Tasks (arq handles both tasks + cron)
    "arq>=0.26.0,<0.27",
    "redis[hiredis]>=5.0.0,<6",

    # Config
    "pydantic-settings>=2.5.0,<3",
    "pyyaml>=6.0.0,<7",

    # Security
    "cryptography>=44.0.0,<45",
    "bcrypt>=4.2.0,<5",

    # HTTP
    "aiohttp>=3.11.0,<4",

    # Logging
    "loguru>=0.7.0,<0.8",

    # CRUD Generation (runtime - used in API routes)
    "fastapi-crudrouter>=0.8.0,<0.9",

    # Agent System (Transcript Analysis)
    "crewai>=0.86.0,<1",
    "crewai-tools>=0.17.0,<1",
    "langchain-groq>=0.2.0,<1",
]

[project.optional-dependencies]
admin = [
    "streamlit>=1.41.0,<2",
    "streamlit-extras>=0.4.0,<0.5",
    "streamlit-authenticator>=0.3.0,<0.4",
]
dev = [
    # Code Quality
    "ruff>=0.8.0",
    "mypy>=1.14.0",
    "pre-commit>=4.0.0",
    # Testing
    "ward>=0.67.0",
    "pytest-asyncio>=0.24.0",
    "coverage>=7.0.0",
    # Code Generation (dev-only tools)
    "datamodel-code-generator>=0.26.0,<0.27",  # Pydantic from JSON Schema
    "eralchemy2>=1.4.0,<2",                     # ER diagrams from SQLModel
    # Local Development
    "sounddevice>=0.5.0,<0.6",                 # Local mic testing only
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_ignores = true
```

---

## 14. Environment Variables

### .env.example
```bash
# API Keys
GROQ_API_KEY=gsk_xxxx
DEEPGRAM_API_KEY=xxxx
PLIVO_AUTH_ID=xxxx
PLIVO_AUTH_TOKEN=xxxx

# Security (generate with: openssl rand -hex 32)
PHONE_ENCRYPTION_KEY=<64 hex chars>
PHONE_HASH_PEPPER=<64 hex chars>
ADMIN_PASSWORD_HASH=<bcrypt hash>
SESSION_SECRET=<32 random chars>

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/vartalaap.db

# Redis
REDIS_URL=redis://localhost:6379

# App
DEBUG=false
LOG_LEVEL=INFO
ENVIRONMENT=production

# WhatsApp Webhook (optional)
WHATSAPP_WEBHOOK_URL=
WHATSAPP_WEBHOOK_TOKEN=

# TTS
PIPER_MODEL_PATH=
PIPER_VOICE=hi_IN-female-medium
EDGE_TTS_VOICE=hi-IN-SwaraNeural
TTS_TARGET_SAMPLE_RATE=8000

# Feature Flags
EDGE_TTS_ENABLED=false  # Enable Edge TTS as fallback (unofficial API, may be unreliable)
```

---

## 15. Project Structure

```
vartalaap/
├── .env.example
├── .env.development
├── .env.production
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── Dockerfile.admin
├── docker-compose.yml
├── Caddyfile
├── README.md
│
├── schemas/                    # JSON Schema (source of truth for codegen)
│   ├── call_log.json
│   ├── reservation.json
│   ├── caller_preferences.json
│   ├── whatsapp_followup.json
│   └── conversation_turn.json
│
├── config/
│   ├── business/
│   │   └── himalayan_kitchen.yaml
│   └── prompts/
│       └── restaurant_bot.txt
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Pydantic settings
│   ├── logging_config.py       # Loguru setup
│   │
│   ├── schemas/                # Generated Pydantic models (DO NOT EDIT)
│   │   ├── __init__.py
│   │   ├── _generated.py       # Auto-generated marker
│   │   ├── call_log.py
│   │   ├── reservation.py
│   │   ├── caller_preferences.py
│   │   └── whatsapp_followup.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── plivo_webhook.py
│   │   │   └── crud.py         # Auto-generated CRUD (fastapi-crudrouter)
│   │   └── websocket/
│   │       ├── __init__.py
│   │       └── audio_stream.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pipeline.py         # Main voice pipeline (MANUAL)
│   │   ├── session.py          # Call session manager (MANUAL)
│   │   └── context.py          # Conversation context (MANUAL)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stt/
│   │   │   ├── __init__.py
│   │   │   └── deepgram.py     # (MANUAL)
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── groq.py         # (MANUAL)
│   │   ├── tts/
│   │   │   ├── __init__.py
│   │   │   ├── piper.py        # (MANUAL)
│   │   │   └── edge.py         # (MANUAL)
│   │   └── telephony/
│   │       ├── __init__.py
│   │       └── plivo.py        # (MANUAL)
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLModel models (inherits generated schemas)
│   │   ├── session.py          # DB session
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── calls.py
│   │       └── reservations.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── crypto.py           # AES-256-GCM, HMAC (MANUAL)
│   │   └── auth.py             # Admin auth
│   │
│   └── worker.py               # arq worker settings
│
├── admin/
│   ├── __init__.py
│   ├── app.py                  # Streamlit entry
│   ├── pages/
│   │   ├── 1_dashboard.py
│   │   ├── 2_reservations.py
│   │   ├── 3_call_logs.py
│   │   └── 4_config.py
│   └── components/
│       └── auth.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_pipeline.py
│   ├── test_services/
│   └── test_api/
│
├── scripts/
│   ├── init_db.py
│   ├── generate_keys.py
│   ├── generate.sh             # Run all code generation
│   └── test_call.py
│
├── migrations/                 # Alembic (auto-generated)
│   ├── env.py
│   ├── versions/
│   └── alembic.ini
│
├── data/                       # .gitignored
│   └── vartalaap.db
│
└── logs/                       # .gitignored
    └── vartalaap_*.log
```

---

## 16. Version Pinning Strategy

| Category | Strategy | Example |
|----------|----------|---------|
| **Core (FastAPI, SQLModel)** | Pin minor version | `>=0.115.0,<0.116` |
| **SDKs (Groq, Deepgram, Plivo)** | Pin major version | `>=3.7.0,<4` |
| **Stable libs (numpy, aiohttp)** | Pin major version | `>=2.0.0,<3` |
| **Dev tools (ruff, mypy)** | Floor only (less critical) | `>=0.8.0` |
| **Docker base images** | Pin exact version | `python:3.12.8-slim` |
| **Docker build tools** | Pin exact version | `uv:0.5.14` |

### Reproducibility Checklist

1. **`uv.lock`** - Auto-generated, **commit to git**. Contains exact resolved versions.
2. **`--frozen` flag** - Always use in CI/Docker to prevent lock drift.
3. **Quarterly updates** - Review and bump pinned versions every 3 months.
4. **Python constraint** - `requires-python = ">=3.12,<3.13"` prevents 3.13 surprises.

```bash
# Update dependencies (dev machine only)
uv lock --upgrade

# Verify reproducibility
uv sync --frozen  # Fails if lock is outdated
```

---

## 17. Upgrade Path

### Month 1 (MVP)
- SQLite single file
- Redis for task queue
- Single VPS deployment

### Month 3 (Scale)
- PostgreSQL for concurrent writes
- Connection pooling (asyncpg)
- Consider managed Redis (Upstash)

### Month 6+ (Multi-tenant)
- Database per tenant OR row-level security
- Kubernetes consideration
- CDN for static assets

---

## 18. Code Generation

### 18.1 Philosophy

**Generate boilerplate, write business logic manually.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    GENERATE AUTOMATICALLY                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Pydantic schemas       → datamodel-codegen from JSON Schema  │
│  2. CRUD endpoints         → fastapi-crudrouter from SQLModel    │
│  3. DB migrations          → alembic --autogenerate              │
│  4. OpenAPI spec           → FastAPI built-in                    │
│  5. ER diagrams            → eralchemy2 from SQLModel            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    WRITE MANUALLY                                │
├─────────────────────────────────────────────────────────────────┤
│  1. Voice pipeline logic   (STT → LLM → TTS orchestration)       │
│  2. WebSocket handlers     (Plivo audio streaming)               │
│  3. Business rules         (reservation validation, capacity)    │
│  4. LLM prompts            (conversation flows)                  │
│  5. Language detection     (Hindi/English/Hinglish switching)    │
│  6. Security functions     (AES-256-GCM, HMAC-SHA256)            │
│  7. Background tasks       (WhatsApp sending, purge jobs)        │
└─────────────────────────────────────────────────────────────────┘
```

### 18.2 Code Generation Tools

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| **datamodel-code-generator** | Pydantic models | JSON Schema | `src/schemas/*.py` |
| **fastapi-crudrouter** | REST CRUD endpoints | SQLModel models | API routes |
| **alembic** | Database migrations | SQLModel changes | `migrations/versions/*.py` |
| **eralchemy2** | ER diagrams | SQLModel models | PNG/SVG diagrams |

### 18.3 Schema-First Workflow

JSON Schema is the **source of truth** for data models:

```
schemas/                      # Step 1: Define JSON Schema (manual)
├── reservation.json
├── call_log.json
└── ...
    │
    ▼ datamodel-codegen       # Step 2: Generate Pydantic (automated)
    │
src/schemas/                  # Generated Pydantic models
├── reservation.py           # (DO NOT EDIT - regenerate instead)
├── call_log.py
└── ...
    │
    ▼ inherit + extend        # Step 3: Create SQLModel (manual)
    │
src/db/models.py             # SQLModel with table=True
    │
    ▼ alembic --autogenerate  # Step 4: Generate migrations (automated)
    │
migrations/versions/         # Migration files
```

### 18.4 JSON Schema Examples

**`schemas/reservation.json`:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Reservation",
  "description": "Restaurant table reservation",
  "type": "object",
  "required": ["business_id", "party_size", "reservation_date", "reservation_time"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique identifier (UUID as string for SQLite compatibility)"
    },
    "business_id": {
      "type": "string",
      "description": "Business this reservation belongs to"
    },
    "call_log_id": {
      "type": "string",
      "description": "Associated call log (UUID as string)"
    },
    "customer_name": {
      "type": "string",
      "maxLength": 100
    },
    "customer_phone_encrypted": {
      "type": "string",
      "description": "AES-256-GCM encrypted phone for WhatsApp"
    },
    "party_size": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20
    },
    "reservation_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "reservation_time": {
      "type": "string",
      "pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$",
      "description": "HH:MM format"
    },
    "status": {
      "type": "string",
      "enum": ["confirmed", "cancelled", "completed", "no_show"],
      "default": "confirmed"
    },
    "whatsapp_sent": {
      "type": "boolean",
      "default": false
    },
    "whatsapp_consent": {
      "type": "boolean",
      "default": false
    },
    "notes": {
      "type": "string"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### 18.5 Generated Pydantic Model

Running `datamodel-codegen` produces:

```python
# src/schemas/reservation.py
# AUTO-GENERATED from schemas/reservation.json - DO NOT EDIT
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field

class ReservationStatus(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"

class Reservation(BaseModel):
    """Restaurant table reservation"""
    id: str | None = None
    business_id: str
    call_log_id: str | None = None
    customer_name: Annotated[str | None, Field(max_length=100)] = None
    customer_phone_encrypted: str | None = None
    party_size: Annotated[int, Field(ge=1, le=20)]
    reservation_date: date
    reservation_time: Annotated[str, Field(pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")]
    status: ReservationStatus = ReservationStatus.confirmed
    whatsapp_sent: bool = False
    whatsapp_consent: bool = False
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

### 18.6 SQLModel Integration

Extend generated Pydantic to create SQLModel:

```python
# src/db/models.py
from sqlmodel import SQLModel, Field
from src.schemas.reservation import Reservation as ReservationSchema, ReservationStatus
from uuid import uuid4
from datetime import datetime

class Reservation(ReservationSchema, SQLModel, table=True):
    """SQLModel table extending generated Pydantic schema"""
    __tablename__ = "reservations"

    # Override id to be primary key with default
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    # Add SQLite-specific defaults
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Add indexes (not in JSON Schema)
    class Config:
        # Index on business_id + date + time for availability queries
        pass
```

### 18.7 CRUD Router Setup

Auto-generate REST endpoints with `fastapi-crudrouter`:

```python
# src/api/routes/crud.py
from fastapi import Depends
from fastapi_crudrouter import SQLAlchemyCRUDRouter
from sqlmodel import Session
from src.db.models import Reservation
from src.schemas.reservation import Reservation as ReservationSchema
from src.db.session import get_session

# Create schema variants
class ReservationCreate(ReservationSchema):
    id: None = None  # Exclude id on create
    created_at: None = None
    updated_at: None = None

class ReservationUpdate(ReservationSchema):
    party_size: int | None = None  # All fields optional for PATCH
    reservation_date: str | None = None
    reservation_time: str | None = None

# Auto-generate CRUD endpoints
reservation_router = SQLAlchemyCRUDRouter(
    schema=ReservationSchema,
    create_schema=ReservationCreate,
    update_schema=ReservationUpdate,
    db_model=Reservation,
    db=get_session,
    prefix="reservations",
    tags=["Reservations"],
    # Customize which endpoints to generate
    delete_all_route=False,  # Don't allow DELETE /reservations
)

# Generated endpoints:
# GET    /reservations          - List all (paginated)
# GET    /reservations/{id}     - Get one
# POST   /reservations          - Create
# PUT    /reservations/{id}     - Full update
# PATCH  /reservations/{id}     - Partial update (if update_schema provided)
# DELETE /reservations/{id}     - Delete one
```

### 18.8 Generation Script

**`scripts/generate.sh`:**
```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Vartalaap Code Generation ==="
echo ""

# Step 1: Generate Pydantic schemas from JSON Schema
echo "[1/3] Generating Pydantic schemas from JSON Schema..."
mkdir -p src/schemas

for schema in schemas/*.json; do
    if [ -f "$schema" ]; then
        name=$(basename "$schema" .json)
        echo "  → $name"
        uv run datamodel-codegen \
            --input "$schema" \
            --output "src/schemas/${name}.py" \
            --output-model-type pydantic_v2.BaseModel \
            --use-annotated \
            --field-constraints \
            --use-default \
            --target-python-version 3.12 \
            --disable-timestamp
    fi
done

# Add marker file
echo "# AUTO-GENERATED - DO NOT EDIT" > src/schemas/_generated.py
echo "# Regenerate with: ./scripts/generate.sh" >> src/schemas/_generated.py

# Step 2: Check for database schema changes (don't auto-create migration)
echo ""
echo "[2/3] Checking for database schema changes..."
if [ -d "migrations/versions" ]; then
    # Check if there are pending changes without creating a migration
    CHANGES=$(uv run alembic check 2>&1) || true
    if echo "$CHANGES" | grep -q "FAILED"; then
        echo "  → Schema changes detected. Run: make migration msg=\"description\""
        echo "  → (Manual step to ensure meaningful commit messages)"
    else
        echo "  → No schema changes detected"
    fi
else
    echo "  → Alembic not initialized. Run: uv run alembic init migrations"
fi

# Step 3: Generate ER diagram (optional)
echo ""
echo "[3/3] Generating ER diagram..."
if command -v eralchemy2 &> /dev/null; then
    uv run python -c "
from eralchemy2 import render_er
from src.db.models import SQLModel
render_er(SQLModel.metadata, 'docs/er_diagram.png')
print('  → docs/er_diagram.png')
" 2>/dev/null || echo "  → Skipped (models not ready)"
else
    echo "  → Skipped (eralchemy2 not installed)"
fi

echo ""
echo "=== Generation complete ==="
```

### 18.9 Makefile Integration

```makefile
# Makefile
.PHONY: generate migrate

# Run all code generation
generate:
	@./scripts/generate.sh

# Generate and apply migrations
migrate:
	@uv run alembic upgrade head

# Generate new migration after model changes
migration:
	@uv run alembic revision --autogenerate -m "$(msg)"

# Regenerate schemas only
schemas:
	@./scripts/generate.sh | grep -A 100 "Generating Pydantic"
```

### 18.10 When to Regenerate

| Trigger | Action |
|---------|--------|
| Changed `schemas/*.json` | Run `make generate` |
| Changed `src/db/models.py` | Run `make migration msg="description"` |
| Added new entity | Create JSON Schema → Run `make generate` → Extend in models.py |
| PR review | `make generate` should show no diff (schemas committed) |

### 18.11 CI Integration

```yaml
# .github/workflows/ci.yml (relevant section)
jobs:
  codegen-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install dependencies
        run: uv sync --frozen --all-extras
      - name: Regenerate code
        run: ./scripts/generate.sh
      - name: Check for uncommitted schema changes
        run: |
          if [ -n "$(git status --porcelain src/schemas/)" ]; then
            echo "ERROR: Generated schemas are out of sync!"
            echo "Run './scripts/generate.sh' and commit the changes."
            git diff src/schemas/
            exit 1
          fi
      - name: Check for pending migrations
        run: |
          if uv run alembic check 2>&1 | grep -q "FAILED"; then
            echo "ERROR: Database schema has uncommitted changes!"
            echo "Run 'make migration msg=\"description\"' and commit the migration."
            exit 1
          fi
```

---

## 19. Frontend (React Admin)

| Component | Choice | Version | Rationale |
|-----------|--------|---------|-----------|
| **Framework** | React | 19.2.x | Suspense, Activity API, latest stable |
| **Language** | TypeScript | 5.9.x | Strict typing, excellent tooling |
| **Build** | Vite | 7.x | Fast HMR, **Requires Node 20.19+** |
| **Data Fetching** | TanStack Query | 5.90.x | Caching, Suspense, mutations |
| **API Client** | Orval + Axios | 7.20.x | OpenAPI → React Query codegen |
| **Router** | react-router | 7.x | NOT react-router-dom (deprecated) |
| **UI** | shadcn/ui | Latest | Tailwind v4, OKLCH colors |
| **CSS** | Tailwind CSS | 4.x | tw-animate-css (not tailwindcss-animate) |
| **Auth** | react-oidc-context | 3.x | Modern OIDC client for React 19 |
| **Auth Backend** | Keycloak | 26.2.x | SSO, OIDC, realm management |

### Critical Requirements

- **Node.js 20.19+ or 22.12+** required (Vite 7 dropped Node 18)
- **@react-keycloak/web is deprecated** (last update 2020) - use react-oidc-context
- **react-router-dom is deprecated in v7** - import from `react-router` directly
- **tw-animate-css** replaces tailwindcss-animate for Tailwind v4

### Frontend Code Generation

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPENAPI → TYPESCRIPT CODEGEN                 │
├─────────────────────────────────────────────────────────────────┤
│  FastAPI                                                        │
│  src/main.py                                                    │
│      │                                                          │
│      ▼ GET /openapi.json                                        │
│  openapi.json  ─────────────────────────────────────────────┐   │
│      │                                                      │   │
│      ▼ orval generate                                       │   │
│  web/src/api/                                               │   │
│  ├── model.ts           # Generated types (DO NOT EDIT)     │   │
│  ├── endpoints/         # Generated React Query hooks       │   │
│  └── mutator/           # Custom axios instance (MANUAL)    │   │
└─────────────────────────────────────────────────────────────────┘
```

### Dependencies

```toml
# web/package.json (key dependencies)
{
  "dependencies": {
    "react": "^19.2.3",
    "react-dom": "^19.2.3",
    "@tanstack/react-query": "^5.90.0",
    "react-router": "^7.12.0",
    "axios": "^1.7.0",
    "oidc-client-ts": "^3.1.0",
    "react-oidc-context": "^3.2.0",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "orval": "^7.20.0",
    "typescript": "^5.9.0",
    "vite": "^7.3.0"
  }
}
```

### Quick Commands

```bash
# Development
cd web && npm run dev                 # Start dev server (http://localhost:5173)

# Code Generation
uv run python scripts/export_openapi.py   # Export OpenAPI from FastAPI
cd web && npm run generate:api            # Generate TypeScript client

# Full-stack
./scripts/generate-fullstack.sh           # Complete codegen pipeline

# Quality
cd web && npm run typecheck               # TypeScript check
cd web && npm run build                   # Production build
```

---

*Document maintained by: Pronav*
*Last updated: February 1, 2026*
