"""STT (Speech-to-Text) service protocol and data types."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class DetectedLanguage(str, Enum):
    """Detected spoken language."""

    HINDI = "hi"
    ENGLISH = "en"
    HINGLISH = "hi-Latn"  # Hindi written in Latin script (romanized)
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TranscriptChunk:
    """A chunk of transcribed speech.

    Deepgram returns interim results that may change,
    followed by a final result for each utterance.
    """

    text: str
    is_final: bool
    confidence: float = 0.0
    detected_language: DetectedLanguage = DetectedLanguage.UNKNOWN
    start_time: float = 0.0  # seconds from stream start
    end_time: float = 0.0  # seconds from stream start
    speech_final: bool = False  # True when utterance is complete (endpoint detected)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TranscriptMetadata:
    """Metadata collected during transcription session."""

    model: str = ""
    total_audio_seconds: float = 0.0
    total_utterances: int = 0
    avg_confidence: float = 0.0
    detected_languages: list[str] = field(default_factory=list)
    first_word_ms: float | None = None  # Time to first word


class STTService(Protocol):
    """Protocol for STT (Speech-to-Text) service implementations."""

    async def transcribe_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        channels: int = 1,
        language: str = "hi",
    ) -> AsyncGenerator[TranscriptChunk, None]:
        """Transcribe streaming audio and yield transcript chunks.

        Args:
            audio_chunks: Async generator yielding raw audio bytes
            sample_rate: Audio sample rate in Hz (default 16kHz for telephony)
            encoding: Audio encoding (linear16, mulaw, etc.)
            channels: Number of audio channels (1 for mono)
            language: Primary language code (hi for Hindi)

        Yields:
            TranscriptChunk objects for each interim/final result
        """
        ...

    async def close(self) -> None:
        """Close any open connections and clean up resources."""
        ...

    async def health_check(self) -> bool:
        """Check if the service is operational."""
        ...
