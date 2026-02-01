"""Orchestrate reservation booking flow.

Coordinates between:
- Extraction results from LLM
- Conversation state machine
- Reservation repository for availability/booking
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from src.core.conversation_state import (
    ConversationPhase,
    ConversationState,
    determine_next_phase,
)
from src.db.models import Reservation, ReservationStatus
from src.db.repositories.reservations import AvailabilityResult
from src.logging_config import get_logger
from src.services.llm.extractor import ExtractedReservation, ExtractionIntent

if TYPE_CHECKING:
    from src.db.repositories.reservations import AsyncReservationRepository

logger: Any = get_logger(__name__)


@dataclass
class BookingResult:
    """Result of a booking attempt."""

    success: bool
    reservation_id: str | None = None
    message: str = ""
    alternatives: list[dict] | None = None


# Response templates (bilingual)
RESPONSES = {
    "booking_success": (
        "Bahut accha! Aapki booking confirm ho gayi - {date_str} ko {time}, "
        "{party_size} logon ke liye, {name} ji ke naam se. "
        "{restaurant_name} mein milte hain!"
    ),
    "slot_unavailable": (
        "Maaf kijiye, {date_str} ko {time} slot available nahi hai. "
        "{alternatives}"
    ),
    "alternatives_offered": "{alt1} ya {alt2} available hai - kaunsa better hai?",
    "no_alternatives": "Kya aap koi aur din ya time try karna chahenge?",
    "party_too_large": (
        "{party_size} logon ke liye phone par booking nahi ho sakti - "
        "max {max_size} tak. Bade groups ke liye WhatsApp par contact karein."
    ),
    "too_soon": (
        "Maaf kijiye, reservation kam se kam {min_minutes} minute pehle honi chahiye."
    ),
    "closed_day": "Maaf kijiye, {day} ko hum band rehte hain. Kya koi aur din suit karega?",
    "outside_hours": (
        "Maaf kijiye, {time} par hum open nahi hain. "
        "Hum {open_time} se {close_time} tak khule hain."
    ),
}


class ReservationFlow:
    """Manages the reservation booking process.

    Coordinates the conversation state machine with the
    reservation repository to check availability and create bookings.
    """

    def __init__(
        self,
        repo: AsyncReservationRepository,
        business_id: str,
        business_name: str = "restaurant",
        timezone: str = "Asia/Kolkata",
    ) -> None:
        """Initialize reservation flow.

        Args:
            repo: Async reservation repository
            business_id: Business identifier
            business_name: Display name for responses
            timezone: Business timezone for date/time handling
        """
        self._repo = repo
        self._business_id = business_id
        self._business_name = business_name
        self._tz = ZoneInfo(timezone)

    async def process_extraction(
        self,
        extraction: ExtractedReservation,
        state: ConversationState,
    ) -> tuple[str | None, ConversationState]:
        """Process extracted data and return response + updated state.

        This is the main entry point for the reservation flow. It:
        1. Updates the state with new extraction data
        2. Determines the next phase
        3. Generates an appropriate response

        Args:
            extraction: Newly extracted reservation data
            state: Current conversation state

        Returns:
            Tuple of (response_override, new_state)
            response_override is None if LLM response should be used as-is
        """
        # Handle operator transfer request
        if extraction.intent == ExtractionIntent.OPERATOR_REQUEST:
            state.transition_to(ConversationPhase.TRANSFERRED)
            return None, state  # Let LLM handle the response

        # Handle non-reservation intents
        if extraction.intent not in (
            ExtractionIntent.MAKE_RESERVATION,
            ExtractionIntent.MODIFY_RESERVATION,
        ):
            return None, state  # Let LLM handle inquiries, chitchat

        # Update state with new extraction
        state.update_reservation(extraction)

        # Determine next phase
        next_phase = determine_next_phase(
            state.phase,
            state.pending_reservation,
        )
        state.transition_to(next_phase)

        # Generate response based on phase
        if next_phase == ConversationPhase.GATHERING_INFO:
            # Check if we should proceed to confirmation (info is complete)
            if state.should_confirm():
                state.transition_to(ConversationPhase.CONFIRMING)
                next_phase = ConversationPhase.CONFIRMING
            else:
                # Still collecting info - ask next question
                question = state.get_next_question()
                if question:
                    return question, state
                return None, state  # Let LLM continue conversation

        if next_phase == ConversationPhase.CONFIRMING:
            # All info collected - generate confirmation
            confirmation = state.get_confirmation_message()
            if confirmation:
                state.transition_to(ConversationPhase.AWAITING_CONFIRMATION)
                state.increment_confirmation()
                return confirmation, state
            return None, state

        return None, state

    async def handle_confirmation(
        self,
        confirmed: bool,
        state: ConversationState,
        caller_phone_encrypted: str | None = None,
        call_log_id: str | None = None,
    ) -> tuple[str, ConversationState]:
        """Handle user's confirmation response.

        Args:
            confirmed: Whether user confirmed the booking
            state: Current conversation state
            caller_phone_encrypted: Encrypted phone for reservation
            call_log_id: Associated call log ID

        Returns:
            Tuple of (response, new_state)
        """
        if not confirmed:
            # User didn't confirm - go back to gathering
            state.transition_to(ConversationPhase.GATHERING_INFO)
            state.reset_asked_fields()
            return "Theek hai, kya change karna chahenge?", state

        if state.pending_reservation is None:
            return "Maaf kijiye, booking details missing hain.", state

        # Attempt to book
        result = await self.check_and_book(
            state.pending_reservation,
            caller_phone_encrypted=caller_phone_encrypted,
            call_log_id=call_log_id,
        )

        if result.success:
            state.transition_to(ConversationPhase.COMPLETED)
            return result.message, state
        else:
            # Booking failed - offer alternatives or ask for changes
            if result.alternatives:
                state.transition_to(ConversationPhase.GATHERING_INFO)
            return result.message, state

    async def check_and_book(
        self,
        extraction: ExtractedReservation,
        caller_phone_encrypted: str | None = None,
        call_log_id: str | None = None,
    ) -> BookingResult:
        """Check availability and create reservation if possible.

        Args:
            extraction: Complete reservation details
            caller_phone_encrypted: Encrypted phone for the reservation
            call_log_id: Associated call log ID

        Returns:
            BookingResult with success status and message
        """
        if not extraction.is_complete:
            return BookingResult(
                success=False,
                message="Reservation details incomplete.",
            )

        # Check availability
        availability = await self._repo.check_availability(
            business_id=self._business_id,
            reservation_date=extraction.reservation_date,  # type: ignore
            reservation_time=extraction.reservation_time,  # type: ignore
            party_size=extraction.party_size,  # type: ignore
        )

        if not availability.available:
            return await self._handle_unavailable(extraction, availability)

        # Create the reservation
        # At this point extraction.is_complete is True, so these fields are not None
        assert extraction.party_size is not None
        assert extraction.reservation_date is not None
        assert extraction.reservation_time is not None

        reservation = Reservation(
            business_id=self._business_id,
            call_log_id=call_log_id,
            customer_name=extraction.customer_name,
            customer_phone_encrypted=caller_phone_encrypted,
            party_size=extraction.party_size,
            reservation_date=extraction.reservation_date.isoformat(),
            reservation_time=extraction.reservation_time,
            status=ReservationStatus.confirmed,
            notes=extraction.special_requests,
        )

        self._repo.session.add(reservation)

        # Format success message (fields asserted non-None above)
        date_str = self._format_date(extraction.reservation_date)
        time_str = self._format_time(extraction.reservation_time)

        message = RESPONSES["booking_success"].format(
            date_str=date_str,
            time=time_str,
            party_size=extraction.party_size,
            name=extraction.customer_name or "Guest",
            restaurant_name=self._business_name,
        )

        logger.info(
            f"Reservation created: {reservation.id} for {extraction.party_size} "
            f"on {extraction.reservation_date} at {extraction.reservation_time}"
        )

        return BookingResult(
            success=True,
            reservation_id=reservation.id,
            message=message,
        )

    async def _handle_unavailable(
        self,
        extraction: ExtractedReservation,
        availability: AvailabilityResult,
    ) -> BookingResult:
        """Handle unavailable slot - generate appropriate response.

        Args:
            extraction: The requested reservation details
            availability: Result from availability check

        Returns:
            BookingResult with failure message and alternatives if any
        """
        date_str = self._format_date(extraction.reservation_date)  # type: ignore
        time_str = self._format_time(extraction.reservation_time)  # type: ignore

        reason = availability.reason or "unavailable"

        if reason == "party_size_too_large":
            message = RESPONSES["party_too_large"].format(
                party_size=extraction.party_size,
                max_size=10,  # Could load from config
            )
            return BookingResult(success=False, message=message)

        if reason == "too_soon":
            message = RESPONSES["too_soon"].format(min_minutes=30)
            return BookingResult(success=False, message=message)

        if reason == "closed":
            day_name = extraction.reservation_date.strftime("%A")  # type: ignore
            message = RESPONSES["closed_day"].format(day=day_name)
            return BookingResult(success=False, message=message)

        if reason == "outside_hours":
            # Could load actual hours from config
            message = RESPONSES["outside_hours"].format(
                time=time_str,
                open_time="11 baje",
                close_time="10:30 baje",
            )
            return BookingResult(success=False, message=message)

        # Capacity full - try to find alternatives
        alternatives = await self.generate_alternatives(extraction)

        if alternatives:
            alt_text = RESPONSES["alternatives_offered"].format(
                alt1=self._format_time(alternatives[0]["time"]),
                alt2=self._format_time(alternatives[1]["time"]) if len(alternatives) > 1 else "",
            )
        else:
            alt_text = RESPONSES["no_alternatives"]

        message = RESPONSES["slot_unavailable"].format(
            date_str=date_str,
            time=time_str,
            alternatives=alt_text,
        )

        return BookingResult(
            success=False,
            message=message,
            alternatives=alternatives if alternatives else None,
        )

    async def generate_alternatives(
        self,
        extraction: ExtractedReservation,
        num_alternatives: int = 2,
    ) -> list[dict]:
        """Generate alternative times if requested slot is unavailable.

        Args:
            extraction: The original reservation request
            num_alternatives: Number of alternatives to suggest

        Returns:
            List of available alternative slots
        """
        if extraction.reservation_date is None or extraction.reservation_time is None:
            return []

        alternatives: list[dict] = []
        base_time = datetime.strptime(extraction.reservation_time, "%H:%M")

        # Try times before and after the requested time
        offsets = [-60, -30, 30, 60, 90, 120]  # minutes

        for offset in offsets:
            if len(alternatives) >= num_alternatives:
                break

            new_time = base_time + timedelta(minutes=offset)
            time_str = new_time.strftime("%H:%M")

            # Skip very early or very late times
            hour = new_time.hour
            if hour < 11 or hour > 21:
                continue

            availability = await self._repo.check_availability(
                business_id=self._business_id,
                reservation_date=extraction.reservation_date,
                reservation_time=time_str,
                party_size=extraction.party_size or 2,
            )

            if availability.available:
                alternatives.append({
                    "date": extraction.reservation_date.isoformat(),
                    "time": time_str,
                    "available_seats": (
                        availability.total_seats - availability.used_seats
                        if availability.total_seats and availability.used_seats is not None
                        else None
                    ),
                })

        return alternatives

    def _format_date(self, reservation_date: date) -> str:
        """Format date for display in responses."""
        today = datetime.now(self._tz).date()

        if reservation_date == today:
            return "aaj"
        elif reservation_date == today + timedelta(days=1):
            return "kal"
        elif reservation_date == today + timedelta(days=2):
            return "parson"
        else:
            return reservation_date.strftime("%A, %d %B")

    def _format_time(self, time_str: str) -> str:
        """Format time for display in responses."""
        try:
            hour = int(time_str.split(":")[0])
            minute = int(time_str.split(":")[1])

            if minute == 0:
                minute_str = ""
            elif minute == 30:
                minute_str = " aadha"
            else:
                minute_str = f":{minute:02d}"

            if hour >= 17:
                display_hour = hour - 12 if hour > 12 else hour
                return f"{display_hour}{minute_str} baje shaam"
            elif hour >= 12:
                display_hour = hour - 12 if hour > 12 else hour
                return f"{display_hour}{minute_str} baje dopahar"
            else:
                return f"{hour}{minute_str} baje subah"
        except (ValueError, IndexError):
            return time_str
