"""Core voice pipeline components.

This module provides the core orchestration for voice calls:
- CallSession: Manages per-call state and metrics
- ConversationManager: Handles conversation history and context
- VoicePipeline: Orchestrates STT → LLM → TTS pipeline
"""

from src.core.context import ConversationManager
from src.core.pipeline import (
    AudioBuffer,
    AudioSender,
    PipelineConfig,
    PipelineMetrics,
    PipelineState,
    VoicePipeline,
)
from src.core.session import CallSession

__all__ = [
    # Session management
    "CallSession",
    "ConversationManager",
    # Pipeline
    "VoicePipeline",
    "PipelineState",
    "PipelineConfig",
    "PipelineMetrics",
    "AudioBuffer",
    "AudioSender",
]
