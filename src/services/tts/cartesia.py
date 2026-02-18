"""Cartesia Sonic TTS service — primary TTS for Vartalaap.

Uses Cartesia's sonic-3 model via raw WebSocket streaming.
Connects directly to wss://api.cartesia.ai/tts/websocket — does NOT use the
AsyncCartesia SDK client for the streaming path (matches Pipecat's approach).

Why Cartesia:
- sonic-3 supports Hindi natively
- ~90ms time-to-first-chunk via persistent WebSocket
- True streaming: audio bytes arrive while model is still generating
- Far more natural voice than alternatives for Hindi and Hinglish
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.logging_config import get_logger
from src.services.tts.exceptions import TTSSynthesisError
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler

if TYPE_CHECKING:
    pass

logger: Any = get_logger(__name__)

# Cartesia sonic-3 outputs 22050Hz PCM by default
CARTESIA_SOURCE_RATE = 22050
CARTESIA_MODEL = "sonic-3"
CARTESIA_VERSION = "2025-04-16"
CARTESIA_WS_URL = "wss://api.cartesia.ai/tts/websocket"


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
        self._cancel_event: asyncio.Event | None = None

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
        """Stream audio via raw WebSocket — same approach as Pipecat's CartesiaTTSService.

        Bypasses the AsyncCartesia SDK client entirely for the streaming path.
        Connects directly to the Cartesia WebSocket API with JSON messages.
        """
        from websockets.asyncio.client import connect as ws_connect

        start_time = time.perf_counter()
        first_chunk_yielded = False
        total_samples = 0
        resampler = AudioResampler(CARTESIA_SOURCE_RATE, target_sample_rate)

        bytes_per_ms = (target_sample_rate * 2) / 1000
        target_chunk_bytes = int(chunk_size_ms * bytes_per_ms)
        context_id = str(uuid.uuid4())

        url = f"{CARTESIA_WS_URL}?api_key={self._api_key}&cartesia_version={CARTESIA_VERSION}"

        try:
            async with ws_connect(url) as ws:
                # Send TTS request as JSON (Pipecat-compatible message format)
                msg = json.dumps({
                    "transcript": text,
                    "model_id": self._model_id,
                    "voice": {"mode": "id", "id": self._voice_id},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": CARTESIA_SOURCE_RATE,
                    },
                    "language": language,
                    "context_id": context_id,
                    "continue": False,
                    "add_timestamps": False,
                })
                await ws.send(msg)

                async for raw_msg in ws:
                    # Barge-in: cancel and stop
                    if self._cancel_event and self._cancel_event.is_set():
                        logger.debug("Cartesia TTS cancelled (barge-in)")
                        with contextlib.suppress(Exception):
                            await ws.send(json.dumps({"context_id": context_id, "cancel": True}))
                        return

                    data = json.loads(raw_msg)
                    msg_type = data.get("type")

                    if msg_type == "done":
                        break

                    if msg_type == "error":
                        raise TTSSynthesisError(f"Cartesia error: {data.get('error', data)}")

                    if msg_type != "chunk":
                        continue

                    # data["data"] is base64-encoded raw PCM
                    audio: bytes = base64.b64decode(data["data"])

                    if resampler.needs_resampling:
                        audio = await resampler.resample(audio)

                    if not audio:
                        continue

                    if not first_chunk_yielded:
                        metadata.first_chunk_ms = (time.perf_counter() - start_time) * 1000
                        first_chunk_yielded = True
                        logger.debug(
                            f"Cartesia first chunk: {metadata.first_chunk_ms:.0f}ms "
                            f"(lang={language})"
                        )

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
        """No persistent client to close — each synthesis opens/closes its own WebSocket."""
        self._cancel_event = None

    async def health_check(self) -> bool:
        """Verify Cartesia API key is set."""
        return bool(self._api_key)
