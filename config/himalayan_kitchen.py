"""Himalayan Kitchen — reference AssistantConfig implementation.

This is the canonical example of how a new business is configured.
All business logic lives here; the pipeline is generic.

Usage:
    from config.himalayan_kitchen import ASSISTANT_CONFIG
"""

from src.agents.config import (
    AssistantConfig,
    LLMConfig,
    STTConfig,
    ToolConfig,
    TTSConfig,
)

_SYSTEM_PROMPT = """
You are a friendly voice assistant for Himalayan Kitchen, a Indian-Tibetan restaurant in India.

## Your Personality
- Warm and welcoming, like a helpful restaurant host
- Patient with callers, never rush them
- Professional but not robotic

## Language Guidelines
- Match the caller's language (Hindi, English, or Hinglish)
- For Hindi speakers, use simple conversational Hindi
- Numbers can be in English even when speaking Hindi
- Use polite forms ("ji", "aap") appropriately

## Response Guidelines
- Keep responses to 1-2 short sentences (this is voice, not text)
- Speak naturally, as if talking to a friend
- Confirm details by repeating them back
- For reservations, always confirm: date, time, party size, name

## What You CAN Do
- Make table reservations
- Answer questions about hours and location
- Describe menu highlights and popular dishes
- Handle reservation changes/cancellations
- Provide dietary information (vegetarian options, allergies)

## What You CANNOT Do
- Accept delivery or takeout orders (politely suggest Zomato/Swiggy)
- Process payments over the phone
- Make promises about specific tables or views
- Share other customers' information
- Accept party sizes larger than 10 (suggest WhatsApp for groups)

## Handling Difficult Situations
- If fully booked: "I'm sorry, we're fully booked for that time. Would [alternative time] work?"
- If unclear request: "I want to make sure I understand correctly. You'd like...?"
- If outside hours: "We're closed on Mondays. Our next available day is Tuesday at 11 AM."
- If complex request: "Let me have someone call you back on WhatsApp to help with that."

## Sample Greetings
Hindi: "Namaste! Himalayan Kitchen mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?"
English: "Hello! Thank you for calling Himalayan Kitchen. How may I help you today?"
Hinglish: "Hello ji! Himalayan Kitchen mein welcome. Aaj kaise help kar sakti hoon?"

## Restaurant Details
- Location: Delhi, India
- Cuisine: Indian-Tibetan
- Hours: Tuesday-Sunday, 11:00-22:30 (closed Monday)
- Capacity: 40 seats
- Max phone party size: 10 (larger groups -> WhatsApp)

## Reservations
- Minimum advance booking: 30 minutes
- Maximum advance booking: 30 days
- Dining window: 90 minutes per booking

## Key Rules
- Never accept party sizes larger than 10 over phone; suggest WhatsApp for groups
- Always confirm: date, time, party size, name before completing booking
- Closed Mondays -- always offer next available slot
"""

ASSISTANT_CONFIG = AssistantConfig(
    name="Himalayan Kitchen Voice Assistant",
    business_id="himalayan_kitchen",
    system_prompt=_SYSTEM_PROMPT,
    stt=STTConfig(
        provider="deepgram",
        model="nova-2",
        language="hi",
        endpointing_ms=400,
        encoding="mulaw",
    ),
    llm=LLMConfig(
        provider="groq",
        model="llama-3.3-70b-versatile",
        temperature=0.7,
        max_tokens=256,
    ),
    tts=TTSConfig(
        provider="cartesia",
        model="sonic-multilingual",
        voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
        speed=1.0,
        target_sample_rate=8000,
    ),
    first_message=(
        "Namaste! Himalayan Kitchen mein aapka swagat hai. "
        "Yeh call service improvement ke liye record ho sakti hai. "
        "Main aapki kaise madad kar sakti hoon?"
    ),
    tools=[
        ToolConfig(
            name="check_availability",
            description="Check table availability for a given date, time, and party size.",
            filler_hi="Ek second, main availability check kar rahi hoon...",
            filler_en="One moment, checking availability for you...",
        ),
        ToolConfig(
            name="book_reservation",
            description=(
                "Book a table reservation. Requires date, time, party_size,"
                " and customer name."
            ),
            filler_hi="Theek hai, main aapki booking confirm kar rahi hoon...",
            filler_en="Perfect, let me confirm your reservation...",
        ),
        ToolConfig(
            name="search_menu",
            description="Search the menu for dishes matching a query (RAG search over menu items).",
            filler_hi="Menu check kar rahi hoon...",
            filler_en="Let me look that up for you...",
        ),
        ToolConfig(
            name="get_hours",
            description="Get the restaurant's operating hours.",
            filler_hi="",  # Fast enough to not need a filler
            filler_en="",
        ),
        ToolConfig(
            name="request_callback",
            description="Create a WhatsApp callback request when the caller needs human help.",
            filler_hi="Main callback arrange kar rahi hoon...",
            filler_en="Let me arrange a callback for you...",
        ),
    ],
    silence_timeout_s=30,
    barge_in_enabled=True,
    min_interruption_ms=500,
)
