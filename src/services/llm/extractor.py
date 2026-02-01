"""Extract structured reservation data from LLM responses.

Uses a two-pass approach:
1. First pass: LLM generates natural conversational response (streaming)
2. Second pass: Separate LLM call extracts structured JSON from the turn

This preserves low-latency streaming for voice while enabling structured extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from src.logging_config import get_logger

if TYPE_CHECKING:
    from src.services.llm.groq import GroqService
    from src.services.llm.protocol import Message

logger: Any = get_logger(__name__)


class ExtractionIntent(Enum):
    """Intent detected from conversation."""

    MAKE_RESERVATION = auto()
    MODIFY_RESERVATION = auto()
    CANCEL_RESERVATION = auto()
    INQUIRY = auto()  # Questions about hours, menu, etc.
    CHITCHAT = auto()  # General conversation
    OPERATOR_REQUEST = auto()  # Wants to speak to human


@dataclass
class ExtractedReservation:
    """Structured reservation data extracted from conversation.

    All fields except intent are optional - they get filled in
    as the conversation progresses.
    """

    intent: ExtractionIntent
    party_size: int | None = None
    reservation_date: date | None = None
    reservation_time: str | None = None  # HH:MM format (24h)
    customer_name: str | None = None
    special_requests: str | None = None
    confidence: float = 0.0
    missing_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Calculate missing fields after initialization."""
        self.missing_fields = self._calculate_missing_fields()

    def _calculate_missing_fields(self) -> list[str]:
        """Determine which required fields are still missing."""
        missing = []
        if self.intent == ExtractionIntent.MAKE_RESERVATION:
            if self.party_size is None:
                missing.append("party_size")
            if self.reservation_date is None:
                missing.append("date")
            if self.reservation_time is None:
                missing.append("time")
            if self.customer_name is None:
                missing.append("name")
        return missing

    @property
    def is_complete(self) -> bool:
        """Check if all required fields are filled."""
        return len(self.missing_fields) == 0

    def merge_with(self, other: ExtractedReservation) -> ExtractedReservation:
        """Merge another extraction, keeping non-None values."""
        return ExtractedReservation(
            intent=other.intent if other.intent != ExtractionIntent.CHITCHAT else self.intent,
            party_size=other.party_size if other.party_size is not None else self.party_size,
            reservation_date=(
                other.reservation_date
                if other.reservation_date is not None
                else self.reservation_date
            ),
            reservation_time=(
                other.reservation_time
                if other.reservation_time is not None
                else self.reservation_time
            ),
            customer_name=(
                other.customer_name if other.customer_name is not None else self.customer_name
            ),
            special_requests=(
                other.special_requests
                if other.special_requests is not None
                else self.special_requests
            ),
            confidence=max(self.confidence, other.confidence),
        )


# Extraction system prompt
EXTRACTION_SYSTEM_PROMPT = """You are analyzing a restaurant voice conversation to extract reservation details.

Output ONLY valid JSON with these fields (use null for unknown/not mentioned):
{
  "intent": "MAKE_RESERVATION" | "MODIFY" | "CANCEL" | "INQUIRY" | "CHITCHAT" | "OPERATOR",
  "party_size": number or null,
  "date": "YYYY-MM-DD" or "today" or "tomorrow" or null,
  "time": "HH:MM" (24h format) or null,
  "name": string or null,
  "special_requests": string or null,
  "confidence": 0.0 to 1.0
}

Extraction Rules:
- Only extract EXPLICITLY stated information, never assume
- Hindi numbers: "char log" = 4, "paanch" = 5, "do" = 2, "teen" = 3
- Dates: "kal" = tomorrow, "parson" = day after tomorrow, "aaj" = today
- Times: "7 baje" = "19:00", "saat baje shaam" = "19:00", "dopahar" = afternoon (null - need specific)
- "shaam" alone = evening (null - need specific time)
- If user says "table book karna hai" without details, intent is MAKE_RESERVATION but fields are null
- confidence should be high (0.8+) only when information is explicitly stated"""


class ReservationExtractor:
    """Extract reservation details using Groq JSON mode.

    Uses a separate LLM call after the conversational response
    to extract structured data from the turn.
    """

    def __init__(self, llm_service: GroqService | None = None) -> None:
        """Initialize extractor.

        Args:
            llm_service: Optional GroqService instance. If not provided,
                         creates a new one when needed.
        """
        self._llm: GroqService | None = llm_service
        self._today: date | None = None  # For date resolution

    @property
    def llm(self) -> GroqService:
        """Lazy initialization of LLM service."""
        if self._llm is None:
            from src.services.llm.groq import GroqService

            self._llm = GroqService()
        return self._llm

    async def extract(
        self,
        user_message: str,
        assistant_response: str,
        conversation_history: list[Message] | None = None,
    ) -> ExtractedReservation | None:
        """Extract structured data from a conversation turn.

        Args:
            user_message: What the user said (transcript)
            assistant_response: What the bot replied
            conversation_history: Optional full conversation for context

        Returns:
            ExtractedReservation if extraction succeeded, None on error
        """
        # Build extraction prompt
        history_summary = self._summarize_history(conversation_history) if conversation_history else ""

        extraction_prompt = f"""Analyze this restaurant voice conversation turn:

{f"Previous context: {history_summary}" if history_summary else ""}

User: {user_message}
Assistant: {assistant_response}

Extract reservation details from the USER's message. Output JSON only."""

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": extraction_prompt},
        ]

        try:
            result = await self.llm.extract_json(messages)
            return self._parse_extraction(result)
        except Exception as e:
            logger.warning(f"Extraction failed: {e}")
            return None

    def _summarize_history(self, history: list[Message]) -> str:
        """Create a brief summary of conversation history for context."""
        if not history:
            return ""

        # Take last 4 messages
        recent = history[-4:]
        lines = []
        for msg in recent:
            role = "User" if msg.role.value == "user" else "Bot"
            # Truncate long messages
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _parse_extraction(self, raw: dict) -> ExtractedReservation:
        """Parse raw JSON extraction into ExtractedReservation."""
        # Parse intent
        intent_str = raw.get("intent", "CHITCHAT").upper()
        intent_map = {
            "MAKE_RESERVATION": ExtractionIntent.MAKE_RESERVATION,
            "MODIFY": ExtractionIntent.MODIFY_RESERVATION,
            "MODIFY_RESERVATION": ExtractionIntent.MODIFY_RESERVATION,
            "CANCEL": ExtractionIntent.CANCEL_RESERVATION,
            "CANCEL_RESERVATION": ExtractionIntent.CANCEL_RESERVATION,
            "INQUIRY": ExtractionIntent.INQUIRY,
            "CHITCHAT": ExtractionIntent.CHITCHAT,
            "OPERATOR": ExtractionIntent.OPERATOR_REQUEST,
            "OPERATOR_REQUEST": ExtractionIntent.OPERATOR_REQUEST,
        }
        intent = intent_map.get(intent_str, ExtractionIntent.CHITCHAT)

        # Parse party size
        party_size = None
        if raw.get("party_size") is not None:
            try:
                party_size = int(raw["party_size"])
            except (ValueError, TypeError):
                pass

        # Parse date
        reservation_date = self._parse_date(raw.get("date"))

        # Parse time
        reservation_time = self._parse_time(raw.get("time"))

        # Parse name and special requests
        customer_name = raw.get("name")
        if customer_name and isinstance(customer_name, str):
            customer_name = customer_name.strip()
            if not customer_name:
                customer_name = None

        special_requests = raw.get("special_requests")
        if special_requests and isinstance(special_requests, str):
            special_requests = special_requests.strip()
            if not special_requests:
                special_requests = None

        # Parse confidence
        confidence = 0.0
        if raw.get("confidence") is not None:
            try:
                confidence = float(raw["confidence"])
                confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1
            except (ValueError, TypeError):
                pass

        return ExtractedReservation(
            intent=intent,
            party_size=party_size,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            customer_name=customer_name,
            special_requests=special_requests,
            confidence=confidence,
        )

    def _parse_date(self, date_str: str | None) -> date | None:
        """Parse date string into date object.

        Handles:
        - "YYYY-MM-DD" format
        - "today", "tomorrow", "day after tomorrow"
        - None/null
        """
        if not date_str:
            return None

        date_str = date_str.lower().strip()
        today = self._today or date.today()

        if date_str == "today" or date_str == "aaj":
            return today
        elif date_str == "tomorrow" or date_str == "kal":
            return today + timedelta(days=1)
        elif date_str in ("day after tomorrow", "parson"):
            return today + timedelta(days=2)
        else:
            # Try parsing as YYYY-MM-DD
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

            # Try parsing as DD-MM-YYYY
            try:
                return datetime.strptime(date_str, "%d-%m-%Y").date()
            except ValueError:
                pass

        return None

    def _parse_time(self, time_str: str | None) -> str | None:
        """Parse time string into HH:MM format.

        Handles:
        - "HH:MM" format
        - "7 baje", "19:00"
        - None/null
        """
        if not time_str:
            return None

        time_str = time_str.strip()

        # Already in HH:MM format
        if re.match(r"^\d{1,2}:\d{2}$", time_str):
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            return f"{hour:02d}:{minute:02d}"

        # Extract hour from strings like "7", "19"
        match = re.match(r"^(\d{1,2})$", time_str)
        if match:
            hour = int(match.group(1))
            # Assume PM for hours 1-6
            if hour <= 6:
                hour += 12
            return f"{hour:02d}:00"

        return None

    async def validate(
        self,
        extracted: ExtractedReservation,
        business_rules: dict,
    ) -> list[str]:
        """Validate extracted data against business rules.

        Args:
            extracted: The extraction to validate
            business_rules: Dict with max_party_size, min_advance_minutes, etc.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate party size
        if extracted.party_size is not None:
            max_size = business_rules.get("max_phone_party_size", 10)
            if extracted.party_size > max_size:
                errors.append(
                    f"Party size {extracted.party_size} exceeds maximum of {max_size} "
                    "for phone reservations. Please contact us on WhatsApp for larger groups."
                )
            if extracted.party_size < 1:
                errors.append("Party size must be at least 1.")

        # Validate date
        if extracted.reservation_date is not None:
            today = self._today or date.today()
            max_advance_days = business_rules.get("max_advance_days", 30)

            if extracted.reservation_date < today:
                errors.append("Cannot make reservations for past dates.")
            elif (extracted.reservation_date - today).days > max_advance_days:
                errors.append(
                    f"Reservations can only be made up to {max_advance_days} days in advance."
                )

        return errors

    async def close(self) -> None:
        """Close the LLM service."""
        if self._llm:
            await self._llm.close()
