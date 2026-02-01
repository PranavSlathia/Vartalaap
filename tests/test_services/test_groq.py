"""Tests for Groq LLM service."""

import os
from datetime import datetime

import pytest

from src.services.llm.groq import GroqService
from src.services.llm.protocol import ConversationContext, Message, Role
from src.services.llm.token_counter import estimate_llama_tokens


@pytest.fixture
def sample_context():
    """Sample conversation context."""
    return ConversationContext(
        business_name="Test Restaurant",
        business_type="restaurant",
        timezone="Asia/Kolkata",
        current_datetime=datetime(2024, 1, 15, 14, 30),
        operating_hours={"monday": "closed", "tuesday": "11:00-22:00"},
        reservation_rules={"max_phone_party_size": 10},
    )


@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        Message(role=Role.USER, content="I want to book a table for 4"),
    ]


class TestTokenEstimation:
    """Test suite for token counting."""

    def test_estimate_tokens_english(self):
        """Test token estimation for English text."""
        text = "Hello, I would like to make a reservation."
        tokens = estimate_llama_tokens(text)

        # ~43 chars / 4 * 1.1 + 1 = ~13 tokens
        assert 10 <= tokens <= 20

    def test_estimate_tokens_hindi(self):
        """Test token estimation for Hindi text."""
        text = "नमस्ते, मुझे एक टेबल बुक करनी है"
        tokens = estimate_llama_tokens(text)

        # Hindi uses more tokens per character
        assert tokens > 0

    def test_estimate_tokens_empty(self):
        """Test token estimation for empty text."""
        assert estimate_llama_tokens("") == 0

    def test_estimate_tokens_mixed(self):
        """Test mixed Hindi-English text."""
        text = "Table for 4 लोगों के लिए"
        tokens = estimate_llama_tokens(text)
        assert tokens > 0

    def test_estimate_tokens_long_text(self):
        """Test longer text estimation."""
        text = "a" * 1000
        tokens = estimate_llama_tokens(text)
        # ~1000/4 * 1.1 + 1 = ~276
        assert 250 <= tokens <= 300


class TestGroqService:
    """Test suite for GroqService."""

    @pytest.fixture
    def groq_service(self, settings_factory):
        """Create GroqService with real Settings."""
        return GroqService(settings=settings_factory())

    def test_estimate_tokens(self, groq_service):
        """Test service token estimation wrapper."""
        text = "Hello world"
        tokens = groq_service.estimate_tokens(text)
        assert tokens > 0

    def test_build_system_prompt(self, groq_service, sample_context):
        """Test system prompt generation."""
        prompt = groq_service._build_system_prompt(sample_context)

        assert "Test Restaurant" in prompt
        assert "Asia/Kolkata" in prompt
        assert "monday" in prompt.lower()
        assert "11:00-22:00" in prompt

    def test_build_system_prompt_with_capacity(self, groq_service, sample_context):
        """Test system prompt with current capacity."""
        sample_context.current_capacity = 25
        prompt = groq_service._build_system_prompt(sample_context)

        assert "25" in prompt
        assert "available seats" in prompt.lower()

    def test_build_system_prompt_with_menu(self, groq_service, sample_context):
        """Test system prompt with menu summary."""
        sample_context.menu_summary = "Momos, Thukpa, Chow Mein"
        prompt = groq_service._build_system_prompt(sample_context)

        assert "Momos" in prompt
        assert "Menu Highlights" in prompt

    def test_format_messages(self, groq_service, sample_messages):
        """Test message formatting for API."""
        system_prompt = "You are a helpful assistant."
        api_messages = groq_service._format_messages(system_prompt, sample_messages)

        assert len(api_messages) == 2
        assert api_messages[0]["role"] == "system"
        assert api_messages[0]["content"] == system_prompt
        assert api_messages[1]["role"] == "user"
        assert "table for 4" in api_messages[1]["content"]

    def test_format_messages_multi_turn(self, groq_service):
        """Test multi-turn conversation formatting."""
        messages = [
            Message(role=Role.USER, content="Hi"),
            Message(role=Role.ASSISTANT, content="Hello!"),
            Message(role=Role.USER, content="Book a table"),
        ]
        api_messages = groq_service._format_messages("System prompt", messages)

        assert len(api_messages) == 4  # system + 3 messages
        assert api_messages[1]["role"] == "user"
        assert api_messages[2]["role"] == "assistant"
        assert api_messages[3]["role"] == "user"

    @pytest.mark.asyncio
    async def test_close(self, groq_service):
        """Test client cleanup."""
        _ = groq_service.client
        await groq_service.close()
        assert groq_service._client is None


def _has_groq_key() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


@pytest.mark.skipif(not _has_groq_key(), reason="GROQ_API_KEY not set")
class TestGroqIntegration:
    """Integration tests for Groq API (env-gated)."""

    @pytest.fixture
    def service(self, settings_factory):
        settings = settings_factory(groq_api_key=os.environ["GROQ_API_KEY"])
        return GroqService(settings=settings)

    @pytest.fixture
    def context(self, sample_context):
        return sample_context

    @pytest.mark.asyncio
    async def test_stream_chat(self, service, context, sample_messages):
        """Test streaming chat returns content and metadata."""
        generator, metadata = await service.stream_chat(
            sample_messages,
            context,
            max_tokens=16,
            temperature=0.2,
        )

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        assert "".join(chunks).strip() != ""
        assert metadata.model == "llama-3.3-70b-versatile"
        assert metadata.first_token_ms is not None

        await service.close()

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        """Test health check hits Groq API."""
        result = await service.health_check()
        assert result is True
