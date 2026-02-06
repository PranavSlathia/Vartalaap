"""ElevenLabs TTS service implementation for high-naturalness speech."""

from __future__ import annotations

import asyncio
import io
import time
from collections.abc import AsyncGenerator
from typing import Any

from src.config import Settings, get_settings
from src.logging_config import get_logger
from src.services.tts.edge import _decode_mp3_to_pcm
from src.services.tts.exceptions import TTSConnectionError, TTSSynthesisError
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler

logger: Any = get_logger(__name__)

ELEVENLABS_DEFAULT_VOICE_ID = "9BWtsMINqrJLrRacOk9x"  # Aria
ELEVENLABS_DEFAULT_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_SOURCE_SAMPLE_RATE = 44100


class ElevenLabsTTSService:
    """ElevenLabs TTS service with streaming chunk output."""

    def __init__(
        self,
        settings: Settings | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._voice_id = voice_id or ELEVENLABS_DEFAULT_VOICE_ID
        self._model_id = model_id or ELEVENLABS_DEFAULT_MODEL_ID
        self._resampler: AudioResampler | None = None
        self._cancel_event: asyncio.Event | None = None
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not self._settings.elevenlabs_api_key:
                raise TTSConnectionError("ElevenLabs API key is not configured")
            from elevenlabs import ElevenLabs

            self._client = ElevenLabs(
                api_key=self._settings.elevenlabs_api_key.get_secret_value()
            )
        return self._client

    def _get_resampler(self, target_rate: int) -> AudioResampler:
        if self._resampler is None or self._resampler._target_rate != target_rate:
            self._resampler = AudioResampler(ELEVENLABS_SOURCE_SAMPLE_RATE, target_rate)
        return self._resampler

    async def synthesize_stream(
        self,
        text: str,
        *,
        target_sample_rate: int | None = None,
        chunk_size_ms: int = 100,
    ) -> tuple[AsyncGenerator[AudioChunk, None], SynthesisMetadata]:
        """Synthesize text and return streaming PCM chunks."""
        if target_sample_rate is None:
            target_sample_rate = self._settings.tts_target_sample_rate

        self._cancel_event = asyncio.Event()

        metadata = SynthesisMetadata(
            model="elevenlabs",
            voice=self._voice_id,
            input_chars=len(text),
            source_sample_rate=ELEVENLABS_SOURCE_SAMPLE_RATE,
            resampled=(target_sample_rate != ELEVENLABS_SOURCE_SAMPLE_RATE),
        )

        generator = self._synthesize_stream_impl(
            text=text,
            target_sample_rate=target_sample_rate,
            chunk_size_ms=chunk_size_ms,
            metadata=metadata,
        )
        return generator, metadata

    async def _synthesize_stream_impl(
        self,
        *,
        text: str,
        target_sample_rate: int,
        chunk_size_ms: int,
        metadata: SynthesisMetadata,
    ) -> AsyncGenerator[AudioChunk, None]:
        start_time = time.perf_counter()
        first_chunk_yielded = False
        resampler = self._get_resampler(target_sample_rate)

        bytes_per_ms = (target_sample_rate * 2) / 1000
        target_chunk_bytes = int(chunk_size_ms * bytes_per_ms)

        try:
            mp3_bytes = await asyncio.to_thread(self._synthesize_to_mp3, text)
            if not mp3_bytes:
                raise TTSSynthesisError("No audio received from ElevenLabs")

            raw_audio, decoded_rate = await asyncio.to_thread(_decode_mp3_to_pcm, mp3_bytes)
            if decoded_rate != ELEVENLABS_SOURCE_SAMPLE_RATE:
                resampler = AudioResampler(decoded_rate, target_sample_rate)

            if resampler.needs_resampling:
                raw_audio = await resampler.resample(raw_audio)

            total_output_samples = len(raw_audio) // 2
            metadata.output_samples = total_output_samples
            metadata.output_duration_ms = (total_output_samples / target_sample_rate) * 1000

            offset = 0
            while offset < len(raw_audio):
                if self._cancel_event and self._cancel_event.is_set():
                    logger.debug("ElevenLabs synthesis cancelled (barge-in)")
                    return

                chunk_bytes = raw_audio[offset: offset + target_chunk_bytes]
                offset += target_chunk_bytes
                is_final = offset >= len(raw_audio)

                if not first_chunk_yielded:
                    metadata.first_chunk_ms = (time.perf_counter() - start_time) * 1000
                    first_chunk_yielded = True

                chunk_samples = len(chunk_bytes) // 2
                yield AudioChunk(
                    audio_bytes=chunk_bytes,
                    sample_rate=target_sample_rate,
                    duration_ms=(chunk_samples / target_sample_rate) * 1000,
                    is_final=is_final,
                )

            metadata.total_synthesis_ms = (time.perf_counter() - start_time) * 1000

        except TTSSynthesisError:
            raise
        except Exception as e:
            logger.error(f"ElevenLabs synthesis error: {e}")
            raise TTSConnectionError(f"ElevenLabs connection failed: {e}") from e

    def _synthesize_to_mp3(self, text: str) -> bytes:
        client = self._get_client()

        audio_chunks = client.text_to_speech.convert(
            text=text,
            voice_id=self._voice_id,
            model_id=self._model_id,
            output_format="mp3_44100_128",
        )

        buffer = io.BytesIO()
        for chunk in audio_chunks:
            buffer.write(chunk)
        return buffer.getvalue()

    async def synthesize(
        self,
        text: str,
        *,
        target_sample_rate: int | None = None,
    ) -> tuple[bytes, SynthesisMetadata]:
        if target_sample_rate is None:
            target_sample_rate = self._settings.tts_target_sample_rate

        generator, metadata = await self.synthesize_stream(
            text,
            target_sample_rate=target_sample_rate,
        )
        chunks: list[bytes] = []
        async for chunk in generator:
            chunks.append(chunk.audio_bytes)
        return b"".join(chunks), metadata

    def cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()

    async def close(self) -> None:
        self._resampler = None
        self._cancel_event = None
        self._client = None

    async def health_check(self) -> bool:
        return bool(self._settings.elevenlabs_api_key)
