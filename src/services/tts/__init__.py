"""Text-to-Speech services.

Primary: CartesiaTTSService (sonic-multilingual, streaming, Hindi/English)
"""

from src.services.tts.cartesia import CartesiaTTSService
from src.services.tts.exceptions import (
    TTSConnectionError,
    TTSModelNotFoundError,
    TTSResamplingError,
    TTSServiceError,
    TTSSynthesisError,
)
from src.services.tts.protocol import AudioChunk, SynthesisMetadata, TTSService
from src.services.tts.resampler import AudioResampler

__all__ = [
    # Primary service
    "CartesiaTTSService",
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
