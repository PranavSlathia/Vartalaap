# Vartalaap — Strategic Roadmap

> Source: "What Vartalaap Should Steal from Vapi AI" (architecture & competitive strategy doc)
> This is the north star for all development. Read before starting any significant feature work.

---

## The Mission

Build a self-hosted Vapi AI alternative for the Indian SMB market:
- 5–10x cheaper ($0.02–0.05/min vs Vapi's $0.15–0.30/min)
- Lower latency via Indian cloud deployment (AWS Mumbai / GCP Mumbai)
- Native Indic language support (Hindi, Hinglish, eventually other Indian languages)
- Self-hosted → no vendor lock-in, Indian data residency
- Developer experience that matches Vapi: assistant-as-config, not pipeline code

**Structural advantages over Vapi (never give these up):**
- Cartesia sonic-multilingual = ~90ms TTFB, native Hindi, no English-only TTS quality gap
- Groq = sub-100ms first token (Vapi uses OpenAI = slower + more expensive)
- Plivo Indian DIDs = better India routing + cheaper
- SQLite/Postgres on Indian cloud = <50ms latency to Indian callers

---

## What We Steal from Vapi (and What We Don't)

### Steal These Patterns

| Pattern | Why It Matters | Where to Implement |
|---------|---------------|-------------------|
| Overlapping pipeline execution | 40–60% latency reduction | `src/core/pipeline.py` |
| Sentence-boundary LLM→TTS chunking | First audio word before LLM finishes | `src/core/frames.py` |
| Silero VAD for interruption | Natural barge-in, not energy threshold | `src/services/vad/` |
| Assistant-as-config (Pydantic) | New business = new config, not new code | `src/agents/` |
| Function calling with filler phrases | Prevents dead air during tool calls | `src/core/tools.py` |
| Multi-agent squads | Context-preserving agent handoffs | `src/agents/squads.py` |
| Per-turn latency metrics | Transparent debugging (STT_ms, LLM_ms, TTS_ms) | `src/observability/` |
| Deepgram `utterance_end_ms` config | Per-agent endpointing tuning | Agent config model |

### Steal the Architecture From These OSS Projects

| Project | What to Take |
|---------|-------------|
| **Pipecat** (Daily.co, BSD-2) | Frame-based pipeline, typed frames, InterruptionFrame propagation |
| **LiveKit** (Apache 2.0) | State machine values (min_interruption_duration: 500ms), plugin interface |
| **Bolna AI** (MIT, India) | Plivo WebSocket patterns, multilingual routing, Bhashini API |
| **Vocode** (MIT) | FastAPI telephony server pattern, Pydantic config classes for components |

### Don't Copy These

| Vapi Feature | Why Not |
|-------------|---------|
| Per-minute pricing | Indian SMBs → flat monthly (₹2,999/500 calls) or per-call (₹5/call) |
| WebRTC (Daily.co) | Overkill for telephony-only; WebSocket to Plivo is sufficient |
| Multi-provider voice cloning | $0.10–0.30/min TTS cost; adds complexity with no quality benefit |
| HIPAA/SOC2 compliance | Indian SMB market needs data residency + encryption, not certifications |
| Real-time dashboard | Log to Postgres + CSV export first; dashboard when users justify it |

---

## Phased Implementation Plan

### Phase 1 — Foundation Hardening (Current State → v0.4)
**Status:** Mostly done. These are cleanup tasks.

- [x] Basic voice pipeline (STT → LLM → TTS)
- [x] Plivo WebSocket integration
- [x] Simple state machine (IDLE, LISTENING, PROCESSING, SPEAKING, INTERRUPTED)
- [x] CrewAI transcript analysis (QA crew)
- [x] ChromaDB knowledge base
- [x] Streamlit admin UI
- [ ] **Connection pooling** — pre-warm Deepgram/Groq WebSocket connections per call
- [ ] **Per-turn latency logging** — log STT_ms, LLM_first_token_ms, TTS_first_chunk_ms per turn
- [ ] **Deepgram utterance_end_ms config** — expose as per-business config (default: 400ms)

---

### Phase 2 — Pipeline Architecture (v0.5) ← NEXT MAJOR WORK

**Goal:** Replace the current monolithic pipeline with a Pipecat-inspired frame-based design.
**Expected impact:** Cleaner code, proper interruption handling, enables all future features.

#### 2a. Frame Types (`src/core/frames.py`)
Define typed frame dataclasses:
```python
@dataclass class AudioRawFrame      # Raw audio bytes + sample_rate + encoding
@dataclass class TranscriptionFrame  # STT text + is_final + speech_final
@dataclass class LLMTokenFrame       # Single LLM token + is_sentence_boundary
@dataclass class TTSAudioFrame       # TTS audio chunk + provider
@dataclass class InterruptionFrame   # Signal to flush all downstream processors
@dataclass class FunctionCallFrame   # Tool name + args + filler_phrase
@dataclass class FunctionResultFrame # Tool result to feed back to LLM
@dataclass class AgentTransferFrame  # New agent config + transfer summary
```

#### 2b. Silero VAD (`src/services/vad/silero.py`)
- Run on every 30ms incoming audio chunk
- Only trigger interruption if speech persists > 500ms (avoid false positives from noise)
- Replace current energy-threshold barge-in in `pipeline.py`
- Install: `pip install silero-vad` (CPU-only inference, ~10ms per frame)

#### 2c. Streaming LLM-to-TTS (`src/core/pipeline.py`)
**Single biggest latency win (40–60% improvement):**
- Buffer Groq tokens until sentence boundary detected (`.`, `?`, `!`, or `,` + 4+ words)
- Send chunk to Cartesia TTS immediately while Groq continues generating
- User hears first words while LLM is still thinking about the rest
- Current code waits for full LLM response — this is the bug to fix

#### 2d. Enhanced State Machine
Add missing states to `src/core/conversation_state.py`:
- `FUNCTION_CALLING` — executing a tool, filler phrase playing
- `TRANSFERRING` — agent handoff in progress
- `ENDED` — call concluded

**Key transition:** `SPEAKING → INTERRUPTED → LISTENING`
When VAD fires during SPEAKING: flush audio buffer, abort Groq stream, log partial
bot response to conversation history, transition to LISTENING.

---

### Phase 3 — Assistant-as-Config (v0.6)

**Goal:** A complete voice bot is a Pydantic config object. No new pipeline code for new businesses.

#### 3a. Agent Config Model (`src/agents/config.py`)
```python
class AssistantConfig(BaseModel):
    name: str
    system_prompt: str
    stt: STTConfig          # provider, model, language, endpointing_ms
    llm: LLMConfig          # provider, model, temperature, max_tokens
    tts: TTSConfig          # provider, voice, speed
    tools: list[ToolConfig] # registered functions with filler phrases
    first_message: str
    silence_timeout_s: int = 30
    barge_in_enabled: bool = True
    min_interruption_ms: int = 500
```

#### 3b. Three-Layer Provider Abstraction
Separate `TranscriberConfig`, `ModelConfig`, `VoiceConfig` as independently swappable.
Swapping STT provider (Deepgram → Bhashini) should not touch LLM or TTS code.

#### 3c. Per-Business Config Migration
Migrate `config/*.yaml` business configs to `AssistantConfig` Pydantic models.
Himalayan Kitchen config becomes the reference implementation.

---

### Phase 4 — Function Calling System (v0.7)

**Goal:** LLM can invoke tools; bot speaks filler while tools execute; no dead air.

#### 4a. Tool Registry (`src/core/tools.py`)
```python
@tool_registry.register(
    name="check_availability",
    filler_hi="Ek second, main availability check kar rahi hoon...",
    filler_en="One moment, checking availability for you..."
)
async def check_availability(date: str, party_size: int) -> str: ...
```

#### 4b. Filler Phrase System
- When LLM returns tool call: speak filler immediately, execute async
- Filler selection: Hindi/English based on conversation language detection
- Async execution: filler plays while DB query / API call runs
- Return result to LLM for natural spoken response

#### 4c. Built-in Tools for Restaurant Use Case
- `check_availability(date, party_size)` → reservation slot check
- `book_reservation(date, time, party_size, name)` → creates booking
- `search_menu(query)` → ChromaDB RAG search
- `get_hours()` → business hours lookup
- `request_callback(reason)` → creates WhatsApp followup

---

### Phase 5 — Multi-Agent Squads (v0.8)

**Goal:** A receptionist agent routes to specialized agents without dropping the call.

#### Squad Architecture
- `ReceptionistAgent` — greeting, intent detection, routing
- `BookingAgent` — reservation flow, availability, confirmation
- `SupportAgent` — menu queries, hours, general info
- `TransferAgent` — warm transfer to human, WhatsApp handoff

#### Implementation
- Handoff = swap active `AssistantConfig`, inject conversation history into new agent's context
- Transfer summary injected as system message: "User wants to book for 4 people on Saturday"
- Audio stream continues uninterrupted — no telephony-level transfer needed
- Full conversation history available to receiving agent

---

### Phase 6 — Platform Expansion (v1.0)

- PostgreSQL migration (multi-tenant support)
- Bhashini API integration (government-backed Indian language AI)
- Exotel telephony support (broader India coverage)
- Multi-business admin (one deployment, multiple restaurants)
- Indian pricing model: ₹2,999/month for 500 calls, ₹5/call thereafter
- Deploy target: AWS Mumbai (ap-south-1) for sub-50ms to Indian callers

---

## Priority Order for Next Work Session

When you sit down to code, work in this order:

1. **Per-turn latency logging** — quick win, needed for baseline metrics before optimization
2. **Streaming LLM-to-TTS chunking** — single biggest latency improvement, relatively contained change
3. **Silero VAD** — replaces hacky energy threshold, enables proper barge-in
4. **Frame types** — refactor enables everything else; do with Silero VAD as part of Phase 2
5. **Function calling + fillers** — high UX impact, needed for complex reservation flows
6. **AssistantConfig** — enables multi-business without code changes
7. **Squads** — builds directly on AssistantConfig

---

## Success Metrics by Phase

| Phase | Key Metric |
|-------|-----------|
| Phase 2 | P95 latency < 1.0s (down from 1.2s target) |
| Phase 3 | New business onboarding: config change only, no code |
| Phase 4 | Zero dead air (>0.5s silence) during tool calls |
| Phase 5 | Booking completion rate ≥ 95% with multi-agent flow |
| Phase 6 | First paying customer at ₹2,999/month |
