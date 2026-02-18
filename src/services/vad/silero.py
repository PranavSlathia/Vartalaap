"""Silero VAD — streaming voice activity detection.

Silero VAD is a pre-trained neural network for speech detection that runs on
CPU in ~10ms per 30ms audio frame.  Compared to energy-threshold detection it
handles background noise, music, and coughs without false positives.

Model details:
  - Frame size: 512 samples at 16kHz (32ms) or 256 samples at 8kHz (32ms)
  - Output:     speech probability in [0.0, 1.0]
  - Weights:    bundled with the silero-vad PyPI package (no runtime download)

Barge-in debounce:
  Speech must persist for `min_speech_ms` (default 500ms) before a barge-in
  is signalled.  Any silence frame resets the counter, so brief noise never
  triggers an interruption.

Usage::

    vad = SileroVAD(sample_rate=16000, min_speech_ms=500)
    vad.load()                        # call once at startup (loads model)

    # Per audio chunk from Plivo/mic:
    if vad.is_speech(audio_bytes):    # True only after 500ms sustained speech
        handle_barge_in()

    vad.reset()                       # call at start of each new call
"""

from __future__ import annotations

from typing import Any

from src.logging_config import get_logger

logger = get_logger(__name__)

# Silero expects these exact frame sizes; other sizes are silently mis-inferred.
_FRAME_SAMPLES_16K = 512  # 32ms at 16 kHz
_FRAME_SAMPLES_8K = 256   # 32ms at  8 kHz

_DEFAULT_SPEECH_THRESHOLD = 0.5
_DEFAULT_MIN_SPEECH_MS = 500
_ENERGY_FALLBACK_THRESHOLD = 500.0   # RMS energy (same as original pipeline default)
_ENERGY_FALLBACK_CHUNK_MS = 20.0     # Estimated Plivo chunk size for fallback counter


class SileroVAD:
    """Streaming voice activity detector backed by Silero VAD.

    If ``silero-vad`` / ``torch`` are not installed the class falls back to
    energy-threshold detection with the same 500ms debounce — so barge-in
    still works correctly, just with less precision on noisy calls.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        speech_threshold: float = _DEFAULT_SPEECH_THRESHOLD,
        min_speech_ms: int = _DEFAULT_MIN_SPEECH_MS,
    ) -> None:
        self._sample_rate = sample_rate
        self._threshold = speech_threshold
        self._min_speech_ms = min_speech_ms

        # Choose frame geometry based on sample rate
        self._frame_samples = (
            _FRAME_SAMPLES_16K if sample_rate >= 16000 else _FRAME_SAMPLES_8K
        )
        self._frame_bytes = self._frame_samples * 2          # PCM16 → 2 bytes/sample
        self._frame_ms = (self._frame_samples / sample_rate) * 1000  # ms per frame

        # Frame accumulation buffer (accumulate partial chunks into full frames)
        self._frame_buffer = bytearray()

        # Debounce: consecutive speech duration in ms
        self._consecutive_speech_ms: float = 0.0

        # Model refs (populated by load())
        self._model: Any = None
        self._torch: Any = None
        self._loaded = False
        self._use_fallback = False  # set True if silero unavailable

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the Silero VAD model.

        Safe to call multiple times; subsequent calls are no-ops.
        Weights are bundled with the silero-vad package — no internet required.
        Typical load time: 200–500ms on first call, ~0ms thereafter (cached).
        """
        if self._loaded or self._use_fallback:
            return

        try:
            import torch
            from silero_vad import load_silero_vad  # type: ignore[import-untyped]

            self._model = load_silero_vad(onnx=False)
            self._model.eval()
            self._model.reset_states()
            self._torch = torch
            self._loaded = True
            logger.info(
                f"Silero VAD ready — {self._sample_rate}Hz, "
                f"threshold={self._threshold}, min_speech={self._min_speech_ms}ms"
            )
        except Exception as e:
            logger.warning(
                f"Silero VAD unavailable ({e}). "
                "Falling back to energy-threshold barge-in with 500ms debounce."
            )
            self._use_fallback = True

    def is_speech(self, audio_bytes: bytes) -> bool:
        """Process an incoming audio chunk; return True when barge-in should fire.

        Accumulates audio into full 32ms frames, runs Silero inference on each
        frame, and returns True only once speech has persisted for
        ``min_speech_ms``.  Any silence frame resets the persistence counter.

        Args:
            audio_bytes: Raw PCM16 audio (any chunk size; internally buffered).

        Returns:
            True if sustained speech detected — caller should trigger barge-in.
        """
        if self._use_fallback:
            return self._energy_is_speech(audio_bytes)

        if not self._loaded:
            return False

        self._frame_buffer.extend(audio_bytes)
        triggered = False

        while len(self._frame_buffer) >= self._frame_bytes:
            frame = bytes(self._frame_buffer[: self._frame_bytes])
            self._frame_buffer = self._frame_buffer[self._frame_bytes :]

            prob = self._infer_frame(frame)

            if prob >= self._threshold:
                self._consecutive_speech_ms += self._frame_ms
                if self._consecutive_speech_ms >= self._min_speech_ms:
                    # Sustained speech confirmed — trigger barge-in once, then
                    # reset so re-trigger requires another full persistence window.
                    triggered = True
                    self._consecutive_speech_ms = 0.0
            else:
                # Silence — reset persistence counter
                self._consecutive_speech_ms = 0.0

        return triggered

    def reset(self) -> None:
        """Reset debounce state and model LSTM hidden state.

        Call at the start of each new call and after barge-in fires, to
        prevent the previous call's speech from bleeding into the next.
        """
        self._consecutive_speech_ms = 0.0
        self._frame_buffer = bytearray()
        if self._loaded:
            import contextlib

            with contextlib.suppress(Exception):
                self._model.reset_states()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _infer_frame(self, pcm_bytes: bytes) -> float:
        """Run Silero inference on one complete frame.

        Returns speech probability in [0.0, 1.0].
        """
        try:
            import numpy as np

            # PCM16 → float32 in [-1.0, 1.0] (Silero's expected normalisation)
            samples = (
                np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            tensor = self._torch.from_numpy(samples)
            return float(self._model(tensor, self._sample_rate).item())
        except Exception as exc:
            logger.debug(f"Silero inference error: {exc}")
            return 0.0

    def _energy_is_speech(self, audio_bytes: bytes) -> bool:
        """Fallback: energy-threshold detection with 500ms debounce."""
        try:
            import audioop

            energy = float(audioop.rms(audio_bytes, 2))
        except Exception:
            return False

        # Estimate chunk duration from byte count (PCM16 = 2 bytes/sample)
        chunk_ms = (len(audio_bytes) / 2 / self._sample_rate) * 1000

        if energy > _ENERGY_FALLBACK_THRESHOLD:
            self._consecutive_speech_ms += chunk_ms
            if self._consecutive_speech_ms >= self._min_speech_ms:
                self._consecutive_speech_ms = 0.0
                return True
        else:
            self._consecutive_speech_ms = 0.0
        return False
