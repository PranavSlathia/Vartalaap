"""Voice pipeline orchestrator for real-time call handling.

Orchestrates the full voice pipeline:
- Audio input → STT → LLM → TTS → Audio output
- Supports barge-in (user can interrupt bot speech)
- Tracks metrics for monitoring
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Protocol

from src.config import Settings, get_settings
from src.core.session import CallSession
from src.logging_config import get_logger
from src.observability.metrics import ACTIVE_CALLS, record_call_metrics
from src.services.stt.protocol import TranscriptChunk
from src.services.telephony.plivo import is_speech
from src.services.tts.piper import PiperTTSService

if TYPE_CHECKING:
    pass

logger: Any = get_logger(__name__)

# Per-step timeout budgets (seconds)
STT_TIMEOUT = 10.0  # Max time for speech recognition per utterance
LLM_TIMEOUT = 15.0  # Max time for LLM response generation
TTS_TIMEOUT = 10.0  # Max time for TTS synthesis


class PipelineState(Enum):
    """State machine for voice pipeline."""

    IDLE = auto()  # Waiting for user speech
    LISTENING = auto()  # Receiving user speech (STT active)
    PROCESSING = auto()  # LLM generating response
    SPEAKING = auto()  # TTS playing response
    INTERRUPTED = auto()  # Barge-in detected, cancelling TTS


class AudioSender(Protocol):
    """Protocol for sending audio back to caller."""

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio bytes to caller."""
        ...

    async def clear_audio(self) -> None:
        """Clear any buffered audio (for barge-in)."""
        ...


@dataclass
class PipelineConfig:
    """Configuration for voice pipeline."""

    # Audio settings
    input_sample_rate: int = 16000
    output_sample_rate: int = 8000
    input_encoding: str = "linear16"

    # VAD settings
    barge_in_enabled: bool = True
    barge_in_threshold: float = 500.0
    speech_timeout_ms: float = 1000.0  # Silence before considering utterance complete

    # Greeting
    greeting_text: str = "Namaste! Himalayan Kitchen mein aapka swagat hai."

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> PipelineConfig:
        """Create config from application settings."""
        s = settings or get_settings()
        return cls(
            input_sample_rate=s.plivo_sample_rate,
            output_sample_rate=s.tts_target_sample_rate,
            input_encoding="linear16" if s.plivo_audio_format == "linear16" else "mulaw",
            barge_in_enabled=s.barge_in_enabled,
            barge_in_threshold=s.barge_in_threshold,
            greeting_text=s.greeting_text,
        )


@dataclass
class PipelineMetrics:
    """Metrics collected during pipeline execution."""

    total_audio_received_bytes: int = 0
    total_audio_sent_bytes: int = 0
    total_turns: int = 0
    barge_in_count: int = 0

    # Latency tracking
    stt_latencies_ms: list[float] = field(default_factory=list)
    llm_first_token_ms: list[float] = field(default_factory=list)
    tts_first_chunk_ms: list[float] = field(default_factory=list)

    # Timestamps
    pipeline_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        duration = (datetime.now(UTC) - self.pipeline_start).total_seconds()
        return {
            "total_audio_received_bytes": self.total_audio_received_bytes,
            "total_audio_sent_bytes": self.total_audio_sent_bytes,
            "total_turns": self.total_turns,
            "barge_in_count": self.barge_in_count,
            "duration_seconds": duration,
            "avg_stt_latency_ms": self._avg(self.stt_latencies_ms),
            "avg_llm_first_token_ms": self._avg(self.llm_first_token_ms),
            "avg_tts_first_chunk_ms": self._avg(self.tts_first_chunk_ms),
        }

    def _avg(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0


class AudioBuffer:
    """Thread-safe async audio buffer for streaming."""

    def __init__(self, max_size: int = 100) -> None:
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=max_size)
        self._closed = False

    def append(self, chunk: bytes) -> None:
        """Add audio chunk to buffer."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            # Drop oldest chunk to make room
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except asyncio.QueueEmpty:
                pass

    async def get(self, timeout: float = 1.0) -> bytes | None:
        """Get next audio chunk from buffer.

        Returns None on timeout or when closed.
        """
        if self._closed and self._queue.empty():
            return None
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def drain(self) -> AsyncGenerator[bytes, None]:
        """Drain all buffered audio chunks."""
        while not self._queue.empty():
            try:
                chunk = self._queue.get_nowait()
                if chunk is not None:
                    yield chunk
            except asyncio.QueueEmpty:
                break

    def clear(self) -> None:
        """Clear all buffered audio."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def close(self) -> None:
        """Close buffer and signal end of stream."""
        self._closed = True
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

    @property
    def size(self) -> int:
        """Current buffer size."""
        return self._queue.qsize()


class VoicePipeline:
    """Orchestrates STT → LLM → TTS voice pipeline with streaming.

    Manages the full lifecycle of a voice interaction:
    1. Receives audio from Plivo
    2. Transcribes via Deepgram (STT)
    3. Generates response via Groq (LLM)
    4. Synthesizes speech via Piper (TTS)
    5. Sends audio back to Plivo

    Supports barge-in (user can interrupt bot speech).
    """

    def __init__(
        self,
        session: CallSession,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._config = PipelineConfig.from_settings(self._settings)
        self._metrics = PipelineMetrics()

        # State
        self._state = PipelineState.IDLE
        self._state_lock = asyncio.Lock()

        # TTS service (use existing session's STT, create own TTS)
        self._tts = PiperTTSService(settings=self._settings)

        # Audio handling
        self._audio_buffer = AudioBuffer()
        self._tts_cancel_event = asyncio.Event()

        # Background tasks
        self._stt_task: asyncio.Task[None] | None = None

        # Transcript accumulator
        self._current_transcript: list[str] = []
        self._transcript_lock = asyncio.Lock()

        # Track active call in Prometheus metrics
        ACTIVE_CALLS.labels(business_id=session.business_id).inc()

    @property
    def state(self) -> PipelineState:
        """Current pipeline state."""
        return self._state

    @property
    def metrics(self) -> PipelineMetrics:
        """Pipeline metrics."""
        return self._metrics

    async def configure(
        self,
        input_sample_rate: int | None = None,
        output_sample_rate: int | None = None,
        input_encoding: str | None = None,
    ) -> None:
        """Configure pipeline for specific audio format.

        Called when call connects to set up audio parameters.
        """
        if input_sample_rate:
            self._config.input_sample_rate = input_sample_rate
        if output_sample_rate:
            self._config.output_sample_rate = output_sample_rate
        if input_encoding:
            self._config.input_encoding = input_encoding

        logger.info(
            f"Pipeline configured: {self._config.input_sample_rate}Hz "
            f"{self._config.input_encoding} → {self._config.output_sample_rate}Hz"
        )

    async def send_greeting(self, sender: AudioSender) -> None:
        """Send initial greeting when call connects."""
        logger.info(f"Sending greeting for call {self._session.call_id}")
        await self._speak(self._config.greeting_text, sender)

    async def process_audio_chunk(
        self,
        audio_bytes: bytes,
        sender: AudioSender,
    ) -> None:
        """Process incoming audio chunk from caller.

        This is called for each audio chunk received from Plivo.
        Handles buffering, STT processing, and barge-in detection.
        """
        self._metrics.total_audio_received_bytes += len(audio_bytes)
        self._metrics.last_activity = datetime.now(UTC)

        # Check for barge-in: user speaking while bot is speaking
        if (
            self._state == PipelineState.SPEAKING
            and self._config.barge_in_enabled
            and is_speech(audio_bytes, threshold=self._config.barge_in_threshold)
        ):
            await self._handle_barge_in(sender)

        # Buffer audio for STT processing
        self._audio_buffer.append(audio_bytes)

        # Start STT processing if idle
        if self._state == PipelineState.IDLE:
            await self._set_state(PipelineState.LISTENING)
            self._start_stt_processing(sender)

    async def _set_state(self, new_state: PipelineState) -> None:
        """Thread-safe state transition."""
        async with self._state_lock:
            old_state = self._state
            self._state = new_state
            logger.debug(f"Pipeline state: {old_state.name} → {new_state.name}")

    async def _handle_barge_in(self, sender: AudioSender) -> None:
        """Handle user interrupting bot speech."""
        if self._state != PipelineState.SPEAKING:
            return

        logger.info(f"Barge-in detected for call {self._session.call_id}")
        self._metrics.barge_in_count += 1

        # Signal TTS cancellation
        self._tts_cancel_event.set()
        self._tts.cancel()

        # Clear Plivo audio buffer
        await sender.clear_audio()

        # Reset to listening state
        await self._set_state(PipelineState.LISTENING)
        self._tts_cancel_event.clear()

    def _start_stt_processing(self, sender: AudioSender) -> None:
        """Start background STT processing task."""
        if self._stt_task and not self._stt_task.done():
            return

        self._stt_task = asyncio.create_task(
            self._stt_pipeline(sender),
            name=f"stt-{self._session.call_id}",
        )

    async def _stt_pipeline(self, sender: AudioSender) -> None:
        """Background STT processing pipeline.

        Continuously processes buffered audio, transcribes it,
        and triggers LLM response when utterance is complete.
        """
        async def audio_generator() -> AsyncGenerator[bytes, None]:
            """Generate audio chunks from buffer."""
            while True:
                chunk = await self._audio_buffer.get(timeout=self._config.speech_timeout_ms / 1000)
                if chunk is None:
                    # Timeout or closed - check if we have a pending transcript
                    async with self._transcript_lock:
                        if self._current_transcript:
                            # Process what we have
                            break
                    # No transcript, keep waiting
                    if self._state == PipelineState.LISTENING:
                        continue
                    break
                yield chunk

        try:
            async for chunk in self._session.transcribe_audio(
                audio_generator(),
                sample_rate=self._config.input_sample_rate,
                encoding=self._config.input_encoding,
            ):
                await self._process_transcript_chunk(chunk, sender)

        except Exception as e:
            logger.error(f"STT pipeline error: {e}")
            await self._set_state(PipelineState.IDLE)

    async def _process_transcript_chunk(
        self,
        chunk: TranscriptChunk,
        sender: AudioSender,
    ) -> None:
        """Process a transcript chunk from STT."""
        async with self._transcript_lock:
            if chunk.is_final and chunk.text.strip():
                self._current_transcript.append(chunk.text)

            # End of utterance detected
            if chunk.speech_final:
                full_transcript = " ".join(self._current_transcript).strip()
                self._current_transcript = []

                if full_transcript:
                    self._metrics.total_turns += 1
                    await self._process_transcript(full_transcript, sender)

    async def _process_transcript(
        self,
        transcript: str,
        sender: AudioSender,
    ) -> None:
        """Process complete transcript through LLM and TTS."""
        logger.info(f"Processing transcript: {transcript[:50]}...")

        await self._set_state(PipelineState.PROCESSING)

        # Get LLM response with timeout
        response_parts: list[str] = []
        try:
            async def collect_response() -> list[str]:
                parts: list[str] = []
                async for chunk in self._session.stream_response(transcript):
                    parts.append(chunk)
                return parts

            response_parts = await asyncio.wait_for(
                collect_response(),
                timeout=LLM_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(f"LLM timeout exceeded ({LLM_TIMEOUT}s)")
            response_parts = ["Maaf kijiye, thoda time lag raha hai. Kripya dobara bolein."]
        except Exception as e:
            logger.error(f"LLM error: {e}")
            response_parts = ["Sorry, I'm having trouble. Please try again."]

        full_response = "".join(response_parts)

        if full_response:
            await self._speak(full_response, sender)

        await self._set_state(PipelineState.IDLE)

    async def _speak(
        self,
        text: str,
        sender: AudioSender,
    ) -> None:
        """Synthesize text and stream to caller."""
        await self._set_state(PipelineState.SPEAKING)

        try:
            # TTS synthesis with timeout
            generator, metadata = await asyncio.wait_for(
                self._tts.synthesize_stream(
                    text,
                    target_sample_rate=self._config.output_sample_rate,
                ),
                timeout=TTS_TIMEOUT,
            )

            if metadata.first_chunk_ms:
                self._metrics.tts_first_chunk_ms.append(metadata.first_chunk_ms)

            async for chunk in generator:
                # Check for cancellation (barge-in)
                if self._tts_cancel_event.is_set():
                    logger.debug("TTS cancelled due to barge-in")
                    break

                audio_bytes = chunk.audio_bytes
                self._metrics.total_audio_sent_bytes += len(audio_bytes)

                # Send to caller
                await sender.send_audio(audio_bytes)

                # Small yield to allow barge-in detection
                await asyncio.sleep(0.001)

        except asyncio.TimeoutError:
            logger.error(f"TTS timeout exceeded ({TTS_TIMEOUT}s) for text: {text[:50]}...")

        except Exception as e:
            logger.error(f"TTS error: {e}")

        finally:
            if self._state == PipelineState.SPEAKING:
                await self._set_state(PipelineState.IDLE)

    async def handle_dtmf(
        self,
        digit: str,
        sender: AudioSender,
    ) -> None:
        """Handle DTMF digit press.

        0 = Transfer to operator (creates WhatsApp followup)
        * = Repeat last response
        # = Confirm reservation (if awaiting confirmation)
        """
        logger.info(f"DTMF received: {digit} for call {self._session.call_id}")

        if digit == "0":
            await self._request_operator_transfer()
            await self._speak(
                "Main aapko operator se connect kar rahi hoon. "
                "Kripya hold karein, ya hum aapko WhatsApp par call back karenge.",
                sender,
            )

        elif digit == "*":
            # Repeat last response
            last_response = self._session.last_response
            if last_response:
                await self._speak(last_response, sender)
            else:
                await self._speak(
                    "Kya aap apna sawaal dobara pooch sakte hain?",
                    sender,
                )

        elif digit == "#":
            # Confirm reservation if awaiting confirmation
            from src.core.conversation_state import ConversationPhase

            if self._session.state.phase == ConversationPhase.AWAITING_CONFIRMATION:
                response = await self._session.handle_confirmation(confirmed=True)
                if response:
                    await self._speak(response, sender)
            else:
                await self._speak(
                    "Abhi koi confirmation pending nahi hai.",
                    sender,
                )

    async def _request_operator_transfer(self) -> None:
        """Create WhatsApp followup for operator callback.

        This marks the session as transferred and creates a record
        so staff can call back the customer.
        """
        from src.core.conversation_state import ConversationPhase

        # Mark session as transferred
        self._session.state.transition_to(ConversationPhase.TRANSFERRED)

        # Create followup record for operator callback
        try:
            from src.db.repositories.calls import AsyncCallLogRepository
            from src.db.session import get_session_context

            async with get_session_context() as db_session:
                repo = AsyncCallLogRepository(db_session)
                transcript_excerpt = self._session.get_transcript()[:200]
                await repo.create_followup(
                    business_id=self._session.business_id,
                    customer_phone_encrypted=self._session.caller_phone_encrypted or "",
                    reason="callback_request",
                    summary=f"Operator transfer requested. Transcript: {transcript_excerpt}",
                    call_log_id=self._session.call_id,
                )
                await db_session.commit()

            logger.info(f"Created operator transfer followup for call {self._session.call_id}")

        except Exception as e:
            logger.error(f"Failed to create operator followup: {e}")

    async def finalize(self) -> dict[str, Any]:
        """Clean up pipeline resources and return metrics.

        Call this when the call ends.
        """
        logger.info(f"Finalizing pipeline for call {self._session.call_id}")

        # Cancel any running tasks
        if self._stt_task and not self._stt_task.done():
            self._stt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stt_task

        # Close audio buffer
        self._audio_buffer.close()

        # Close TTS
        await self._tts.close()

        # Close session
        await self._session.close()

        # Return combined metrics
        pipeline_metrics = self._metrics.to_dict()
        session_metrics = self._session.get_metrics()

        # Record Prometheus metrics
        ACTIVE_CALLS.labels(business_id=self._session.business_id).dec()

        # Determine outcome based on metrics
        outcome = "resolved"
        if pipeline_metrics.get("total_turns", 0) == 0:
            outcome = "dropped"

        record_call_metrics(
            outcome=outcome,
            business_id=self._session.business_id,
            duration_seconds=pipeline_metrics.get("duration_seconds", 0),
            stt_latency_ms=pipeline_metrics.get("avg_stt_latency_ms"),
            llm_latency_ms=pipeline_metrics.get("avg_llm_first_token_ms"),
            tts_latency_ms=pipeline_metrics.get("avg_tts_first_chunk_ms"),
            barge_in_count=pipeline_metrics.get("barge_in_count", 0),
        )

        return {
            **pipeline_metrics,
            **session_metrics,
            "transcript": self._session.get_transcript(),
        }

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics without finalizing."""
        return self._metrics.to_dict()
