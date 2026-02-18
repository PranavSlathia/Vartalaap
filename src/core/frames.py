"""Typed frame dataclasses for the Vartalaap voice pipeline.

Frames flow through processors — one InterruptionFrame flushes everything
downstream simultaneously (soul.md: "Frames, not buffers").

Three layers:
  - Control  — lifecycle signals (StartFrame, EndFrame, CancelFrame)
  - System   — urgent, bypass normal queues (InterruptionFrame)
  - Data     — pipeline payload (Audio, Transcription, LLM, TTS, Function, Agent)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(UTC)


def _uid() -> str:
    return str(uuid4())


# ── Control frames ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StartFrame:
    """Pipeline start — call connected and ready to process."""
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class EndFrame:
    """Call ended cleanly — downstream processors should flush and close."""
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class CancelFrame:
    """Abort all processing immediately — call dropped or error."""
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


# ── System frames (urgent, bypass normal queues) ──────────────────────────────

@dataclass(frozen=True)
class InterruptionFrame:
    """Barge-in detected — flush everything downstream simultaneously.

    Sent when Silero VAD detects sustained speech while the bot is speaking.
    Every downstream processor must honour this frame immediately, cancelling
    any in-progress TTS synthesis and clearing audio buffers.
    """
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


# ── Data frames ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AudioRawFrame:
    """Raw audio chunk from telephony provider (Plivo).

    Contains μ-law or PCM audio before any processing.
    """
    audio: bytes
    sample_rate: int
    encoding: str  # "mulaw" | "linear16"
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class TranscriptionFrame:
    """STT output from Deepgram nova-2.

    is_final: this word/phrase is locked (won't change)
    speech_final: end of utterance detected — trigger LLM
    language: detected language code ("hi", "en", etc.)
    """
    text: str
    is_final: bool
    speech_final: bool
    language: str = "hi"
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class LLMTokenFrame:
    """Single token from Groq streaming response.

    is_sentence_boundary: True when a sentence-ending punctuation (.!?।)
    was detected in the accumulated buffer — signals TTS to start synthesis.
    """
    token: str
    is_sentence_boundary: bool = False
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class TTSAudioFrame:
    """Synthesized audio chunk from Cartesia sonic-multilingual.

    Contains resampled PCM ready for Plivo (8kHz μ-law after encoding).
    is_final: last chunk for this utterance.
    """
    audio_bytes: bytes
    sample_rate: int
    is_final: bool = False
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class FunctionCallFrame:
    """LLM has requested a tool call.

    filler_phrase: spoken to caller while tool executes
    (e.g. "Ek minute, main check kar rahi hoon…")
    """
    name: str
    args: dict[str, Any]
    filler_phrase: str = ""
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class FunctionResultFrame:
    """Result of a tool execution ready to feed back to LLM."""
    result: Any
    feed_back_to_llm: bool = True
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class AgentTransferFrame:
    """Hand off conversation to a different agent squad.

    new_agent_id: target agent identifier in the squad registry
    transfer_summary: brief context passed to the new agent
    """
    new_agent_id: str
    transfer_summary: str
    id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=_now)
