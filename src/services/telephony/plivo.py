"""Plivo telephony service for voice bot integration.

Handles:
- XML response generation for call flow
- Audio format conversion (μ-law ↔ PCM)
- Call management via Plivo SDK
"""

from __future__ import annotations

import audioop
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal
from xml.etree.ElementTree import Element, SubElement, tostring

from src.config import Settings, get_settings
from src.logging_config import get_logger

if TYPE_CHECKING:
    import plivo

logger: Any = get_logger(__name__)

# Audio format constants
MULAW_SAMPLE_WIDTH = 1  # μ-law is 8-bit
PCM16_SAMPLE_WIDTH = 2  # 16-bit PCM
TELEPHONY_SAMPLE_RATE = 8000
WIDEBAND_SAMPLE_RATE = 16000


@dataclass(frozen=True, slots=True)
class PlivoCallInfo:
    """Information about a Plivo call."""

    call_uuid: str
    from_number: str
    to_number: str
    direction: Literal["inbound", "outbound"]
    status: str = "initiated"
    answered_at: datetime | None = None

    @classmethod
    def from_webhook(cls, form_data: dict[str, str]) -> PlivoCallInfo:
        """Create from Plivo webhook form data."""
        return cls(
            call_uuid=form_data.get("CallUUID", ""),
            from_number=form_data.get("From", ""),
            to_number=form_data.get("To", ""),
            direction=form_data.get("Direction", "inbound"),  # type: ignore[arg-type]
            status=form_data.get("CallStatus", "initiated"),
            answered_at=datetime.now(UTC) if form_data.get("CallStatus") == "answered" else None,
        )


@dataclass(frozen=True, slots=True)
class AudioFormat:
    """Audio format specification for Plivo streams."""

    encoding: Literal["PCMU", "PCMA", "L16"]
    sample_rate: int = 8000
    channels: int = 1

    @property
    def content_type(self) -> str:
        """Get HTTP content type string."""
        if self.encoding == "L16":
            return f"audio/x-l16;rate={self.sample_rate}"
        elif self.encoding == "PCMU":
            return "audio/basic"  # μ-law
        else:
            return "audio/x-alaw"

    @property
    def is_pcm16(self) -> bool:
        """Check if format is 16-bit linear PCM."""
        return self.encoding == "L16"


class PlivoService:
    """Service for Plivo telephony operations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: plivo.RestClient | None = None

    @property
    def client(self) -> plivo.RestClient:
        """Lazy-initialize Plivo REST client."""
        if self._client is None:
            import plivo

            self._client = plivo.RestClient(
                auth_id=self._settings.plivo_auth_id,
                auth_token=self._settings.plivo_auth_token.get_secret_value(),
            )
        return self._client

    def generate_stream_xml(
        self,
        websocket_url: str,
        *,
        bidirectional: bool = True,
        audio_track: str = "inbound",
        content_type: str = "audio/x-l16;rate=16000",
        stream_timeout: int = 3600,
    ) -> str:
        """Generate Plivo XML for WebSocket audio streaming.

        Args:
            websocket_url: WebSocket URL for audio stream
            bidirectional: Enable bidirectional audio
            audio_track: Which audio track to stream (inbound/outbound/both)
            content_type: Audio content type
            stream_timeout: Stream timeout in seconds

        Returns:
            XML string for Plivo response
        """
        response = Element("Response")

        stream = SubElement(response, "Stream")
        stream.set("bidirectional", str(bidirectional).lower())
        stream.set("audioTrack", audio_track)
        stream.set("contentType", content_type)
        stream.set("streamTimeout", str(stream_timeout))
        stream.text = websocket_url

        xml_str = tostring(response, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'

    def generate_speak_xml(
        self,
        text: str,
        *,
        voice: str = "Polly.Aditi",
        language: str = "hi-IN",
    ) -> str:
        """Generate Plivo XML for text-to-speech.

        Used for fallback when custom TTS fails.
        """
        response = Element("Response")

        speak = SubElement(response, "Speak")
        speak.set("voice", voice)
        speak.set("language", language)
        speak.text = text

        xml_str = tostring(response, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'

    def generate_hangup_xml(self, reason: str = "") -> str:
        """Generate Plivo XML to hangup call."""
        response = Element("Response")

        if reason:
            speak = SubElement(response, "Speak")
            speak.set("voice", "Polly.Aditi")
            speak.set("language", "hi-IN")
            speak.text = reason

        SubElement(response, "Hangup")

        xml_str = tostring(response, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'

    def generate_wait_xml(self, seconds: int = 1) -> str:
        """Generate Plivo XML to wait/pause."""
        response = Element("Response")

        wait = SubElement(response, "Wait")
        wait.set("length", str(seconds))

        xml_str = tostring(response, encoding="unicode")
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_str}'

    async def make_call(
        self,
        from_number: str,
        to_number: str,
        answer_url: str,
        *,
        hangup_url: str | None = None,
        fallback_url: str | None = None,
    ) -> PlivoCallInfo:
        """Initiate an outbound call.

        Args:
            from_number: Caller ID (must be a Plivo number)
            to_number: Number to call
            answer_url: Webhook URL when call is answered
            hangup_url: Optional webhook for hangup events
            fallback_url: Optional fallback URL on error

        Returns:
            Call information
        """
        import asyncio

        params: dict[str, Any] = {
            "from_": from_number,
            "to_": to_number,
            "answer_url": answer_url,
        }
        if hangup_url:
            params["hangup_url"] = hangup_url
        if fallback_url:
            params["fallback_url"] = fallback_url

        # Run sync SDK call in thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.calls.create(**params),
        )

        return PlivoCallInfo(
            call_uuid=response.request_uuid,
            from_number=from_number,
            to_number=to_number,
            direction="outbound",
            status="initiated",
        )

    async def hangup_call(self, call_uuid: str) -> bool:
        """Hangup an active call.

        Returns:
            True if successful
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.calls.delete(call_uuid),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to hangup call {call_uuid}: {e}")
            return False

    async def health_check(self) -> bool:
        """Check Plivo API connectivity."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            # Get account details to verify credentials
            await loop.run_in_executor(
                None,
                lambda: self.client.account.get(),
            )
            return True
        except Exception as e:
            logger.warning(f"Plivo health check failed: {e}")
            return False


# =============================================================================
# Audio Conversion Utilities
# =============================================================================


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert μ-law encoded audio to 16-bit signed PCM.

    μ-law (PCMU) is the standard encoding for telephony audio.
    This converts it to linear 16-bit PCM for processing.

    Args:
        mulaw_bytes: μ-law encoded audio bytes

    Returns:
        16-bit signed PCM bytes (little-endian)
    """
    return audioop.ulaw2lin(mulaw_bytes, PCM16_SAMPLE_WIDTH)


def pcm16_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit signed PCM to μ-law encoding.

    Args:
        pcm_bytes: 16-bit signed PCM bytes (little-endian)

    Returns:
        μ-law encoded audio bytes
    """
    return audioop.lin2ulaw(pcm_bytes, PCM16_SAMPLE_WIDTH)


def alaw_to_pcm16(alaw_bytes: bytes) -> bytes:
    """Convert A-law encoded audio to 16-bit signed PCM.

    A-law (PCMA) is used in European telephony.

    Args:
        alaw_bytes: A-law encoded audio bytes

    Returns:
        16-bit signed PCM bytes (little-endian)
    """
    return audioop.alaw2lin(alaw_bytes, PCM16_SAMPLE_WIDTH)


def pcm16_to_alaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit signed PCM to A-law encoding.

    Args:
        pcm_bytes: 16-bit signed PCM bytes (little-endian)

    Returns:
        A-law encoded audio bytes
    """
    return audioop.lin2alaw(pcm_bytes, PCM16_SAMPLE_WIDTH)


def resample_audio(
    audio_bytes: bytes,
    source_rate: int,
    target_rate: int,
    *,
    sample_width: int = PCM16_SAMPLE_WIDTH,
    channels: int = 1,
) -> bytes:
    """Resample audio using audioop (lower quality than soxr but no deps).

    For high-quality resampling, use AudioResampler from tts.resampler.

    Args:
        audio_bytes: Input audio bytes
        source_rate: Source sample rate
        target_rate: Target sample rate
        sample_width: Bytes per sample (2 for 16-bit)
        channels: Number of channels

    Returns:
        Resampled audio bytes
    """
    if source_rate == target_rate:
        return audio_bytes

    # audioop.ratecv for resampling
    converted, _ = audioop.ratecv(
        audio_bytes,
        sample_width,
        channels,
        source_rate,
        target_rate,
        None,
    )
    return converted


def compute_audio_energy(audio_bytes: bytes, sample_width: int = 2) -> float:
    """Compute RMS energy of audio for VAD.

    Args:
        audio_bytes: PCM audio bytes
        sample_width: Bytes per sample

    Returns:
        RMS energy value (0.0 to 32767.0 for 16-bit audio)
    """
    if not audio_bytes:
        return 0.0
    return float(audioop.rms(audio_bytes, sample_width))


def is_speech(
    audio_bytes: bytes,
    threshold: float = 500.0,
    sample_width: int = 2,
) -> bool:
    """Simple energy-based voice activity detection.

    Args:
        audio_bytes: PCM audio bytes
        threshold: Energy threshold for speech detection
        sample_width: Bytes per sample

    Returns:
        True if audio likely contains speech
    """
    energy = compute_audio_energy(audio_bytes, sample_width)
    return energy > threshold
