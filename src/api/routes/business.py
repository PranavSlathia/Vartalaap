"""Business settings API routes.

Security: All endpoints require authentication and tenant scoping.
Only admins can access business settings for their authorized businesses.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select

from src.db.models import Business, BusinessPhoneNumber, BusinessStatus, BusinessType
from src.db.session import get_session

router = APIRouter(prefix="/api/business", tags=["business"])

# Valid time format HH:MM
TIME_PATTERN = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


# =============================================================================
# Authentication Dependency
# =============================================================================


async def get_current_business_id(
    x_business_id: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract and validate business_id from request.

    In production, this should validate the JWT token and extract
    the authorized business_id from claims. For MVP, we use a header.

    TODO: Integrate with Keycloak JWT validation to extract business_id
    from token claims (e.g., resource_access or custom claim).
    """
    if not x_business_id:
        raise HTTPException(
            status_code=401,
            detail="X-Business-ID header required. Set VITE_BUSINESS_ID in frontend.",
        )
    # TODO: Validate that the authenticated user has access to this business
    # by checking JWT claims against x_business_id
    return x_business_id


# =============================================================================
# Request/Response Schemas
# =============================================================================


class OperatingHours(BaseModel):
    """Operating hours for a single day."""

    open: str | None = Field(None, description="Opening time (HH:MM) or null if closed")
    close: str | None = Field(None, description="Closing time (HH:MM) or null if closed")

    @model_validator(mode="after")
    def validate_times(self) -> "OperatingHours":
        """Validate time format."""
        if self.open is not None and not TIME_PATTERN.match(self.open):
            raise ValueError(f"Invalid opening time format: {self.open}. Use HH:MM.")
        if self.close is not None and not TIME_PATTERN.match(self.close):
            raise ValueError(f"Invalid closing time format: {self.close}. Use HH:MM.")
        if self.open and self.close:
            # Basic sanity: close should be after open (doesn't handle overnight)
            if self.close <= self.open:
                raise ValueError("Closing time must be after opening time")
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


# =============================================================================
# Helper Functions
# =============================================================================


def parse_json_field(json_str: str | None, default: dict | list) -> dict | list:
    """Safely parse JSON field."""
    if not json_str:
        return default
    try:
        import json

        return json.loads(json_str)
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
        else ReservationRules(),
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
        delete(BusinessPhoneNumber).where(BusinessPhoneNumber.business_id == business_id)
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
    session: AsyncSession = Depends(get_session),
    auth_business_id: str = Depends(get_current_business_id),
) -> BusinessResponse:
    """Get business settings by ID.

    Requires X-Business-ID header matching the requested business_id.
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
    session: AsyncSession = Depends(get_session),
    auth_business_id: str = Depends(get_current_business_id),
) -> BusinessResponse:
    """Update business settings.

    Requires X-Business-ID header matching the requested business_id.
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
        hours_dict = {}
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

    session.add(business)
    await session.commit()
    await session.refresh(business)

    return business_to_response(business)


# Note: Removed GET /api/business (list all) endpoint to prevent cross-tenant data leakage.
# Each business can only access their own settings via GET /api/business/{business_id}.
