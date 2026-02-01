"""Prompts for JSON extraction from conversations.

These prompts are used in the second-pass extraction to convert
conversational responses into structured reservation data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.llm.protocol import Message

# System prompt for extraction
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

## Extraction Rules

### Intent Classification
- MAKE_RESERVATION: User wants to book a table ("table book karna hai", "reservation chahiye")
- MODIFY: User wants to change existing reservation ("time change karna hai")
- CANCEL: User wants to cancel ("cancel karna hai", "booking hatana hai")
- INQUIRY: Questions about hours, menu, location ("kab tak khule ho?", "menu mein kya hai?")
- CHITCHAT: General conversation, greetings ("namaste", "thank you")
- OPERATOR: Wants to speak to human ("kisi se baat karni hai", "manager se connect karo")

### Hindi Number Extraction
- "ek" / "1" = 1
- "do" / "2" = 2
- "teen" / "3" = 3
- "char" / "4" = 4
- "paanch" / "5" = 5
- "cheh" / "6" = 6
- "saat" / "7" = 7
- "aath" / "8" = 8
- "nau" / "9" = 9
- "das" / "10" = 10

### Date Extraction
- "aaj" = "today"
- "kal" = "tomorrow"
- "parson" = day after tomorrow (calculate actual date)
- "is Saturday" / "aane wale Saturday" = next Saturday (calculate)
- Specific dates like "15 January" = "YYYY-01-15"

### Time Extraction
- "7 baje" = "19:00" (assume evening for dining)
- "saat baje shaam" = "19:00"
- "8 baje" = "20:00"
- "dopahar ko" = null (need specific time)
- "shaam ko" = null (need specific time)
- "lunch time" = null (need specific time)
- "dinner time" = null (need specific time)
- If just hour mentioned (1-6), assume PM: "3 baje" = "15:00"
- If just hour mentioned (7-11), could be AM or PM, prefer PM for restaurant: "7 baje" = "19:00"

### Confidence Scoring
- 0.9-1.0: All mentioned fields are explicitly and clearly stated
- 0.7-0.8: Information is stated but might need confirmation
- 0.5-0.6: Some inference required from context
- 0.3-0.4: Vague or ambiguous information
- 0.0-0.2: Mostly guessing or very unclear

### Important Rules
1. Only extract EXPLICITLY stated information
2. Do not assume party size if not mentioned
3. Do not assume date/time if user just says "table book karna hai"
4. If user mentions "4 log" or "char log" = party_size: 4
5. Names should be extracted exactly as stated ("Sharma ji" → "Sharma")
6. Special requests include dietary needs, seating preferences, occasions"""


class ExtractionPromptBuilder:
    """Build prompts for extraction API calls."""

    def __init__(self) -> None:
        self._system_prompt = EXTRACTION_SYSTEM_PROMPT

    def build_extraction_prompt(
        self,
        user_message: str,
        assistant_response: str,
        history_summary: str | None = None,
    ) -> list[dict]:
        """Build messages for extraction API call.

        Args:
            user_message: What the user said
            assistant_response: What the bot replied
            history_summary: Optional summary of conversation history

        Returns:
            List of message dicts for LLM API
        """
        context_part = ""
        if history_summary:
            context_part = f"Previous context:\n{history_summary}\n\n"

        user_prompt = f"""{context_part}Analyze this conversation turn:

User: {user_message}
Assistant: {assistant_response}

Extract reservation details from the USER's message. Output JSON only."""

        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def build_batch_extraction_prompt(
        self,
        conversation: list[Message],
    ) -> list[dict]:
        """Build prompt to extract from entire conversation.

        Useful for extracting cumulative state from full history.

        Args:
            conversation: Full conversation history

        Returns:
            List of message dicts for LLM API
        """
        # Format conversation
        turns = []
        for msg in conversation:
            role = "User" if msg.role.value == "user" else "Bot"
            turns.append(f"{role}: {msg.content}")

        conversation_text = "\n".join(turns)

        user_prompt = f"""Analyze this full restaurant conversation and extract the FINAL reservation state:

{conversation_text}

Extract the cumulative reservation details (combine information from all turns). Output JSON only."""

        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]
