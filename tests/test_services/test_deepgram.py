"""Tests for Deepgram STT service."""

import os
from pathlib import Path

import pytest

from src.services.stt.deepgram import LANGUAGE_MAP, DeepgramService
from src.services.stt.protocol import DetectedLanguage, TranscriptChunk


class TestTranscriptChunk:
    """Tests for TranscriptChunk dataclass."""

    def test_create_chunk(self) -> None:
        """Test basic chunk creation."""
        chunk = TranscriptChunk(
            text="Hello",
            is_final=True,
            confidence=0.95,
        )
        assert chunk.text == "Hello"
        assert chunk.is_final is True
        assert chunk.confidence == 0.95
        assert chunk.detected_language == DetectedLanguage.UNKNOWN

    def test_chunk_with_language(self) -> None:
        """Test chunk with detected language."""
        chunk = TranscriptChunk(
            text="Namaste",
            is_final=True,
            detected_language=DetectedLanguage.HINDI,
        )
        assert chunk.detected_language == DetectedLanguage.HINDI

    def test_chunk_with_timing(self) -> None:
        """Test chunk with timing info."""
        chunk = TranscriptChunk(
            text="Test",
            is_final=False,
            start_time=1.5,
            end_time=2.0,
        )
        assert chunk.start_time == 1.5
        assert chunk.end_time == 2.0

    def test_chunk_speech_final(self) -> None:
        """Test speech_final flag for utterance boundaries."""
        chunk = TranscriptChunk(
            text="Complete sentence.",
            is_final=True,
            speech_final=True,
        )
        assert chunk.speech_final is True


class TestLanguageMapping:
    """Tests for language code mapping."""

    def test_hindi_mapping(self) -> None:
        """Test Hindi language code mapping."""
        assert LANGUAGE_MAP["hi"] == DetectedLanguage.HINDI

    def test_english_mapping(self) -> None:
        """Test English language code mappings."""
        assert LANGUAGE_MAP["en"] == DetectedLanguage.ENGLISH
        assert LANGUAGE_MAP["en-US"] == DetectedLanguage.ENGLISH
        assert LANGUAGE_MAP["en-IN"] == DetectedLanguage.ENGLISH

    def test_hinglish_mapping(self) -> None:
        """Test Hinglish (romanized Hindi) mapping."""
        assert LANGUAGE_MAP["hi-Latn"] == DetectedLanguage.HINGLISH

    def test_unknown_language(self) -> None:
        """Test unknown language returns UNKNOWN."""
        unknown = LANGUAGE_MAP.get("fr", DetectedLanguage.UNKNOWN)
        assert unknown == DetectedLanguage.UNKNOWN


class TestDeepgramService:
    """Tests for DeepgramService."""

    @pytest.fixture
    def service(self, settings_factory) -> DeepgramService:
        """Create service instance with real Settings."""
        return DeepgramService(settings=settings_factory())

    def test_init_default_model(self, service: DeepgramService) -> None:
        """Test service initializes with default nova-2 model."""
        assert service._model == "nova-2"

    def test_init_custom_model(self, settings_factory) -> None:
        """Test service with custom model."""
        service = DeepgramService(settings=settings_factory(), model="nova-2-general")
        assert service._model == "nova-2-general"

    def test_client_lazy_init(self, service: DeepgramService) -> None:
        """Test client is None until accessed."""
        assert service._client is None

    def test_client_initialized_on_access(self, service: DeepgramService) -> None:
        """Test client is initialized on first access."""
        assert service._client is None
        client = service.client
        assert client is not None
        assert service._client is client

    def test_client_reused(self, service: DeepgramService) -> None:
        """Test client is reused on subsequent accesses."""
        client1 = service.client
        client2 = service.client
        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close(self, service: DeepgramService) -> None:
        """Test close clears client."""
        _ = service.client
        await service.close()
        assert service._client is None

    @pytest.mark.asyncio
    async def test_health_check_success(self, service: DeepgramService) -> None:
        """Test health check succeeds with valid client."""
        result = await service.health_check()
        assert result is True


class TestDetectedLanguageEnum:
    """Tests for DetectedLanguage enum."""

    def test_language_values(self) -> None:
        """Test language enum values."""
        assert DetectedLanguage.HINDI.value == "hi"
        assert DetectedLanguage.ENGLISH.value == "en"
        assert DetectedLanguage.HINGLISH.value == "hi-Latn"
        assert DetectedLanguage.UNKNOWN.value == "unknown"

    def test_language_is_string_enum(self) -> None:
        """Test language enum is string-based."""
        assert str(DetectedLanguage.HINDI) == "DetectedLanguage.HINDI"
        assert DetectedLanguage.HINDI == "hi"


def _has_deepgram_key() -> bool:
    return bool(os.environ.get("DEEPGRAM_API_KEY"))


@pytest.mark.skipif(
    not _has_deepgram_key() or not os.environ.get("DEEPGRAM_TEST_AUDIO"),
    reason="DEEPGRAM_API_KEY or DEEPGRAM_TEST_AUDIO not set",
)
class TestTranscriptionIntegration:
    """Integration tests for Deepgram transcription (env-gated)."""

    @pytest.fixture
    def service(self, settings_factory) -> DeepgramService:
        settings = settings_factory(deepgram_api_key=os.environ["DEEPGRAM_API_KEY"])
        return DeepgramService(settings=settings)

    @pytest.mark.asyncio
    async def test_transcribe_file(self, service: DeepgramService) -> None:
        """Test transcribing a real audio file."""
        audio_path = Path(os.environ["DEEPGRAM_TEST_AUDIO"])
        audio_data = audio_path.read_bytes()

        transcript, metadata = await service.transcribe_file(audio_data)

        assert isinstance(transcript, str)
        assert metadata.model == service._model
