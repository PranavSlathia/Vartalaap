"""Text-to-Speech services (Piper, Edge TTS).

Provides TTS capabilities for the voice bot:
- PiperTTSService: Self-hosted, offline TTS using Piper
- EdgeTTSService: Microsoft Edge TTS fallback (unofficial API)
"""

from src.services.tts.edge import EdgeTTSService
from src.services.tts.elevenlabs import ElevenLabsTTSService
from src.services.tts.exceptions import (
    TTSConnectionError,
    TTSModelNotFoundError,
    TTSResamplingError,
    TTSServiceError,
    TTSSynthesisError,
)
from src.services.tts.piper import PiperTTSService
from src.services.tts.protocol import AudioChunk, SynthesisMetadata, TTSService
from src.services.tts.resampler import AudioResampler

__all__ = [
    # Services
    "PiperTTSService",
    "EdgeTTSService",
    "ElevenLabsTTSService",
    # Protocol
    "TTSService",
    # Data types
    "AudioChunk",
    "SynthesisMetadata",
    # Utilities
    "AudioResampler",
    # Exceptions
    "TTSServiceError",
    "TTSModelNotFoundError",
    "TTSSynthesisError",
    "TTSConnectionError",
    "TTSResamplingError",
]
