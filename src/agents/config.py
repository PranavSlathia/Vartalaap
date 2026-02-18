"""AssistantConfig — the complete voice bot as a Pydantic config object.

A new business = a new AssistantConfig instance. No pipeline code changes.
Inspired by Vapi's assistant-as-config pattern, adapted for Indian SMB context.

Three-layer provider abstraction:
  STTConfig   — transcription (Deepgram, Bhashini)
  LLMConfig   — language model (Groq, OpenAI)
  TTSConfig   — voice synthesis (Cartesia)

Each layer is independently swappable. Changing STT provider does not
touch LLM or TTS code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── STT Layer ─────────────────────────────────────────────────────────────────

class STTConfig(BaseModel):
    """Speech-to-text transcription configuration."""

    provider: Literal["deepgram"] = "deepgram"
    model: str = "nova-2"
    language: str = "hi"            # Primary language; Deepgram also detects English
    endpointing_ms: int = 400       # Silence (ms) before utterance is declared complete
    encoding: str = "mulaw"         # "mulaw" for Plivo telephony, "linear16" for testing


# ── LLM Layer ─────────────────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    """Language model configuration."""

    provider: Literal["groq"] = "groq"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=256, ge=1, le=4096)
    # system_prompt is on AssistantConfig, not here — it's business logic, not model config


# ── TTS Layer ─────────────────────────────────────────────────────────────────

class TTSConfig(BaseModel):
    """Text-to-speech voice configuration."""

    provider: Literal["cartesia"] = "cartesia"
    model: str = "sonic-multilingual"
    voice_id: str                   # Required — from play.cartesia.ai/voices
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_sample_rate: int = 8000  # 8000Hz for Plivo telephony


# ── Tool Layer ────────────────────────────────────────────────────────────────

class ToolConfig(BaseModel):
    """A single callable tool available to the LLM.

    filler_hi / filler_en: spoken immediately when LLM invokes this tool,
    while the async function executes. Prevents dead air.
    """

    name: str                       # Function name in tool registry
    description: str                # Shown to LLM in system context
    filler_hi: str = ""             # Hindi filler: "Ek second, check kar rahi hoon..."
    filler_en: str = ""             # English filler: "One moment, let me check..."
    enabled: bool = True


# ── Top-level AssistantConfig ─────────────────────────────────────────────────

class AssistantConfig(BaseModel):
    """Complete voice assistant configuration.

    One AssistantConfig = one voice bot persona.
    New business → new instance of this class (no code changes).

    Usage:
        from config.himalayan_kitchen import ASSISTANT_CONFIG

        session = CallSession(
            business_id="himalayan_kitchen",
            assistant_config=ASSISTANT_CONFIG,
        )
    """

    # Identity
    name: str
    business_id: str                # Must match a row in the businesses table
    system_prompt: str              # Full system prompt for the LLM

    # Pipeline layers (independently swappable)
    stt: STTConfig = Field(default_factory=STTConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig                  # Required — voice_id must be set

    # Conversation behaviour
    first_message: str              # Spoken when call connects
    tools: list[ToolConfig] = Field(default_factory=list)
    silence_timeout_s: int = 30     # Hang up after this many seconds of silence
    barge_in_enabled: bool = True   # Allow user to interrupt bot speech
    min_interruption_ms: int = 500  # VAD must detect speech for this long before barge-in

    class Config:
        # Allow string literals alongside enum values for forward compatibility
        use_enum_values = True
