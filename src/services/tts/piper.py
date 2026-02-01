"""Piper TTS service implementation for offline speech synthesis.

Uses sherpa-onnx for inference, which provides better cross-platform
compatibility than the piper-tts package.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.config import Settings, get_settings
from src.logging_config import get_logger
from src.services.tts.exceptions import TTSModelNotFoundError, TTSSynthesisError
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler

if TYPE_CHECKING:
    import sherpa_onnx

logger: Any = get_logger(__name__)

# Default Piper model configuration
DEFAULT_PIPER_MODEL = "hi_IN-priyamvada-medium"
PIPER_SAMPLE_RATE = 22050  # Piper outputs 22050Hz


class PiperTTSService:
    """Piper TTS service for offline, self-hosted speech synthesis.

    Uses sherpa-onnx for inference, providing:
    - Hindi voice output (hi_IN-priyamvada)
    - Low latency streaming
    - CPU-friendly inference
    - Resampling to telephony rates (8kHz)
    - Cancellation for barge-in support
    - Better cross-platform compatibility (macOS ARM64, Linux, etc.)
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model_path: str | Path | None = None,
        voice_name: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._voice_name = voice_name or self._settings.piper_voice

        # Model path resolution (configurable via settings or constructor)
        if model_path:
            self._model_path = Path(model_path)
        elif self._settings.piper_model_path:
            self._model_path = Path(self._settings.piper_model_path)
        else:
            # Default to data/models/piper/{voice_name}.onnx
            self._model_path = Path("data/models/piper") / f"{self._voice_name}.onnx"

        # Derived paths
        self._tokens_path = self._model_path.parent / "tokens.txt"
        self._espeak_data_dir = Path("data/models/espeak-ng-data")

        self._tts: sherpa_onnx.OfflineTts | None = None
        self._resampler: AudioResampler | None = None
        self._load_lock = asyncio.Lock()
        self._cancel_event: asyncio.Event | None = None

    @property
    def tts(self) -> Any:
        """Lazy initialization of sherpa-onnx TTS.

        Note: For async contexts, use _ensure_tts_loaded() instead
        to properly handle concurrent loading.
        """
        if self._tts is None:
            self._load_tts_sync()
        return self._tts

    def _load_tts_sync(self) -> None:
        """Synchronous TTS loading (for non-async contexts)."""
        try:
            import sherpa_onnx
        except ImportError as e:
            raise TTSModelNotFoundError(
                f"sherpa-onnx not installed: {e}"
            ) from e

        if not self._model_path.exists():
            raise TTSModelNotFoundError(str(self._model_path))

        if not self._tokens_path.exists():
            raise TTSModelNotFoundError(
                f"Tokens file not found: {self._tokens_path}. "
                "Generate it from the model's .onnx.json file."
            )

        if not self._espeak_data_dir.exists():
            raise TTSModelNotFoundError(
                f"espeak-ng-data not found: {self._espeak_data_dir}. "
                "Download from: https://github.com/k2-fsa/sherpa-onnx/releases"
            )

        logger.info(f"Loading Piper model via sherpa-onnx: {self._model_path}")

        # Configure VITS model (Piper uses VITS architecture)
        vits_config = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=str(self._model_path),
            tokens=str(self._tokens_path),
            data_dir=str(self._espeak_data_dir),
            length_scale=1.0,  # Speed (1.0 = normal)
            noise_scale=0.667,  # From model config
            noise_scale_w=0.8,  # From model config
        )

        model_config = sherpa_onnx.OfflineTtsModelConfig(
            vits=vits_config,
            num_threads=2,  # CPU threads
            debug=False,
        )

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=model_config,
            max_num_sentences=1,  # Process one sentence at a time for lower latency
        )

        self._tts = sherpa_onnx.OfflineTts(tts_config)
        logger.info(f"Piper model loaded via sherpa-onnx: {self._voice_name}")

    async def _ensure_tts_loaded(self) -> Any:
        """Ensure TTS is loaded with async lock to prevent double-loading."""
        if self._tts is not None:
            return self._tts

        async with self._load_lock:
            # Double-check after acquiring lock
            if self._tts is not None:
                return self._tts

            # Load in thread pool to avoid blocking
            await asyncio.to_thread(self._load_tts_sync)
            return self._tts

    def _get_resampler(self, target_rate: int) -> AudioResampler:
        """Get or create resampler for target rate."""
        if (
            self._resampler is None
            or self._resampler._target_rate != target_rate
        ):
            self._resampler = AudioResampler(PIPER_SAMPLE_RATE, target_rate)
        return self._resampler

    async def synthesize_stream(
        self,
        text: str,
        *,
        target_sample_rate: int | None = None,
        chunk_size_ms: int = 50,  # Smaller chunks for faster first audio byte
    ) -> tuple[AsyncGenerator[AudioChunk, None], SynthesisMetadata]:
        """Synthesize text to streaming audio chunks.

        sherpa-onnx synthesizes the complete audio, which we then chunk
        and resample for streaming output.
        """
        if target_sample_rate is None:
            target_sample_rate = self._settings.tts_target_sample_rate

        # Create cancel event for barge-in support
        self._cancel_event = asyncio.Event()

        metadata = SynthesisMetadata(
            model="piper",
            voice=self._voice_name,
            input_chars=len(text),
            source_sample_rate=PIPER_SAMPLE_RATE,
            resampled=(target_sample_rate != PIPER_SAMPLE_RATE),
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
            # Ensure TTS is loaded with async lock
            await self._ensure_tts_loaded()

            # sherpa-onnx synthesize is synchronous, run in thread pool
            raw_audio = await asyncio.to_thread(
                self._synthesize_to_bytes, text
            )

            if not raw_audio:
                return

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
                # Check for cancellation (barge-in)
                if self._cancel_event and self._cancel_event.is_set():
                    logger.debug("Piper TTS synthesis cancelled (barge-in)")
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
                        f"First TTS chunk latency: {metadata.first_chunk_ms:.1f}ms"
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
                f"TTS synthesis complete: {metadata.input_chars} chars -> "
                f"{metadata.output_duration_ms:.0f}ms audio in "
                f"{metadata.total_synthesis_ms:.0f}ms"
            )

        except TTSModelNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Piper synthesis error: {e}")
            raise TTSSynthesisError(f"Synthesis failed: {e}") from e

    def _synthesize_to_bytes(self, text: str) -> bytes:
        """Synthesize text to raw PCM bytes (synchronous)."""
        import numpy as np

        # Get the TTS instance (may trigger lazy load)
        tts = self.tts

        # sherpa-onnx generate returns an object with samples (float32 array)
        # and sample_rate
        audio = tts.generate(text, sid=0, speed=1.0)

        if audio.sample_rate != PIPER_SAMPLE_RATE:
            logger.warning(
                f"Unexpected sample rate: {audio.sample_rate} vs expected {PIPER_SAMPLE_RATE}"
            )

        # Convert float32 samples to int16 PCM bytes
        samples = np.array(audio.samples)
        # Normalize and convert to int16
        samples_int16 = (samples * 32767).astype(np.int16)

        return samples_int16.tobytes()

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
        """Release model resources."""
        if self._resampler:
            self._resampler = None
        self._tts = None
        self._cancel_event = None

    async def health_check(self) -> bool:
        """Check if Piper model is loadable."""
        try:
            # Check if model file exists
            if not self._model_path.exists():
                logger.warning(f"Piper model not found: {self._model_path}")
                return False
            if not self._tokens_path.exists():
                logger.warning(f"Tokens file not found: {self._tokens_path}")
                return False
            if not self._espeak_data_dir.exists():
                logger.warning(f"espeak-ng-data not found: {self._espeak_data_dir}")
                return False
            # Try to load the model with async lock
            await self._ensure_tts_loaded()
            return True
        except Exception as e:
            logger.warning(f"Piper health check failed: {e}")
            return False

    def validate_model_path(self) -> None:
        """Validate model path at startup. Raises if invalid."""
        if not self._model_path.exists():
            raise TTSModelNotFoundError(str(self._model_path))

        if not self._tokens_path.exists():
            raise TTSModelNotFoundError(
                f"Tokens file not found: {self._tokens_path}"
            )

        if not self._espeak_data_dir.exists():
            raise TTSModelNotFoundError(
                f"espeak-ng-data not found: {self._espeak_data_dir}"
            )
