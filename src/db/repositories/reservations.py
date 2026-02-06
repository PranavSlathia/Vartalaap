"""Reservation repository with business-rule helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from src.db.models import Business, Reservation, ReservationStatus


def _load_business_config(business_id: str) -> dict:
    path = Path(f"config/business/{business_id}.yaml")
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_reservation_rules(raw: dict[str, Any]) -> dict[str, int]:
    """Normalize legacy and canonical rule keys to one runtime schema."""
    normalized = dict(raw)

    # Legacy keys accepted for backward compatibility.
    if "advance_days" not in normalized and "max_advance_booking_days" in normalized:
        normalized["advance_days"] = normalized["max_advance_booking_days"]
    if "slot_duration_minutes" not in normalized and "dining_window_mins" in normalized:
        normalized["slot_duration_minutes"] = normalized["dining_window_mins"]
    if (
        "buffer_between_bookings_minutes" not in normalized
        and "buffer_between_bookings_mins" in normalized
    ):
        normalized["buffer_between_bookings_minutes"] = normalized["buffer_between_bookings_mins"]
    if (
        "min_advance_booking_minutes" not in normalized
        and "min_advance_booking_mins" in normalized
    ):
        normalized["min_advance_booking_minutes"] = normalized["min_advance_booking_mins"]

    return {
        "min_party_size": int(normalized.get("min_party_size", 1)),
        "max_party_size": int(normalized.get("max_party_size", 10)),
        "max_phone_party_size": int(
            normalized.get("max_phone_party_size", normalized.get("max_party_size", 10))
        ),
        "total_seats": int(normalized.get("total_seats", 40)),
        "advance_days": int(normalized.get("advance_days", 30)),
        "slot_duration_minutes": int(normalized.get("slot_duration_minutes", 90)),
        "buffer_between_bookings_minutes": int(
            normalized.get("buffer_between_bookings_minutes", 15)
        ),
        "min_advance_booking_minutes": int(normalized.get("min_advance_booking_minutes", 30)),
    }


def _load_runtime_config_from_yaml(business_id: str) -> tuple[dict[str, Any], dict[str, int]]:
    config = _load_business_config(business_id)
    business = config.get("business", {}) if isinstance(config.get("business"), dict) else {}
    rules = config.get("reservation_rules", {})
    if not isinstance(rules, dict):
        rules = {}
    return business, _normalize_reservation_rules(rules)


def _load_runtime_config_from_db(business: Business) -> tuple[dict[str, Any], dict[str, int]]:
    business_config = {
        "timezone": business.timezone or "Asia/Kolkata",
        "operating_hours": _parse_json_object(business.operating_hours_json),
    }
    rules = _normalize_reservation_rules(_parse_json_object(business.reservation_rules_json))
    return business_config, rules


def _get_business_from_sync_db(session: Session, business_id: str) -> Business | None:
    result = session.execute(select(Business).where(Business.id == business_id))  # type: ignore[arg-type]
    return result.scalar_one_or_none()


async def _get_business_from_async_db(
    session: AsyncSession, business_id: str
) -> Business | None:
    result = await session.execute(select(Business).where(Business.id == business_id))  # type: ignore[arg-type]
    return result.scalar_one_or_none()


def _parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def _combine(d: date, t: time, tz: ZoneInfo | None = None) -> datetime:
    dt = datetime.combine(d, t)
    return dt.replace(tzinfo=tz) if tz else dt


@dataclass(slots=True)
class AvailabilityResult:
    available: bool
    reason: str | None = None
    used_seats: int | None = None
    total_seats: int | None = None


class ReservationRepository:
    """Sync repository for admin UI."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, reservation_id: str) -> Reservation | None:
        return self.session.get(Reservation, reservation_id)

    def list_by_date_range(
        self,
        business_id: str,
        start: date,
        end: date,
        status: ReservationStatus | None = None,
    ) -> list[Reservation]:
        query = select(Reservation).where(
            Reservation.business_id == business_id  # type: ignore[arg-type]
        )
        query = query.where(
            Reservation.reservation_date >= start.isoformat()  # type: ignore[arg-type]
        )
        query = query.where(
            Reservation.reservation_date <= end.isoformat()  # type: ignore[arg-type]
        )
        if status:
            query = query.where(Reservation.status == status)  # type: ignore[arg-type]

        query = query.order_by(desc(Reservation.reservation_date), Reservation.reservation_time)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def update_status(self, reservation_id: str, status: ReservationStatus) -> Reservation | None:
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        reservation.status = status
        reservation.updated_at = datetime.now(UTC)
        self.session.add(reservation)
        return reservation

    def check_availability(
        self,
        business_id: str,
        reservation_date: date,
        reservation_time: str,
        party_size: int,
    ) -> AvailabilityResult:
        business = _get_business_from_sync_db(self.session, business_id)
        if business:
            business_config, rules = _load_runtime_config_from_db(business)
        else:
            business_config, rules = _load_runtime_config_from_yaml(business_id)

        return _check_availability_common(
            business_id=business_id,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            party_size=party_size,
            reservations=self._load_reservations_for_date(business_id, reservation_date),
            business_config=business_config,
            rules=rules,
        )

    def _load_reservations_for_date(
        self, business_id: str, reservation_date: date
    ) -> list[Reservation]:
        query = select(Reservation).where(
            Reservation.business_id == business_id,  # type: ignore[arg-type]
            Reservation.reservation_date == reservation_date.isoformat(),  # type: ignore[arg-type]
            Reservation.status == ReservationStatus.confirmed,  # type: ignore[arg-type]
        )
        result = self.session.execute(query)
        return list(result.scalars().all())


class AsyncReservationRepository:
    """Async repository for workers and API."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, reservation_id: str) -> Reservation | None:
        return await self.session.get(Reservation, reservation_id)

    async def list_by_date_range(
        self,
        business_id: str,
        start: date,
        end: date,
        status: ReservationStatus | None = None,
    ) -> list[Reservation]:
        query = select(Reservation).where(
            Reservation.business_id == business_id  # type: ignore[arg-type]
        )
        query = query.where(
            Reservation.reservation_date >= start.isoformat()  # type: ignore[arg-type]
        )
        query = query.where(
            Reservation.reservation_date <= end.isoformat()  # type: ignore[arg-type]
        )
        if status:
            query = query.where(Reservation.status == status)  # type: ignore[arg-type]
        query = query.order_by(desc(Reservation.reservation_date), Reservation.reservation_time)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def check_availability(
        self,
        business_id: str,
        reservation_date: date,
        reservation_time: str,
        party_size: int,
    ) -> AvailabilityResult:
        reservations = await self._load_reservations_for_date(business_id, reservation_date)
        business = await _get_business_from_async_db(self.session, business_id)
        if business:
            business_config, rules = _load_runtime_config_from_db(business)
        else:
            business_config, rules = _load_runtime_config_from_yaml(business_id)

        return _check_availability_common(
            business_id=business_id,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            party_size=party_size,
            reservations=reservations,
            business_config=business_config,
            rules=rules,
        )

    async def _load_reservations_for_date(
        self, business_id: str, reservation_date: date
    ) -> list[Reservation]:
        query = select(Reservation).where(
            Reservation.business_id == business_id,  # type: ignore[arg-type]
            Reservation.reservation_date == reservation_date.isoformat(),  # type: ignore[arg-type]
            Reservation.status == ReservationStatus.confirmed,  # type: ignore[arg-type]
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


def _check_availability_common(
    *,
    business_id: str,
    reservation_date: date,
    reservation_time: str,
    party_size: int,
    reservations: list[Reservation],
    business_config: dict[str, Any],
    rules: dict[str, int],
) -> AvailabilityResult:
    min_party = int(rules.get("min_party_size", 1))
    max_party = int(rules.get("max_phone_party_size", rules.get("max_party_size", 10)))
    total_seats = int(rules.get("total_seats", 40))
    dining_window = int(rules.get("slot_duration_minutes", 90))
    buffer_mins = int(rules.get("buffer_between_bookings_minutes", 15))
    min_advance = int(rules.get("min_advance_booking_minutes", 30))
    max_advance_days = int(rules.get("advance_days", 30))

    if party_size < min_party:
        return AvailabilityResult(False, reason="party_size_too_small")
    if party_size > max_party:
        return AvailabilityResult(False, reason="party_size_too_large")

    tz_name = business_config.get("timezone", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    now = datetime.now(tz)
    requested_time = _parse_time(reservation_time)
    requested_dt = _combine(reservation_date, requested_time, tz)

    if requested_dt < (now + timedelta(minutes=min_advance)):
        return AvailabilityResult(False, reason="too_soon")
    if requested_dt > (now + timedelta(days=max_advance_days)):
        return AvailabilityResult(False, reason="too_far")

    # Operating-hours check (supports legacy "09:00-22:00" and structured objects).
    day_key = reservation_date.strftime("%A").lower()
    hours = business_config.get("operating_hours", {}).get(day_key, "closed")
    if not hours or hours == "closed":
        return AvailabilityResult(False, reason="closed")

    parsed_hours = _parse_day_hours(hours)
    if not parsed_hours:
        return AvailabilityResult(False, reason="invalid_hours")
    start_time, end_time, overnight = parsed_hours

    if overnight:
        in_hours = requested_time >= start_time or requested_time <= end_time
    else:
        in_hours = start_time <= requested_time <= end_time
    if not in_hours:
        return AvailabilityResult(False, reason="outside_hours")

    # Capacity check within dining window + buffer
    window_start = requested_dt - timedelta(minutes=buffer_mins)
    window_end = requested_dt + timedelta(minutes=dining_window + buffer_mins)

    used_seats = 0
    for reservation in reservations:
        try:
            existing_date = date.fromisoformat(reservation.reservation_date)
            existing_time = _parse_time(reservation.reservation_time)
        except ValueError:
            continue
        existing_start = _combine(existing_date, existing_time, tz)
        existing_end = existing_start + timedelta(minutes=dining_window)

        if existing_start <= window_end and existing_end >= window_start:
            used_seats += reservation.party_size

    if used_seats + party_size > total_seats:
        return AvailabilityResult(
            False,
            reason="capacity_full",
            used_seats=used_seats,
            total_seats=total_seats,
        )

    return AvailabilityResult(
        True,
        used_seats=used_seats,
        total_seats=total_seats,
    )


def _parse_day_hours(day_hours: Any) -> tuple[time, time, bool] | None:
    """Parse day schedule from string or object representation."""
    if isinstance(day_hours, str):
        if day_hours.lower() == "closed":
            return None
        try:
            start_str, end_str = day_hours.split("-", 1)
            return _parse_time(start_str.strip()), _parse_time(end_str.strip()), False
        except ValueError:
            return None

    if isinstance(day_hours, dict):
        open_time_raw = day_hours.get("open")
        close_time_raw = day_hours.get("close")
        if not open_time_raw or not close_time_raw:
            return None
        try:
            return (
                _parse_time(str(open_time_raw)),
                _parse_time(str(close_time_raw)),
                bool(day_hours.get("overnight", False)),
            )
        except ValueError:
            return None

    return None
