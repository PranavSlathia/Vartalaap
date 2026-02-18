# Vartalaap — Product Soul

> वार्तालाप (vārtālāp) — "conversation" in Hindi.

Read this before working on anything in this codebase. If you read only one file, it's this one.

---

## What This Actually Is

Vartalaap is a **self-hosted voice AI platform for the Indian SMB market** — a direct alternative to Vapi AI and Retell, built specifically for the conditions of India: Hindi-English code-switching, 4G callers in noisy environments, Indian telephony (Plivo), and low-latency deployment close to Indian callers.

**The reference implementation is Himalayan Kitchen** — an Indian-Tibetan restaurant in Delhi where the owner misses calls because he's in the kitchen. It is the proof point, the demo, and the first customer. It is not the ceiling.

**The actual opportunity:** Developers validate voice AI use cases on Vapi, then hit cost and latency walls at scale. Vapi has no India-region servers and no native Indic language support. We solve both.

**The pitch in one sentence:** Vapi's architecture, India's latency, self-hosted control, native Hinglish.

---

## What We Optimize For

**In order — this order matters when making tradeoffs:**

1. **Correctness.** The caller is understood and the response is right. If Deepgram mishears "kal ke liye" as "call ke liye", that breaks trust permanently. STT accuracy and LLM faithfulness to the restaurant's actual data come before everything.

2. **Latency.** P50 < 500ms processing, P95 < 1.2s end-to-end. Dead air sounds like a broken system to the caller. The streaming pipeline — STT frames → LLM tokens at sentence boundaries → TTS chunks before LLM finishes — is not an optimization. It is the architecture.

3. **Naturalness.** The voice should not sound like a call center bot. Cartesia sonic-multilingual with proper Hindi language detection, filler phrases, and sentence-boundary chunking makes it sound like a person who happens to be fast. This is the voice quality gap Vapi has in India.

4. **Cost.** Self-hosted, Plivo DIDs, Groq's fast inference, and Cartesia's competitive pricing puts us at $0.02–0.04/minute — 2–4x cheaper than Vapi at comparable quality. The cost advantage compounds at scale.

5. **Operator simplicity.** The restaurant owner changes the menu via Streamlit on their phone, not YAML. If a config change requires a developer, the abstraction is wrong.

6. **Developer experience.** The assistant is a Pydantic config object. A new business should be a new config file, not a new deployment.

---

## What We Never Do

**PII:** Raw phone numbers never appear in logs, DB columns, API responses, or memory beyond the entry point. HMAC-SHA256 for deduplication. AES-256-GCM for WhatsApp delivery. No exceptions, not even in debug.

**Fallback chains:** We chose Deepgram, Groq, and Cartesia. One provider per role. If Cartesia is down, the call fails gracefully — it does not fall back to a worse provider and pretend everything is fine. Reliability comes from provider uptime, not from duct-tape fallbacks that introduce latency and unpredictable voice quality.

**Waiting when we can stream:** Deepgram gets audio frames as they arrive. LLM tokens feed TTS at sentence boundaries. TTS chunks go to Plivo before the LLM finishes. Waiting for a full response to start TTS is the difference between 500ms and 2000ms. Never do it.

**Adding latency to the hot path for convenience:** Every processor in STT→LLM→TTS must justify its existence in milliseconds. Analytics, logging, and DB writes happen async after the call or on a separate path.

**Copying Vapi's mistakes:** Per-minute pricing that creates cost anxiety for Indian SMBs. WebRTC infrastructure for telephony-only calls. Enterprise certifications (HIPAA/SOC2) before product-market fit. None of these.

**Relitigating settled decisions:** The decisions table at the bottom of this file is settled. Don't bring them back up without new data.

---

## The Architecture We're Building Toward

Inspired by Pipecat (frame-based pipeline), LiveKit (state machine), Bolna AI (Indian telephony), and Vocode (FastAPI patterns):

```
Frame-based pipeline:
  AudioRawFrame → Resampler → VAD (Silero) → STT (Deepgram nova-2, streaming)
  → LLM (Groq llama-3.3-70b-versatile, sentence-boundary chunking)
  → TTS (Cartesia sonic-multilingual, WebSocket streaming chunks)
  → AudioRawFrame → Plivo

Audio format chain:
  Plivo 8kHz μ-law → decode+resample → 16kHz PCM → Deepgram
  Cartesia 22050Hz PCM → resample → encode μ-law → Plivo 8kHz

State machine per call:
  IDLE → LISTENING → PROCESSING → THINKING → SPEAKING → LISTENING
  With: INTERRUPTED (barge-in), FUNCTION_CALLING (tool use), TRANSFERRING (agent handoff)

Assistant-as-config:
  Each voice bot is a Pydantic AssistantConfig: system_prompt + STT config + LLM config
  + TTS config + endpointing + tools + behavioral parameters.
  No pipeline code changes for new businesses.

Multi-agent squads:
  Receptionist → BookingAgent / SupportAgent / TransferAgent
  Handoff = swap active AssistantConfig, preserve conversation history.
  No telephony-level transfer needed within the same call.
```

See `.claude/roadmap.md` for the phased implementation plan.

---

## The Bot's Voice

Warm. Helpful. Hinglish by default.

- Hindi sentence structure, occasional English words where natural, never forced bilingualism
- Efficient — customers want the answer, not a conversation
- Honest about waiting — "Ek second dijiye, main check kar rahi hoon" not silence
- Never robotic — "Maaf kijiye, thoda wait karein" not "Processing your request"
- Confident about what it knows (menu, hours, reservations), honest about what it doesn't

The filler phrases must come from a config file. Never hardcoded in pipeline logic.

---

## The Code's Personality

**Frames, not buffers.** Typed frame objects (`AudioRawFrame`, `TranscriptionFrame`, `LLMTokenFrame`, `TTSAudioFrame`, `InterruptionFrame`) flowing through processors. Not raw bytes passed between monolithic functions. One `InterruptionFrame` flushes everything downstream simultaneously.

**Config, not code.** New assistant = new `AssistantConfig` Pydantic object. New tool = `@tool` decorator registration. If adding a new business requires touching `pipeline.py`, the abstraction is wrong.

**Explicit state.** The state machine is real code (`PipelineState` enum). Every transition is intentional and logged. No implicit state through variable names, flags, or global variables.

**Generated code stays generated.** `src/schemas/*.py` and `web/src/api/` are outputs of a workflow, not files to edit. The workflow runs forward: JSON Schema → Pydantic → SQLModel → Alembic → OpenAPI → TypeScript. Never backwards, never manually.

**Loud failures in dev, clean failures in prod.** Validation errors at startup — not at call time. A missing `CARTESIA_API_KEY` should crash the server on boot, not fail silently on the first call. In production, a failed call logs its error, saves its partial state, and ends cleanly. A failed call is not a failed system.

---

## People

**Builder:** Pranav. Solo developer. Every architectural decision must be implementable incrementally by one person. Sophistication is earned, not assumed.

**Admin user:** Restaurant owner or manager. Not technical. On their phone. Reads Hindi. The Streamlit admin must work for them without explanation, without training, and without calling the developer.

**Callers:** Mixed Hindi/English speakers. 4G connections. Noisy environments — street, auto-rickshaw, kitchen. STT must handle ambient noise, code-switching, and regional accents. If it only works in a quiet room with RP English, it has failed.

**Future customers:** Indian SMB developers who hit Vapi's cost ceiling, Indian businesses that need Indic language support, teams that need self-hosted data residency for compliance.

---

## Decisions Made — Don't Relitigate Without New Data

| Decision | Why | Revisit when |
|----------|-----|-------------|
| Cartesia sonic-multilingual for TTS | ~90ms TTFB, native Hindi, WebSocket streaming, one API — no fallback complexity | A demonstrably better Hindi voice provider emerges |
| Groq llama-3.3-70b-versatile for LLM | Sub-100ms first token, best multilingual on Groq, cost-effective | Quality issues at scale or a better option benchmarks significantly higher |
| Deepgram nova-2 for STT | Best Hindi+English streaming, `utterance_end_ms` tuning, reliable WebSocket | Re-evaluate Sarvam/Bhashini for pure Hindi deployments |
| Plivo for telephony | Cheapest Indian DIDs, India routing, reliable WebSocket | Add Exotel for broader coverage in Phase 5+ |
| SQLite → PostgreSQL (roadmap) | SQLite is sufficient for single-tenant demo | First paying customer or multi-tenant requirement |
| Streamlit for admin | Fast to build, sufficient for non-technical SMB operator | Multi-tenant SaaS needs a proper React admin |
| Frame-based pipeline | Composable, testable, proven by Pipecat — the right abstraction | Never |
| No WebRTC | Telephony-only use case; Plivo WebSocket is sufficient | Only if browser-to-bot calls are needed |
| No fallback providers | Single provider per role; fallbacks add latency and unpredictable behavior | Never — reliability via provider SLAs, not duct-tape chains |

---

## When In Doubt

Two questions:

1. **"Does this make calls work better for the caller?"** (correctness, naturalness, latency)
2. **"Does this make Vartalaap a better platform than Vapi for Indian developers?"** (cost, Indic support, DX, self-hosted)

If the answer is no to both, it's not in scope.
If it answers one, consider it.
If it answers both, ship it.
