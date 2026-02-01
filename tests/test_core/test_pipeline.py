"""Tests for VoicePipeline orchestrator."""

import asyncio

import pytest

from src.core.pipeline import (
    AudioBuffer,
    PipelineConfig,
    PipelineMetrics,
    PipelineState,
    VoicePipeline,
)
from src.core.session import CallSession


class TestPipelineState:
    """Tests for PipelineState enum."""

    def test_states_exist(self) -> None:
        """Test all states are defined."""
        assert PipelineState.IDLE
        assert PipelineState.LISTENING
        assert PipelineState.PROCESSING
        assert PipelineState.SPEAKING
        assert PipelineState.INTERRUPTED


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = PipelineConfig()

        assert config.input_sample_rate == 16000
        assert config.output_sample_rate == 8000
        assert config.input_encoding == "linear16"
        assert config.barge_in_enabled is True
        assert config.barge_in_threshold == 500.0

    def test_from_settings(self, settings_factory) -> None:
        """Test creating config from settings."""
        settings = settings_factory(
            plivo_sample_rate=8000,
            tts_target_sample_rate=8000,
            plivo_audio_format="mulaw",
            barge_in_enabled=False,
        )
        config = PipelineConfig.from_settings(settings)

        assert config.input_sample_rate == 8000
        assert config.output_sample_rate == 8000
        assert config.input_encoding == "mulaw"
        assert config.barge_in_enabled is False


class TestPipelineMetrics:
    """Tests for PipelineMetrics dataclass."""

    def test_default_metrics(self) -> None:
        """Test default metrics values."""
        metrics = PipelineMetrics()

        assert metrics.total_audio_received_bytes == 0
        assert metrics.total_audio_sent_bytes == 0
        assert metrics.total_turns == 0
        assert metrics.barge_in_count == 0
        assert metrics.stt_latencies_ms == []
        assert metrics.llm_first_token_ms == []
        assert metrics.tts_first_chunk_ms == []

    def test_to_dict(self) -> None:
        """Test metrics to dictionary conversion."""
        metrics = PipelineMetrics()
        metrics.total_audio_received_bytes = 1000
        metrics.total_audio_sent_bytes = 2000
        metrics.total_turns = 3
        metrics.barge_in_count = 1
        metrics.stt_latencies_ms = [100.0, 200.0]

        result = metrics.to_dict()

        assert result["total_audio_received_bytes"] == 1000
        assert result["total_audio_sent_bytes"] == 2000
        assert result["total_turns"] == 3
        assert result["barge_in_count"] == 1
        assert result["avg_stt_latency_ms"] == 150.0
        assert "duration_seconds" in result


class TestAudioBuffer:
    """Tests for AudioBuffer class."""

    def test_append_and_get(self) -> None:
        """Test appending and getting audio chunks."""
        buffer = AudioBuffer()
        buffer.append(b"\x00\x01\x02")

        # Get with longer timeout
        chunk = asyncio.get_event_loop().run_until_complete(
            buffer.get(timeout=1.0)
        )

        assert chunk == b"\x00\x01\x02"

    @pytest.mark.asyncio
    async def test_get_timeout(self) -> None:
        """Test get returns None on timeout."""
        buffer = AudioBuffer()

        chunk = await buffer.get(timeout=0.01)

        assert chunk is None

    def test_clear(self) -> None:
        """Test clearing buffer."""
        buffer = AudioBuffer()
        buffer.append(b"\x00")
        buffer.append(b"\x01")

        buffer.clear()

        assert buffer.size == 0

    def test_close(self) -> None:
        """Test closing buffer."""
        buffer = AudioBuffer()
        buffer.close()

        # After close, appending should be ignored
        buffer.append(b"\x00")

    @pytest.mark.asyncio
    async def test_drain(self) -> None:
        """Test draining buffer."""
        buffer = AudioBuffer()
        buffer.append(b"\x00")
        buffer.append(b"\x01")
        buffer.append(b"\x02")

        chunks = []
        async for chunk in buffer.drain():
            chunks.append(chunk)

        assert len(chunks) == 3

    def test_size(self) -> None:
        """Test buffer size property."""
        buffer = AudioBuffer()

        assert buffer.size == 0

        buffer.append(b"\x00")
        buffer.append(b"\x01")

        assert buffer.size == 2

    def test_max_size_drops_old(self) -> None:
        """Test that buffer drops oldest when full."""
        buffer = AudioBuffer(max_size=2)

        buffer.append(b"\x00")
        buffer.append(b"\x01")
        buffer.append(b"\x02")  # Should drop \x00

        assert buffer.size == 2


class TestVoicePipeline:
    """Tests for VoicePipeline class."""

    @pytest.fixture(autouse=True)
    def patch_settings(self, settings_factory, monkeypatch) -> None:
        """Patch get_settings for all tests in this class."""
        test_settings = settings_factory()
        monkeypatch.setattr("src.config.get_settings", lambda: test_settings)
        monkeypatch.setattr("src.services.llm.groq.get_settings", lambda: test_settings)
        monkeypatch.setattr("src.services.stt.deepgram.get_settings", lambda: test_settings)
        monkeypatch.setattr("src.core.pipeline.get_settings", lambda: test_settings)

    @pytest.fixture
    def session(self) -> CallSession:
        """Create a test call session."""
        return CallSession(
            call_id="test-call-id",
            business_id="test_business",
        )

    @pytest.fixture
    def pipeline(self, session: CallSession) -> VoicePipeline:
        """Create a test pipeline."""
        return VoicePipeline(session)

    def test_initial_state(self, pipeline: VoicePipeline) -> None:
        """Test pipeline starts in IDLE state."""
        assert pipeline.state == PipelineState.IDLE

    def test_metrics_accessible(self, pipeline: VoicePipeline) -> None:
        """Test metrics property is accessible."""
        metrics = pipeline.metrics

        assert isinstance(metrics, PipelineMetrics)
        assert metrics.total_turns == 0

    @pytest.mark.asyncio
    async def test_configure(self, pipeline: VoicePipeline) -> None:
        """Test pipeline configuration."""
        await pipeline.configure(
            input_sample_rate=8000,
            output_sample_rate=8000,
            input_encoding="mulaw",
        )

        assert pipeline._config.input_sample_rate == 8000
        assert pipeline._config.output_sample_rate == 8000
        assert pipeline._config.input_encoding == "mulaw"

    def test_get_metrics(self, pipeline: VoicePipeline) -> None:
        """Test getting metrics as dict."""
        metrics_dict = pipeline.get_metrics()

        assert isinstance(metrics_dict, dict)
        assert "total_turns" in metrics_dict
        assert "barge_in_count" in metrics_dict

    @pytest.mark.asyncio
    async def test_finalize(self, pipeline: VoicePipeline) -> None:
        """Test pipeline finalization."""
        metrics = await pipeline.finalize()

        assert isinstance(metrics, dict)
        assert "call_id" in metrics
        assert metrics["call_id"] == "test-call-id"
