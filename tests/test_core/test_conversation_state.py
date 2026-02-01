"""Tests for conversation state machine."""

from datetime import date

from src.core.conversation_state import (
    FIELD_QUESTIONS,
    ConversationPhase,
    ConversationState,
    determine_next_phase,
)
from src.services.llm.extractor import ExtractedReservation, ExtractionIntent


class TestConversationState:
    """Tests for ConversationState dataclass."""

    def test_initial_state(self) -> None:
        """New state starts in GREETING phase."""
        state = ConversationState()
        assert state.phase == ConversationPhase.GREETING
        assert state.pending_reservation is None
        assert state.last_response == ""
        assert state.confirmation_attempts == 0
        assert state.asked_fields == set()

    def test_needs_field_no_reservation(self) -> None:
        """needs_field returns True when no reservation exists."""
        state = ConversationState()
        assert state.needs_field("party_size") is True
        assert state.needs_field("date") is True

    def test_needs_field_with_partial_reservation(self) -> None:
        """needs_field returns True for missing fields."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )
        state.pending_reservation = extraction

        assert state.needs_field("party_size") is False
        assert state.needs_field("date") is True
        assert state.needs_field("time") is True
        assert state.needs_field("name") is True

    def test_get_next_question_priority_order(self) -> None:
        """Questions are asked in priority order: party_size, date, time, name."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
        )
        state.pending_reservation = extraction

        # First question should be party_size
        question = state.get_next_question()
        assert question == FIELD_QUESTIONS["party_size"]
        assert "party_size" in state.asked_fields

        # Second question should be date (party_size already asked)
        question = state.get_next_question()
        assert question == FIELD_QUESTIONS["date"]

        # Third should be time
        question = state.get_next_question()
        assert question == FIELD_QUESTIONS["time"]

        # Fourth should be name
        question = state.get_next_question()
        assert question == FIELD_QUESTIONS["name"]

        # No more questions
        question = state.get_next_question()
        assert question is None

    def test_get_next_question_skips_filled_fields(self) -> None:
        """Questions skip fields that are already filled."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,  # Already have this
            reservation_date=date(2025, 2, 15),  # And this
        )
        state.pending_reservation = extraction

        # Should skip party_size and date, ask time
        question = state.get_next_question()
        assert question == FIELD_QUESTIONS["time"]

    def test_get_next_question_no_reservation(self) -> None:
        """Returns None when no pending reservation."""
        state = ConversationState()
        assert state.get_next_question() is None

    def test_get_confirmation_message_complete(self) -> None:
        """Generates confirmation for complete reservation."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )
        state.pending_reservation = extraction

        message = state.get_confirmation_message()
        assert message is not None
        assert "4 logon" in message
        assert "Sharma" in message
        assert "7 baje shaam" in message

    def test_get_confirmation_message_incomplete(self) -> None:
        """Returns None for incomplete reservation."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            # Missing date, time, name
        )
        state.pending_reservation = extraction

        assert state.get_confirmation_message() is None

    def test_should_confirm(self) -> None:
        """should_confirm returns True when reservation is complete."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )
        state.pending_reservation = extraction

        assert state.should_confirm() is True

    def test_should_confirm_incomplete(self) -> None:
        """should_confirm returns False when reservation is incomplete."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )
        state.pending_reservation = extraction

        assert state.should_confirm() is False

    def test_should_confirm_max_attempts(self) -> None:
        """should_confirm returns False after max confirmation attempts."""
        state = ConversationState()
        state.confirmation_attempts = 3
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )
        state.pending_reservation = extraction

        assert state.should_confirm() is False

    def test_transition_to(self) -> None:
        """transition_to updates phase and resets counters appropriately."""
        state = ConversationState()
        state.confirmation_attempts = 2
        state.asked_fields = {"party_size", "date"}

        state.transition_to(ConversationPhase.GATHERING_INFO)

        assert state.phase == ConversationPhase.GATHERING_INFO
        assert state.confirmation_attempts == 0
        assert state.asked_fields == set()

    def test_update_reservation_new(self) -> None:
        """update_reservation sets new pending reservation."""
        state = ConversationState()
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )

        state.update_reservation(extraction)

        assert state.pending_reservation is not None
        assert state.pending_reservation.party_size == 4

    def test_update_reservation_merge(self) -> None:
        """update_reservation merges with existing reservation."""
        state = ConversationState()
        first = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )
        state.pending_reservation = first
        state.asked_fields = {"party_size"}

        second = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            reservation_date=date(2025, 2, 15),
        )
        state.update_reservation(second)

        # Should merge both
        assert state.pending_reservation is not None
        assert state.pending_reservation.party_size == 4
        assert state.pending_reservation.reservation_date == date(2025, 2, 15)
        # Should reset asked fields
        assert state.asked_fields == set()

    def test_clear(self) -> None:
        """clear resets all state."""
        state = ConversationState()
        state.phase = ConversationPhase.BOOKING
        state.pending_reservation = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION
        )
        state.last_response = "test"
        state.confirmation_attempts = 2
        state.asked_fields = {"party_size"}

        state.clear()

        assert state.phase == ConversationPhase.GREETING
        assert state.pending_reservation is None
        assert state.last_response == ""
        assert state.confirmation_attempts == 0
        assert state.asked_fields == set()


class TestDetermineNextPhase:
    """Tests for state transition logic."""

    def test_greeting_to_gathering(self) -> None:
        """GREETING + reservation intent -> GATHERING_INFO."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
        )
        next_phase = determine_next_phase(
            ConversationPhase.GREETING,
            extraction,
        )
        assert next_phase == ConversationPhase.GATHERING_INFO

    def test_greeting_stays_greeting(self) -> None:
        """GREETING + no intent -> stays GREETING."""
        next_phase = determine_next_phase(
            ConversationPhase.GREETING,
            None,
        )
        assert next_phase == ConversationPhase.GREETING

    def test_gathering_to_confirming(self) -> None:
        """GATHERING_INFO + complete info -> CONFIRMING."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
            reservation_date=date(2025, 2, 15),
            reservation_time="19:00",
            customer_name="Sharma",
        )
        next_phase = determine_next_phase(
            ConversationPhase.GATHERING_INFO,
            extraction,
        )
        assert next_phase == ConversationPhase.CONFIRMING

    def test_gathering_stays_gathering(self) -> None:
        """GATHERING_INFO + incomplete info -> stays GATHERING_INFO."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
            party_size=4,
        )
        next_phase = determine_next_phase(
            ConversationPhase.GATHERING_INFO,
            extraction,
        )
        assert next_phase == ConversationPhase.GATHERING_INFO

    def test_confirming_to_awaiting(self) -> None:
        """CONFIRMING -> AWAITING_CONFIRMATION."""
        next_phase = determine_next_phase(
            ConversationPhase.CONFIRMING,
            None,
        )
        assert next_phase == ConversationPhase.AWAITING_CONFIRMATION

    def test_awaiting_to_booking_on_confirm(self) -> None:
        """AWAITING_CONFIRMATION + confirmed -> BOOKING."""
        next_phase = determine_next_phase(
            ConversationPhase.AWAITING_CONFIRMATION,
            None,
            user_confirmed=True,
        )
        assert next_phase == ConversationPhase.BOOKING

    def test_awaiting_to_gathering_on_reject(self) -> None:
        """AWAITING_CONFIRMATION + not confirmed -> GATHERING_INFO."""
        next_phase = determine_next_phase(
            ConversationPhase.AWAITING_CONFIRMATION,
            None,
            user_confirmed=False,
        )
        assert next_phase == ConversationPhase.GATHERING_INFO

    def test_booking_to_completed(self) -> None:
        """BOOKING -> COMPLETED."""
        next_phase = determine_next_phase(
            ConversationPhase.BOOKING,
            None,
        )
        assert next_phase == ConversationPhase.COMPLETED

    def test_completed_stays_completed(self) -> None:
        """COMPLETED -> stays COMPLETED (no new intent)."""
        next_phase = determine_next_phase(
            ConversationPhase.COMPLETED,
            None,
        )
        assert next_phase == ConversationPhase.COMPLETED

    def test_completed_can_restart(self) -> None:
        """COMPLETED + new reservation intent -> GATHERING_INFO."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.MAKE_RESERVATION,
        )
        next_phase = determine_next_phase(
            ConversationPhase.COMPLETED,
            extraction,
        )
        assert next_phase == ConversationPhase.GATHERING_INFO

    def test_operator_request_from_any_state(self) -> None:
        """Operator request transitions to TRANSFERRED from any state."""
        extraction = ExtractedReservation(
            intent=ExtractionIntent.OPERATOR_REQUEST,
        )

        for phase in ConversationPhase:
            next_phase = determine_next_phase(phase, extraction)
            assert next_phase == ConversationPhase.TRANSFERRED

    def test_transferred_stays_transferred(self) -> None:
        """TRANSFERRED -> stays TRANSFERRED."""
        next_phase = determine_next_phase(
            ConversationPhase.TRANSFERRED,
            None,
        )
        assert next_phase == ConversationPhase.TRANSFERRED
