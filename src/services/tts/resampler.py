"""Audio resampling utilities using soxr."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import soxr

from src.logging_config import get_logger
from src.services.tts.exceptions import TTSResamplingError

logger: Any = get_logger(__name__)


class AudioResampler:
    """High-quality audio resampler using soxr.

    Handles conversion from TTS engine output rates to telephony rates:
    - Piper: 22050Hz → 8000Hz
    - Edge TTS: 24000Hz → 8000Hz
    """

    def __init__(
        self,
        source_rate: int,
        target_rate: int,
        quality: str = "HQ",  # VHQ, HQ, MQ, LQ, QQ
    ) -> None:
        self._source_rate = source_rate
        self._target_rate = target_rate
        self._quality = quality

    @property
    def ratio(self) -> float:
        """Resampling ratio (target/source)."""
        return self._target_rate / self._source_rate

    @property
    def needs_resampling(self) -> bool:
        """Check if resampling is actually needed."""
        return self._source_rate != self._target_rate

    async def resample(self, audio_data: bytes) -> bytes:
        """Resample audio data asynchronously.

        Args:
            audio_data: Raw audio bytes (16-bit PCM, mono)

        Returns:
            Resampled audio bytes (16-bit PCM, mono)
        """
        if not self.needs_resampling:
            return audio_data

        if not audio_data:
            return audio_data

        try:
            # Run resampling in thread pool (CPU-bound)
            return await asyncio.to_thread(self._resample_sync, audio_data)
        except Exception as e:
            logger.error(f"Resampling failed: {e}")
            raise TTSResamplingError(f"Failed to resample audio: {e}") from e

    def _resample_sync(self, audio_data: bytes) -> bytes:
        """Synchronous resampling (called in thread pool)."""
        # Convert bytes to numpy array (int16)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Normalize to float64 for soxr (range -1 to 1)
        audio_float = audio_array.astype(np.float64) / 32768.0

        # Resample using soxr
        resampled = soxr.resample(
            audio_float,
            self._source_rate,
            self._target_rate,
            quality=self._quality,
        )

        # Convert back to int16
        resampled_int16 = (resampled * 32767).clip(-32768, 32767).astype(np.int16)

        return bytes(resampled_int16.tobytes())

    def resample_sync(self, audio_data: bytes) -> bytes:
        """Synchronous resample for use in non-async contexts."""
        if not self.needs_resampling:
            return audio_data
        if not audio_data:
            return audio_data
        return self._resample_sync(audio_data)
