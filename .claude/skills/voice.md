# /voice - Voice Pipeline Development

## Context

You are working on **Vartalaap**, a voice bot platform for local Indian businesses.

**Tech Stack Reference:** `docs/TECH_STACK.md` (Section 4, 5)
**PRD Reference:** `docs/PRD.md` (Section 5, 6)

## Stack Summary

- **STT:** Deepgram (streaming, Hindi support)
- **LLM:** Groq (llama-3.1-70b-versatile, streaming)
- **TTS Primary:** Piper (self-hosted, CPU-friendly)
- **TTS Fallback:** Edge TTS (feature-flagged)
- **Telephony:** Plivo (WebSocket audio streams)
- **Audio:** soundfile, soxr (resampling), numpy

## Voice Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VOICE PIPELINE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Plivo          Deepgram         Groq           Piper/Edge     │
│  (Telephony)      (STT)           (LLM)            (TTS)         │
│      │              │               │                │           │
│      │   Audio      │   Text        │   Text         │   Audio   │
│      │   Stream     │   Stream      │   Stream       │   Stream  │
│      ▼              ▼               ▼                ▼           │
│   ┌──────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│   │WebSoc│───▶│ Deepgram │───▶│   Groq   │───▶│  Piper   │      │
│   │  ket │◀───│ Streaming│◀───│ Streaming│◀───│   TTS    │      │
│   └──────┘    └──────────┘    └──────────┘    └──────────┘      │
│      ▲              │               │                │           │
│      │              │               │                │           │
│      └──────────────┴───────────────┴────────────────┘           │
│                         Pipeline Orchestrator                    │
│                         (src/core/pipeline.py)                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
src/
├── core/
│   ├── pipeline.py         # Main orchestrator (THIS FILE IS CRITICAL)
│   ├── session.py          # Call session state management
│   └── context.py          # Conversation context accumulator
│
├── services/
│   ├── stt/
│   │   ├── __init__.py
│   │   └── deepgram.py     # Deepgram streaming client
│   ├── llm/
│   │   ├── __init__.py
│   │   └── groq.py         # Groq streaming client
│   ├── tts/
│   │   ├── __init__.py
│   │   ├── piper.py        # Piper TTS (primary)
│   │   └── edge.py         # Edge TTS (fallback)
│   └── telephony/
│       ├── __init__.py
│       └── plivo.py        # Plivo WebSocket handler
│
└── api/websocket/
    └── audio_stream.py     # FastAPI WebSocket endpoint
```

## Latency Budget (from PRD 6.1)

**Target: P50 < 500ms processing, P95 < 1.2s end-to-end**

```
Caller stops speaking
    │
    ├── [50-100ms]  VAD silence detection
    ├── [100-200ms] STT final transcript (Deepgram)
    ├── [150-300ms] LLM first token (Groq)
    ├── [100-200ms] TTS first audio chunk (Piper)
    └── [50-100ms]  Network to caller (Plivo)
    │
    ▼
First bot audio reaches caller
```

## STT: Deepgram Integration

```python
# src/services/stt/deepgram.py
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from loguru import logger
import asyncio

class DeepgramSTT:
    def __init__(self, api_key: str):
        self.client = DeepgramClient(api_key)
        self.connection = None

    async def start_stream(
        self,
        on_transcript: callable,
        on_utterance_end: callable,
    ):
        """Start streaming transcription."""
        self.connection = self.client.listen.asynclive.v("1")

        # Configure for Hindi + English
        options = LiveOptions(
            model="nova-2",
            language="hi",  # Hindi primary
            detect_language=True,  # Auto-detect Hindi/English
            smart_format=True,
            interim_results=True,
            utterance_end_ms=1000,  # Detect end of speech
            vad_events=True,
            punctuate=True,
        )

        # Event handlers
        self.connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        self.connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        self.connection.on(LiveTranscriptionEvents.Error, self._on_error)

        await self.connection.start(options)
        logger.info("Deepgram stream started")

    async def send_audio(self, audio_chunk: bytes):
        """Send audio chunk to Deepgram."""
        if self.connection:
            await self.connection.send(audio_chunk)

    async def stop(self):
        """Stop the stream."""
        if self.connection:
            await self.connection.finish()

    def _on_error(self, error):
        logger.error(f"Deepgram error: {error}")
```

## LLM: Groq Integration

```python
# src/services/llm/groq.py
from groq import AsyncGroq
from typing import AsyncIterator
from loguru import logger

class GroqLLM:
    def __init__(self, api_key: str):
        self.client = AsyncGroq(api_key=api_key)
        self.model = "llama-3.1-70b-versatile"

    async def stream_response(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        user_message: str,
    ) -> AsyncIterator[str]:
        """Stream LLM response token by token."""
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": user_message},
        ]

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            max_tokens=256,  # Keep responses concise
            temperature=0.7,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def build_system_prompt(
        self,
        business_config: dict,
        menu_data: dict,
        available_capacity: int,
    ) -> str:
        """Build system prompt with context."""
        # See PRD Section 16.A for full prompt template
        return f"""
You are a friendly voice assistant for {business_config['name']}.

PERSONALITY:
- Warm, professional, helpful
- Speaks in Hindi/Hinglish/English based on caller
- Keeps responses concise (1-2 sentences)

CURRENT CONTEXT:
- Restaurant: {business_config['name']}
- Hours: {business_config['hours']}
- Available capacity: {available_capacity} seats

MENU:
{menu_data}

When you cannot help, offer to have someone call back via WhatsApp.
"""
```

## TTS: Piper Integration (Primary)

```python
# src/services/tts/piper.py
from piper import PiperVoice
from typing import AsyncIterator
import numpy as np
import soundfile as sf
import soxr
import io
from loguru import logger

class PiperTTS:
    def __init__(self, model_path: str):
        self.voice = PiperVoice.load(model_path)
        self.sample_rate = 22050  # Piper default

    async def synthesize_stream(
        self,
        text: str,
        target_sample_rate: int = 8000,  # Plivo uses 8kHz
    ) -> AsyncIterator[bytes]:
        """Synthesize text to audio chunks."""
        # Generate audio
        audio_data = []
        for audio_chunk in self.voice.synthesize_stream_raw(text):
            audio_data.append(audio_chunk)

        # Combine and resample
        audio = np.concatenate(audio_data)

        # Resample to target rate (Plivo)
        if target_sample_rate != self.sample_rate:
            audio = soxr.resample(
                audio,
                self.sample_rate,
                target_sample_rate,
            )

        # Convert to bytes (16-bit PCM)
        audio_bytes = (audio * 32767).astype(np.int16).tobytes()

        # Yield in chunks for streaming
        chunk_size = target_sample_rate // 10  # 100ms chunks
        for i in range(0, len(audio_bytes), chunk_size * 2):
            yield audio_bytes[i:i + chunk_size * 2]
```

## TTS: Edge TTS Fallback

```python
# src/services/tts/edge.py
import edge_tts
from typing import AsyncIterator
import soxr
import numpy as np
from loguru import logger
import os

class EdgeTTS:
    """Edge TTS fallback - FEATURE FLAGGED."""

    def __init__(self, voice: str = "hi-IN-SwaraNeural"):
        self.voice = voice
        self.enabled = os.environ.get("EDGE_TTS_ENABLED", "false").lower() == "true"

    async def synthesize_stream(
        self,
        text: str,
        target_sample_rate: int = 8000,
    ) -> AsyncIterator[bytes]:
        """Synthesize using Edge TTS (if enabled)."""
        if not self.enabled:
            raise RuntimeError("Edge TTS is disabled. Set EDGE_TTS_ENABLED=true")

        logger.warning("Using Edge TTS fallback (unofficial API)")

        communicate = edge_tts.Communicate(text, self.voice)

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                # Edge TTS returns MP3, need to decode and resample
                # ... decode MP3 to PCM
                # ... resample to target_sample_rate
                yield processed_audio
```

## Pipeline Orchestrator

```python
# src/core/pipeline.py
from src.services.stt.deepgram import DeepgramSTT
from src.services.llm.groq import GroqLLM
from src.services.tts.piper import PiperTTS
from src.core.session import CallSession
from src.core.context import ConversationContext
from loguru import logger
import asyncio
import time

class VoicePipeline:
    def __init__(
        self,
        stt: DeepgramSTT,
        llm: GroqLLM,
        tts: PiperTTS,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts

    async def process_turn(
        self,
        session: CallSession,
        context: ConversationContext,
        user_transcript: str,
        send_audio: callable,
    ) -> None:
        """Process one conversation turn with latency tracking."""
        turn_start = time.perf_counter()

        # Log STT completion
        stt_time = time.perf_counter()
        logger.info(f"STT latency: {(stt_time - turn_start) * 1000:.0f}ms")

        # Stream LLM response
        llm_start = time.perf_counter()
        full_response = ""
        first_token = True

        async for token in self.llm.stream_response(
            system_prompt=context.system_prompt,
            conversation_history=context.history,
            user_message=user_transcript,
        ):
            if first_token:
                llm_first_token = time.perf_counter()
                logger.info(f"LLM first token: {(llm_first_token - llm_start) * 1000:.0f}ms")
                first_token = False

            full_response += token

            # Sentence-level TTS streaming
            if self._is_sentence_end(full_response):
                sentence = self._extract_sentence(full_response)
                full_response = full_response[len(sentence):]

                # Stream TTS audio
                tts_start = time.perf_counter()
                first_chunk = True
                async for audio_chunk in self.tts.synthesize_stream(sentence):
                    if first_chunk:
                        logger.info(f"TTS first chunk: {(time.perf_counter() - tts_start) * 1000:.0f}ms")
                        first_chunk = False
                    await send_audio(audio_chunk)

        # Update context
        context.add_turn("user", user_transcript)
        context.add_turn("assistant", full_response)

        total_time = time.perf_counter() - turn_start
        logger.info(f"Turn total: {total_time * 1000:.0f}ms")

    def _is_sentence_end(self, text: str) -> bool:
        """Check if text ends with sentence-ending punctuation."""
        return text.rstrip().endswith((".", "!", "?", "।"))

    def _extract_sentence(self, text: str) -> str:
        """Extract the first complete sentence."""
        for i, char in enumerate(text):
            if char in ".!?।":
                return text[:i + 1]
        return text
```

## Barge-in Handling (from PRD 5.4)

```python
# In pipeline.py or separate handler

async def handle_barge_in(
    self,
    session: CallSession,
    tts_task: asyncio.Task,
) -> None:
    """Handle caller interruption.

    From PRD:
    - VAD threshold: 300ms of speech
    - Ignore audio < 200ms (noise)
    - Stop TTS within 100ms
    """
    if session.is_tts_playing and session.speech_duration > 0.3:
        # Valid barge-in detected
        logger.info("Barge-in detected, stopping TTS")

        # Cancel TTS immediately
        tts_task.cancel()
        session.is_tts_playing = False

        # Flush any queued audio
        await session.flush_audio_queue()
```

## Audio Format Handling

```python
# Audio format notes from TECH_STACK.md Section 5

PLIVO_INCOMING = {
    "sample_rate": 8000,  # or 16000
    "channels": 1,
    "format": "mulaw",  # or "pcm"
}

DEEPGRAM_INPUT = {
    "sample_rate": 16000,  # recommended
    "channels": 1,
    "format": "pcm",
}

PIPER_OUTPUT = {
    "sample_rate": 22050,  # typical
    "channels": 1,
    "format": "pcm",
}

def resample_for_deepgram(plivo_audio: bytes) -> bytes:
    """Resample Plivo 8kHz to Deepgram 16kHz."""
    audio = np.frombuffer(plivo_audio, dtype=np.int16)
    resampled = soxr.resample(audio, 8000, 16000)
    return resampled.astype(np.int16).tobytes()

def resample_for_plivo(tts_audio: bytes, tts_rate: int = 22050) -> bytes:
    """Resample TTS output to Plivo 8kHz."""
    audio = np.frombuffer(tts_audio, dtype=np.int16)
    resampled = soxr.resample(audio, tts_rate, 8000)
    return resampled.astype(np.int16).tobytes()
```

## Language Detection (from PRD 5.2)

```python
# src/core/context.py

class LanguageDetector:
    """Detect and track caller's language preference."""

    def __init__(self):
        self.detected_language: str | None = None
        self.confidence: float = 0.0

    def update_from_deepgram(self, result: dict) -> None:
        """Update from Deepgram's language detection."""
        if "detected_language" in result:
            lang = result["detected_language"]
            conf = result.get("language_confidence", 0.5)

            # Thresholds from PRD 5.2.1
            if conf > 0.85:
                # High confidence - switch immediately
                self.detected_language = lang
                self.confidence = conf
            elif conf > 0.70:
                # Medium confidence - switch but monitor
                self.detected_language = lang
                self.confidence = conf
            else:
                # Low confidence - stay in Hindi default
                if self.detected_language is None:
                    self.detected_language = "hi"
                    self.confidence = 0.5

    def get_tts_voice(self) -> str:
        """Get appropriate TTS voice for detected language."""
        voice_map = {
            "hi": "hi_IN-female",  # Hindi
            "en": "en_IN-female",  # English (Indian)
            "hinglish": "hi_IN-female",  # Hinglish uses Hindi voice
        }
        return voice_map.get(self.detected_language, "hi_IN-female")
```

## Testing Voice Pipeline

```python
# tests/test_pipeline.py
from ward import test
import asyncio

@test("Pipeline latency meets P50 target")
async def _():
    pipeline = VoicePipeline(...)

    start = time.perf_counter()
    await pipeline.process_turn(
        session=mock_session,
        context=mock_context,
        user_transcript="Table book karni hai",
        send_audio=mock_send,
    )
    latency = time.perf_counter() - start

    assert latency < 0.5  # P50 target: 500ms
```

## Checklist for Voice Components

- [ ] STT service handles Hindi/English/Hinglish
- [ ] LLM responses are streamed (first token < 300ms)
- [ ] TTS synthesis is streamed (first chunk < 200ms)
- [ ] Audio resampling handles format conversions
- [ ] Barge-in detection works (300ms threshold)
- [ ] Language detection updates TTS voice
- [ ] All latencies are logged per turn
- [ ] Error handling doesn't crash the call
