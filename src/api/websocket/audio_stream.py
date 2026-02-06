"""WebSocket handler for Plivo bidirectional audio streaming.

Handles the Plivo WebSocket protocol:
- Receives audio from caller
- Sends audio back to caller
- Manages call session lifecycle
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from src.config import Settings, get_settings
from src.core.pipeline import AudioSender, VoicePipeline
from src.core.session import CallSession
from src.db.repositories.calls import AsyncCallLogRepository
from src.db.session import get_session_context
from src.logging_config import get_logger
from src.services.telephony.plivo import mulaw_to_pcm16, pcm16_to_mulaw

logger: Any = get_logger(__name__)

# System capacity limit to prevent overload
MAX_CONCURRENT_CALLS = 10  # Adjust based on server resources (CPU, memory)


class CallCapacityError(Exception):
    """Raised when system is at maximum call capacity."""

    pass


@dataclass
class CallSessionEntry:
    """Entry in the call session registry."""

    session: CallSession
    pipeline: VoicePipeline
    websocket: WebSocket | None = None
    stream_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CallSessionRegistry:
    """Thread-safe registry of active call sessions.

    Manages the lifecycle of call sessions across webhooks
    and WebSocket connections.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, CallSessionEntry] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        call_id: str,
        *,
        business_id: str = "himalayan_kitchen",
        caller_id_hash: str | None = None,
        caller_phone_encrypted: str | None = None,
        greeting_text: str | None = None,
        settings: Settings | None = None,
    ) -> tuple[CallSession, VoicePipeline]:
        """Create a new call session.

        Called when call is answered (from webhook).

        Raises:
            CallCapacityError: If system is at maximum capacity.
        """
        async with self._lock:
            if call_id in self._sessions:
                entry = self._sessions[call_id]
                return entry.session, entry.pipeline

            # Check capacity before creating new session
            if len(self._sessions) >= MAX_CONCURRENT_CALLS:
                logger.warning(
                    f"Max concurrent calls reached ({MAX_CONCURRENT_CALLS}), "
                    f"rejecting call {call_id}"
                )
                raise CallCapacityError(
                    f"System at capacity ({MAX_CONCURRENT_CALLS} concurrent calls)"
                )

            session = CallSession(
                call_id=call_id,
                business_id=business_id,
                caller_id_hash=caller_id_hash,
                caller_phone_encrypted=caller_phone_encrypted,
                greeting_text=greeting_text,
            )
            pipeline = VoicePipeline(session, settings=settings)

            self._sessions[call_id] = CallSessionEntry(
                session=session,
                pipeline=pipeline,
            )

            logger.info(
                f"Created session for call {call_id} (business: {business_id}, "
                f"active: {len(self._sessions)}/{MAX_CONCURRENT_CALLS})"
            )
            return session, pipeline

    async def get(self, call_id: str) -> tuple[CallSession, VoicePipeline] | None:
        """Get existing session and pipeline."""
        async with self._lock:
            entry = self._sessions.get(call_id)
            if entry:
                return entry.session, entry.pipeline
            return None

    async def set_websocket(
        self,
        call_id: str,
        websocket: WebSocket,
        stream_id: str = "",
    ) -> None:
        """Associate WebSocket connection with session."""
        async with self._lock:
            if call_id in self._sessions:
                self._sessions[call_id].websocket = websocket
                self._sessions[call_id].stream_id = stream_id

    async def remove(self, call_id: str) -> CallSessionEntry | None:
        """Remove session from registry.

        Returns the entry for final cleanup.
        """
        async with self._lock:
            return self._sessions.pop(call_id, None)

    async def close_all(self) -> None:
        """Close all sessions (for shutdown)."""
        async with self._lock:
            for call_id, entry in list(self._sessions.items()):
                try:
                    await entry.pipeline.finalize()
                except Exception as e:
                    logger.error(f"Error closing session {call_id}: {e}")
            self._sessions.clear()

    @property
    def active_count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)


# Global registry instance
call_registry = CallSessionRegistry()


class PlivoAudioSender(AudioSender):
    """Sends audio to Plivo via WebSocket.

    Implements the AudioSender protocol for VoicePipeline.
    """

    def __init__(
        self,
        websocket: WebSocket,
        stream_id: str,
        *,
        encoding: str = "linear16",
        sample_rate: int = 16000,
    ) -> None:
        self._websocket = websocket
        self._stream_id = stream_id
        self._encoding = encoding
        self._sample_rate = sample_rate
        self._sequence = 0

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio bytes to caller via WebSocket."""
        # Convert to μ-law if needed
        if self._encoding == "mulaw":
            audio_bytes = pcm16_to_mulaw(audio_bytes)

        # Encode as base64
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        # Send media message
        message = {
            "event": "media",
            "streamId": self._stream_id,
            "media": {
                "payload": audio_b64,
                "timestamp": str(self._sequence * 20),  # 20ms per chunk
            },
        }

        try:
            await self._websocket.send_json(message)
            self._sequence += 1
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")

    async def clear_audio(self) -> None:
        """Clear buffered audio (for barge-in)."""
        message = {
            "event": "clear",
            "streamId": self._stream_id,
        }

        try:
            await self._websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to clear audio: {e}")


async def audio_stream_endpoint(websocket: WebSocket, call_id: str) -> None:
    """Handle Plivo audio stream WebSocket connection.

    This is the main WebSocket endpoint for bidirectional audio.

    Protocol:
    - Receives JSON messages with events: start, media, dtmf, stop
    - Sends JSON messages with event: media (audio chunks)
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for call {call_id}")

    settings = get_settings()
    pipeline: VoicePipeline | None = None
    sender: PlivoAudioSender | None = None
    stream_id: str = ""
    encoding: str = "linear16"
    sample_rate: int = 16000

    try:
        while True:
            # Receive message
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received for call {call_id}")
                continue

            event = message.get("event", "")

            if event == "start":
                # Stream started - extract format info
                start_data = message.get("start", {})
                stream_id = start_data.get("streamId", call_id)

                media_format = start_data.get("mediaFormat", {})
                encoding = media_format.get("encoding", "linear16").lower()
                sample_rate = int(media_format.get("sampleRate", 16000))

                logger.info(
                    f"Stream started: {stream_id}, {encoding}@{sample_rate}Hz"
                )

                # Get or create session
                result = await call_registry.get(call_id)
                if result:
                    session, pipeline = result
                else:
                    session, pipeline = await call_registry.create(
                        call_id,
                        settings=settings,
                    )

                await call_registry.set_websocket(call_id, websocket, stream_id)

                # Configure pipeline
                await pipeline.configure(
                    input_sample_rate=sample_rate,
                    output_sample_rate=settings.tts_target_sample_rate,
                    input_encoding=encoding,
                )

                # Create sender
                sender = PlivoAudioSender(
                    websocket,
                    stream_id,
                    encoding=encoding,
                    sample_rate=sample_rate,
                )

                # Send greeting
                await pipeline.send_greeting(sender)

            elif event == "media":
                # Audio data received
                if not pipeline or not sender:
                    continue

                media = message.get("media", {})
                payload = media.get("payload", "")

                if not payload:
                    continue

                # Decode base64 audio
                try:
                    audio_bytes = base64.b64decode(payload)
                except Exception:
                    logger.warning("Failed to decode audio payload")
                    continue

                # Convert from μ-law if needed
                if encoding == "mulaw" or encoding == "pcmu":
                    audio_bytes = mulaw_to_pcm16(audio_bytes)

                # Process through pipeline
                await pipeline.process_audio_chunk(audio_bytes, sender)

            elif event == "dtmf":
                # DTMF digit pressed
                if pipeline and sender:
                    dtmf_data = message.get("dtmf", {})
                    digit = dtmf_data.get("digit", "")
                    if digit:
                        await pipeline.handle_dtmf(digit, sender)

            elif event == "stop":
                # Stream stopped
                logger.info(f"Stream stopped for call {call_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call {call_id}")

    except Exception as e:
        logger.error(f"WebSocket error for call {call_id}: {e}")

    finally:
        # Cleanup
        await _cleanup_call(call_id, pipeline)


async def _cleanup_call(
    call_id: str,
    pipeline: VoicePipeline | None,
) -> None:
    """Clean up call resources and persist metrics."""
    logger.info(f"Cleaning up call {call_id}")

    metrics: dict[str, Any] = {}

    # Finalize pipeline
    if pipeline:
        try:
            metrics = await pipeline.finalize()
        except Exception as e:
            logger.error(f"Error finalizing pipeline: {e}")

    # Remove from registry
    entry = await call_registry.remove(call_id)

    # Persist to database
    if entry and metrics:
        try:
            async with get_session_context() as db_session:
                repo = AsyncCallLogRepository(db_session)
                await repo.upsert_call_log(
                    call_id=call_id,
                    business_id=entry.session.business_id,
                    caller_id_hash=entry.session.caller_id_hash,
                    transcript=metrics.get("transcript"),
                    duration_seconds=int(metrics.get("duration_seconds", 0)),
                    detected_language=entry.session.detected_language,
                )
                await db_session.commit()
                logger.info(f"Persisted call log for {call_id}")
        except Exception as e:
            logger.error(f"Failed to persist call log: {e}")
