# Vartalaap - Voice Bot Platform

**Repository:** https://github.com/PranavSlathia/Vartalaap

## Project Overview

**Vartalaap** (वार्तालाप - "conversation" in Hindi) is a self-hosted voice bot platform for local Indian businesses. The MVP is a demo for **Himalayan Kitchen**, an Indian-Tibetan restaurant in Delhi.

### What It Does

- Handles inbound customer calls autonomously
- Supports natural Hindi-English-Hinglish code-switching
- Books table reservations with availability checking
- Answers menu and timing queries
- Falls back to WhatsApp for complex requests
- Costs ~$16-27/month to operate

### Core Value Proposition

Existing solutions (Retell, etc.) are expensive and have poor Hindi voice quality. Vartalaap provides:
- Self-hosted control and privacy
- Native Hindi/Hinglish support
- Low latency (P50 < 500ms processing)
- Simple configuration via Streamlit admin UI

---

## Tech Stack Summary

```
Python 3.12 + FastAPI + SQLModel + Piper TTS + Deepgram STT + Groq LLM + Plivo
Docker + Caddy + Redis (arq) + SQLite
Codegen: datamodel-codegen + fastapi-crudrouter + alembic
```

| Layer | Technology |
|-------|------------|
| **API** | FastAPI 0.115.x, uvicorn, WebSockets |
| **Database** | SQLite + SQLModel + Alembic migrations |
| **STT** | Deepgram (streaming, Hindi support) |
| **LLM** | Groq (llama-3.3-70b-versatile, streaming) |
| **TTS** | Piper (primary, self-hosted) / Edge TTS (fallback, feature-flagged) |
| **Telephony** | Plivo (WebSocket audio streams) |
| **Background Tasks** | arq + Redis |
| **Admin UI** | Streamlit on subdomain |

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| [docs/PRD.md](docs/PRD.md) | Product requirements, user flows, success metrics |
| [docs/TECH_STACK.md](docs/TECH_STACK.md) | Complete technical specification (v1.2) |
| [.claude/skills/README.md](.claude/skills/README.md) | Skills index and quick commands |

---

## Skills Reference

Use these slash commands for context-rich assistance:

| Skill | Command | Use When |
|-------|---------|----------|
| **Backend** | `/backend` | FastAPI routes, services, middleware, dependency injection |
| **Model** | `/model` | Database models, JSON Schema, migrations, SQLModel |
| **Admin** | `/admin` | Streamlit pages, authentication, PII masking |
| **Voice** | `/voice` | Voice pipeline (STT → LLM → TTS), latency optimization |
| **API** | `/api` | CRUD endpoints, fastapi-crudrouter, OpenAPI |

---

## Architecture Overview

### Voice Pipeline

```
Plivo (8kHz) → Resample → Deepgram STT → Groq LLM → Piper TTS → Resample → Plivo
     ↑                         ↓              ↓            ↓              ↓
  WebSocket              Streaming      Streaming     Streaming      WebSocket
```

**Latency Budget:** P50 < 500ms processing, P95 < 1.2s end-to-end

### Code Generation Workflow

```
schemas/*.json              # 1. JSON Schema (source of truth)
    ↓ datamodel-codegen
src/schemas/*.py            # 2. Generated Pydantic (DO NOT EDIT)
    ↓ extend
src/db/models.py            # 3. SQLModel tables (manual)
    ↓ alembic --autogenerate
migrations/versions/*.py    # 4. Database migrations
    ↓ include in app
src/api/routes/crud.py      # 5. CRUD endpoints (fastapi-crudrouter)
```

### Project Structure

```
vartalaap/
├── schemas/                # JSON Schema (source of truth)
├── src/
│   ├── schemas/            # Generated Pydantic (DO NOT EDIT)
│   ├── db/models.py        # SQLModel tables
│   ├── api/routes/         # FastAPI routes
│   ├── core/pipeline.py    # Voice pipeline orchestrator
│   └── services/           # STT, LLM, TTS, Telephony
├── admin/                  # Streamlit admin UI
├── migrations/             # Alembic migrations
└── config/                 # Business configs (YAML)
```

---

## Key Patterns & Conventions

### Phone Number Security

| Purpose | Method | Field |
|---------|--------|-------|
| Caller deduplication | HMAC-SHA256 with global pepper | `caller_id_hash` |
| WhatsApp delivery | AES-256-GCM encryption | `customer_phone_encrypted` |

### PII Handling

- **Logs:** Never log phone numbers or PII
- **Admin UI:** Mask phones as `98XXXX1234`
- **Retention:** 90-day auto-purge for transcripts and encrypted phones

### Background Tasks

- **arq** handles both task queue AND cron jobs
- Single worker for MVP (cron jobs not "exactly once" across multiple workers)
- Redis for job persistence

### Admin Authentication

- Single admin user (MVP)
- bcrypt password hash in `.env`
- Streamlit runs on subdomain: `admin.vartalaap.yourdomain.com`

---

## Claude Code Tools

| Tool | Command | Use When |
|------|---------|----------|
| **osgrep** | `osgrep "question"` | Semantic code search - find code by concept, not just text. Ask "where is X implemented?", "how does Y work?", "find the logic for Z". Returns file paths with line numbers and code snippets. |
| **/commit** | `/commit` | Create git commits with proper message formatting |

**Note:** For greenfield work (creating new files), direct file creation is faster. Use `osgrep` when navigating existing code.

---

## Quick Commands

```bash
# Development
uv run uvicorn src.main:app --reload          # API server
uv run streamlit run admin/app.py             # Admin UI
uv run arq src.worker.WorkerSettings          # Background worker

# Code Generation
./scripts/generate.sh                         # Generate all (schemas, check migrations, ER diagram)
make migration msg="description"              # Create new migration
uv run alembic upgrade head                   # Apply migrations

# Testing
uv run ward                                   # Run tests
uv run ruff check .                           # Lint
uv run mypy src/                              # Type check
```

---

## Environment Variables

Required in `.env`:

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

# Feature Flags
EDGE_TTS_ENABLED=false
```

---

## What to Write Manually vs Generate

### Generate Automatically
- Pydantic schemas from JSON Schema (`datamodel-codegen`)
- CRUD endpoints from SQLModel (`fastapi-crudrouter`)
- Database migrations (`alembic --autogenerate`)
- OpenAPI spec (FastAPI built-in)
- ER diagrams (`eralchemy2`)

### Write Manually
- Voice pipeline logic (STT → LLM → TTS orchestration)
- WebSocket handlers (Plivo audio streaming)
- Business rules (reservation validation, capacity)
- LLM prompts (conversation flows)
- Security functions (AES-256-GCM, HMAC-SHA256)
- Background tasks (WhatsApp sending, purge jobs)

---

## Demo Business: Himalayan Kitchen

- **Type:** Indian-Tibetan restaurant, Delhi
- **Hours:** Tuesday-Sunday, 11:00-22:30 (closed Monday)
- **Capacity:** 40 seats
- **Phone booking limit:** 10 people (larger groups → WhatsApp handoff)

Sample greeting:
```
"Namaste! Himalayan Kitchen mein aapka swagat hai.
Yeh call service improvement ke liye transcribe ho sakti hai.
Main aapki kaise madad kar sakti hoon?"
```

---

## Success Metrics (MVP)

| Metric | Target |
|--------|--------|
| Reservation accuracy | ≥ 95% |
| Menu query accuracy | ≥ 98% |
| Response latency (P95) | < 1.2s |
| Call completion rate | ≥ 98% |
| STT Word Error Rate (Hindi) | < 15% |

---

*For detailed specifications, see [docs/TECH_STACK.md](docs/TECH_STACK.md) and [docs/PRD.md](docs/PRD.md).*
