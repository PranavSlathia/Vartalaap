"""Tests for reservation extraction from LLM responses."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.llm.extractor import (
    ExtractedReservation,
    ExtractionIntent,
    ReservationExtractor,
)


class TestExtractedReservation:
    """Tests for ExtractedReservation dataclass."""

    def test_missing_fields_for_reservation_intent(self) -> None:
        """Test that missing fields are calculated for MAKE_RESERVATION."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )

        assert "date" in extraction.missing_fields
        assert "time" in extraction.missing_fields
        assert "name" in extraction.missing_fields
        assert "party_size" not in extraction.missing_fields

    def test_is_complete_when_all_fields_present(self) -> None:
        """Test is_complete returns True when all required fields present."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date.today() + timedelta(days=1),
            reservation_time="19:00",
            customer_name="Sharma",
            confidence=0.9,
        )

        assert extraction.is_complete is True
        assert len(extraction.missing_fields) == 0

    def test_is_complete_false_when_missing_fields(self) -> None:
        """Test is_complete returns False when fields missing."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )

        assert extraction.is_complete is False
        assert len(extraction.missing_fields) > 0

    def test_inquiry_intent_has_no_missing_fields(self) -> None:
        """Test that INQUIRY intent doesn't require reservation fields."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.INQUIRY,
        )

        assert len(extraction.missing_fields) == 0
        assert extraction.is_complete is True

    def test_merge_preserves_existing_values(self) -> None:
        """Test merge keeps existing values when new ones are None."""
        existing = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date.today(),
        )

        new = ExtractedReservation(
            intent=ExtractionIntent.CHITCHAT,  # Should not override
            reservation_time="19:00",
            customer_name="Sharma",
        )

        merged = existing.merge_with(new)

        assert merged.intent == ExtractionIntent.MAKE_RESERVATION  # Preserved
        assert merged.party_size == 4  # Preserved
        assert merged.reservation_date == date.today()  # Preserved
        assert merged.reservation_time == "19:00"  # New
        assert merged.customer_name == "Sharma"  # New

    def test_merge_takes_new_non_chitchat_intent(self) -> None:
        """Test merge takes new intent if it's not CHITCHAT."""
        existing = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
        )

        new = ExtractedReservation(
            intent=ExtractionIntent.CANCEL_RESERVATION,
        )

        merged = existing.merge_with(new)
        assert merged.intent == ExtractionIntent.CANCEL_RESERVATION

    def test_merge_keeps_higher_confidence(self) -> None:
        """Test merge keeps the higher confidence value."""
        existing = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            confidence=0.5,
        )

        new = ExtractedReservation(
            intent=ExtractionIntent.CHITCHAT,
            confidence=0.8,
        )

        merged = existing.merge_with(new)
        assert merged.confidence == 0.8


class TestReservationExtractorParsing:
    """Tests for extraction parsing logic (no LLM calls)."""

    @pytest.fixture
    def extractor(self) -> ReservationExtractor:
        """Create extractor with mocked LLM."""
        mock_llm = MagicMock()
        return ReservationExtractor(llm_service=mock_llm)

    def test_parse_date_today(self, extractor: ReservationExtractor) -> None:
        """Test parsing 'today'."""
        extractor._today = date(2026, 2, 1)

        result = extractor._parse_date("today")
        assert result == date(2026, 2, 1)

    def test_parse_date_tomorrow(self, extractor: ReservationExtractor) -> None:
        """Test parsing 'tomorrow' / 'kal'."""
        extractor._today = date(2026, 2, 1)

        assert extractor._parse_date("tomorrow") == date(2026, 2, 2)
        assert extractor._parse_date("kal") == date(2026, 2, 2)

    def test_parse_date_day_after_tomorrow(self, extractor: ReservationExtractor) -> None:
        """Test parsing 'parson' (day after tomorrow)."""
        extractor._today = date(2026, 2, 1)

        assert extractor._parse_date("parson") == date(2026, 2, 3)
        assert extractor._parse_date("day after tomorrow") == date(2026, 2, 3)

    def test_parse_date_iso_format(self, extractor: ReservationExtractor) -> None:
        """Test parsing YYYY-MM-DD format."""
        result = extractor._parse_date("2026-02-15")
        assert result == date(2026, 2, 15)

    def test_parse_date_dd_mm_yyyy_format(self, extractor: ReservationExtractor) -> None:
        """Test parsing DD-MM-YYYY format."""
        result = extractor._parse_date("15-02-2026")
        assert result == date(2026, 2, 15)

    def test_parse_date_invalid_returns_none(self, extractor: ReservationExtractor) -> None:
        """Test invalid date strings return None."""
        assert extractor._parse_date("invalid") is None
        assert extractor._parse_date("") is None
        assert extractor._parse_date(None) is None

    def test_parse_time_hh_mm_format(self, extractor: ReservationExtractor) -> None:
        """Test parsing HH:MM format."""
        assert extractor._parse_time("19:00") == "19:00"
        assert extractor._parse_time("7:30") == "07:30"
        assert extractor._parse_time("20:30") == "20:30"

    def test_parse_time_single_number_assumes_pm(self, extractor: ReservationExtractor) -> None:
        """Test single hour assumes PM for 1-6."""
        # Hours 1-6 should be converted to PM (add 12)
        assert extractor._parse_time("3") == "15:00"
        assert extractor._parse_time("6") == "18:00"

        # Hours 7+ stay as-is (already PM hours for dining)
        assert extractor._parse_time("7") == "07:00"  # 7 stays as 07
        assert extractor._parse_time("8") == "08:00"

    def test_parse_time_invalid_returns_none(self, extractor: ReservationExtractor) -> None:
        """Test invalid time strings return None."""
        assert extractor._parse_time("invalid") is None
        assert extractor._parse_time("") is None
        assert extractor._parse_time(None) is None
        assert extractor._parse_time("shaam") is None  # Too vague

    def test_parse_extraction_full_response(self, extractor: ReservationExtractor) -> None:
        """Test parsing a complete extraction response."""
        extractor._today = date(2026, 2, 1)

        raw = {
            "intent": "MAKE_RESERVATION",
            "party_size": 4,
            "date": "tomorrow",
            "time": "19:00",
            "name": "Sharma",
            "special_requests": "Window seat please",
            "confidence": 0.9,
        }

        result = extractor._parse_extraction(raw)

        assert result.intent == ExtractionIntent.MAKE_RESERVATION
        assert result.party_size == 4
        assert result.reservation_date == date(2026, 2, 2)
        assert result.reservation_time == "19:00"
        assert result.customer_name == "Sharma"
        assert result.special_requests == "Window seat please"
        assert result.confidence == 0.9
        assert result.is_complete is True

    def test_parse_extraction_partial_response(self, extractor: ReservationExtractor) -> None:
        """Test parsing a partial extraction response."""
        raw = {
            "intent": "MAKE_RESERVATION",
            "party_size": 4,
            "date": None,
            "time": None,
            "name": None,
            "confidence": 0.6,
        }

        result = extractor._parse_extraction(raw)

        assert result.intent == ExtractionIntent.MAKE_RESERVATION
        assert result.party_size == 4
        assert result.reservation_date is None
        assert result.reservation_time is None
        assert result.is_complete is False
        assert "date" in result.missing_fields
        assert "time" in result.missing_fields
        assert "name" in result.missing_fields

    def test_parse_extraction_intent_variations(self, extractor: ReservationExtractor) -> None:
        """Test parsing different intent strings."""
        test_cases = [
            ("MAKE_RESERVATION", ExtractionIntent.MAKE_RESERVATION),
            ("MODIFY", ExtractionIntent.MODIFY_RESERVATION),
            ("MODIFY_RESERVATION", ExtractionIntent.MODIFY_RESERVATION),
            ("CANCEL", ExtractionIntent.CANCEL_RESERVATION),
            ("INQUIRY", ExtractionIntent.INQUIRY),
            ("CHITCHAT", ExtractionIntent.CHITCHAT),
            ("OPERATOR", ExtractionIntent.OPERATOR_REQUEST),
            ("unknown", ExtractionIntent.CHITCHAT),  # Default
        ]

        for intent_str, expected in test_cases:
            raw = {"intent": intent_str, "confidence": 0.5}
            result = extractor._parse_extraction(raw)
            assert result.intent == expected, f"Failed for {intent_str}"

    def test_parse_extraction_clamps_confidence(self, extractor: ReservationExtractor) -> None:
        """Test that confidence is clamped to 0-1 range."""
        raw = {"intent": "CHITCHAT", "confidence": 1.5}
        result = extractor._parse_extraction(raw)
        assert result.confidence == 1.0

        raw = {"intent": "CHITCHAT", "confidence": -0.5}
        result = extractor._parse_extraction(raw)
        assert result.confidence == 0.0

    def test_parse_extraction_strips_whitespace_from_name(
        self, extractor: ReservationExtractor
    ) -> None:
        """Test that name is stripped of whitespace."""
        raw = {"intent": "MAKE_RESERVATION", "name": "  Sharma ji  ", "confidence": 0.5}
        result = extractor._parse_extraction(raw)
        assert result.customer_name == "Sharma ji"

    def test_parse_extraction_empty_name_becomes_none(
        self, extractor: ReservationExtractor
    ) -> None:
        """Test that empty/whitespace name becomes None."""
        raw = {"intent": "MAKE_RESERVATION", "name": "   ", "confidence": 0.5}
        result = extractor._parse_extraction(raw)
        assert result.customer_name is None


class TestReservationExtractorValidation:
    """Tests for validation logic."""

    @pytest.fixture
    def extractor(self) -> ReservationExtractor:
        """Create extractor with mocked LLM."""
        mock_llm = MagicMock()
        extractor = ReservationExtractor(llm_service=mock_llm)
        extractor._today = date(2026, 2, 1)
        return extractor

    @pytest.fixture
    def business_rules(self) -> dict:
        """Standard business rules for testing."""
        return {
            "max_phone_party_size": 10,
            "min_advance_minutes": 30,
            "max_advance_days": 30,
        }

    @pytest.mark.asyncio
    async def test_validate_party_size_exceeds_max(
        self, extractor: ReservationExtractor, business_rules: dict
    ) -> None:
        """Test validation fails when party size exceeds max."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=15,
        )

        errors = await extractor.validate(extraction, business_rules)

        assert len(errors) == 1
        assert "15" in errors[0]
        assert "10" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_party_size_zero(
        self, extractor: ReservationExtractor, business_rules: dict
    ) -> None:
        """Test validation fails for party size < 1."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=0,
        )

        errors = await extractor.validate(extraction, business_rules)

        assert len(errors) == 1
        assert "at least 1" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_past_date(
        self, extractor: ReservationExtractor, business_rules: dict
    ) -> None:
        """Test validation fails for past dates."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            reservation_date=date(2026, 1, 15),  # Past date
        )

        errors = await extractor.validate(extraction, business_rules)

        assert len(errors) == 1
        assert "past" in errors[0].lower()

    @pytest.mark.asyncio
    async def test_validate_date_too_far_in_future(
        self, extractor: ReservationExtractor, business_rules: dict
    ) -> None:
        """Test validation fails for dates too far in advance."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            reservation_date=date(2026, 4, 1),  # >30 days
        )

        errors = await extractor.validate(extraction, business_rules)

        assert len(errors) == 1
        assert "30 days" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_valid_extraction(
        self, extractor: ReservationExtractor, business_rules: dict
    ) -> None:
        """Test validation passes for valid extraction."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2026, 2, 5),  # Valid future date
            reservation_time="19:00",
            customer_name="Sharma",
            confidence=0.9,
        )

        errors = await extractor.validate(extraction, business_rules)

        assert len(errors) == 0


class TestReservationExtractorLLMCalls:
    """Tests for extract() method with mocked LLM."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create mock LLM service."""
        mock = MagicMock()
        mock.extract_json = AsyncMock()
        return mock

    @pytest.fixture
    def extractor(self, mock_llm: MagicMock) -> ReservationExtractor:
        """Create extractor with mocked LLM."""
        extractor = ReservationExtractor(llm_service=mock_llm)
        extractor._today = date(2026, 2, 1)
        return extractor

    @pytest.mark.asyncio
    async def test_extract_calls_llm_with_correct_format(
        self, extractor: ReservationExtractor, mock_llm: MagicMock
    ) -> None:
        """Test extract() calls LLM with properly formatted messages."""
        mock_llm.extract_json.return_value = {
            "intent": "MAKE_RESERVATION",
            "party_size": 4,
            "confidence": 0.8,
        }

        await extractor.extract(
            user_message="Table book karna hai 4 logon ke liye",
            assistant_response="Zaroor! Kis din ke liye?",
        )

        # Verify LLM was called
        mock_llm.extract_json.assert_called_once()
        call_args = mock_llm.extract_json.call_args[0][0]

        # Should have system and user messages
        assert len(call_args) == 2
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"
        assert "4 logon" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_extract_returns_parsed_result(
        self, extractor: ReservationExtractor, mock_llm: MagicMock
    ) -> None:
        """Test extract() returns properly parsed ExtractedReservation."""
        mock_llm.extract_json.return_value = {
            "intent": "MAKE_RESERVATION",
            "party_size": 4,
            "date": "tomorrow",
            "time": "19:00",
            "name": "Sharma",
            "confidence": 0.9,
        }

        result = await extractor.extract(
            user_message="Kal 7 baje 4 log, Sharma naam hai",
            assistant_response="Perfect! Confirm kar dein?",
        )

        assert result is not None
        assert result.intent == ExtractionIntent.MAKE_RESERVATION
        assert result.party_size == 4
        assert result.reservation_date == date(2026, 2, 2)
        assert result.reservation_time == "19:00"
        assert result.customer_name == "Sharma"

    @pytest.mark.asyncio
    async def test_extract_returns_none_on_error(
        self, extractor: ReservationExtractor, mock_llm: MagicMock
    ) -> None:
        """Test extract() returns None when LLM call fails."""
        mock_llm.extract_json.side_effect = Exception("API error")

        result = await extractor.extract(
            user_message="Table book karna hai",
            assistant_response="Zaroor!",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_includes_history_summary(
        self, extractor: ReservationExtractor, mock_llm: MagicMock
    ) -> None:
        """Test extract() includes conversation history in prompt."""
        from src.services.llm.protocol import Message, Role

        mock_llm.extract_json.return_value = {
            "intent": "MAKE_RESERVATION",
            "confidence": 0.5,
        }

        history = [
            Message(role=Role.USER, content="Table chahiye"),
            Message(role=Role.ASSISTANT, content="Kitne logon ke liye?"),
        ]

        await extractor.extract(
            user_message="4 log",
            assistant_response="Theek hai, 4 log. Kab?",
            conversation_history=history,
        )

        call_args = mock_llm.extract_json.call_args[0][0]
        user_content = call_args[1]["content"]

        # Should include previous context
        assert "Table chahiye" in user_content or "Previous context" in user_content


class TestPromptBuilders:
    """Tests for prompt builder classes."""

    def test_extraction_prompt_builder_basic(self) -> None:
        """Test ExtractionPromptBuilder creates valid messages."""
        from src.prompts.extraction import ExtractionPromptBuilder

        builder = ExtractionPromptBuilder()
        messages = builder.build_extraction_prompt(
            user_message="Table book karna hai",
            assistant_response="Kitne logon ke liye?",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Table book karna hai" in messages[1]["content"]

    def test_extraction_prompt_builder_with_history(self) -> None:
        """Test ExtractionPromptBuilder includes history summary."""
        from src.prompts.extraction import ExtractionPromptBuilder

        builder = ExtractionPromptBuilder()
        messages = builder.build_extraction_prompt(
            user_message="4 log",
            assistant_response="Theek hai",
            history_summary="User asked about table booking",
        )

        assert "User asked about table booking" in messages[1]["content"]

    def test_restaurant_prompt_builder_includes_examples(self) -> None:
        """Test RestaurantPromptBuilder includes few-shot examples."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from src.prompts.restaurant import RestaurantPromptBuilder
        from src.services.llm.protocol import ConversationContext

        builder = RestaurantPromptBuilder()
        context = ConversationContext(
            business_name="Test Restaurant",
            business_type="restaurant",
            timezone="Asia/Kolkata",
            current_datetime=datetime.now(ZoneInfo("Asia/Kolkata")),
            operating_hours={"monday": "closed", "tuesday": "11:00-22:00"},
            reservation_rules={"max_phone_party_size": 10},
        )

        prompt = builder.build_system_prompt(context)

        assert "Example" in prompt
        assert "Test Restaurant" in prompt
        assert "10" in prompt  # max party size

    def test_restaurant_prompt_builder_returns_examples_list(self) -> None:
        """Test get_few_shot_examples returns list of examples."""
        from src.prompts.restaurant import RestaurantPromptBuilder

        builder = RestaurantPromptBuilder()
        examples = builder.get_few_shot_examples()

        assert len(examples) > 0
        assert "user" in examples[0]
        assert "assistant" in examples[0]
