"""Speech-to-Text services (Deepgram)."""

from src.services.stt.deepgram import DeepgramService
from src.services.stt.protocol import (
    DetectedLanguage,
    STTService,
    TranscriptChunk,
    TranscriptMetadata,
)

__all__ = [
    "DeepgramService",
    "DetectedLanguage",
    "STTService",
    "TranscriptChunk",
    "TranscriptMetadata",
]
