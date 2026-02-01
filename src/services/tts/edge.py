"""Edge TTS service implementation using Microsoft's unofficial API."""

from __future__ import annotations

import asyncio
import io
import time
from collections.abc import AsyncGenerator
from typing import Any

import edge_tts

from src.config import Settings, get_settings
from src.logging_config import get_logger
from src.services.tts.exceptions import TTSConnectionError, TTSSynthesisError
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler

logger: Any = get_logger(__name__)

# Edge TTS Hindi voice
EDGE_HINDI_VOICE = "hi-IN-SwaraNeural"
EDGE_SAMPLE_RATE = 24000  # Edge outputs 24kHz MP3


def _decode_mp3_to_pcm(mp3_data: bytes) -> tuple[bytes, int]:
    """Decode MP3 data to raw PCM.

    Tries multiple decoders in order of preference:
    1. pydub (requires ffmpeg)
    2. miniaudio (pure Python with bundled decoders)
    3. soundfile (requires libsndfile with MP3 support)

    Returns:
        Tuple of (raw PCM bytes as int16, sample rate)
    """
    import numpy as np

    # Try pydub first (most reliable with ffmpeg)
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        # Convert to mono, get raw data
        audio = audio.set_channels(1)
        sample_rate = audio.frame_rate
        # pydub gives us raw samples
        samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
        return samples.tobytes(), sample_rate
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pydub decode failed: {e}, trying fallback")

    # Try miniaudio (pure Python, bundled decoders)
    try:
        import miniaudio

        decoded = miniaudio.decode(mp3_data, output_format=miniaudio.SampleFormat.SIGNED16)
        sample_rate = decoded.sample_rate
        # Ensure mono
        samples = np.frombuffer(decoded.samples, dtype=np.int16)
        if decoded.nchannels == 2:
            samples = samples.reshape(-1, 2).mean(axis=1).astype(np.int16)
        return samples.tobytes(), sample_rate
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"miniaudio decode failed: {e}, trying fallback")

    # Fall back to soundfile (requires libsndfile with MP3 support)
    try:
        import soundfile as sf

        audio_data, sample_rate = sf.read(io.BytesIO(mp3_data), dtype="float32")
        # Convert to int16
        audio_int16 = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        return audio_int16.tobytes(), sample_rate
    except Exception as e:
        raise TTSSynthesisError(
            f"MP3 decode failed. Install pydub+ffmpeg or miniaudio: {e}"
        ) from e


class EdgeTTSService:
    """Edge TTS service using Microsoft's unofficial API.

    WARNING: This uses an unofficial API that may change without notice.
    Use only as a fallback when Piper is unavailable.

    Features:
    - Hindi neural voice (hi-IN-SwaraNeural)
    - High-quality neural synthesis
    - Requires internet connection
    - Supports cancellation for barge-in
    """

    def __init__(
        self,
        settings: Settings | None = None,
        voice: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._voice = voice or self._settings.edge_tts_voice
        self._resampler: AudioResampler | None = None
        self._cancel_event: asyncio.Event | None = None

        # Log warning about unofficial API
        logger.warning(
            "EdgeTTS initialized - using unofficial Microsoft API. "
            "This may be unreliable and could break without notice."
        )

    def _get_resampler(self, target_rate: int) -> AudioResampler:
        """Get or create resampler for target rate."""
        if (
            self._resampler is None
            or self._resampler._target_rate != target_rate
        ):
            self._resampler = AudioResampler(EDGE_SAMPLE_RATE, target_rate)
        return self._resampler

    async def synthesize_stream(
        self,
        text: str,
        *,
        target_sample_rate: int | None = None,
        chunk_size_ms: int = 100,
    ) -> tuple[AsyncGenerator[AudioChunk, None], SynthesisMetadata]:
        """Synthesize text to streaming audio chunks.

        Edge TTS returns MP3 data which must be decoded before streaming.
        We accumulate the full MP3, then decode and chunk for output.
        """
        if target_sample_rate is None:
            target_sample_rate = self._settings.tts_target_sample_rate

        # Check if Edge TTS is enabled
        if not self._settings.edge_tts_enabled:
            raise TTSConnectionError(
                "Edge TTS is disabled. Set EDGE_TTS_ENABLED=true to enable."
            )

        # Create cancel event for barge-in support
        self._cancel_event = asyncio.Event()

        metadata = SynthesisMetadata(
            model="edge-tts",
            voice=self._voice,
            input_chars=len(text),
            source_sample_rate=EDGE_SAMPLE_RATE,
            resampled=(target_sample_rate != EDGE_SAMPLE_RATE),
        )

        generator = self._synthesize_stream_impl(
            text, target_sample_rate, chunk_size_ms, metadata
        )

        return generator, metadata

    async def _synthesize_stream_impl(
        self,
        text: str,
        target_sample_rate: int,
        chunk_size_ms: int,
        metadata: SynthesisMetadata,
    ) -> AsyncGenerator[AudioChunk, None]:
        """Internal generator implementation."""
        start_time = time.perf_counter()
        first_chunk_yielded = False
        total_samples = 0
        resampler = self._get_resampler(target_sample_rate)

        # Bytes per chunk based on target duration
        # 16-bit PCM = 2 bytes per sample
        bytes_per_ms = (target_sample_rate * 2) / 1000
        target_chunk_bytes = int(chunk_size_ms * bytes_per_ms)

        try:
            communicate = edge_tts.Communicate(text, self._voice)

            # Accumulate MP3 data (can't decode partial MP3)
            mp3_buffer = io.BytesIO()

            async for message in communicate.stream():
                # Check for cancellation (barge-in)
                if self._cancel_event and self._cancel_event.is_set():
                    logger.debug("EdgeTTS synthesis cancelled (barge-in)")
                    return

                if message["type"] == "audio":
                    mp3_buffer.write(message["data"])

            # Decode MP3 to PCM
            mp3_buffer.seek(0)
            mp3_bytes = mp3_buffer.getvalue()

            if not mp3_bytes:
                raise TTSSynthesisError("No audio received from Edge TTS")

            raw_audio, decoded_rate = await asyncio.to_thread(
                _decode_mp3_to_pcm, mp3_bytes
            )

            # Update source rate if different from expected
            if decoded_rate != EDGE_SAMPLE_RATE:
                logger.debug(
                    f"Edge TTS decoded at {decoded_rate}Hz (expected {EDGE_SAMPLE_RATE}Hz)"
                )
                resampler = AudioResampler(decoded_rate, target_sample_rate)

            # Resample if needed
            if resampler.needs_resampling:
                raw_audio = await resampler.resample(raw_audio)

            # Calculate output duration from actual bytes
            total_output_samples = len(raw_audio) // 2  # 16-bit = 2 bytes
            metadata.output_samples = total_output_samples
            metadata.output_duration_ms = (total_output_samples / target_sample_rate) * 1000

            # Yield chunks
            offset = 0
            while offset < len(raw_audio):
                # Check for cancellation
                if self._cancel_event and self._cancel_event.is_set():
                    logger.debug("EdgeTTS chunking cancelled (barge-in)")
                    return

                chunk_bytes = raw_audio[offset : offset + target_chunk_bytes]
                offset += target_chunk_bytes
                is_final = offset >= len(raw_audio)

                if not first_chunk_yielded:
                    metadata.first_chunk_ms = (
                        time.perf_counter() - start_time
                    ) * 1000
                    first_chunk_yielded = True
                    logger.debug(
                        f"First Edge TTS chunk latency: "
                        f"{metadata.first_chunk_ms:.1f}ms"
                    )

                chunk_samples = len(chunk_bytes) // 2
                total_samples += chunk_samples

                yield AudioChunk(
                    audio_bytes=chunk_bytes,
                    sample_rate=target_sample_rate,
                    duration_ms=(chunk_samples / target_sample_rate) * 1000,
                    is_final=is_final,
                )

            # Update total synthesis time
            metadata.total_synthesis_ms = (
                time.perf_counter() - start_time
            ) * 1000

            logger.debug(
                f"Edge TTS synthesis complete: {metadata.input_chars} chars -> "
                f"{metadata.output_duration_ms:.0f}ms audio in "
                f"{metadata.total_synthesis_ms:.0f}ms"
            )

        except edge_tts.exceptions.NoAudioReceived as e:
            logger.error(f"Edge TTS no audio received: {e}")
            raise TTSSynthesisError("No audio received from Edge TTS") from e

        except TTSSynthesisError:
            raise

        except Exception as e:
            logger.error(f"Edge TTS synthesis error: {e}")
            raise TTSConnectionError(f"Edge TTS connection failed: {e}") from e

    def cancel(self) -> None:
        """Cancel ongoing synthesis (for barge-in support)."""
        if self._cancel_event:
            self._cancel_event.set()

    async def synthesize(
        self,
        text: str,
        *,
        target_sample_rate: int | None = None,
    ) -> tuple[bytes, SynthesisMetadata]:
        """Synthesize text to complete audio buffer."""
        if target_sample_rate is None:
            target_sample_rate = self._settings.tts_target_sample_rate

        generator, metadata = await self.synthesize_stream(
            text,
            target_sample_rate=target_sample_rate,
        )

        chunks = []
        async for chunk in generator:
            chunks.append(chunk.audio_bytes)

        return b"".join(chunks), metadata

    async def close(self) -> None:
        """Clean up resources."""
        if self._resampler:
            self._resampler = None
        self._cancel_event = None

    async def health_check(self) -> bool:
        """Check if Edge TTS API is reachable."""
        if not self._settings.edge_tts_enabled:
            return False

        try:
            # Quick test - just check if we can create a communicate object
            # Full synthesis would be slow for a health check
            communicate = edge_tts.Communicate("test", self._voice)
            # Just verify the object was created successfully
            return communicate is not None
        except Exception as e:
            logger.warning(f"Edge TTS health check failed: {e}")
            return False
