"""WebSocket handlers for real-time audio streaming.

This module provides WebSocket endpoints for Plivo audio:
- audio_stream_endpoint: Main WebSocket handler
- call_registry: Global session registry
"""

from src.api.websocket.audio_stream import (
    CallSessionEntry,
    CallSessionRegistry,
    PlivoAudioSender,
    audio_stream_endpoint,
    call_registry,
)

__all__ = [
    "audio_stream_endpoint",
    "call_registry",
    "CallSessionRegistry",
    "CallSessionEntry",
    "PlivoAudioSender",
]
