"""Conversation state tracking for reservation flow.

Tracks the conversation phase and accumulated reservation details
across multiple turns of dialogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.llm.extractor import ExtractedReservation


class ConversationPhase(Enum):
    """Conversation phases for reservation flow."""

    GREETING = auto()  # Initial greeting, no intent detected yet
    GATHERING_INFO = auto()  # Collecting reservation details
    CONFIRMING = auto()  # Presenting details for confirmation
    AWAITING_CONFIRMATION = auto()  # Waiting for user to confirm
    BOOKING = auto()  # Creating the reservation
    COMPLETED = auto()  # Reservation successfully made
    TRANSFERRED = auto()  # Handed off to operator


# Questions to ask for missing fields (bilingual)
FIELD_QUESTIONS = {
    "party_size": "Kitne logon ke liye table chahiye?",  # How many people?
    "date": "Kis din ke liye reservation karein?",  # Which day?
    "time": "Kaunsi time prefer karenge - lunch ya dinner?",  # What time?
    "name": "Booking ke liye aapka naam bata dijiye?",  # Your name please?
}

# Confirmation messages for different scenarios
CONFIRMATION_TEMPLATE = (
    "Main confirm karti hoon - {date_str} ko {time}, "
    "{party_size} logon ke liye, {name} ji ke naam se. "
    "Kya yeh sahi hai?"
)


@dataclass
class ConversationState:
    """Tracks conversation state and accumulated reservation data.

    This state is maintained across conversation turns and used to:
    - Track which phase of the reservation flow we're in
    - Accumulate extracted reservation details
    - Generate appropriate follow-up questions
    - Cache the last response for repeat functionality
    """

    phase: ConversationPhase = ConversationPhase.GREETING
    pending_reservation: ExtractedReservation | None = None
    last_response: str = ""  # For DTMF * repeat functionality
    confirmation_attempts: int = 0
    max_confirmation_attempts: int = 3

    # Track which fields we've asked about to avoid repetition
    asked_fields: set[str] = field(default_factory=set)

    def needs_field(self, field_name: str) -> bool:
        """Check if we still need to collect a specific field.

        Args:
            field_name: One of 'party_size', 'date', 'time', 'name'

        Returns:
            True if the field is still needed
        """
        if self.pending_reservation is None:
            return True

        return field_name in self.pending_reservation.missing_fields

    def get_next_question(self) -> str | None:
        """Get the next question to ask for missing information.

        Returns question text, or None if no more questions needed.
        Prioritizes fields in order: party_size, date, time, name.
        """
        if self.pending_reservation is None:
            return None

        # Priority order for asking questions
        priority_order = ["party_size", "date", "time", "name"]

        for field_name in priority_order:
            # Only ask if field is missing and we haven't asked about it yet
            if (
                field_name in self.pending_reservation.missing_fields
                and field_name not in self.asked_fields
            ):
                self.asked_fields.add(field_name)
                return FIELD_QUESTIONS.get(field_name)

        return None

    def get_confirmation_message(self) -> str | None:
        """Generate confirmation message for the pending reservation.

        Returns formatted confirmation message, or None if reservation
        is incomplete.
        """
        if self.pending_reservation is None or not self.pending_reservation.is_complete:
            return None

        res = self.pending_reservation

        # Format date for display
        if res.reservation_date:
            # Format as "Saturday, 15 February" or "kal" if tomorrow
            from datetime import date, timedelta

            today = date.today()
            if res.reservation_date == today:
                date_str = "aaj"
            elif res.reservation_date == today + timedelta(days=1):
                date_str = "kal"
            else:
                date_str = res.reservation_date.strftime("%A, %d %B")
        else:
            date_str = "selected date"

        # Format time for display (19:00 -> "7 baje shaam")
        time_str = res.reservation_time or ""
        if time_str:
            hour = int(time_str.split(":")[0])
            if hour >= 17:
                time_str = f"{hour - 12 if hour > 12 else hour} baje shaam"
            elif hour >= 12:
                time_str = f"{hour - 12 if hour > 12 else hour} baje dopahar"
            else:
                time_str = f"{hour} baje subah"

        return CONFIRMATION_TEMPLATE.format(
            date_str=date_str,
            time=time_str,
            party_size=res.party_size,
            name=res.customer_name or "Guest",
        )

    def should_confirm(self) -> bool:
        """Check if we should move to confirmation phase.

        Returns True if reservation is complete and we haven't
        exceeded confirmation attempts.
        """
        if self.pending_reservation is None:
            return False

        return (
            self.pending_reservation.is_complete
            and self.confirmation_attempts < self.max_confirmation_attempts
        )

    def increment_confirmation(self) -> None:
        """Increment confirmation attempt counter."""
        self.confirmation_attempts += 1

    def reset_asked_fields(self) -> None:
        """Reset the set of asked fields (e.g., after user provides new info)."""
        self.asked_fields = set()

    def transition_to(self, new_phase: ConversationPhase) -> None:
        """Transition to a new conversation phase.

        Args:
            new_phase: The phase to transition to
        """
        self.phase = new_phase

        # Reset confirmation attempts when moving to new phase
        if new_phase == ConversationPhase.GATHERING_INFO:
            self.confirmation_attempts = 0
            self.asked_fields = set()

    def update_reservation(self, extraction: ExtractedReservation) -> None:
        """Update the pending reservation with new extraction data.

        If there's an existing pending reservation, merges the new
        extraction with it. Otherwise, sets it as the new pending reservation.

        Args:
            extraction: New extraction to merge/set
        """
        if self.pending_reservation is None:
            self.pending_reservation = extraction
        else:
            self.pending_reservation = self.pending_reservation.merge_with(extraction)

        # Reset asked fields when we get new information
        self.reset_asked_fields()

    def clear(self) -> None:
        """Clear state for a new conversation."""
        self.phase = ConversationPhase.GREETING
        self.pending_reservation = None
        self.last_response = ""
        self.confirmation_attempts = 0
        self.asked_fields = set()


def determine_next_phase(
    current_phase: ConversationPhase,
    extraction: ExtractedReservation | None,
    user_confirmed: bool = False,
) -> ConversationPhase:
    """Determine the next conversation phase based on current state.

    State machine logic:
    - GREETING + reservation intent -> GATHERING_INFO
    - GATHERING_INFO + complete info -> CONFIRMING
    - CONFIRMING -> AWAITING_CONFIRMATION
    - AWAITING_CONFIRMATION + confirmed -> BOOKING
    - BOOKING + success -> COMPLETED
    - Any + operator request -> TRANSFERRED

    Args:
        current_phase: Current conversation phase
        extraction: Latest extraction result (if any)
        user_confirmed: Whether user confirmed the reservation

    Returns:
        Next conversation phase
    """
    from src.services.llm.extractor import ExtractionIntent

    # Handle operator transfer request from any state
    if extraction and extraction.intent == ExtractionIntent.OPERATOR_REQUEST:
        return ConversationPhase.TRANSFERRED

    # State transitions based on current phase
    if current_phase == ConversationPhase.GREETING:
        if extraction and extraction.intent == ExtractionIntent.MAKE_RESERVATION:
            return ConversationPhase.GATHERING_INFO
        return ConversationPhase.GREETING

    elif current_phase == ConversationPhase.GATHERING_INFO:
        if extraction and extraction.is_complete:
            return ConversationPhase.CONFIRMING
        return ConversationPhase.GATHERING_INFO

    elif current_phase == ConversationPhase.CONFIRMING:
        return ConversationPhase.AWAITING_CONFIRMATION

    elif current_phase == ConversationPhase.AWAITING_CONFIRMATION:
        if user_confirmed:
            return ConversationPhase.BOOKING
        # User didn't confirm - might be changing something
        return ConversationPhase.GATHERING_INFO

    elif current_phase == ConversationPhase.BOOKING:
        return ConversationPhase.COMPLETED

    elif current_phase == ConversationPhase.COMPLETED:
        # Stay completed or restart if new intent
        if extraction and extraction.intent == ExtractionIntent.MAKE_RESERVATION:
            return ConversationPhase.GATHERING_INFO
        return ConversationPhase.COMPLETED

    elif current_phase == ConversationPhase.TRANSFERRED:
        # Stay transferred
        return ConversationPhase.TRANSFERRED

    return current_phase
