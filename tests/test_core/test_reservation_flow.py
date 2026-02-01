"""Tests for reservation flow orchestrator."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.conversation_state import ConversationPhase, ConversationState
from src.core.reservation_flow import BookingResult, ReservationFlow
from src.db.models import ReservationStatus
from src.db.repositories.reservations import AvailabilityResult
from src.services.llm.extractor import ExtractedReservation, ExtractionIntent


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Create a mock async reservation repository."""
    repo = AsyncMock()
    repo.session = MagicMock()
    repo.session.add = MagicMock()
    return repo


@pytest.fixture
def flow(mock_repo: AsyncMock) -> ReservationFlow:
    """Create a ReservationFlow instance with mocked repo."""
    return ReservationFlow(
        repo=mock_repo,
        business_id="test_business",
        business_name="Test Restaurant",
        timezone="Asia/Kolkata",
    )


class TestReservationFlow:
    """Tests for ReservationFlow class."""

    @pytest.mark.asyncio
    async def test_process_extraction_operator_request(
        self, flow: ReservationFlow
    ) -> None:
        """Operator request transitions to TRANSFERRED."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.OPERATOR_REQUEST,
        )

        response, new_state = await flow.process_extraction(extraction, state)

        assert response is None  # Let LLM handle
        assert new_state.phase == ConversationPhase.TRANSFERRED

    @pytest.mark.asyncio
    async def test_process_extraction_chitchat(self, flow: ReservationFlow) -> None:
        """Non-reservation intents pass through."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.CHITCHAT,
        )

        response, new_state = await flow.process_extraction(extraction, state)

        assert response is None
        assert new_state.phase == ConversationPhase.GREETING

    @pytest.mark.asyncio
    async def test_process_extraction_partial_info(
        self, flow: ReservationFlow
    ) -> None:
        """Partial reservation info triggers follow-up question."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )

        response, new_state = await flow.process_extraction(extraction, state)

        assert new_state.phase == ConversationPhase.GATHERING_INFO
        assert new_state.pending_reservation is not None
        assert new_state.pending_reservation.party_size == 4
        # Should ask for next field (date)
        assert response is not None
        assert "din" in response.lower() or "date" in response.lower()

    @pytest.mark.asyncio
    async def test_process_extraction_complete_info(
        self, flow: ReservationFlow
    ) -> None:
        """Complete reservation info triggers confirmation."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        response, new_state = await flow.process_extraction(extraction, state)

        assert new_state.phase == ConversationPhase.AWAITING_CONFIRMATION
        assert response is not None
        assert "confirm" in response.lower() or "sahi" in response.lower()

    @pytest.mark.asyncio
    async def test_process_extraction_accumulates_info(
        self, flow: ReservationFlow
    ) -> None:
        """Subsequent extractions accumulate data."""
        state = ConversationState()

        # First extraction - party size
        first = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )
        _, state = await flow.process_extraction(first, state)

        # Second extraction - date
        second = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            reservation_date=date(2025, 2, 15),
        )
        _, state = await flow.process_extraction(second, state)

        # Should have both
        assert state.pending_reservation is not None
        assert state.pending_reservation.party_size == 4
        assert state.pending_reservation.reservation_date == date(2025, 2, 15)


class TestHandleConfirmation:
    """Tests for confirmation handling."""

    @pytest.mark.asyncio
    async def test_handle_confirmation_rejected(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """User rejecting confirmation goes back to gathering."""
        state = ConversationState()
        state.phase = ConversationPhase.AWAITING_CONFIRMATION
        state.pending_reservation = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        response, new_state = await flow.handle_confirmation(
            confirmed=False, state=state
        )

        assert new_state.phase == ConversationPhase.GATHERING_INFO
        assert "change" in response.lower()
        mock_repo.check_availability.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_confirmation_success(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Successful confirmation creates reservation."""
        state = ConversationState()
        state.phase = ConversationPhase.AWAITING_CONFIRMATION
        state.pending_reservation = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=True,
            used_seats=10,
            total_seats=40,
        )

        response, new_state = await flow.handle_confirmation(
            confirmed=True,
            state=state,
            caller_phone_encrypted="encrypted_phone",
            call_log_id="call_123",
        )

        assert new_state.phase == ConversationPhase.COMPLETED
        assert "confirm" in response.lower() or "booking" in response.lower()
        mock_repo.session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_confirmation_unavailable(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Unavailable slot offers alternatives."""
        state = ConversationState()
        state.phase = ConversationPhase.AWAITING_CONFIRMATION
        state.pending_reservation = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=False,
            reason="capacity_full",
            used_seats=38,
            total_seats=40,
        )

        response, new_state = await flow.handle_confirmation(
            confirmed=True, state=state
        )

        # Should not complete
        assert new_state.phase != ConversationPhase.COMPLETED
        assert "available nahi" in response.lower() or "maaf" in response.lower()


class TestCheckAndBook:
    """Tests for check_and_book method."""

    @pytest.mark.asyncio
    async def test_check_and_book_incomplete(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Incomplete reservation fails."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            # Missing date, time, name
        )

        result = await flow.check_and_book(extraction)

        assert result.success is False
        assert "incomplete" in result.message.lower()
        mock_repo.check_availability.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_and_book_party_too_large(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Party too large returns appropriate message."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=15,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=False,
            reason="party_size_too_large",
        )

        result = await flow.check_and_book(extraction)

        assert result.success is False
        assert "whatsapp" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_and_book_too_soon(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Booking too close to now returns appropriate message."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=False,
            reason="too_soon",
        )

        result = await flow.check_and_book(extraction)

        assert result.success is False
        assert "minute" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_and_book_closed_day(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Booking on closed day returns appropriate message."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 17),  # Monday
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=False,
            reason="closed",
        )

        result = await flow.check_and_book(extraction)

        assert result.success is False
        assert "band" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_and_book_success(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Successful booking creates reservation and returns message."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=True,
            used_seats=10,
            total_seats=40,
        )

        result = await flow.check_and_book(
            extraction,
            caller_phone_encrypted="encrypted_phone",
            call_log_id="call_123",
        )

        assert result.success is True
        assert result.reservation_id is not None
        assert "sharma" in result.message.lower()
        assert "4 logon" in result.message

        # Verify reservation was added to session
        mock_repo.session.add.assert_called_once()
        added_reservation = mock_repo.session.add.call_args[0][0]
        assert added_reservation.party_size == 4
        assert added_reservation.customer_name == "Sharma"
        assert added_reservation.status == ReservationStatus.confirmed


class TestGenerateAlternatives:
    """Tests for alternative time generation."""

    @pytest.mark.asyncio
    async def test_generate_alternatives_finds_slots(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Generates alternative times when some are available."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
        )

        # First few calls unavailable, then available
        mock_repo.check_availability.side_effect = [
            AvailabilityResult(available=False, reason="capacity_full"),
            AvailabilityResult(available=True, used_seats=10, total_seats=40),
            AvailabilityResult(available=True, used_seats=15, total_seats=40),
        ]

        alternatives = await flow.generate_alternatives(extraction)

        assert len(alternatives) == 2
        assert all("time" in alt for alt in alternatives)
        assert all("date" in alt for alt in alternatives)

    @pytest.mark.asyncio
    async def test_generate_alternatives_none_available(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Returns empty list when no alternatives available."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
        )

        mock_repo.check_availability.return_value = AvailabilityResult(
            available=False,
            reason="capacity_full",
        )

        alternatives = await flow.generate_alternatives(extraction)

        assert alternatives == []

    @pytest.mark.asyncio
    async def test_generate_alternatives_missing_data(
        self, flow: ReservationFlow, mock_repo: AsyncMock
    ) -> None:
        """Returns empty list when extraction missing date/time."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )

        alternatives = await flow.generate_alternatives(extraction)

        assert alternatives == []
        mock_repo.check_availability.assert_not_called()


class TestFormatHelpers:
    """Tests for date/time formatting."""

    def test_format_time_evening(self, flow: ReservationFlow) -> None:
        """Formats evening time correctly."""
        assert "shaam" in flow._format_time("19:00")
        assert "7" in flow._format_time("19:00")

    def test_format_time_afternoon(self, flow: ReservationFlow) -> None:
        """Formats afternoon time correctly."""
        result = flow._format_time("14:00")
        assert "dopahar" in result
        assert "2" in result

    def test_format_time_morning(self, flow: ReservationFlow) -> None:
        """Formats morning time correctly."""
        result = flow._format_time("10:00")
        assert "subah" in result
        assert "10" in result

    def test_format_time_half_hour(self, flow: ReservationFlow) -> None:
        """Formats half-hour times correctly."""
        result = flow._format_time("19:30")
        assert "aadha" in result

    def test_format_time_invalid(self, flow: ReservationFlow) -> None:
        """Returns original for invalid time."""
        assert flow._format_time("invalid") == "invalid"


class TestBookingResult:
    """Tests for BookingResult dataclass."""

    def test_booking_result_success(self) -> None:
        """BookingResult with success."""
        result = BookingResult(
            success=True,
            reservation_id="res_123",
            message="Booking confirmed",
        )
        assert result.success is True
        assert result.reservation_id == "res_123"
        assert result.alternatives is None

    def test_booking_result_failure_with_alternatives(self) -> None:
        """BookingResult with failure and alternatives."""
        result = BookingResult(
            success=False,
            message="Slot unavailable",
            alternatives=[{"time": "18:00"}, {"time": "20:00"}],
        )
        assert result.success is False
        assert result.reservation_id is None
        assert len(result.alternatives) == 2
