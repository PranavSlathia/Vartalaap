# Voice Pipeline — Institutional Memory

## Audio Format & Resampling

- **Plivo → app**: 8kHz μ-law (PCMU), codec code `0`
- **App → Deepgram**: resample 8kHz μ-law → 16kHz PCM (Deepgram requires 16kHz)
- **Piper output**: 22.05kHz PCM → resample to 8kHz μ-law → Plivo
- Resampling logic lives in `src/services/audio/resampler.py`

## Deepgram STT

- Use `language=hi` for Hindi; supports code-switching automatically
- Recommended model: `nova-2` (best accuracy for Indian English + Hindi)
- Encoding for Plivo input: `mulaw`, `sample_rate=8000`
- Streaming via WebSocket; partial transcripts ignored, only `is_final=True` consumed
- Config: `DEEPGRAM_API_KEY` in `.env`

## Cartesia Sonic TTS (Primary — only TTS)

- Provider: `cartesia.ai`, model: `sonic-multilingual` (supports Hindi natively)
- `CARTESIA_API_KEY` in `.env` (required — no fallback)
- `CARTESIA_VOICE_ID` — find voices at https://play.cartesia.ai/voices
- ~90ms time-to-first-chunk (true streaming, not synthesize-then-chunk like Piper)
- Language auto-detected per synthesis call: >15% Devanagari Unicode chars → `"hi"`, else `"en"`
  - Hinglish typed in Latin script ("aap kya chahte hain") is sent as `"en"` — Cartesia handles it well
  - Hinglish with actual Devanagari chars ("आप kya chahte हैं") → `"hi"` — better prosody
- Output: raw PCM s16le at 22050Hz → resampled to 8000Hz for Plivo
- WebSocket connection kept open per call for lowest per-turn latency
- Service: `src/services/tts/cartesia.py` — `CartesiaTTSService`
- No fallback chain. If Cartesia fails, the call logs the error and continues (no audio for that turn).

## Groq LLM

- Model: `llama-3.3-70b-versatile`
- Streaming enabled for lower time-to-first-token
- Rate limiter: `src/services/llm/rate_limiter.py` (token bucket)
- Temperature: 0.3 for reservation tasks (deterministic), 0.7 for general chat
- Max tokens: 200 per turn (keep responses short for voice)

## Pipeline Orchestration

- Main file: `src/core/pipeline.py`
- Barge-in threshold: 300ms (interruption detection)
- Latency budget: P50 < 500ms processing, P95 < 1.2s end-to-end
- State machine in `src/core/session.py`

## Testing

- Voice smoke test: `uv run python scripts/voice_test.py`
- Simulates full pipeline without live telephony
- Admin voice test page: `http://localhost:8501` → Voice Test tab

## Known Gotchas

- Piper model must be downloaded separately; app won't start without it
- μ-law encoding is signed 8-bit, not standard PCM — use `audioop.ulaw2lin()` or `scipy`
- Deepgram WebSocket closes if no audio received for > 10s — implement keepalive ping
- Groq has per-minute token limits; back off on `429` responses
- First Piper invocation has ~200ms startup; subsequent calls are faster
