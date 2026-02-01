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
    from src.db.models import Business
    from src.services.knowledge.protocol import KnowledgeResult


@dataclass
class ConversationManager:
    """Manages conversation state and context building."""

    business_id: str
    messages: list[Message] = field(default_factory=list)
    max_history: int = 10  # Keep last N turns for context window

    _business_config: dict | None = field(default=None, init=False, repr=False)
    _business_db: "Business | None" = field(default=None, init=False, repr=False)
    _retrieved_knowledge: "KnowledgeResult | None" = field(default=None, init=False, repr=False)

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

    def set_business(self, business: "Business") -> None:
        """Set database Business object for config.

        When set, database config takes precedence over YAML.
        """
        self._business_db = business

    def set_retrieved_knowledge(self, knowledge: "KnowledgeResult") -> None:
        """Set retrieved knowledge for LLM context injection."""
        self._retrieved_knowledge = knowledge

    def build_context(
        self,
        current_capacity: int | None = None,
        caller_history: str | None = None,
    ) -> ConversationContext:
        """Build context for LLM from business config.

        Priority:
        1. Database Business object (if set via set_business)
        2. YAML config file (fallback)
        """
        # Prefer database config over YAML
        if self._business_db:
            return self._build_context_from_db(
                current_capacity=current_capacity,
                caller_history=caller_history,
            )

        # Fallback to YAML config
        config = self._load_business_config()

        business = config.get("business", {})
        rules = config.get("reservation_rules", {})
        tz_name = business.get("timezone", "Asia/Kolkata")

        # Use timezone-aware datetime for consistent prompt timestamps
        try:
            tz = ZoneInfo(tz_name)
        except KeyError:
            tz = ZoneInfo("Asia/Kolkata")

        # Load prompt template and few-shot examples
        prompt_template = self._load_prompt_template()
        few_shot_examples = self._get_few_shot_examples()

        return ConversationContext(
            business_name=business.get("name", "Restaurant"),
            business_type=business.get("type", "restaurant"),
            timezone=tz_name,
            current_datetime=datetime.now(tz),
            operating_hours=business.get("operating_hours", {}),
            reservation_rules=rules,
            current_capacity=current_capacity,
            caller_history=caller_history,
            prompt_template=prompt_template,
            few_shot_examples=few_shot_examples,
            retrieved_knowledge=self._retrieved_knowledge,
        )

    def _build_context_from_db(
        self,
        current_capacity: int | None = None,
        caller_history: str | None = None,
    ) -> ConversationContext:
        """Build context from database Business object."""
        import json

        business = self._business_db
        assert business is not None

        tz_name = business.timezone or "Asia/Kolkata"

        try:
            tz = ZoneInfo(tz_name)
        except KeyError:
            tz = ZoneInfo("Asia/Kolkata")

        # Parse JSON fields
        operating_hours = {}
        if business.operating_hours_json:
            try:
                operating_hours = json.loads(business.operating_hours_json)
            except json.JSONDecodeError:
                pass

        reservation_rules = {}
        if business.reservation_rules_json:
            try:
                reservation_rules = json.loads(business.reservation_rules_json)
            except json.JSONDecodeError:
                pass

        # Load prompt template and few-shot examples
        prompt_template = self._load_prompt_template()
        few_shot_examples = self._get_few_shot_examples()

        return ConversationContext(
            business_name=business.name,
            business_type=business.type.value,
            timezone=tz_name,
            current_datetime=datetime.now(tz),
            operating_hours=operating_hours,
            reservation_rules=reservation_rules,
            menu_summary=business.menu_summary,
            current_capacity=current_capacity,
            caller_history=caller_history,
            prompt_template=prompt_template,
            few_shot_examples=few_shot_examples,
            retrieved_knowledge=self._retrieved_knowledge,
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

    def _load_prompt_template(self) -> str | None:
        """Load prompt template from config files.

        Tries business-specific template first, then falls back to generic.
        """
        paths = [
            Path(f"config/prompts/{self.business_id}_bot.txt"),
            Path("config/prompts/restaurant_bot.txt"),
        ]

        for path in paths:
            if path.exists():
                return path.read_text()

        return None

    def _get_few_shot_examples(self) -> list[dict[str, str]]:
        """Get few-shot examples for the LLM.

        Uses the RestaurantPromptBuilder's examples.
        """
        from src.prompts.restaurant import FEW_SHOT_EXAMPLES

        # Return first 6 examples to save tokens (already subset in builder)
        return [
            {"user": ex["user"], "assistant": ex["assistant"]}
            for ex in FEW_SHOT_EXAMPLES[:6]
        ]

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
