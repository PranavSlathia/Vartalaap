"""TTS (Text-to-Speech) service protocol and data types."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """A chunk of synthesized audio.

    Audio is yielded as chunks for streaming playback.
    Each chunk contains raw PCM audio bytes ready for transmission.
    """

    audio_bytes: bytes
    sample_rate: int = 8000  # Target rate after resampling (telephony)
    sample_width: int = 2  # Bytes per sample (2 for 16-bit PCM)
    channels: int = 1
    duration_ms: float = 0.0  # Duration of this chunk
    is_final: bool = False  # True for last chunk
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SynthesisMetadata:
    """Metadata collected during/after synthesis."""

    model: str = ""
    voice: str = ""
    input_chars: int = 0
    output_samples: int = 0
    output_duration_ms: float = 0.0
    first_chunk_ms: float | None = None  # Latency to first audio
    total_synthesis_ms: float | None = None
    resampled: bool = False
    source_sample_rate: int = 0


class TTSService(Protocol):
    """Protocol for TTS (Text-to-Speech) service implementations."""

    async def synthesize_stream(
        self,
        text: str,
        *,
        target_sample_rate: int = 8000,
        chunk_size_ms: int = 100,
    ) -> tuple[AsyncGenerator[AudioChunk, None], SynthesisMetadata]:
        """Synthesize text to streaming audio.

        Args:
            text: Text to synthesize (Hindi/English/Hinglish)
            target_sample_rate: Output sample rate (8000 for Plivo telephony)
            chunk_size_ms: Target duration per chunk (for streaming)

        Returns:
            Tuple of (audio chunk generator, metadata object).
            Metadata is populated after generator exhaustion.
        """
        ...

    async def synthesize(
        self,
        text: str,
        *,
        target_sample_rate: int = 8000,
    ) -> tuple[bytes, SynthesisMetadata]:
        """Synthesize text to complete audio buffer.

        Convenience method for non-streaming use cases.

        Returns:
            Tuple of (complete audio bytes, metadata)
        """
        ...

    async def close(self) -> None:
        """Close any open connections and clean up resources."""
        ...

    async def health_check(self) -> bool:
        """Check if the service is operational."""
        ...
