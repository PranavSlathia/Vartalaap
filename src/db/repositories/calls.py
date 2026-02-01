"""Call log and followup repositories."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from src.db.models import (
    AuditLog,
    CallerPreferences,
    CallLog,
    CallOutcome,
    ConsentType,
    DetectedLanguage,
    FollowupStatus,
    WhatsappFollowup,
)


def _date_range(start_date: date | None, end_date: date | None) -> tuple[datetime, datetime] | None:
    if not start_date or not end_date:
        return None
    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=UTC)
    end_dt = datetime.combine(end_date, time.max).replace(tzinfo=UTC)
    return start_dt, end_dt


class CallLogRepository:
    """Sync repository for admin UI."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, call_id: str) -> CallLog | None:
        return self.session.get(CallLog, call_id)

    def list(
        self,
        *,
        business_id: str | None = None,
        outcome: CallOutcome | None = None,
        language: DetectedLanguage | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CallLog]:
        query = select(CallLog)
        if business_id:
            query = query.where(CallLog.business_id == business_id)  # type: ignore[arg-type]
        if outcome:
            query = query.where(CallLog.outcome == outcome)  # type: ignore[arg-type]
        if language:
            query = query.where(CallLog.detected_language == language)  # type: ignore[arg-type]

        range_dt = _date_range(start_date, end_date)
        if range_dt:
            query = query.where(
                CallLog.created_at >= range_dt[0],  # type: ignore[arg-type]
                CallLog.created_at <= range_dt[1],  # type: ignore[arg-type]
            )

        query = query.order_by(desc(CallLog.created_at)).offset(offset).limit(limit)  # type: ignore[arg-type]
        result = self.session.execute(query)
        return list(result.scalars().all())

    def upsert_call_log(self, call_id: str, **fields) -> CallLog:
        call_log = self.get_by_id(call_id)
        if not call_log:
            call_log = CallLog(id=call_id, business_id=fields.pop("business_id", "default"))
        for key, value in fields.items():
            setattr(call_log, key, value)
        self.session.add(call_log)
        return call_log


class AsyncCallLogRepository:
    """Async repository for workers and API."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, call_id: str) -> CallLog | None:
        return await self.session.get(CallLog, call_id)

    async def upsert_call_log(self, call_id: str, **fields) -> CallLog:
        call_log = await self.get_by_id(call_id)
        if not call_log:
            call_log = CallLog(id=call_id, business_id=fields.pop("business_id", "default"))
        for key, value in fields.items():
            setattr(call_log, key, value)
        self.session.add(call_log)
        return call_log

    async def record_preferences(
        self,
        caller_id_hash: str,
        *,
        transcript_opt_out: bool | None = None,
        whatsapp_opt_out: bool | None = None,
    ) -> CallerPreferences:
        prefs = await self.session.get(CallerPreferences, caller_id_hash)
        now = datetime.now(UTC)
        if not prefs:
            prefs = CallerPreferences(
                caller_id_hash=caller_id_hash,
                first_seen=now,
                last_seen=now,
            )
        if transcript_opt_out is not None:
            prefs.transcript_opt_out = transcript_opt_out
        if whatsapp_opt_out is not None:
            prefs.whatsapp_opt_out = whatsapp_opt_out
        prefs.last_seen = now
        prefs.updated_at = now
        self.session.add(prefs)
        return prefs

    async def create_followup(
        self,
        *,
        business_id: str,
        call_log_id: str | None,
        customer_phone_encrypted: str,
        summary: str | None,
        reason: str | None,
        whatsapp_consent: bool = True,
    ) -> WhatsappFollowup:
        followup = WhatsappFollowup(
            business_id=business_id,
            call_log_id=call_log_id,
            customer_phone_encrypted=customer_phone_encrypted,
            summary=summary,
            reason=reason,
            whatsapp_consent=whatsapp_consent,
            status=FollowupStatus.pending,
        )
        self.session.add(followup)
        return followup

    async def record_audit(
        self,
        *,
        action: str,
        admin_user: str | None,
        details: str | None,
        ip_address: str | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            action=action,
            admin_user=admin_user,
            details=details,
            ip_address=ip_address,
        )
        self.session.add(audit)
        return audit


def parse_outcome(value: str | None) -> CallOutcome | None:
    if not value:
        return None
    try:
        return CallOutcome(value)
    except ValueError:
        return None


def parse_language(value: str | None) -> DetectedLanguage | None:
    if not value:
        return None
    try:
        return DetectedLanguage(value)
    except ValueError:
        return None


def parse_consent(value: str | None) -> ConsentType | None:
    if not value:
        return None
    try:
        return ConsentType(value)
    except ValueError:
        return None
