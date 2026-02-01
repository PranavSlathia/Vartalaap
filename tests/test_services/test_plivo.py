"""Tests for Plivo telephony service."""

import pytest

from src.services.telephony.plivo import (
    PCM16_SAMPLE_WIDTH,
    TELEPHONY_SAMPLE_RATE,
    WIDEBAND_SAMPLE_RATE,
    AudioFormat,
    PlivoCallInfo,
    PlivoService,
    alaw_to_pcm16,
    compute_audio_energy,
    is_speech,
    mulaw_to_pcm16,
    pcm16_to_alaw,
    pcm16_to_mulaw,
    resample_audio,
)


class TestPlivoCallInfo:
    """Tests for PlivoCallInfo dataclass."""

    def test_create_call_info(self) -> None:
        """Test basic call info creation."""
        call_info = PlivoCallInfo(
            call_uuid="test-uuid",
            from_number="+911234567890",
            to_number="+919876543210",
            direction="inbound",
        )
        assert call_info.call_uuid == "test-uuid"
        assert call_info.from_number == "+911234567890"
        assert call_info.direction == "inbound"
        assert call_info.status == "initiated"
        assert call_info.answered_at is None

    def test_from_webhook(self) -> None:
        """Test creating call info from webhook data."""
        form_data = {
            "CallUUID": "webhook-uuid",
            "From": "+919999999999",
            "To": "+918888888888",
            "Direction": "inbound",
            "CallStatus": "ringing",
        }
        call_info = PlivoCallInfo.from_webhook(form_data)

        assert call_info.call_uuid == "webhook-uuid"
        assert call_info.from_number == "+919999999999"
        assert call_info.to_number == "+918888888888"
        assert call_info.direction == "inbound"
        assert call_info.status == "ringing"

    def test_from_webhook_answered(self) -> None:
        """Test that answered_at is set when call is answered."""
        form_data = {
            "CallUUID": "answered-uuid",
            "From": "+919999999999",
            "To": "+918888888888",
            "Direction": "inbound",
            "CallStatus": "answered",
        }
        call_info = PlivoCallInfo.from_webhook(form_data)

        assert call_info.answered_at is not None

    def test_from_webhook_defaults(self) -> None:
        """Test webhook parsing with missing fields."""
        form_data = {}
        call_info = PlivoCallInfo.from_webhook(form_data)

        assert call_info.call_uuid == ""
        assert call_info.from_number == ""
        assert call_info.to_number == ""


class TestAudioFormat:
    """Tests for AudioFormat dataclass."""

    def test_pcm16_content_type(self) -> None:
        """Test L16 content type."""
        fmt = AudioFormat(encoding="L16", sample_rate=16000)
        assert fmt.content_type == "audio/x-l16;rate=16000"
        assert fmt.is_pcm16 is True

    def test_mulaw_content_type(self) -> None:
        """Test PCMU content type."""
        fmt = AudioFormat(encoding="PCMU", sample_rate=8000)
        assert fmt.content_type == "audio/basic"
        assert fmt.is_pcm16 is False

    def test_alaw_content_type(self) -> None:
        """Test PCMA content type."""
        fmt = AudioFormat(encoding="PCMA", sample_rate=8000)
        assert fmt.content_type == "audio/x-alaw"
        assert fmt.is_pcm16 is False


class TestPlivoService:
    """Tests for PlivoService."""

    @pytest.fixture
    def service(self, settings_factory) -> PlivoService:
        """Create service with test settings."""
        return PlivoService(settings=settings_factory())

    def test_generate_stream_xml(self, service: PlivoService) -> None:
        """Test stream XML generation."""
        xml = service.generate_stream_xml("wss://example.com/ws/audio/123")

        assert '<?xml version="1.0"' in xml
        assert "<Response>" in xml
        assert "<Stream" in xml
        assert 'bidirectional="true"' in xml
        assert "wss://example.com/ws/audio/123" in xml

    def test_generate_stream_xml_custom_params(self, service: PlivoService) -> None:
        """Test stream XML with custom parameters."""
        xml = service.generate_stream_xml(
            "wss://example.com/ws",
            bidirectional=False,
            audio_track="both",
            content_type="audio/basic",
            stream_timeout=1800,
        )

        assert 'bidirectional="false"' in xml
        assert 'audioTrack="both"' in xml
        assert 'contentType="audio/basic"' in xml
        assert 'streamTimeout="1800"' in xml

    def test_generate_speak_xml(self, service: PlivoService) -> None:
        """Test speak XML generation."""
        xml = service.generate_speak_xml("Namaste!")

        assert "<Speak" in xml
        assert "Namaste!" in xml
        assert 'voice="Polly.Aditi"' in xml
        assert 'language="hi-IN"' in xml

    def test_generate_hangup_xml_no_reason(self, service: PlivoService) -> None:
        """Test hangup XML without reason."""
        xml = service.generate_hangup_xml()

        assert "<Hangup" in xml
        assert "<Speak" not in xml

    def test_generate_hangup_xml_with_reason(self, service: PlivoService) -> None:
        """Test hangup XML with reason."""
        xml = service.generate_hangup_xml(reason="Goodbye!")

        assert "<Hangup" in xml
        assert "<Speak" in xml
        assert "Goodbye!" in xml

    def test_generate_wait_xml(self, service: PlivoService) -> None:
        """Test wait XML generation."""
        xml = service.generate_wait_xml(seconds=5)

        assert "<Wait" in xml
        assert 'length="5"' in xml


class TestAudioConversion:
    """Tests for audio conversion utilities."""

    def test_mulaw_roundtrip(self) -> None:
        """Test μ-law conversion roundtrip."""
        # Create simple PCM data
        original_pcm = bytes([0, 0, 0, 128, 255, 127] * 100)  # 600 bytes

        # Convert to μ-law and back
        mulaw = pcm16_to_mulaw(original_pcm)
        recovered_pcm = mulaw_to_pcm16(mulaw)

        # μ-law is lossy, so we just check lengths
        assert len(mulaw) == len(original_pcm) // 2  # μ-law is 8-bit
        assert len(recovered_pcm) == len(original_pcm)

    def test_alaw_roundtrip(self) -> None:
        """Test A-law conversion roundtrip."""
        original_pcm = bytes([0, 0, 0, 128, 255, 127] * 100)

        alaw = pcm16_to_alaw(original_pcm)
        recovered_pcm = alaw_to_pcm16(alaw)

        assert len(alaw) == len(original_pcm) // 2
        assert len(recovered_pcm) == len(original_pcm)

    def test_resample_same_rate(self) -> None:
        """Test resampling with same source and target rate."""
        audio = bytes([0, 0, 128, 128] * 100)

        resampled = resample_audio(audio, 16000, 16000)

        assert resampled == audio

    def test_resample_downsample(self) -> None:
        """Test downsampling audio."""
        # 16kHz to 8kHz should halve the sample count
        audio = bytes([0, 0, 128, 128] * 200)  # 800 bytes = 400 samples

        resampled = resample_audio(audio, 16000, 8000)

        # Resampled should be approximately half the size
        assert len(resampled) < len(audio)

    def test_compute_audio_energy_silence(self) -> None:
        """Test energy computation on silence."""
        silence = bytes(1600)  # 800 samples of silence

        energy = compute_audio_energy(silence)

        assert energy == 0.0

    def test_compute_audio_energy_loud(self) -> None:
        """Test energy computation on loud audio."""
        # Max amplitude 16-bit audio
        loud = bytes([255, 127] * 400)  # 32767 repeated

        energy = compute_audio_energy(loud)

        assert energy > 30000  # Should be close to 32767

    def test_compute_audio_energy_empty(self) -> None:
        """Test energy computation on empty audio."""
        energy = compute_audio_energy(b"")

        assert energy == 0.0

    def test_is_speech_silence(self) -> None:
        """Test speech detection on silence."""
        silence = bytes(1600)

        assert is_speech(silence) is False

    def test_is_speech_loud(self) -> None:
        """Test speech detection on loud audio."""
        loud = bytes([255, 127] * 400)

        assert is_speech(loud) is True

    def test_is_speech_custom_threshold(self) -> None:
        """Test speech detection with custom threshold."""
        # Medium amplitude
        medium = bytes([0, 64] * 400)  # 16384 amplitude

        # Should detect with low threshold
        assert is_speech(medium, threshold=100) is True

        # Should not detect with high threshold
        assert is_speech(medium, threshold=20000) is False


class TestConstants:
    """Tests for audio constants."""

    def test_sample_width(self) -> None:
        """Test PCM16 sample width."""
        assert PCM16_SAMPLE_WIDTH == 2

    def test_sample_rates(self) -> None:
        """Test sample rate constants."""
        assert TELEPHONY_SAMPLE_RATE == 8000
        assert WIDEBAND_SAMPLE_RATE == 16000
