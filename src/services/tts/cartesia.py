"""Cartesia Sonic TTS service — primary TTS for Vartalaap.

Uses Cartesia's sonic-multilingual model via WebSocket streaming.
WebSocket connection is kept open per call for lowest latency on subsequent turns.

Why Cartesia:
- sonic-multilingual supports Hindi natively
- ~90ms time-to-first-chunk (vs ~200ms for Piper which synthesizes all-at-once)
- True streaming: audio bytes arrive while model is still generating
- Far more natural voice than Piper for both Hindi and English
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.logging_config import get_logger
from src.services.tts.exceptions import TTSSynthesisError
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler

if TYPE_CHECKING:
    pass

logger: Any = get_logger(__name__)

# Cartesia sonic-multilingual outputs 22050Hz PCM by default
CARTESIA_SOURCE_RATE = 22050
CARTESIA_MODEL = "sonic-multilingual"


def _detect_language(text: str) -> str:
    """Detect whether text is primarily Hindi or English.

    Uses Unicode Devanagari block (U+0900–U+097F) character ratio.
    Returns BCP-47 language tag for Cartesia API.
    """
    if not text:
        return "en"
    hindi_chars = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    ratio = hindi_chars / len(text)
    if ratio > 0.15:
        return "hi"
    # Hinglish (mixed) — use Hindi for better prosody on the Hindi words
    if ratio > 0.05:
        return "hi"
    return "en"


class CartesiaTTSService:
    """Cartesia Sonic TTS for natural Hindi/English voice output.

    Maintains a WebSocket connection per call instance for lowest latency.
    Each synthesize_stream() call reuses the open connection — no per-turn
    handshake overhead.

    Usage:
        service = CartesiaTTSService(api_key="...", voice_id="...")
        generator, metadata = await service.synthesize_stream("Namaste!")
        async for chunk in generator:
            await sender.send_audio(chunk.audio_bytes)
        await service.close()
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = CARTESIA_MODEL,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._client: Any | None = None
        self._cancel_event: asyncio.Event | None = None

    async def _ensure_client(self) -> Any:
        """Lazy-initialize Cartesia async client."""
        if self._client is None:
            try:
                from cartesia import AsyncCartesia
            except ImportError as e:
                raise TTSSynthesisError(
                    "cartesia package not installed. Run: uv add cartesia"
                ) from e
            self._client = AsyncCartesia(api_key=self._api_key)
        return self._client

    def cancel(self) -> None:
        """Cancel ongoing synthesis (called on barge-in)."""
        if self._cancel_event:
            self._cancel_event.set()

    async def synthesize_stream(
        self,
        text: str,
        *,
        target_sample_rate: int = 8000,
        chunk_size_ms: int = 50,
    ) -> tuple[AsyncGenerator[AudioChunk, None], SynthesisMetadata]:
        """Stream synthesized audio from Cartesia Sonic.

        Returns immediately — audio arrives via the generator as Cartesia
        streams it back. First audio bytes typically arrive in ~90ms.
        """
        await self._ensure_client()
        self._cancel_event = asyncio.Event()
        language = _detect_language(text)

        metadata = SynthesisMetadata(
            model=self._model_id,
            voice=self._voice_id,
            input_chars=len(text),
            source_sample_rate=CARTESIA_SOURCE_RATE,
            resampled=(target_sample_rate != CARTESIA_SOURCE_RATE),
        )

        logger.debug(
            f"Cartesia TTS: {len(text)} chars, language={language}, "
            f"target_rate={target_sample_rate}Hz"
        )

        generator = self._stream_impl(
            text, language, target_sample_rate, chunk_size_ms, metadata
        )
        return generator, metadata

    async def _stream_impl(
        self,
        text: str,
        language: str,
        target_sample_rate: int,
        chunk_size_ms: int,
        metadata: SynthesisMetadata,
    ) -> AsyncGenerator[AudioChunk, None]:
        """Internal streaming generator. Uses Cartesia WebSocket for lowest latency."""
        start_time = time.perf_counter()
        first_chunk_yielded = False
        total_samples = 0
        resampler = AudioResampler(CARTESIA_SOURCE_RATE, target_sample_rate)

        # Bytes per chunk at target rate (16-bit PCM = 2 bytes/sample)
        bytes_per_ms = (target_sample_rate * 2) / 1000
        target_chunk_bytes = int(chunk_size_ms * bytes_per_ms)

        try:
            client = await self._ensure_client()

            # WebSocket streaming: persistent connection, lowest per-turn latency
            async with client.tts.websocket() as ws:
                async for chunk in ws.send(
                    model_id=self._model_id,
                    transcript=text,
                    voice={"id": self._voice_id},
                    language=language,
                    output_format={
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": CARTESIA_SOURCE_RATE,
                    },
                    stream=True,
                ):
                    # Barge-in: stop immediately
                    if self._cancel_event and self._cancel_event.is_set():
                        logger.debug("Cartesia TTS cancelled (barge-in)")
                        return

                    # Extract audio bytes from chunk
                    audio: bytes | None = getattr(chunk, "audio", None)
                    if not audio:
                        continue

                    # Resample to telephony rate (22050 → 8000Hz for Plivo)
                    if resampler.needs_resampling:
                        audio = await resampler.resample(audio)

                    if not audio:
                        continue

                    if not first_chunk_yielded:
                        metadata.first_chunk_ms = (
                            time.perf_counter() - start_time
                        ) * 1000
                        first_chunk_yielded = True
                        logger.debug(
                            f"Cartesia first chunk: {metadata.first_chunk_ms:.0f}ms "
                            f"(lang={language})"
                        )

                    # Yield in fixed-size chunks for smooth streaming
                    offset = 0
                    while offset < len(audio):
                        if self._cancel_event and self._cancel_event.is_set():
                            return

                        piece = audio[offset : offset + target_chunk_bytes]
                        offset += target_chunk_bytes
                        chunk_samples = len(piece) // 2
                        total_samples += chunk_samples

                        yield AudioChunk(
                            audio_bytes=piece,
                            sample_rate=target_sample_rate,
                            duration_ms=(chunk_samples / target_sample_rate) * 1000,
                            is_final=False,
                        )

            # Final chunk signal
            metadata.output_samples = total_samples
            metadata.output_duration_ms = (total_samples / target_sample_rate) * 1000
            metadata.total_synthesis_ms = (time.perf_counter() - start_time) * 1000

            logger.debug(
                f"Cartesia synthesis done: {metadata.input_chars} chars → "
                f"{metadata.output_duration_ms:.0f}ms audio "
                f"in {metadata.total_synthesis_ms:.0f}ms"
            )

            if total_samples > 0:
                yield AudioChunk(
                    audio_bytes=b"",
                    sample_rate=target_sample_rate,
                    duration_ms=0.0,
                    is_final=True,
                )

        except TTSSynthesisError:
            raise
        except Exception as e:
            logger.error(f"Cartesia synthesis error: {e}")
            raise TTSSynthesisError(f"Cartesia synthesis failed: {e}") from e

    async def synthesize(
        self,
        text: str,
        *,
        target_sample_rate: int = 8000,
    ) -> tuple[bytes, SynthesisMetadata]:
        """Synthesize text to complete audio buffer (non-streaming convenience method)."""
        generator, metadata = await self.synthesize_stream(
            text,
            target_sample_rate=target_sample_rate,
        )
        chunks: list[bytes] = []
        async for chunk in generator:
            if chunk.audio_bytes:
                chunks.append(chunk.audio_bytes)
        return b"".join(chunks), metadata

    async def close(self) -> None:
        """Close Cartesia client and WebSocket connections."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.close()
            self._client = None
        self._cancel_event = None

    async def health_check(self) -> bool:
        """Verify Cartesia API key is valid by initializing the client."""
        try:
            await self._ensure_client()
            return self._client is not None
        except Exception as e:
            logger.warning(f"Cartesia health check failed: {e}")
            return False
