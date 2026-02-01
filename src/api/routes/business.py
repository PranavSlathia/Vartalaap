"""Business settings API routes.

Security: All endpoints require authentication and tenant scoping.
Only admins can access business settings for their authorized businesses.
"""

import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select

from src.api.auth import RequireBusinessAccess
from src.db.models import Business, BusinessPhoneNumber, BusinessStatus, BusinessType
from src.db.session import get_session

router = APIRouter(prefix="/api/business", tags=["business"])

# Valid time format HH:MM (supports single-digit hours like 9:00)
TIME_PATTERN = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


# =============================================================================
# Request/Response Schemas
# =============================================================================


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM time string to minutes since midnight.

    Handles single-digit hours (e.g., "9:00" → 540, "10:00" → 600).
    This avoids string comparison bugs like "10:00" < "9:00".
    """
    hours, minutes = time_str.split(":")
    return int(hours) * 60 + int(minutes)


class OperatingHours(BaseModel):
    """Operating hours for a single day."""

    open: str | None = Field(None, description="Opening time (HH:MM) or null if closed")
    close: str | None = Field(None, description="Closing time (HH:MM) or null if closed")
    overnight: bool = Field(
        False,
        description="True if close time is the next day (e.g., 22:00-02:00)",
    )

    @model_validator(mode="after")
    def validate_times(self) -> "OperatingHours":
        """Validate time format and order."""
        if self.open is not None and not TIME_PATTERN.match(self.open):
            raise ValueError(f"Invalid opening time format: {self.open}. Use HH:MM.")
        if self.close is not None and not TIME_PATTERN.match(self.close):
            raise ValueError(f"Invalid closing time format: {self.close}. Use HH:MM.")

        if self.open and self.close:
            # Convert to minutes for proper numeric comparison
            open_mins = time_to_minutes(self.open)
            close_mins = time_to_minutes(self.close)

            if self.overnight:
                # Overnight hours: close can be <= open (e.g., 22:00-02:00)
                # But must make sense (not 02:00-02:00)
                if open_mins == close_mins:
                    raise ValueError("Open and close times cannot be identical")
            else:
                # Same-day hours: close must be after open
                if close_mins <= open_mins:
                    raise ValueError(
                        f"Closing time ({self.close}) must be after opening ({self.open}). "
                        "For overnight hours (e.g., 22:00-02:00), set overnight: true"
                    )
        return self


class ReservationRules(BaseModel):
    """Reservation rules for the business."""

    min_party_size: int = Field(1, ge=1)
    max_party_size: int = Field(10, ge=1)
    max_phone_party_size: int = Field(
        10, ge=1, description="Max party size bookable by phone (larger → WhatsApp)"
    )
    total_seats: int = Field(40, ge=1)
    advance_days: int = Field(30, ge=1, description="How many days ahead can book")
    slot_duration_minutes: int = Field(90, ge=15)

    @model_validator(mode="after")
    def validate_party_sizes(self) -> "ReservationRules":
        """Validate cross-field constraints."""
        if self.min_party_size > self.max_party_size:
            raise ValueError(
                f"min_party_size ({self.min_party_size}) cannot exceed "
                f"max_party_size ({self.max_party_size})"
            )
        if self.max_phone_party_size > self.max_party_size:
            raise ValueError(
                f"max_phone_party_size ({self.max_phone_party_size}) cannot exceed "
                f"max_party_size ({self.max_party_size})"
            )
        # Ensure phone booking is possible (min_party_size must be achievable by phone)
        if self.min_party_size > self.max_phone_party_size:
            raise ValueError(
                f"min_party_size ({self.min_party_size}) cannot exceed "
                f"max_phone_party_size ({self.max_phone_party_size}). "
                "This would make phone booking impossible."
            )
        if self.max_party_size > self.total_seats:
            raise ValueError(
                f"max_party_size ({self.max_party_size}) cannot exceed "
                f"total_seats ({self.total_seats})"
            )
        return self


class BusinessResponse(BaseModel):
    """Business settings response."""

    id: str
    name: str
    type: BusinessType
    timezone: str
    status: BusinessStatus
    phone_numbers: list[str]
    operating_hours: dict[str, OperatingHours | str]
    reservation_rules: ReservationRules
    greeting_text: str | None
    menu_summary: str | None


class BusinessUpdate(BaseModel):
    """Business settings update request."""

    name: str | None = None
    timezone: str | None = None
    phone_numbers: list[str] | None = None
    operating_hours: dict[str, OperatingHours | str] | None = None
    reservation_rules: ReservationRules | None = None
    greeting_text: str | None = None
    menu_summary: str | None = None

    @model_validator(mode="after")
    def validate_operating_hours(self) -> "BusinessUpdate":
        """Validate operating hours structure."""
        if self.operating_hours:
            for day, hours in self.operating_hours.items():
                if day.lower() not in VALID_DAYS:
                    raise ValueError(f"Invalid day name: {day}. Must be one of: {VALID_DAYS}")
                # Allow "closed" string or OperatingHours object
                if isinstance(hours, str) and hours.lower() != "closed":
                    raise ValueError(
                        f"Invalid hours for {day}: '{hours}'. "
                        "Use 'closed' or {{open: 'HH:MM', close: 'HH:MM'}}"
                    )
        return self

    @model_validator(mode="after")
    def validate_phone_numbers(self) -> "BusinessUpdate":
        """Validate phone numbers are E.164 format."""
        if self.phone_numbers:
            for phone in self.phone_numbers:
                if not phone.startswith("+") or not phone[1:].isdigit():
                    raise ValueError(f"Invalid E.164 phone number: {phone}")
        return self

    @model_validator(mode="after")
    def validate_timezone(self) -> "BusinessUpdate":
        """Validate timezone is a valid IANA name."""
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as e:
                raise ValueError(
                    f"Invalid timezone: '{self.timezone}'. "
                    "Use IANA timezone names like 'Asia/Kolkata' or 'America/New_York'."
                ) from e
        return self


# =============================================================================
# Helper Functions
# =============================================================================


def parse_json_field(json_str: str | None, default: dict | list) -> dict | list:
    """Safely parse JSON field."""
    if not json_str:
        return default
    try:
        import json

        result = json.loads(json_str)
        return result  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return default


def serialize_json_field(value: dict | list | None) -> str | None:
    """Serialize to JSON string."""
    if value is None:
        return None
    import json

    return json.dumps(value)


def business_to_response(business: Business) -> BusinessResponse:
    """Convert Business model to response."""
    phone_numbers = parse_json_field(business.phone_numbers_json, [])
    operating_hours = parse_json_field(business.operating_hours_json, {})
    reservation_rules_dict = parse_json_field(business.reservation_rules_json, {})

    return BusinessResponse(
        id=business.id,
        name=business.name,
        type=business.type,
        timezone=business.timezone,
        status=business.status,
        phone_numbers=phone_numbers if isinstance(phone_numbers, list) else [],
        operating_hours=operating_hours if isinstance(operating_hours, dict) else {},
        reservation_rules=ReservationRules(**reservation_rules_dict)
        if isinstance(reservation_rules_dict, dict)
        else ReservationRules(),  # type: ignore[call-arg]
        greeting_text=business.greeting_text,
        menu_summary=business.menu_summary,
    )


async def sync_phone_numbers(
    session: AsyncSession, business_id: str, phone_numbers: list[str]
) -> None:
    """Sync phone numbers to the lookup table.

    Removes old numbers and adds new ones to ensure call routing works.
    """
    # Delete existing phone numbers for this business
    await session.execute(
        delete(BusinessPhoneNumber).where(BusinessPhoneNumber.business_id == business_id)  # type: ignore[arg-type]
    )

    # Add new phone numbers
    for i, phone in enumerate(phone_numbers):
        phone_record = BusinessPhoneNumber(
            phone_number=phone,
            business_id=business_id,
            is_primary=(i == 0),  # First number is primary
        )
        session.add(phone_record)


# =============================================================================
# Routes
# =============================================================================


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: str,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Get business settings by ID.

    Requires JWT authentication and X-Business-ID header.
    User must have access to the requested business.
    """
    # Tenant isolation: only allow access to authorized business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    result = await session.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' not found")

    return business_to_response(business)


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: str,
    update: BusinessUpdate,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Update business settings.

    Requires JWT authentication and X-Business-ID header.
    User must have access to the requested business.
    """
    # Tenant isolation: only allow access to authorized business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to modify business '{business_id}'",
        )

    result = await session.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' not found")

    # Apply updates
    if update.name is not None:
        business.name = update.name
    if update.timezone is not None:
        business.timezone = update.timezone
    if update.phone_numbers is not None:
        business.phone_numbers_json = serialize_json_field(update.phone_numbers)
        # Sync to lookup table for call routing
        await sync_phone_numbers(session, business_id, update.phone_numbers)
    if update.operating_hours is not None:
        # Convert OperatingHours to dict
        hours_dict: dict[str, Any] = {}
        for day, hours in update.operating_hours.items():
            if isinstance(hours, str):
                hours_dict[day] = hours
            else:
                hours_dict[day] = hours.model_dump()
        business.operating_hours_json = serialize_json_field(hours_dict)
    if update.reservation_rules is not None:
        business.reservation_rules_json = serialize_json_field(
            update.reservation_rules.model_dump()
        )
    if update.greeting_text is not None:
        business.greeting_text = update.greeting_text
    if update.menu_summary is not None:
        business.menu_summary = update.menu_summary

    # Always update timestamp on modification
    business.updated_at = datetime.now(UTC)

    session.add(business)
    await session.commit()
    await session.refresh(business)

    return business_to_response(business)


# Note: Removed GET /api/business (list all) endpoint to prevent cross-tenant data leakage.
# Each business can only access their own settings via GET /api/business/{business_id}.
