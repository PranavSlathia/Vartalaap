"""Restaurant-specific prompt templates with few-shot examples.

These prompts are used for the conversational response generation,
not for extraction. They include few-shot examples for common
reservation scenarios.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.services.llm.protocol import ConversationContext


# Few-shot examples for Hindi/Hinglish restaurant conversations
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    # Example 1: Complete reservation in one turn
    {
        "user": "Main kal shaam ko 4 logon ke liye table book karna chahti hoon, 7 baje",
        "assistant": "Zaroor! Kal shaam 7 baje, 4 logon ke liye. Booking ke liye aapka naam bata dijiye?",
        "notes": "User provides date, time, party size. Ask for name.",
    },
    # Example 2: Providing name after being asked
    {
        "user": "Sharma",
        "assistant": "Shukriya Sharma ji! Main confirm karti hoon - kal shaam 7 baje, 4 log, Sharma ji ke naam se. Kya yeh sahi hai?",
        "notes": "Confirm all details before booking.",
    },
    # Example 3: User confirms
    {
        "user": "Haan, sahi hai",
        "assistant": "Bahut accha! Aapki booking confirm ho gayi - kal shaam 7 baje, 4 log. Himalayan Kitchen mein milte hain!",
        "notes": "Booking confirmed, friendly closing.",
    },
    # Example 4: Partial information - just wants to book
    {
        "user": "Table book karna hai",
        "assistant": "Zaroor! Kitne logon ke liye table chahiye?",
        "notes": "Start gathering info - party size first.",
    },
    # Example 5: After party size, ask date
    {
        "user": "5 log hain",
        "assistant": "5 log ke liye. Kis din ke liye book karein - aaj, kal, ya koi aur din?",
        "notes": "Got party size, now ask date.",
    },
    # Example 6: After date, ask time
    {
        "user": "Kal ke liye",
        "assistant": "Kal ke liye, 5 log. Kaunsi time prefer karenge - 7 baje ya 8 baje?",
        "notes": "Got date, offer time options.",
    },
    # Example 7: Slot unavailable - offer alternatives
    {
        "user": "7 baje",
        "assistant": "Maaf kijiye, kal 7 baje fully booked hai. 6:30 ya 8 baje available hai - kaunsa better hai aapke liye?",
        "notes": "Requested time unavailable, offer alternatives.",
    },
    # Example 8: Inquiry about hours
    {
        "user": "Aap kab tak khule rehte ho?",
        "assistant": "Hum Tuesday se Sunday, 11 baje se raat 10:30 tak khule rehte hain. Monday ko closed hai.",
        "notes": "Answer hours inquiry concisely.",
    },
    # Example 9: Menu inquiry
    {
        "user": "Vegetarian options hain?",
        "assistant": "Haan, bilkul! Humare paas kaafi vegetarian options hain - paneer dishes, dal makhani, aur fresh salads. Kya aap reservation bhi karna chahenge?",
        "notes": "Answer inquiry, then redirect to reservation.",
    },
    # Example 10: Large party (exceeds phone limit)
    {
        "user": "15 logon ke liye table chahiye",
        "assistant": "15 logon ke liye phone par booking nahi ho sakti - max 10 tak. Bade groups ke liye WhatsApp par contact karein, hum special arrangements kar sakte hain.",
        "notes": "Redirect large parties to WhatsApp.",
    },
    # Example 11: Operator request
    {
        "user": "Kisi se baat karni hai",
        "assistant": "Zaroor, main aapko connect kar rahi hoon. Aap 0 press karein, ya hum aapko WhatsApp par call back kar sakte hain.",
        "notes": "Acknowledge operator request, offer options.",
    },
    # Example 12: Cancellation
    {
        "user": "Mujhe booking cancel karni hai",
        "assistant": "Theek hai. Kya aap apna naam aur booking date bata sakte hain?",
        "notes": "Ask for details to find the booking.",
    },
]


class RestaurantPromptBuilder:
    """Build system prompts for restaurant voice assistant."""

    def __init__(self, business_id: str = "himalayan_kitchen") -> None:
        self._business_id = business_id
        self._prompt_template: str | None = None

    def build_system_prompt(self, context: ConversationContext) -> str:
        """Build full system prompt with context injection.

        Args:
            context: Business context with hours, rules, etc.

        Returns:
            Complete system prompt string
        """
        # Load template from file if available
        template = self._load_prompt_template()

        # Format operating hours
        hours_lines = []
        for day, hours in context.operating_hours.items():
            hours_lines.append(f"  - {day.capitalize()}: {hours}")
        hours_text = "\n".join(hours_lines)

        # Format current datetime
        dt_text = context.current_datetime.strftime("%A, %B %d, %Y at %I:%M %p")

        # Build the prompt
        prompt = f"""You are a friendly voice assistant for {context.business_name}, a {context.business_type} in India.

## Current Information
- Current date/time: {dt_text} ({context.timezone})

## Operating Hours
{hours_text}

## Reservation Rules
- Maximum party size (phone): {context.reservation_rules.get('max_phone_party_size', 10)} people
- Minimum advance booking: {context.reservation_rules.get('min_advance_minutes', 30)} minutes
- Maximum advance booking: {context.reservation_rules.get('max_advance_days', 30)} days
- Total capacity: {context.reservation_rules.get('total_seats', 40)} seats
"""

        if context.current_capacity is not None:
            prompt += f"- Current available seats: {context.current_capacity}\n"

        if context.menu_summary:
            prompt += f"\n## Menu Highlights\n{context.menu_summary}\n"

        if context.caller_history:
            prompt += f"\n## Caller History\n{context.caller_history}\n"

        # Add template guidelines if available
        if template:
            prompt += f"\n## Guidelines\n{template}\n"
        else:
            prompt += self._default_guidelines()

        # Add few-shot examples
        prompt += self._format_few_shot_examples()

        return prompt

    def _load_prompt_template(self) -> str | None:
        """Load prompt template from config file."""
        if self._prompt_template is not None:
            return self._prompt_template

        # Try business-specific template first
        paths = [
            Path(f"config/prompts/{self._business_id}_bot.txt"),
            Path("config/prompts/restaurant_bot.txt"),
        ]

        for path in paths:
            if path.exists():
                self._prompt_template = path.read_text()
                return self._prompt_template

        self._prompt_template = ""
        return None

    def _default_guidelines(self) -> str:
        """Return default guidelines if no template file exists."""
        return """
## Guidelines
- Be concise - responses should be 1-2 sentences for voice
- Use natural, conversational language
- Adapt to Hindi, English, or Hinglish based on caller's language
- For Hindi speakers, use simple conversational Hindi with polite forms ("ji", "aap")
- Always confirm reservation details before finalizing (date, time, party size, name)
- Do not accept delivery orders - politely redirect to Zomato/Swiggy
- For large parties (>10), redirect to WhatsApp
- If unsure about availability, offer to check and call back via WhatsApp
"""

    def _format_few_shot_examples(self) -> str:
        """Format few-shot examples for the prompt."""
        lines = ["\n## Example Conversations\n"]

        # Include a subset of examples (first 6) to save tokens
        for i, example in enumerate(FEW_SHOT_EXAMPLES[:6], 1):
            lines.append(f"Example {i}:")
            lines.append(f"  User: {example['user']}")
            lines.append(f"  Assistant: {example['assistant']}")
            lines.append("")

        return "\n".join(lines)

    def get_few_shot_examples(self) -> list[dict[str, Any]]:
        """Return all few-shot examples.

        Useful for testing or validation.
        """
        return FEW_SHOT_EXAMPLES.copy()
