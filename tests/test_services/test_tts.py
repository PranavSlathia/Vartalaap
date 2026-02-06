"""Tests for TTS services (Piper, Edge TTS).

Tests are organized as:
- Pure unit tests for dataclasses, exceptions, and resampler
- Integration tests for Piper/Edge behind env flags (skip if model/network unavailable)
"""

import math
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from src.services.tts.edge import EDGE_HINDI_VOICE, EDGE_SAMPLE_RATE, EdgeTTSService
from src.services.tts.exceptions import (
    TTSConnectionError,
    TTSModelNotFoundError,
    TTSResamplingError,
    TTSServiceError,
    TTSSynthesisError,
)
from src.services.tts.piper import DEFAULT_PIPER_MODEL, PIPER_SAMPLE_RATE, PiperTTSService
from src.services.tts.protocol import AudioChunk, SynthesisMetadata
from src.services.tts.resampler import AudioResampler


def generate_sine_wave(
    frequency: float,
    duration_seconds: float,
    sample_rate: int,
    amplitude: float = 0.5,
) -> bytes:
    """Generate a sine wave as 16-bit PCM bytes.

    Args:
        frequency: Frequency in Hz
        duration_seconds: Duration of the audio
        sample_rate: Sample rate in Hz
        amplitude: Amplitude (0.0 to 1.0)

    Returns:
        Raw PCM bytes (int16, little-endian)
    """
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
    signal = amplitude * np.sin(2 * math.pi * frequency * t)
    # Convert to int16
    int16_signal = (signal * 32767).astype(np.int16)
    return int16_signal.tobytes()


class TestAudioChunk:
    """Tests for AudioChunk dataclass."""

    def test_create_chunk(self) -> None:
        """Test basic chunk creation."""
        chunk = AudioChunk(audio_bytes=b"\x00\x00\x01\x00")
        assert chunk.audio_bytes == b"\x00\x00\x01\x00"
        assert chunk.sample_rate == 8000
        assert chunk.sample_width == 2
        assert chunk.channels == 1
        assert chunk.is_final is False

    def test_chunk_with_duration(self) -> None:
        """Test chunk with duration."""
        chunk = AudioChunk(
            audio_bytes=b"\x00" * 1600,
            sample_rate=8000,
            duration_ms=100.0,
            is_final=True,
        )
        assert chunk.duration_ms == 100.0
        assert chunk.is_final is True

    def test_chunk_has_timestamp(self) -> None:
        """Test chunk has timestamp."""
        before = datetime.now(UTC)
        chunk = AudioChunk(audio_bytes=b"\x00")
        after = datetime.now(UTC)
        assert before <= chunk.timestamp <= after

    def test_chunk_is_frozen(self) -> None:
        """Test chunk is immutable."""
        chunk = AudioChunk(audio_bytes=b"\x00")
        with pytest.raises(AttributeError):
            chunk.audio_bytes = b"\x01"  # type: ignore[misc]


class TestSynthesisMetadata:
    """Tests for SynthesisMetadata dataclass."""

    def test_default_metadata(self) -> None:
        """Test default metadata values."""
        meta = SynthesisMetadata()
        assert meta.model == ""
        assert meta.voice == ""
        assert meta.input_chars == 0
        assert meta.output_samples == 0
        assert meta.first_chunk_ms is None
        assert meta.resampled is False

    def test_metadata_with_values(self) -> None:
        """Test metadata with values."""
        meta = SynthesisMetadata(
            model="piper",
            voice="hi_IN-female-medium",
            input_chars=50,
            output_samples=16000,
            output_duration_ms=2000.0,
            first_chunk_ms=150.5,
            total_synthesis_ms=200.0,
            resampled=True,
            source_sample_rate=22050,
        )
        assert meta.model == "piper"
        assert meta.voice == "hi_IN-female-medium"
        assert meta.input_chars == 50
        assert meta.output_samples == 16000
        assert meta.resampled is True

    def test_metadata_is_mutable(self) -> None:
        """Test metadata can be updated."""
        meta = SynthesisMetadata()
        meta.first_chunk_ms = 100.0
        meta.output_duration_ms = 500.0
        assert meta.first_chunk_ms == 100.0
        assert meta.output_duration_ms == 500.0


class TestTTSExceptions:
    """Tests for TTS exception hierarchy."""

    def test_base_exception(self) -> None:
        """Test TTSServiceError is base."""
        exc = TTSServiceError("base error")
        assert str(exc) == "base error"
        assert isinstance(exc, Exception)

    def test_model_not_found_error(self) -> None:
        """Test TTSModelNotFoundError with path."""
        exc = TTSModelNotFoundError("/path/to/model.onnx")
        assert "TTS model not found" in str(exc)
        assert exc.model_path == "/path/to/model.onnx"
        assert isinstance(exc, TTSServiceError)

    def test_synthesis_error(self) -> None:
        """Test TTSSynthesisError."""
        exc = TTSSynthesisError("synthesis failed")
        assert str(exc) == "synthesis failed"
        assert isinstance(exc, TTSServiceError)

    def test_connection_error(self) -> None:
        """Test TTSConnectionError."""
        exc = TTSConnectionError("network error")
        assert str(exc) == "network error"
        assert isinstance(exc, TTSServiceError)

    def test_resampling_error(self) -> None:
        """Test TTSResamplingError."""
        exc = TTSResamplingError("resample failed")
        assert str(exc) == "resample failed"
        assert isinstance(exc, TTSServiceError)


class TestAudioResampler:
    """Pure unit tests for AudioResampler with generated PCM data."""

    def test_init(self) -> None:
        """Test resampler initialization."""
        resampler = AudioResampler(22050, 8000)
        assert resampler._source_rate == 22050
        assert resampler._target_rate == 8000

    def test_ratio(self) -> None:
        """Test resampling ratio calculation."""
        resampler = AudioResampler(22050, 8000)
        assert abs(resampler.ratio - (8000 / 22050)) < 0.001

    def test_needs_resampling_true(self) -> None:
        """Test needs_resampling when rates differ."""
        resampler = AudioResampler(22050, 8000)
        assert resampler.needs_resampling is True

    def test_needs_resampling_false(self) -> None:
        """Test needs_resampling when rates match."""
        resampler = AudioResampler(8000, 8000)
        assert resampler.needs_resampling is False

    @pytest.mark.asyncio
    async def test_resample_passthrough_same_rate(self) -> None:
        """Test resample passes through when rates match."""
        resampler = AudioResampler(8000, 8000)
        audio_data = generate_sine_wave(440, 0.1, 8000)
        result = await resampler.resample(audio_data)
        assert result == audio_data

    @pytest.mark.asyncio
    async def test_resample_empty_data(self) -> None:
        """Test resample handles empty data."""
        resampler = AudioResampler(22050, 8000)
        result = await resampler.resample(b"")
        assert result == b""

    @pytest.mark.asyncio
    async def test_resample_downsamples_sine_wave(self) -> None:
        """Test downsampling a 440Hz sine wave preserves duration."""
        source_rate = 22050
        target_rate = 8000
        duration = 1.0

        resampler = AudioResampler(source_rate, target_rate)
        audio_data = generate_sine_wave(440, duration, source_rate)

        result = await resampler.resample(audio_data)

        # Check output duration is preserved (within 2%)
        input_samples = len(audio_data) // 2
        output_samples = len(result) // 2

        input_duration = input_samples / source_rate
        output_duration = output_samples / target_rate

        assert abs(output_duration - input_duration) < 0.02  # 20ms tolerance

    @pytest.mark.asyncio
    async def test_resample_reduces_byte_count(self) -> None:
        """Test resampling reduces data size proportionally."""
        source_rate = 22050
        target_rate = 8000

        resampler = AudioResampler(source_rate, target_rate)
        audio_data = generate_sine_wave(440, 1.0, source_rate)

        result = await resampler.resample(audio_data)

        # Output should be roughly (target_rate / source_rate) of input size
        expected_ratio = target_rate / source_rate
        actual_ratio = len(result) / len(audio_data)

        assert abs(actual_ratio - expected_ratio) < 0.05  # 5% tolerance

    def test_resample_sync_with_real_audio(self) -> None:
        """Test synchronous resample with generated audio."""
        resampler = AudioResampler(22050, 8000)
        audio_data = generate_sine_wave(440, 0.1, 22050)  # 100ms of 440Hz

        result = resampler.resample_sync(audio_data)

        # Output should be smaller than input
        assert len(result) < len(audio_data)

        # Check it's valid int16 data (even number of bytes)
        assert len(result) % 2 == 0

    def test_resample_sync_passthrough(self) -> None:
        """Test sync resample passes through when rates match."""
        resampler = AudioResampler(8000, 8000)
        audio_data = generate_sine_wave(440, 0.1, 8000)
        result = resampler.resample_sync(audio_data)
        assert result == audio_data

    @pytest.mark.asyncio
    async def test_resample_piper_to_telephony(self) -> None:
        """Test resampling from Piper rate (22050) to telephony (8000)."""
        resampler = AudioResampler(PIPER_SAMPLE_RATE, 8000)
        # 500ms of audio
        audio_data = generate_sine_wave(880, 0.5, PIPER_SAMPLE_RATE)

        result = await resampler.resample(audio_data)

        # Verify output is valid
        assert len(result) > 0
        assert len(result) % 2 == 0  # Valid int16

        # Check approximate duration preservation
        output_samples = len(result) // 2
        output_duration = output_samples / 8000
        assert 0.48 < output_duration < 0.52  # Within 20ms of 500ms

    @pytest.mark.asyncio
    async def test_resample_edge_to_telephony(self) -> None:
        """Test resampling from Edge TTS rate (24000) to telephony (8000)."""
        resampler = AudioResampler(EDGE_SAMPLE_RATE, 8000)
        # 500ms of audio
        audio_data = generate_sine_wave(880, 0.5, EDGE_SAMPLE_RATE)

        result = await resampler.resample(audio_data)

        # Verify output is valid
        assert len(result) > 0
        assert len(result) % 2 == 0  # Valid int16

        # Check approximate duration preservation
        output_samples = len(result) // 2
        output_duration = output_samples / 8000
        assert 0.48 < output_duration < 0.52  # Within 20ms of 500ms


class TestPiperTTSServiceUnit:
    """Unit tests for PiperTTSService (no model required)."""

    @pytest.fixture
    def base_settings(self, settings_factory):
        return settings_factory(
            piper_voice=DEFAULT_PIPER_MODEL,
            piper_model_path=None,
            tts_target_sample_rate=8000,
        )

    def test_init_default_voice(self, base_settings) -> None:
        """Test service initializes with default Hindi voice."""
        service = PiperTTSService(settings=base_settings)
        assert service._voice_name == DEFAULT_PIPER_MODEL

    def test_init_custom_model_path(self, base_settings) -> None:
        """Test service with custom model path."""
        custom_path = Path("/custom/model.onnx")
        service = PiperTTSService(settings=base_settings, model_path=custom_path)
        assert service._model_path == custom_path

    def test_init_model_path_from_settings(self, settings_factory) -> None:
        """Test model path loaded from settings."""
        settings = settings_factory(
            piper_voice="test_voice",
            piper_model_path="/custom/path/model.onnx",
            tts_target_sample_rate=8000,
        )
        service = PiperTTSService(settings=settings)
        assert service._model_path == Path("/custom/path/model.onnx")

    def test_init_default_model_path(self, base_settings) -> None:
        """Test default model path construction."""
        service = PiperTTSService(settings=base_settings)
        expected = Path(f"data/models/piper/{DEFAULT_PIPER_MODEL}.onnx")
        assert service._model_path == expected

    def test_voice_lazy_init(self, base_settings) -> None:
        """Test voice is None until accessed."""
        service = PiperTTSService(settings=base_settings)
        assert service._tts is None

    def test_voice_model_not_found(self, base_settings) -> None:
        """Test error when model file missing."""
        service = PiperTTSService(
            settings=base_settings,
            model_path=Path("/tmp/missing-piper-model.onnx"),
        )
        with pytest.raises(TTSModelNotFoundError) as exc_info:
            _ = service.tts
        assert "TTS model not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close_clears_resources(self, base_settings) -> None:
        """Test close clears internal resources."""
        service = PiperTTSService(settings=base_settings)
        service._resampler = AudioResampler(22050, 8000)
        await service.close()
        assert service._tts is None
        assert service._resampler is None

    @pytest.mark.asyncio
    async def test_health_check_no_model(self, base_settings) -> None:
        """Test health check fails when model missing."""
        service = PiperTTSService(settings=base_settings)
        result = await service.health_check()
        assert result is False

    def test_get_resampler_creates_new(self, base_settings) -> None:
        """Test _get_resampler creates new resampler."""
        service = PiperTTSService(settings=base_settings)
        resampler = service._get_resampler(8000)
        assert resampler is not None
        assert resampler._target_rate == 8000
        assert resampler._source_rate == PIPER_SAMPLE_RATE

    def test_get_resampler_caches(self, base_settings) -> None:
        """Test _get_resampler caches resampler."""
        service = PiperTTSService(settings=base_settings)
        resampler1 = service._get_resampler(8000)
        resampler2 = service._get_resampler(8000)
        assert resampler1 is resampler2

    def test_get_resampler_different_rate(self, base_settings) -> None:
        """Test _get_resampler creates new for different rate."""
        service = PiperTTSService(settings=base_settings)
        resampler1 = service._get_resampler(8000)
        resampler2 = service._get_resampler(16000)
        assert resampler1 is not resampler2
        assert resampler2._target_rate == 16000

    def test_piper_sample_rate_constant(self) -> None:
        """Test Piper sample rate constant."""
        assert PIPER_SAMPLE_RATE == 22050

    def test_cancel_method_exists(self, base_settings) -> None:
        """Test cancel method for barge-in support."""
        service = PiperTTSService(settings=base_settings)
        # Should not raise
        service.cancel()

    def test_validate_model_path_missing(self, base_settings) -> None:
        """Test validate_model_path raises for missing model."""
        service = PiperTTSService(
            settings=base_settings,
            model_path=Path("/tmp/missing-piper-model.onnx"),
        )
        with pytest.raises(TTSModelNotFoundError):
            service.validate_model_path()


class TestEdgeTTSServiceUnit:
    """Unit tests for EdgeTTSService (no network required)."""

    @pytest.fixture
    def settings_enabled(self, settings_factory):
        return settings_factory(
            edge_tts_enabled=True,
            edge_tts_voice=EDGE_HINDI_VOICE,
            tts_target_sample_rate=8000,
        )

    @pytest.fixture
    def settings_disabled(self, settings_factory):
        return settings_factory(
            edge_tts_enabled=False,
            edge_tts_voice=EDGE_HINDI_VOICE,
            tts_target_sample_rate=8000,
        )

    def test_init_default_voice(self, settings_enabled) -> None:
        """Test service initializes with default Hindi voice."""
        service = EdgeTTSService(settings=settings_enabled)
        assert service._voice == EDGE_HINDI_VOICE
        assert service._voice == "hi-IN-SwaraNeural"

    def test_init_custom_voice(self, settings_enabled) -> None:
        """Test service with custom voice."""
        service = EdgeTTSService(settings=settings_enabled, voice="en-US-JennyNeural")
        assert service._voice == "en-US-JennyNeural"

    def test_edge_sample_rate_constant(self) -> None:
        """Test Edge TTS sample rate constant."""
        assert EDGE_SAMPLE_RATE == 24000

    @pytest.mark.asyncio
    async def test_synthesize_stream_fails_when_disabled(self, settings_disabled) -> None:
        """Test synthesize_stream raises when Edge TTS disabled."""
        service = EdgeTTSService(settings=settings_disabled)
        with pytest.raises(TTSConnectionError) as exc_info:
            await service.synthesize_stream("test")
        assert "Edge TTS is disabled" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_close_clears_resources(self, settings_enabled) -> None:
        """Test close clears internal resources."""
        service = EdgeTTSService(settings=settings_enabled)
        service._resampler = AudioResampler(24000, 8000)
        await service.close()
        assert service._resampler is None

    @pytest.mark.asyncio
    async def test_health_check_disabled(self, settings_disabled) -> None:
        """Test health check returns False when disabled."""
        service = EdgeTTSService(settings=settings_disabled)
        result = await service.health_check()
        assert result is False

    def test_get_resampler_creates_new(self, settings_enabled) -> None:
        """Test _get_resampler creates new resampler."""
        service = EdgeTTSService(settings=settings_enabled)
        resampler = service._get_resampler(8000)
        assert resampler is not None
        assert resampler._target_rate == 8000
        assert resampler._source_rate == EDGE_SAMPLE_RATE

    def test_get_resampler_caches(self, settings_enabled) -> None:
        """Test _get_resampler caches resampler."""
        service = EdgeTTSService(settings=settings_enabled)
        resampler1 = service._get_resampler(8000)
        resampler2 = service._get_resampler(8000)
        assert resampler1 is resampler2

    def test_cancel_method_exists(self, settings_enabled) -> None:
        """Test cancel method for barge-in support."""
        service = EdgeTTSService(settings=settings_enabled)
        # Should not raise
        service.cancel()


# =============================================================================
# Integration Tests (env-gated)
# =============================================================================


def _piper_model_ready() -> bool:
    model_path = os.environ.get("PIPER_MODEL_PATH")
    return bool(model_path and Path(model_path).exists())


@pytest.mark.skipif(
    not _piper_model_ready(),
    reason="PIPER_MODEL_PATH missing or file not found - skipping Piper integration tests",
)
@pytest.mark.external
class TestPiperTTSIntegration:
    """Integration tests for Piper TTS (requires PIPER_MODEL_PATH env var)."""

    @pytest.fixture
    def service(self, settings_factory) -> PiperTTSService:
        """Create service with real model path from env."""
        model_path = os.environ.get("PIPER_MODEL_PATH")
        settings = settings_factory(piper_model_path=model_path)
        return PiperTTSService(settings=settings, model_path=model_path)

    @pytest.mark.asyncio
    async def test_synthesize_hindi_text(self, service: PiperTTSService) -> None:
        """Test synthesizing Hindi text."""
        text = "नमस्ते"
        audio_bytes, metadata = await service.synthesize(text)

        assert len(audio_bytes) > 0
        assert metadata.input_chars == len(text)
        assert metadata.output_duration_ms > 0
        assert metadata.model == "piper"

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_chunks(
        self, service: PiperTTSService
    ) -> None:
        """Test streaming synthesis yields audio chunks."""
        text = "Hello, how are you?"
        generator, metadata = await service.synthesize_stream(text)

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
            assert isinstance(chunk, AudioChunk)
            assert len(chunk.audio_bytes) > 0

        assert len(chunks) > 0
        assert chunks[-1].is_final is True

    @pytest.mark.asyncio
    async def test_health_check_with_model(self, service: PiperTTSService) -> None:
        """Test health check passes with valid model."""
        result = await service.health_check()
        assert result is True


@pytest.mark.skipif(
    os.environ.get("EDGE_TTS_ENABLED", "").lower() != "true",
    reason="EDGE_TTS_ENABLED not true - skipping Edge TTS integration tests",
)
@pytest.mark.external
class TestEdgeTTSIntegration:
    """Integration tests for Edge TTS (requires EDGE_TTS_ENABLED env var)."""

    @pytest.fixture
    def service(self, settings_factory) -> EdgeTTSService:
        """Create service with Edge TTS enabled."""
        settings = settings_factory(
            edge_tts_enabled=True,
            edge_tts_voice=EDGE_HINDI_VOICE,
            tts_target_sample_rate=8000,
        )
        return EdgeTTSService(settings=settings)

    @pytest.mark.asyncio
    async def test_synthesize_hindi_text(self, service: EdgeTTSService) -> None:
        """Test synthesizing Hindi text."""
        text = "नमस्ते"
        audio_bytes, metadata = await service.synthesize(text)

        assert len(audio_bytes) > 0
        assert metadata.input_chars == len(text)
        assert metadata.output_duration_ms > 0
        assert metadata.model == "edge-tts"

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_chunks(
        self, service: EdgeTTSService
    ) -> None:
        """Test streaming synthesis yields audio chunks."""
        text = "Hello, how are you?"
        generator, metadata = await service.synthesize_stream(text)

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)
            assert isinstance(chunk, AudioChunk)
            assert len(chunk.audio_bytes) > 0

        assert len(chunks) > 0
        assert chunks[-1].is_final is True

    @pytest.mark.asyncio
    async def test_health_check_enabled(self, service: EdgeTTSService) -> None:
        """Test health check passes when enabled."""
        result = await service.health_check()
        assert result is True


class TestTTSModuleExports:
    """Tests for TTS module exports."""

    def test_import_services(self) -> None:
        """Test service classes are exported."""
        from src.services.tts import EdgeTTSService, PiperTTSService

        assert PiperTTSService is not None
        assert EdgeTTSService is not None

    def test_import_protocol(self) -> None:
        """Test protocol types are exported."""
        from src.services.tts import AudioChunk, SynthesisMetadata, TTSService

        assert AudioChunk is not None
        assert SynthesisMetadata is not None
        assert TTSService is not None

    def test_import_exceptions(self) -> None:
        """Test exceptions are exported."""
        from src.services.tts import (
            TTSConnectionError,
            TTSModelNotFoundError,
            TTSResamplingError,
            TTSServiceError,
            TTSSynthesisError,
        )

        assert TTSServiceError is not None
        assert TTSModelNotFoundError is not None
        assert TTSSynthesisError is not None
        assert TTSConnectionError is not None
        assert TTSResamplingError is not None

    def test_import_resampler(self) -> None:
        """Test AudioResampler is exported."""
        from src.services.tts import AudioResampler

        assert AudioResampler is not None
