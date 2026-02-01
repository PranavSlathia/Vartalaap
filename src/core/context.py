"""Conversation context management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import yaml

from src.services.llm.protocol import ConversationContext, Message, Role

if TYPE_CHECKING:
    pass


@dataclass
class ConversationManager:
    """Manages conversation state and context building."""

    business_id: str
    messages: list[Message] = field(default_factory=list)
    max_history: int = 10  # Keep last N turns for context window

    _business_config: dict | None = field(default=None, init=False, repr=False)

    def add_user_message(self, content: str) -> Message:
        """Add a user message to history."""
        msg = Message(role=Role.USER, content=content)
        self.messages.append(msg)
        self._trim_history()
        return msg

    def add_assistant_message(self, content: str) -> Message:
        """Add an assistant message to history."""
        msg = Message(role=Role.ASSISTANT, content=content)
        self.messages.append(msg)
        self._trim_history()
        return msg

    def _trim_history(self) -> None:
        """Keep only the last max_history messages."""
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history :]

    def build_context(
        self,
        current_capacity: int | None = None,
        caller_history: str | None = None,
    ) -> ConversationContext:
        """Build context for LLM from business config."""
        config = self._load_business_config()

        business = config.get("business", {})
        rules = config.get("reservation_rules", {})
        tz_name = business.get("timezone", "Asia/Kolkata")

        # Use timezone-aware datetime for consistent prompt timestamps
        try:
            tz = ZoneInfo(tz_name)
        except KeyError:
            tz = ZoneInfo("Asia/Kolkata")

        return ConversationContext(
            business_name=business.get("name", "Restaurant"),
            business_type=business.get("type", "restaurant"),
            timezone=tz_name,
            current_datetime=datetime.now(tz),
            operating_hours=business.get("operating_hours", {}),
            reservation_rules=rules,
            current_capacity=current_capacity,
            caller_history=caller_history,
        )

    def _load_business_config(self) -> dict:
        """Load and cache business configuration."""
        if self._business_config is None:
            config_path = Path(f"config/business/{self.business_id}.yaml")
            if config_path.exists():
                with open(config_path) as f:
                    self._business_config = yaml.safe_load(f)
            else:
                self._business_config = {}
        return self._business_config

    def get_transcript(self) -> str:
        """Get full conversation transcript for logging."""
        lines = []
        for msg in self.messages:
            speaker = "Caller" if msg.role == Role.USER else "Bot"
            lines.append(f"[{msg.timestamp.isoformat()}] {speaker}: {msg.content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
