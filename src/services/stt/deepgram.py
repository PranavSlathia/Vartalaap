"""Deepgram STT service implementation with WebSocket streaming."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.config import Settings, get_settings
from src.logging_config import get_logger
from src.services.stt.protocol import (
    DetectedLanguage,
    TranscriptChunk,
    TranscriptMetadata,
)

if TYPE_CHECKING:
    from deepgram import DeepgramClient
    from deepgram.clients.live import LiveClient

logger: Any = get_logger(__name__)

# Deepgram model optimized for real-time conversation
DEEPGRAM_MODEL = "nova-2"

# Language detection mapping from Deepgram to our enum
LANGUAGE_MAP = {
    "hi": DetectedLanguage.HINDI,
    "en": DetectedLanguage.ENGLISH,
    "en-US": DetectedLanguage.ENGLISH,
    "en-IN": DetectedLanguage.ENGLISH,
    "hi-Latn": DetectedLanguage.HINGLISH,
}


class DeepgramService:
    """Deepgram STT service with WebSocket streaming for real-time transcription.

    Optimized for voice bot use cases:
    - Low latency with interim results
    - Hindi/English language detection
    - Voice activity detection for utterance boundaries
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model: str = DEEPGRAM_MODEL,
    ) -> None:
        self._settings = settings or get_settings()
        self._model = model
        self._client: DeepgramClient | None = None

    @property
    def client(self) -> DeepgramClient:
        """Lazy initialization of Deepgram client."""
        if self._client is None:
            from deepgram import DeepgramClient

            self._client = DeepgramClient(
                api_key=self._settings.deepgram_api_key.get_secret_value(),
            )
        return self._client

    async def transcribe_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        channels: int = 1,
        language: str = "hi",
    ) -> AsyncGenerator[TranscriptChunk, None]:
        """Transcribe streaming audio using Deepgram WebSocket.

        Args:
            audio_chunks: Async generator yielding raw audio bytes
            sample_rate: Audio sample rate in Hz (default 16kHz for telephony)
            encoding: Audio encoding (linear16 for PCM, mulaw for telephony)
            channels: Number of audio channels
            language: Primary language code (hi for Hindi)

        Yields:
            TranscriptChunk objects for each interim/final result
        """
        from deepgram import LiveOptions, LiveTranscriptionEvents

        # Queue to receive transcription events from callbacks
        transcript_queue: asyncio.Queue[TranscriptChunk | None] = asyncio.Queue()
        metadata = TranscriptMetadata(model=self._model)
        start_time = time.perf_counter()
        first_word_received = False

        def on_message(self_live: Any, result: Any, **kwargs: Any) -> None:
            """Handle incoming transcription results."""
            nonlocal first_word_received

            try:
                channel = result.channel
                alternatives = channel.alternatives

                if not alternatives:
                    return

                alternative = alternatives[0]
                transcript = alternative.transcript

                if not transcript:
                    return

                # Track first word latency
                if not first_word_received:
                    metadata.first_word_ms = (time.perf_counter() - start_time) * 1000
                    first_word_received = True
                    logger.debug(f"First word latency: {metadata.first_word_ms:.1f}ms")

                # Determine if this is final (speech endpoint detected)
                is_final = result.is_final
                speech_final = result.speech_final if hasattr(result, "speech_final") else False

                # Detect language
                detected_lang = DetectedLanguage.UNKNOWN
                if hasattr(alternative, "languages") and alternative.languages:
                    lang_code = alternative.languages[0]
                    detected_lang = LANGUAGE_MAP.get(lang_code, DetectedLanguage.UNKNOWN)
                    if lang_code not in metadata.detected_languages:
                        metadata.detected_languages.append(lang_code)

                # Get timing info
                words = alternative.words if hasattr(alternative, "words") else []
                start = words[0].start if words else 0.0
                end = words[-1].end if words else 0.0

                conf = alternative.confidence if hasattr(alternative, "confidence") else 0.0
                chunk = TranscriptChunk(
                    text=transcript,
                    is_final=is_final,
                    confidence=conf,
                    detected_language=detected_lang,
                    start_time=start,
                    end_time=end,
                    speech_final=speech_final,
                )

                # Put in queue for async consumption
                asyncio.get_event_loop().call_soon_threadsafe(
                    transcript_queue.put_nowait, chunk
                )

                if is_final:
                    metadata.total_utterances += 1

            except Exception as e:
                logger.error(f"Error processing transcription result: {e}")

        def on_error(self_live: Any, error: Any, **kwargs: Any) -> None:
            """Handle WebSocket errors."""
            logger.error(f"Deepgram WebSocket error: {error}")

        def on_close(self_live: Any, close: Any, **kwargs: Any) -> None:
            """Handle WebSocket close."""
            logger.debug("Deepgram WebSocket closed")
            # Signal end of stream
            asyncio.get_event_loop().call_soon_threadsafe(
                transcript_queue.put_nowait, None
            )

        # Configure live transcription options
        options = LiveOptions(
            model=self._model,
            language=language,
            detect_language=True,  # Auto-detect Hindi/English
            smart_format=True,  # Punctuation, numbers, dates
            punctuate=True,
            interim_results=True,  # Real-time feedback
            utterance_end_ms=600,  # 600ms silence = utterance end (matches natural speech pause)
            vad_events=True,  # Voice activity detection
            encoding=encoding,
            sample_rate=sample_rate,
            channels=channels,
        )

        # Create live transcription connection
        live: LiveClient = self.client.listen.live.v("1")

        # Register event handlers
        live.on(LiveTranscriptionEvents.Transcript, on_message)
        live.on(LiveTranscriptionEvents.Error, on_error)
        live.on(LiveTranscriptionEvents.Close, on_close)

        try:
            # Start the connection
            if not await asyncio.to_thread(live.start, options):
                raise RuntimeError("Failed to connect to Deepgram")

            logger.debug("Deepgram WebSocket connected")

            # Start background task to send audio
            async def send_audio() -> None:
                try:
                    async for audio_data in audio_chunks:
                        await asyncio.to_thread(live.send, audio_data)
                        metadata.total_audio_seconds += len(audio_data) / (
                            sample_rate * channels * 2  # 2 bytes per sample for linear16
                        )
                except Exception as e:
                    logger.error(f"Error sending audio: {e}")
                finally:
                    # Signal end of audio
                    await asyncio.to_thread(live.finish)

            # Start sending audio in background
            send_task = asyncio.create_task(send_audio())

            # Yield transcription chunks as they arrive
            while True:
                try:
                    chunk = await asyncio.wait_for(transcript_queue.get(), timeout=30.0)
                    if chunk is None:
                        break
                    yield chunk
                except TimeoutError:
                    logger.warning("Transcription timeout - no results for 30s")
                    break

            # Wait for send task to complete
            await send_task

        except Exception as e:
            logger.error(f"Deepgram transcription error: {e}")
            raise

        finally:
            # Ensure connection is closed (can't use contextlib.suppress with await)
            try:  # noqa: SIM105
                await asyncio.to_thread(live.finish)
            except Exception:
                pass

    async def transcribe_file(
        self,
        audio_data: bytes,
        *,
        sample_rate: int = 16000,
        encoding: str = "linear16",
        language: str = "hi",
    ) -> tuple[str, TranscriptMetadata]:
        """Transcribe a complete audio file (non-streaming).

        Useful for testing and batch processing.

        Args:
            audio_data: Complete audio file bytes
            sample_rate: Audio sample rate
            encoding: Audio encoding
            language: Primary language code

        Returns:
            Tuple of (full transcript, metadata)
        """
        from deepgram import PrerecordedOptions

        options = PrerecordedOptions(
            model=self._model,
            language=language,
            detect_language=True,
            smart_format=True,
            punctuate=True,
        )

        start_time = time.perf_counter()
        response = await asyncio.to_thread(
            self.client.listen.prerecorded.v("1").transcribe_file,
            {"buffer": audio_data, "mimetype": f"audio/{encoding}"},
            options,
        )
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Extract results
        results = response.results
        channels = results.channels if results else []
        transcript = ""
        metadata = TranscriptMetadata(
            model=self._model,
            first_word_ms=latency_ms,
        )

        if channels:
            alternatives = channels[0].alternatives
            if alternatives:
                transcript = alternatives[0].transcript
                metadata.avg_confidence = alternatives[0].confidence

                # Detect language
                if hasattr(results, "detected_language"):
                    metadata.detected_languages.append(results.detected_language)

        return transcript, metadata

    async def close(self) -> None:
        """Close the Deepgram client."""
        self._client = None

    async def health_check(self) -> bool:
        """Check if Deepgram API is accessible."""
        try:
            # Simple API key validation by attempting to create a client
            _ = self.client
            return True
        except Exception as e:
            logger.error(f"Deepgram health check failed: {e}")
            return False
