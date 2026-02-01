"""Call session management."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.context import ConversationManager
from src.core.conversation_state import ConversationPhase, ConversationState
from src.logging_config import get_logger
from src.services.llm.exceptions import LLMConnectionError, LLMRateLimitError
from src.services.llm.extractor import ReservationExtractor
from src.services.llm.groq import GroqService
from src.services.stt.deepgram import DeepgramService
from src.services.stt.protocol import DetectedLanguage, TranscriptChunk

if TYPE_CHECKING:
    from src.core.reservation_flow import ReservationFlow
    from src.services.llm.protocol import StreamMetadata

logger: Any = get_logger(__name__)

# Fallback response when LLM is unavailable
FALLBACK_RESPONSE = (
    "I'm sorry, I'm having trouble right now. "
    "Please hold, or I can have someone call you back on WhatsApp."
)


@dataclass
class CallSession:
    """Manages state for a single phone call.

    Created when call starts, destroyed when call ends.
    Conversation history is persisted to DB on call end.
    """

    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    business_id: str = "himalayan_kitchen"
    caller_id_hash: str | None = None
    greeting_text: str | None = None  # Custom greeting from Business config
    call_start: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Services (initialized in __post_init__)
    _llm: GroqService = field(default_factory=GroqService, init=False, repr=False)
    _stt: DeepgramService = field(default_factory=DeepgramService, init=False, repr=False)
    _conversation: ConversationManager = field(init=False, repr=False)
    _extractor: ReservationExtractor = field(init=False, repr=False)
    _state: ConversationState = field(default_factory=ConversationState, init=False, repr=False)
    _flow: ReservationFlow | None = field(default=None, init=False, repr=False)

    # Caller info for reservation creation
    caller_phone_encrypted: str | None = None

    # Metrics
    total_llm_tokens: int = field(default=0, init=False)
    total_llm_calls: int = field(default=0, init=False)
    total_stt_calls: int = field(default=0, init=False)
    total_audio_seconds: float = field(default=0.0, init=False)
    first_token_latencies: list[float] = field(default_factory=list, init=False, repr=False)
    first_word_latencies: list[float] = field(default_factory=list, init=False, repr=False)
    detected_language: DetectedLanguage = field(
        default=DetectedLanguage.UNKNOWN, init=False
    )

    def __post_init__(self) -> None:
        self._conversation = ConversationManager(
            business_id=self.business_id,
            max_history=10,
        )
        self._extractor = ReservationExtractor(llm_service=self._llm)

    async def process_user_input(
        self,
        transcript: str,
        current_capacity: int | None = None,
    ) -> tuple[str, StreamMetadata]:
        """Process user speech and generate response.

        Args:
            transcript: STT output from user speech
            current_capacity: Current available seats (optional)

        Returns:
            Tuple of (full response text, stream metadata)

        Note:
            Returns a fallback response if LLM is rate-limited or unavailable.
        """
        from src.services.llm.protocol import StreamMetadata

        # Add user message
        self._conversation.add_user_message(transcript)

        # Build context
        context = self._conversation.build_context(
            current_capacity=current_capacity,
        )

        try:
            # Get streaming response
            generator, metadata = await self._llm.stream_chat(
                messages=self._conversation.messages,
                context=context,
                max_tokens=256,
                temperature=0.7,
            )

            # Collect full response (for TTS and history)
            response_parts = []
            async for chunk in generator:
                response_parts.append(chunk)

            full_response = "".join(response_parts)

        except LLMRateLimitError as e:
            logger.warning(f"LLM rate limit hit, retry after {e.retry_after}s")
            full_response = FALLBACK_RESPONSE
            metadata = StreamMetadata(model="fallback")

        except LLMConnectionError as e:
            logger.error(f"LLM connection failed: {e}")
            full_response = FALLBACK_RESPONSE
            metadata = StreamMetadata(model="fallback")

        # Run extraction to get structured data
        extraction = await self._extractor.extract(
            user_message=transcript,
            assistant_response=full_response,
            conversation_history=self._conversation.messages,
        )

        # Process through reservation flow if available
        if extraction and self._flow:
            response_override, self._state = await self._flow.process_extraction(
                extraction, self._state
            )
            if response_override:
                full_response = response_override

        # Add to history
        self._conversation.add_assistant_message(full_response)

        # Cache last response for DTMF repeat
        self._state.last_response = full_response

        # Update metrics
        self.total_llm_calls += 1
        if metadata.total_tokens:
            self.total_llm_tokens += metadata.total_tokens
        if metadata.first_token_ms:
            self.first_token_latencies.append(metadata.first_token_ms)

        return full_response, metadata

    async def stream_response(
        self,
        transcript: str,
        current_capacity: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response chunks for real-time TTS.

        Yields chunks as they arrive from the LLM.
        Falls back to a static response if LLM is unavailable.
        """
        self._conversation.add_user_message(transcript)

        context = self._conversation.build_context(
            current_capacity=current_capacity,
        )

        try:
            generator, metadata = await self._llm.stream_chat(
                messages=self._conversation.messages,
                context=context,
            )

            response_parts = []
            async for chunk in generator:
                response_parts.append(chunk)
                yield chunk

            full_response = "".join(response_parts)

        except LLMRateLimitError as e:
            logger.warning(f"LLM rate limit hit during stream, retry after {e.retry_after}s")
            full_response = FALLBACK_RESPONSE
            yield full_response
            metadata = None

        except LLMConnectionError as e:
            logger.error(f"LLM connection failed during stream: {e}")
            full_response = FALLBACK_RESPONSE
            yield full_response
            metadata = None

        # Run extraction
        extraction = await self._extractor.extract(
            user_message=transcript,
            assistant_response=full_response,
            conversation_history=self._conversation.messages,
        )

        # Process through reservation flow if available
        if extraction and self._flow:
            response_override, self._state = await self._flow.process_extraction(
                extraction, self._state
            )
            # Note: For streaming, we don't yield the override since streaming already happened
            # The state is still updated for future turns

        # Add to history
        self._conversation.add_assistant_message(full_response)

        # Cache last response for DTMF repeat
        self._state.last_response = full_response

        # Update metrics
        self.total_llm_calls += 1
        if metadata and metadata.total_tokens:
            self.total_llm_tokens += metadata.total_tokens
        if metadata and metadata.first_token_ms:
            self.first_token_latencies.append(metadata.first_token_ms)

    async def transcribe_audio(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
    ) -> AsyncGenerator[TranscriptChunk, None]:
        """Transcribe streaming audio to text.

        Yields TranscriptChunk objects as speech is recognized.
        Use is_final to determine when an utterance is complete.

        Args:
            audio_chunks: Async generator yielding raw audio bytes
            sample_rate: Audio sample rate in Hz
            encoding: Audio encoding (linear16 for PCM)

        Yields:
            TranscriptChunk with interim/final transcription results
        """
        self.total_stt_calls += 1

        async for chunk in self._stt.transcribe_stream(
            audio_chunks,
            sample_rate=sample_rate,
            encoding=encoding,
        ):
            # Track first word latency
            if chunk.is_final and self.first_word_latencies == []:
                # First final result
                pass
            if chunk.detected_language != DetectedLanguage.UNKNOWN:
                self.detected_language = chunk.detected_language

            yield chunk

    async def process_audio_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        *,
        current_capacity: int | None = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
    ) -> AsyncGenerator[str, None]:
        """Full pipeline: Audio → STT → LLM → Response.

        Transcribes audio, waits for complete utterance, then generates
        LLM response streamed back as text chunks.

        Args:
            audio_chunks: Async generator yielding raw audio bytes
            current_capacity: Current available seats (for context)
            sample_rate: Audio sample rate in Hz
            encoding: Audio encoding

        Yields:
            Response text chunks from LLM
        """
        # Collect transcript until utterance is complete
        transcript_parts = []

        async for chunk in self.transcribe_audio(
            audio_chunks,
            sample_rate=sample_rate,
            encoding=encoding,
        ):
            if chunk.is_final:
                transcript_parts.append(chunk.text)

            # When speech_final is True, the speaker has finished their turn
            if chunk.speech_final:
                break

        # Combine final transcript parts
        full_transcript = " ".join(transcript_parts).strip()

        if not full_transcript:
            return

        # Generate LLM response
        async for response_chunk in self.stream_response(
            full_transcript,
            current_capacity=current_capacity,
        ):
            yield response_chunk

    def get_metrics(self) -> dict:
        """Get session metrics for logging."""
        avg_llm_latency = (
            sum(self.first_token_latencies) / len(self.first_token_latencies)
            if self.first_token_latencies
            else 0
        )
        avg_stt_latency = (
            sum(self.first_word_latencies) / len(self.first_word_latencies)
            if self.first_word_latencies
            else 0
        )

        return {
            "call_id": self.call_id,
            "total_llm_calls": self.total_llm_calls,
            "total_llm_tokens": self.total_llm_tokens,
            "total_stt_calls": self.total_stt_calls,
            "total_audio_seconds": self.total_audio_seconds,
            "detected_language": self.detected_language.value,
            "avg_first_token_ms": avg_llm_latency,
            "avg_first_word_ms": avg_stt_latency,
            "p50_first_token_ms": self._percentile(self.first_token_latencies, 50),
            "p95_first_token_ms": self._percentile(self.first_token_latencies, 95),
        }

    def _percentile(self, data: list[float], p: int) -> float:
        """Calculate percentile of latency data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]

    def get_transcript(self) -> str:
        """Get conversation transcript for DB storage."""
        return self._conversation.get_transcript()

    def set_reservation_flow(self, flow: ReservationFlow) -> None:
        """Set the reservation flow for this session.

        Should be called after session creation when a database session is available.
        """
        self._flow = flow

    @property
    def state(self) -> ConversationState:
        """Get current conversation state."""
        return self._state

    @property
    def last_response(self) -> str:
        """Get last response for DTMF repeat functionality."""
        return self._state.last_response

    @property
    def is_transferred(self) -> bool:
        """Check if call has been transferred to operator."""
        return self._state.phase == ConversationPhase.TRANSFERRED

    async def handle_confirmation(self, confirmed: bool) -> str | None:
        """Handle user confirmation of reservation.

        Args:
            confirmed: Whether user confirmed the booking

        Returns:
            Response message, or None if no flow/reservation
        """
        if not self._flow or not self._state.pending_reservation:
            return None

        response, self._state = await self._flow.handle_confirmation(
            confirmed=confirmed,
            state=self._state,
            caller_phone_encrypted=self.caller_phone_encrypted,
            call_log_id=self.call_id,
        )

        self._state.last_response = response
        return response

    async def close(self) -> None:
        """Clean up session resources."""
        await self._llm.close()
        await self._stt.close()
        await self._extractor.close()
