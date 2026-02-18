# /pipeline — Frame-Based Pipeline Skill

You are working on Vartalaap's voice pipeline engine — the real-time audio processing core.
This is the highest-criticality code in the project. Changes here affect every call.

## Architecture We're Building (Pipecat-inspired)

```
AudioRawFrame → Resampler → VAD (Silero) → STT (Deepgram streaming)
    → LLM (Groq, sentence-boundary chunked) → TTS (Piper streaming)
    → AudioRawFrame → Plivo WebSocket
```

Frames flow through a chain of Processors. Each processor transforms or filters frames.
`InterruptionFrame` propagates downstream, causing each processor to flush its buffers.

## Key Files

| File | Purpose |
|------|---------|
| `src/core/pipeline.py` | Main orchestrator — `VoicePipeline` class |
| `src/core/frames.py` | Frame type definitions (create if doesn't exist) |
| `src/core/conversation_state.py` | State machine (PipelineState enum) |
| `src/core/session.py` | Call session — business context, transcript, metrics |
| `src/services/stt/deepgram.py` | Deepgram streaming STT |
| `src/services/llm/groq.py` | Groq streaming LLM |
| `src/services/tts/piper.py` | Piper TTS (primary) |
| `src/services/tts/resampler.py` | Audio resampling between rates |
| `src/services/vad/` | VAD implementations (Silero target) |
| `src/services/telephony/plivo.py` | Plivo WebSocket audio handling |
| `src/api/websocket/audio_stream.py` | WebSocket connection handler |

## State Machine

Current states + additions needed:
```python
class PipelineState(Enum):
    IDLE = auto()               # Waiting for speech
    LISTENING = auto()          # VAD detected, STT active
    PROCESSING = auto()         # STT final, preparing LLM call
    THINKING = auto()           # LLM streaming tokens
    SPEAKING = auto()           # TTS audio playing to caller
    INTERRUPTED = auto()        # Barge-in: flush + transition to LISTENING
    FUNCTION_CALLING = auto()   # Tool executing, filler phrase speaking
    TRANSFERRING = auto()       # Agent handoff in progress
    ENDED = auto()              # Call concluded
```

**Critical transition:** `SPEAKING → INTERRUPTED → LISTENING`
When Silero VAD detects speech during SPEAKING:
1. Set `_tts_cancel_event`
2. Abort in-flight Groq HTTP stream
3. Flush Plivo audio output buffer
4. Add partial bot response to conversation history
5. Transition to LISTENING, let new speech flow to STT

## Streaming LLM-to-TTS (The Key Latency Optimization)

**Current code (wrong):** Waits for full LLM response, then sends all text to TTS.
**Target:** Buffer tokens until sentence boundary, send chunk to TTS, keep LLM running.

```python
async def _stream_response_to_tts(self, transcript: str, sender: AudioSender):
    buffer = ""
    async for token in groq.stream(transcript):
        buffer += token
        if is_sentence_boundary(buffer):
            # Send chunk to TTS NOW, don't wait for LLM to finish
            asyncio.create_task(self._speak_chunk(buffer, sender))
            buffer = ""
    if buffer.strip():  # Remaining tokens
        await self._speak_chunk(buffer, sender)

def is_sentence_boundary(text: str) -> bool:
    # Period, ?, ! always boundary
    # Comma only if followed by 4+ words (clause boundary, not list item)
    import re
    return bool(re.search(r'[.?!]$|,\s+\w+\s+\w+\s+\w+\s+\w+', text.strip()))
```

## VAD / Barge-in

**Current:** Energy threshold (`is_speech()` in `plivo.py`) — unreliable, noisy environments.
**Target:** Silero VAD — neural network, ~10ms per 30ms chunk, much more accurate.

```python
# Target implementation in src/services/vad/silero.py
class SileroVAD:
    MIN_SPEECH_DURATION_MS = 500  # Avoid false triggers from noise
    CHUNK_MS = 30  # 30ms chunks for Silero

    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        # Returns True if speech detected in chunk
        ...

    def should_interrupt(self, consecutive_speech_ms: float) -> bool:
        return consecutive_speech_ms >= self.MIN_SPEECH_DURATION_MS
```

Install: `uv add silero-vad` (CPU inference, no GPU needed, ~10ms/frame)

## Connection Pooling (Per-Call Setup)

Pre-establish connections at call start, not on first use:
```python
async def setup_connections(self):
    # Do this in send_greeting(), before first user turn
    await self._deepgram_client.connect()  # Pre-warm WS connection
    # Groq uses HTTP streaming — no persistent connection needed
    # Piper is a subprocess — warm it with a dummy synthesis
    await self._piper.warmup()
```

## Deepgram Endpointing

Expose `utterance_end_ms` as per-agent config (not hardcoded):
- Fast sales calls: 250ms
- Patient support calls: 600ms
- Default: 400ms

```python
# In Deepgram STT service init:
options = LiveOptions(
    model="nova-2",
    language="hi",
    endpointing=self.config.endpointing_ms,  # per-agent
    smart_format=True,
    interim_results=True,
)
```

## Per-Turn Latency Logging

Log these for every conversation turn (not just averages):
```python
@dataclass
class TurnMetrics:
    turn_id: str
    stt_start_ms: float    # Audio received → STT final
    llm_first_token_ms: float  # STT final → first LLM token
    tts_first_chunk_ms: float  # First LLM token → first audio sent
    total_response_ms: float   # STT final → first audio to caller
    interrupted: bool
    function_called: str | None
```
Store in `conversation_turns` table for post-call analysis.

## Audio Format Reference

| Stage | Format | Rate |
|-------|--------|------|
| Plivo → App | μ-law (PCMU) | 8kHz |
| App → Deepgram | PCM linear16 | 16kHz |
| Piper output | PCM | 22.05kHz |
| App → Plivo | μ-law (PCMU) | 8kHz |

Resampling in `src/services/tts/resampler.py`. Use `audioop.ulaw2lin()` for μ-law decode.

## Testing

```bash
uv run python scripts/voice_test.py   # Full pipeline smoke test (no real telephony)
uv run ward tests/test_pipeline.py    # Unit tests for pipeline components
```

When changing pipeline.py, always run voice_test.py. Latency regression > 100ms = investigate.

## What Not to Do

- Don't add blocking I/O in the audio receive loop
- Don't accumulate audio before sending to Deepgram (stream immediately)
- Don't wait for full LLM response before starting TTS (sentence boundaries)
- Don't use energy threshold for VAD in noisy environments (Silero only)
- Don't log audio bytes (privacy + storage)
