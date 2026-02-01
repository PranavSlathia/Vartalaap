"""SQLModel database models.

These models extend the generated Pydantic schemas and add:
- table=True for SQLModel table generation
- Primary key configuration
- Default values (timestamps, UUIDs)
- Indexes for common queries

JSON field validation is added for data integrity.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import field_validator
from sqlmodel import Field, SQLModel

# Valid day names for operating hours
VALID_DAYS = frozenset({
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
})

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


class BusinessType(str, Enum):
    """Type of business."""

    restaurant = "restaurant"
    clinic = "clinic"
    salon = "salon"
    other = "other"


class BusinessStatus(str, Enum):
    """Business account status."""

    active = "active"
    suspended = "suspended"
    onboarding = "onboarding"


class KnowledgeCategory(str, Enum):
    """Category of knowledge item."""

    menu_item = "menu_item"
    faq = "faq"
    policy = "policy"
    announcement = "announcement"


class RatingMethod(str, Enum):
    """How a call rating was collected."""

    dtmf = "dtmf"  # Caller pressed digit
    admin = "admin"  # Admin rated manually
    auto = "auto"  # Auto-rated based on outcome


class CallCategory(str, Enum):
    """Category/intent of a call."""

    booking = "booking"
    inquiry = "inquiry"
    complaint = "complaint"
    spam = "spam"
    other = "other"


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

    # Performance metrics (nullable for backwards compat)
    stt_latency_p50_ms: float | None = Field(
        default=None, description="P50 STT latency in milliseconds"
    )
    llm_latency_p50_ms: float | None = Field(
        default=None, description="P50 LLM first token latency in milliseconds"
    )
    tts_latency_p50_ms: float | None = Field(
        default=None, description="P50 TTS first chunk latency in milliseconds"
    )
    barge_in_count: int = Field(default=0, ge=0, description="Number of barge-ins during call")
    total_turns: int = Field(default=0, ge=0, description="Total conversation turns")

    # Call rating and feedback
    call_rating: int | None = Field(
        default=None, ge=1, le=5, description="Caller satisfaction rating (1-5 stars)"
    )
    caller_feedback: str | None = Field(
        default=None, max_length=500, description="Optional caller feedback text"
    )
    rating_method: RatingMethod | None = Field(
        default=None, description="How rating was collected"
    )

    # Call summary (generated by LLM)
    call_summary: str | None = Field(
        default=None, max_length=500, description="LLM-generated call summary"
    )
    call_category: CallCategory | None = Field(
        default=None, description="Call intent category"
    )


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


# =============================================================================
# Multi-Business Models
# =============================================================================


class Business(SQLModel, table=True):
    """Business entity for multi-tenant support."""

    __tablename__ = "businesses"

    id: str = Field(
        primary_key=True,
        description="Business slug identifier (e.g., himalayan_kitchen)",
        max_length=50,
    )
    name: str = Field(max_length=200, description="Display name of the business")
    type: BusinessType = Field(default=BusinessType.restaurant)
    timezone: str = Field(default="Asia/Kolkata", max_length=50)
    status: BusinessStatus = Field(default=BusinessStatus.onboarding, index=True)
    phone_numbers_json: str | None = Field(
        default=None, description="JSON array of phone numbers in E.164 format"
    )
    operating_hours_json: str | None = Field(
        default=None, description="JSON object mapping day names to hours"
    )
    reservation_rules_json: str | None = Field(
        default=None, description="JSON object with reservation rules"
    )
    greeting_text: str | None = Field(
        default=None, max_length=500, description="Custom greeting for voice calls"
    )
    menu_summary: str | None = Field(
        default=None, max_length=2000, description="Brief menu/service summary for LLM"
    )
    admin_password_hash: str | None = Field(
        default=None, description="bcrypt hash for business-specific admin access"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("operating_hours_json", mode="before")
    @classmethod
    def validate_operating_hours(cls, v: Any) -> str | None:
        """Validate operating_hours_json structure."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}") from e
        else:
            data = v
            v = json.dumps(v)

        if not isinstance(data, dict):
            raise ValueError("operating_hours must be an object")
        for day in data.keys():
            if day.lower() not in VALID_DAYS:
                raise ValueError(f"Invalid day name: {day}")
        return v

    @field_validator("phone_numbers_json", mode="before")
    @classmethod
    def validate_phone_numbers(cls, v: Any) -> str | None:
        """Validate phone_numbers_json is a list of E.164 numbers."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}") from e
        else:
            data = v
            v = json.dumps(v)

        if not isinstance(data, list):
            raise ValueError("phone_numbers must be an array")
        for phone in data:
            if not isinstance(phone, str) or not phone.startswith("+"):
                raise ValueError(f"Invalid E.164 phone number: {phone}")
        return v

    @field_validator("reservation_rules_json", mode="before")
    @classmethod
    def validate_reservation_rules(cls, v: Any) -> str | None:
        """Validate reservation_rules_json structure."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}") from e
        else:
            data = v
            v = json.dumps(v)

        if not isinstance(data, dict):
            raise ValueError("reservation_rules must be an object")
        # Validate expected keys have correct types
        if "min_party_size" in data and not isinstance(data["min_party_size"], int):
            raise ValueError("min_party_size must be an integer")
        if "max_phone_party_size" in data and not isinstance(data["max_phone_party_size"], int):
            raise ValueError("max_phone_party_size must be an integer")
        if "total_seats" in data and not isinstance(data["total_seats"], int):
            raise ValueError("total_seats must be an integer")
        return v


class BusinessPhoneNumber(SQLModel, table=True):
    """Phone number lookup table for business resolution."""

    __tablename__ = "business_phone_numbers"

    phone_number: str = Field(
        primary_key=True,
        description="Phone number in E.164 format",
        max_length=20,
    )
    business_id: str = Field(
        foreign_key="businesses.id",
        index=True,
        description="Business this number belongs to",
    )
    is_primary: bool = Field(default=False, description="Whether this is the primary number")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeItem(SQLModel, table=True):
    """Knowledge base item for RAG retrieval during voice calls."""

    __tablename__ = "knowledge_items"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    business_id: str = Field(
        foreign_key="businesses.id",
        index=True,
        description="Business this item belongs to (tenant isolation)",
    )
    category: KnowledgeCategory = Field(
        index=True, description="Type of knowledge item"
    )
    title: str = Field(max_length=200, description="Item title")
    title_hindi: str | None = Field(
        default=None, max_length=200, description="Title in Hindi/Devanagari"
    )
    content: str = Field(max_length=2000, description="Full content/description")
    content_hindi: str | None = Field(
        default=None, max_length=2000, description="Content in Hindi"
    )
    metadata_json: str | None = Field(
        default=None, description="JSON object with category-specific metadata"
    )
    is_active: bool = Field(default=True, index=True, description="Active for retrieval")
    priority: int = Field(default=50, ge=0, le=100, description="Priority for ranking")
    embedding_id: str | None = Field(
        default=None, description="ChromaDB document ID for vector retrieval"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Transcript Analysis Models (Agent QA System)
# =============================================================================


class IssueCategory(str, Enum):
    """Category of issue identified in transcript review."""

    knowledge_gap = "knowledge_gap"  # Missing info in knowledge base
    prompt_weakness = "prompt_weakness"  # LLM prompt needs improvement
    ux_issue = "ux_issue"  # User experience friction
    stt_error = "stt_error"  # Speech-to-text misrecognition
    tts_issue = "tts_issue"  # Text-to-speech quality
    config_error = "config_error"  # Business config problem


class SuggestionStatus(str, Enum):
    """Status of an improvement suggestion."""

    pending = "pending"
    implemented = "implemented"
    rejected = "rejected"
    deferred = "deferred"


class TranscriptReview(SQLModel, table=True):
    """Internal QA review of a call transcript by AI agents."""

    __tablename__ = "transcript_reviews"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    call_log_id: str = Field(
        foreign_key="call_logs.id",
        index=True,
        sa_column_kwargs={"unique": True},  # Prevent duplicate reviews
        description="The call transcript being reviewed",
    )
    business_id: str = Field(
        index=True,
        description="Business for filtering reviews",
    )

    # Review results
    quality_score: int = Field(
        ge=1, le=5, description="Internal quality rating (1-5)"
    )
    issues_json: str | None = Field(
        default=None,
        description="JSON array of identified issues",
    )
    suggestions_json: str | None = Field(
        default=None,
        description="JSON array of improvement suggestions",
    )

    # Issue categories found (for quick filtering)
    has_unanswered_query: bool = Field(
        default=False, description="Caller had question bot couldn't answer"
    )
    has_knowledge_gap: bool = Field(
        default=False, description="Knowledge base missing needed info"
    )
    has_prompt_weakness: bool = Field(
        default=False, description="LLM prompt needs improvement"
    )
    has_ux_issue: bool = Field(
        default=False, description="User experience friction detected"
    )

    # Agent metadata
    agent_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="LLM model used for review",
    )
    review_latency_ms: float | None = Field(
        default=None, description="Time taken for agent review"
    )

    # Timestamps
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        index=True,
        description="When the review was completed",
    )
    reviewed_by: str = Field(
        default="agent",
        description="'agent' for AI review, or admin username for manual",
    )


class ImprovementSuggestion(SQLModel, table=True):
    """Actionable suggestions from transcript reviews."""

    __tablename__ = "improvement_suggestions"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        description="Unique identifier",
    )
    review_id: str = Field(
        foreign_key="transcript_reviews.id",
        index=True,
        description="Source transcript review",
    )
    business_id: str = Field(
        index=True,
        description="Business for filtering suggestions",
    )

    # Suggestion details
    category: IssueCategory = Field(
        description="Type of improvement needed",
    )
    title: str = Field(
        max_length=200, description="Brief description of the suggestion"
    )
    description: str = Field(
        max_length=2000, description="Detailed explanation and rationale"
    )
    priority: int = Field(
        default=3, ge=1, le=5, description="Priority (1=low, 5=critical)"
    )

    # Tracking
    status: SuggestionStatus = Field(
        default=SuggestionStatus.pending,
        index=True,
        description="Implementation status",
    )
    implemented_at: datetime | None = Field(
        default=None, description="When the suggestion was implemented"
    )
    implemented_by: str | None = Field(
        default=None, description="Admin who implemented the suggestion"
    )
    rejection_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Why suggestion was rejected if applicable",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
