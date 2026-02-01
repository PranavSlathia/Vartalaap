"""CRUD endpoints for reservations.

Note: fastapi-crudrouter's SQLAlchemyCRUDRouter is sync-oriented and
incompatible with async sessions. This module provides async CRUD operations.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Reservation, ReservationStatus
from src.db.session import get_session

router = APIRouter(prefix="/reservations", tags=["Reservations"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class ReservationCreate(BaseModel):
    """Schema for creating a reservation."""

    business_id: str
    call_log_id: str | None = None
    customer_name: str | None = Field(None, max_length=100)
    customer_phone_encrypted: str | None = None
    party_size: int = Field(ge=1, le=20)
    reservation_date: date
    reservation_time: str = Field(pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    notes: str | None = None
    whatsapp_consent: bool = False


class ReservationUpdate(BaseModel):
    """Schema for updating a reservation (all fields optional)."""

    customer_name: str | None = None
    party_size: int | None = Field(None, ge=1, le=20)
    reservation_date: date | None = None
    reservation_time: str | None = Field(None, pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    status: ReservationStatus | None = None
    notes: str | None = None
    whatsapp_sent: bool | None = None


class ReservationResponse(BaseModel):
    """Response schema for reservations."""

    id: str
    business_id: str
    call_log_id: str | None
    customer_name: str | None
    party_size: int
    reservation_date: str
    reservation_time: str
    status: ReservationStatus
    whatsapp_sent: bool
    whatsapp_consent: bool
    notes: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("", response_model=list[ReservationResponse])
async def list_reservations(
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Required for tenant isolation"),
    status: ReservationStatus | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[ReservationResponse]:
    """List reservations with optional filters.

    Security: business_id is required to prevent cross-tenant data access.
    """
    query = select(Reservation)

    # Required: always scope by business_id
    query = query.where(Reservation.business_id == business_id)  # type: ignore[arg-type]
    if status:
        query = query.where(Reservation.status == status)  # type: ignore[arg-type]
    if date_from:
        query = query.where(Reservation.reservation_date >= date_from.isoformat())  # type: ignore[arg-type]
    if date_to:
        query = query.where(Reservation.reservation_date <= date_to.isoformat())  # type: ignore[arg-type]

    query = query.offset(skip).limit(limit).order_by(desc(Reservation.reservation_date))

    result = await session.execute(query)
    reservations = result.scalars().all()

    return [
        ReservationResponse(
            id=r.id,
            business_id=r.business_id,
            call_log_id=r.call_log_id,
            customer_name=r.customer_name,
            party_size=r.party_size,
            reservation_date=r.reservation_date,
            reservation_time=r.reservation_time,
            status=r.status,
            whatsapp_sent=r.whatsapp_sent,
            whatsapp_consent=r.whatsapp_consent,
            notes=r.notes,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )
        for r in reservations
    ]


@router.get("/{reservation_id}", response_model=ReservationResponse)
async def get_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_session),
) -> ReservationResponse:
    """Get a reservation by ID."""
    result = await session.execute(
        select(Reservation).where(Reservation.id == reservation_id)  # type: ignore[arg-type]
    )
    reservation = result.scalar_one_or_none()

    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    return ReservationResponse(
        id=reservation.id,
        business_id=reservation.business_id,
        call_log_id=reservation.call_log_id,
        customer_name=reservation.customer_name,
        party_size=reservation.party_size,
        reservation_date=reservation.reservation_date,
        reservation_time=reservation.reservation_time,
        status=reservation.status,
        whatsapp_sent=reservation.whatsapp_sent,
        whatsapp_consent=reservation.whatsapp_consent,
        notes=reservation.notes,
        created_at=reservation.created_at.isoformat(),
        updated_at=reservation.updated_at.isoformat(),
    )


@router.post("", response_model=ReservationResponse, status_code=201)
async def create_reservation(
    data: ReservationCreate,
    session: AsyncSession = Depends(get_session),
) -> ReservationResponse:
    """Create a new reservation."""
    now = datetime.now(UTC)
    reservation = Reservation(
        id=str(uuid4()),
        business_id=data.business_id,
        call_log_id=data.call_log_id,
        customer_name=data.customer_name,
        customer_phone_encrypted=data.customer_phone_encrypted,
        party_size=data.party_size,
        reservation_date=data.reservation_date.isoformat(),
        reservation_time=data.reservation_time,
        status=ReservationStatus.confirmed,
        whatsapp_sent=False,
        whatsapp_consent=data.whatsapp_consent,
        notes=data.notes,
        created_at=now,
        updated_at=now,
    )

    session.add(reservation)
    await session.flush()
    await session.refresh(reservation)

    return ReservationResponse(
        id=reservation.id,
        business_id=reservation.business_id,
        call_log_id=reservation.call_log_id,
        customer_name=reservation.customer_name,
        party_size=reservation.party_size,
        reservation_date=reservation.reservation_date,
        reservation_time=reservation.reservation_time,
        status=reservation.status,
        whatsapp_sent=reservation.whatsapp_sent,
        whatsapp_consent=reservation.whatsapp_consent,
        notes=reservation.notes,
        created_at=reservation.created_at.isoformat(),
        updated_at=reservation.updated_at.isoformat(),
    )


@router.patch("/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: str,
    data: ReservationUpdate,
    session: AsyncSession = Depends(get_session),
) -> ReservationResponse:
    """Update a reservation (partial update)."""
    result = await session.execute(
        select(Reservation).where(Reservation.id == reservation_id)  # type: ignore[arg-type]
    )
    reservation = result.scalar_one_or_none()

    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Apply updates only for provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "reservation_date" and value is not None:
            value = value.isoformat()
        setattr(reservation, field, value)

    reservation.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(reservation)

    return ReservationResponse(
        id=reservation.id,
        business_id=reservation.business_id,
        call_log_id=reservation.call_log_id,
        customer_name=reservation.customer_name,
        party_size=reservation.party_size,
        reservation_date=reservation.reservation_date,
        reservation_time=reservation.reservation_time,
        status=reservation.status,
        whatsapp_sent=reservation.whatsapp_sent,
        whatsapp_consent=reservation.whatsapp_consent,
        notes=reservation.notes,
        created_at=reservation.created_at.isoformat(),
        updated_at=reservation.updated_at.isoformat(),
    )


@router.delete("/{reservation_id}", status_code=204)
async def delete_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a reservation."""
    result = await session.execute(
        select(Reservation).where(Reservation.id == reservation_id)  # type: ignore[arg-type]
    )
    reservation = result.scalar_one_or_none()

    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    await session.delete(reservation)
