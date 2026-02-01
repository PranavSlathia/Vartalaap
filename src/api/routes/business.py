"""Business settings API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db.models import Business, BusinessStatus, BusinessType
from src.db.session import get_session

router = APIRouter(prefix="/api/business", tags=["business"])


# =============================================================================
# Response/Request Schemas
# =============================================================================


class OperatingHours(BaseModel):
    """Operating hours for a single day."""

    open: str | None = Field(None, description="Opening time (HH:MM) or null if closed")
    close: str | None = Field(None, description="Closing time (HH:MM) or null if closed")


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


# =============================================================================
# Routes
# =============================================================================


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: str,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Get business settings by ID."""
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
) -> BusinessResponse:
    """Update business settings."""
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


@router.get("", response_model=list[BusinessResponse])
async def list_businesses(
    session: AsyncSession = Depends(get_session),
) -> list[BusinessResponse]:
    """List all businesses."""
    result = await session.execute(select(Business).order_by(Business.name))
    businesses = result.scalars().all()
    return [business_to_response(b) for b in businesses]
