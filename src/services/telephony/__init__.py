"""Telephony services (Plivo).

This module provides integration with Plivo for voice telephony:
- PlivoService: XML generation, call management
- Audio conversion utilities for μ-law/A-law/PCM
"""

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

__all__ = [
    # Service
    "PlivoService",
    # Data classes
    "PlivoCallInfo",
    "AudioFormat",
    # Audio conversion
    "mulaw_to_pcm16",
    "pcm16_to_mulaw",
    "alaw_to_pcm16",
    "pcm16_to_alaw",
    "resample_audio",
    # VAD utilities
    "compute_audio_energy",
    "is_speech",
    # Constants
    "PCM16_SAMPLE_WIDTH",
    "TELEPHONY_SAMPLE_RATE",
    "WIDEBAND_SAMPLE_RATE",
]
