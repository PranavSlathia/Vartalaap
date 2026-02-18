# Frame-Based Pipeline — Institutional Memory

## The Pattern (from Pipecat, BSD-2)

Everything in the pipeline is a typed frame dataclass. Frames flow through a chain of
Processors. Each Processor transforms, filters, or generates frames.

This replaces the current monolithic `VoicePipeline` class with composable, testable units.

## Frame Types to Define (`src/core/frames.py`)

```python
@dataclass
class AudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int = 1
    encoding: str = "linear16"  # or "mulaw"

@dataclass
class TranscriptionFrame:
    text: str
    is_final: bool
    speech_final: bool  # End of utterance (Deepgram endpointing)
    language: str = "hi"

@dataclass
class LLMTokenFrame:
    token: str
    is_sentence_boundary: bool = False  # Detected by sentence chunker

@dataclass
class TTSAudioFrame:
    audio: bytes
    provider: str  # "piper", "elevenlabs", "edge"

@dataclass
class InterruptionFrame:
    """Propagates downstream, causing each processor to flush its buffers.
    Key mechanism for barge-in: one frame stops everything."""
    reason: str = "barge_in"

@dataclass
class FunctionCallFrame:
    function_name: str
    arguments: dict
    filler_hi: str
    filler_en: str

@dataclass
class FunctionResultFrame:
    function_name: str
    result: str  # String result fed back to LLM

@dataclass
class AgentTransferFrame:
    target_agent_id: str
    transfer_summary: str
    conversation_history: list[dict]
```

## InterruptionFrame Propagation

The key elegance: when barge-in occurs, one `InterruptionFrame` flows through the
pipeline and each processor handles it independently:

- **LLM Processor**: Cancels HTTP stream to Groq
- **TTS Processor**: Cancels Piper subprocess, clears audio queue
- **Audio Output Processor**: Calls `sender.clear_audio()` (flushes Plivo buffer)
- **Transcript Processor**: Records partial bot response to conversation history

This avoids the current approach of checking a shared `_tts_cancel_event` across coroutines.

## Sentence Boundary Detection

```python
import re

SENTENCE_END = re.compile(r'[.?!।]\s*$')  # ।= Hindi danda
CLAUSE_BOUNDARY = re.compile(r',\s+(\w+\s+){3,}')  # Comma + 4+ words

def is_sentence_boundary(text: str) -> bool:
    stripped = text.strip()
    if SENTENCE_END.search(stripped):
        return True
    if CLAUSE_BOUNDARY.search(stripped):
        return True
    # Also break on natural Hindi pause markers
    if stripped.endswith(('...', '—')):
        return True
    return False
```

Test with: "Main check kar rahi hoon," (boundary) vs "hoon, aur" (not a boundary).

## Silero VAD Integration

```python
# src/services/vad/silero.py
# Install: uv add silero-vad
import torch
from silero_vad import load_silero_vad, get_speech_timestamps

class SileroVAD:
    CHUNK_SIZE = 512  # 32ms at 16kHz (Silero requires power-of-2 chunks)
    MIN_SPEECH_MS = 500  # Consecutive speech before triggering interruption

    def __init__(self):
        self.model, self.utils = load_silero_vad()
        self._speech_start: float | None = None

    def process_chunk(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        """Returns True if this chunk contains speech."""
        audio_tensor = torch.from_numpy(
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )
        confidence = self.model(audio_tensor, sample_rate).item()
        return confidence > 0.5

    def should_interrupt(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        """Returns True only after MIN_SPEECH_MS of continuous speech."""
        is_speech = self.process_chunk(audio_bytes, sample_rate)
        now = time.perf_counter() * 1000

        if is_speech and self._speech_start is None:
            self._speech_start = now
        elif not is_speech:
            self._speech_start = None
            return False

        if self._speech_start and (now - self._speech_start) >= self.MIN_SPEECH_MS:
            self._speech_start = None  # Reset after triggering
            return True
        return False
```

**Important:** Silero requires 16kHz input. Resample from 8kHz Plivo input before VAD.

## Connection Pooling Pattern

Pre-warm all connections at call start, not on first use:

```python
async def setup_pipeline(self) -> None:
    """Called once per call during answer webhook, before first audio frame."""
    # Deepgram: establish WS connection early
    await self._stt_service.connect()

    # Piper: start subprocess and synthesize empty string (warm up)
    await self._tts_service.warmup()

    # Groq: HTTP client, no persistent connection needed
    # But pre-build the messages list with system prompt
    self._llm_messages = [{"role": "system", "content": self._session.system_prompt}]
```

## Known Performance Characteristics

- Silero VAD: ~10ms per 30ms chunk on CPU (acceptable for real-time)
- Sentence boundary detection: <1ms (regex, negligible)
- Piper TTS startup: ~200ms first call, ~20ms subsequent (warm)
- Deepgram STT interim results: ~100–200ms after speech starts
- Groq first token: ~50–100ms after prompt submission

## What the Current Code Gets Wrong

1. **`is_speech()` in `plivo.py`** — energy threshold, breaks in noisy environments. Replace with Silero.
2. **`collect_response()` in `pipeline.py`** — accumulates full LLM response before TTS. Replace with sentence chunking.
3. **`_tts_cancel_event` shared event** — fragile cross-coroutine signaling. Replace with InterruptionFrame.
4. **No pre-warming** — Deepgram connection opened on first audio chunk. Pre-warm in `setup_pipeline()`.
