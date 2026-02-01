"""LLM service protocol and data types."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class Role(str, Enum):
    """Message role in conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    """A single message in conversation history."""

    role: Role
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ConversationContext:
    """Context injected into system prompt."""

    business_name: str
    business_type: str
    timezone: str
    current_datetime: datetime
    operating_hours: dict[str, str]
    reservation_rules: dict[str, int]
    menu_summary: str | None = None
    current_capacity: int | None = None
    caller_history: str | None = None
    prompt_template: str | None = None  # Custom prompt template from config
    few_shot_examples: list[dict[str, str]] = field(default_factory=list)


@dataclass
class StreamMetadata:
    """Metadata collected during/after streaming."""

    model: str = ""
    first_token_ms: float | None = None
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None


class LLMService(Protocol):
    """Protocol for LLM service implementations."""

    async def stream_chat(
        self,
        messages: list[Message],
        context: ConversationContext,
        *,
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> tuple[AsyncGenerator[str, None], StreamMetadata]:
        """Stream chat completion with context injection.

        Returns:
            Tuple of (content generator, metadata object).
            Metadata is populated after generator exhaustion.
        """
        ...

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (for rate limiting)."""
        ...

    async def health_check(self) -> bool:
        """Check if the service is operational."""
        ...
