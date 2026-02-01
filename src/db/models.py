"""SQLModel database models.

These models extend the generated Pydantic schemas and add:
- table=True for SQLModel table generation
- Primary key configuration
- Default values (timestamps, UUIDs)
- Indexes for common queries

DO NOT add validation here - that belongs in the JSON Schema.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel

# =============================================================================
# Enums (shared across models)
# =============================================================================


class CallOutcome(str, Enum):
    """How a call ended."""

    resolved = "resolved"
    fallback = "fallback"
    dropped = "dropped"
    error = "error"
    privacy_opt_out = "privacy_opt_out"


class ConsentType(str, Enum):
    """Level of consent given by caller."""

    none = "none"
    transcript = "transcript"
    whatsapp = "whatsapp"


class DetectedLanguage(str, Enum):
    """Detected language during call."""

    hindi = "hindi"
    english = "english"
    hinglish = "hinglish"


class ReservationStatus(str, Enum):
    """Status of a reservation."""

    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class FollowupReason(str, Enum):
    """Why a WhatsApp followup is needed."""

    callback_request = "callback_request"
    large_party = "large_party"
    catering_inquiry = "catering_inquiry"
    complaint = "complaint"
    other = "other"


class FollowupStatus(str, Enum):
    """Status of a WhatsApp followup."""

    pending = "pending"
    sent = "sent"
    responded = "responded"
    expired = "expired"


class AuditAction(str, Enum):
    """Types of auditable actions."""

    config_update = "config_update"
    reservation_cancel = "reservation_cancel"
    reservation_modify = "reservation_modify"
    data_export = "data_export"
    data_purge = "data_purge"
    login = "login"
    logout = "logout"


# =============================================================================
# Database Models
# =============================================================================


class CallLog(SQLModel, table=True):
    """Record of a voice call handled by the bot."""

    __tablename__ = "call_logs"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    business_id: str = Field(index=True, description="Business that received this call")
    caller_id_hash: str | None = Field(
        default=None,
        index=True,
        description="HMAC-SHA256 hash of caller phone for deduplication",
    )
    call_start: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When call started"
    )
    call_end: datetime | None = Field(default=None, description="When call ended")
    duration_seconds: int | None = Field(default=None, ge=0)
    detected_language: DetectedLanguage | None = Field(default=None)
    transcript: str | None = Field(
        default=None, description="JSON string of conversation turns"
    )
    extracted_info: str | None = Field(
        default=None, description="JSON string of extracted entities"
    )
    outcome: CallOutcome | None = Field(default=None)
    consent_type: ConsentType | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class Reservation(SQLModel, table=True):
    """Restaurant table reservation."""

    __tablename__ = "reservations"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    business_id: str = Field(index=True, description="Business this reservation belongs to")
    call_log_id: str | None = Field(
        default=None,
        foreign_key="call_logs.id",
        description="Associated call log",
    )
    customer_name: str | None = Field(default=None, max_length=100)
    customer_phone_encrypted: str | None = Field(
        default=None, description="AES-256-GCM encrypted phone for WhatsApp"
    )
    party_size: int = Field(ge=1, le=20)
    reservation_date: str = Field(description="YYYY-MM-DD format")
    reservation_time: str = Field(description="HH:MM format")
    status: ReservationStatus = Field(default=ReservationStatus.confirmed)
    whatsapp_sent: bool = Field(default=False)
    whatsapp_consent: bool = Field(default=False)
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CallerPreferences(SQLModel, table=True):
    """Caller opt-out preferences and tracking."""

    __tablename__ = "caller_preferences"

    caller_id_hash: str = Field(
        primary_key=True, description="HMAC-SHA256 hash of phone"
    )
    whatsapp_opt_out: bool = Field(default=False, description="Caller replied STOP")
    transcript_opt_out: bool = Field(default=False, description="Caller said don't record")
    first_seen: datetime | None = Field(default=None)
    last_seen: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WhatsappFollowup(SQLModel, table=True):
    """Non-reservation WhatsApp callback requests."""

    __tablename__ = "whatsapp_followups"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    business_id: str = Field(index=True)
    call_log_id: str | None = Field(default=None, foreign_key="call_logs.id")
    customer_phone_encrypted: str = Field(description="AES-256-GCM encrypted phone")
    reason: FollowupReason | None = Field(default=None)
    summary: str | None = Field(default=None, max_length=500)
    status: FollowupStatus = Field(default=FollowupStatus.pending, index=True)
    whatsapp_consent: bool = Field(default=True)
    sent_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditLog(SQLModel, table=True):
    """Audit trail for admin actions."""

    __tablename__ = "audit_logs"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    action: AuditAction = Field(description="Type of action performed")
    admin_user: str | None = Field(default=None)
    details: str | None = Field(default=None, description="JSON with before/after values")
    ip_address: str | None = Field(default=None)
