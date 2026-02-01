"""Background tasks for Vartalaap (arq worker)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from arq import cron
from sqlalchemy import delete, select, update

from src.config import get_settings
from src.db.models import (
    CallLog,
    FollowupStatus,
    Reservation,
    WhatsappFollowup,
)
from src.db.repositories.calls import (
    AsyncCallLogRepository,
    parse_consent,
    parse_language,
    parse_outcome,
)
from src.db.session import get_session_context
from src.logging_config import get_logger
from src.security.crypto import decrypt_phone
from src.services.whatsapp import WhatsAppClient, WhatsAppSendError

logger: Any = get_logger(__name__)

RETENTION_DAYS = 90
FOLLOWUP_EXPIRY_HOURS = 48
FOLLOWUP_BATCH_SIZE = 50


def _load_business_name(business_id: str) -> str:
    path = Path(f"config/business/{business_id}.yaml")
    if not path.exists():
        return "our team"
    try:
        with path.open() as f:
            data = json.loads(json.dumps(yaml.safe_load(f) or {}))
        return str(data.get("business", {}).get("name", "our team"))
    except Exception:
        return "our team"


def _build_followup_message(business_name: str, summary: str | None) -> str:
    if summary:
        return f"Thanks for calling {business_name}. {summary}"
    return f"Thanks for calling {business_name}. We'll get back to you shortly on WhatsApp."


async def send_whatsapp_followup(ctx, followup_id: str) -> None:
    """Send a single WhatsApp followup by ID."""
    settings = get_settings()
    if not settings.whatsapp_webhook_url:
        logger.error("WhatsApp webhook not configured; cannot send followup")
        return

    async with get_session_context() as session:
        followup = await session.get(WhatsappFollowup, followup_id)
        if not followup:
            logger.warning(f"Followup not found: {followup_id}")
            return

        if not followup.whatsapp_consent:
            followup.status = FollowupStatus.expired
            logger.info(f"Followup expired (no consent): {followup_id}")
            return

        if followup.status != FollowupStatus.pending:
            return

        now = datetime.now(UTC)
        age = now - followup.created_at if followup.created_at else timedelta()
        if followup.created_at and age > timedelta(hours=FOLLOWUP_EXPIRY_HOURS):
            followup.status = FollowupStatus.expired
            logger.info(f"Followup expired (age): {followup_id}")
            return

        try:
            phone = decrypt_phone(followup.customer_phone_encrypted)
        except Exception:
            followup.status = FollowupStatus.expired
            logger.error(f"Failed to decrypt followup phone: {followup_id}")
            return

        business_name = _load_business_name(followup.business_id)
        message = _build_followup_message(business_name, followup.summary)

        token = (
            settings.whatsapp_webhook_token.get_secret_value()
            if settings.whatsapp_webhook_token
            else None
        )

        async with WhatsAppClient(settings.whatsapp_webhook_url, token) as client:
            try:
                await client.send_message(
                    phone=phone,
                    message=message,
                    metadata={
                        "followup_id": followup.id,
                        "business_id": followup.business_id,
                        "reason": followup.reason.value if followup.reason else None,
                    },
                )
            except WhatsAppSendError as e:
                logger.error(f"WhatsApp send failed for {followup_id}: {e}")
                return

        followup.status = FollowupStatus.sent
        followup.sent_at = datetime.now(UTC)
        logger.info(f"WhatsApp followup sent: {followup_id}")


async def process_transcript(
    ctx,
    call_log_id: str,
    transcript: str,
    extracted_info: dict[str, Any] | None = None,
    *,
    outcome: str | None = None,
    consent_type: str | None = None,
    detected_language: str | None = None,
    duration_seconds: int | None = None,
    caller_id_hash: str | None = None,
    business_id: str = "himalayan_kitchen",
) -> None:
    """Persist transcript and extracted info to call_logs."""
    async with get_session_context() as session:
        repo = AsyncCallLogRepository(session)
        now = datetime.now(UTC)

        call_log = await repo.upsert_call_log(
            call_log_id,
            business_id=business_id,
            transcript=transcript,
            extracted_info=json.dumps(extracted_info or {}),
            outcome=parse_outcome(outcome),
            consent_type=parse_consent(consent_type),
            detected_language=parse_language(detected_language),
            duration_seconds=duration_seconds,
            caller_id_hash=caller_id_hash,
            call_end=now,
        )

        # Optional followup creation from extracted_info
        followup = (extracted_info or {}).get("whatsapp_followup")
        if followup and followup.get("customer_phone_encrypted"):
            await repo.create_followup(
                business_id=business_id,
                call_log_id=call_log.id,
                customer_phone_encrypted=followup["customer_phone_encrypted"],
                summary=followup.get("summary"),
                reason=followup.get("reason"),
                whatsapp_consent=bool(followup.get("whatsapp_consent", True)),
            )

        if caller_id_hash and (extracted_info or {}).get("transcript_opt_out") is True:
            await repo.record_preferences(caller_id_hash, transcript_opt_out=True)


async def purge_old_records(ctx) -> None:
    """Purge or scrub data older than retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)

    async with get_session_context() as session:
        # Scrub transcripts and extracted info from old call logs
        await session.execute(
            update(CallLog)
            .where(CallLog.created_at < cutoff)  # type: ignore[arg-type]
            .values(transcript=None, extracted_info=None)
        )

        # Scrub encrypted phones from old reservations
        await session.execute(
            update(Reservation)
            .where(Reservation.created_at < cutoff)  # type: ignore[arg-type]
            .values(customer_phone_encrypted=None)
        )

        # Delete expired followups
        await session.execute(
            delete(WhatsappFollowup).where(
                WhatsappFollowup.created_at < cutoff  # type: ignore[arg-type]
            )
        )

    logger.info("Purge job completed")


async def retry_failed_whatsapp(ctx) -> None:
    """Retry pending WhatsApp followups."""
    settings = get_settings()
    if not settings.whatsapp_webhook_url:
        logger.warning("WhatsApp webhook not configured; skipping retry job")
        return

    token = (
        settings.whatsapp_webhook_token.get_secret_value()
        if settings.whatsapp_webhook_token
        else None
    )

    now = datetime.now(UTC)
    expiry_cutoff = now - timedelta(hours=FOLLOWUP_EXPIRY_HOURS)

    async with get_session_context() as session:
        result = await session.execute(
            select(WhatsappFollowup)
            .where(
                WhatsappFollowup.status == FollowupStatus.pending,  # type: ignore[arg-type]
                WhatsappFollowup.whatsapp_consent.is_(True),  # type: ignore[attr-defined]
                WhatsappFollowup.created_at >= expiry_cutoff,  # type: ignore[arg-type]
            )
            .limit(FOLLOWUP_BATCH_SIZE)
        )
        followups = list(result.scalars().all())

        if not followups:
            return

        async with WhatsAppClient(settings.whatsapp_webhook_url, token) as client:
            for followup in followups:
                try:
                    phone = decrypt_phone(followup.customer_phone_encrypted)
                except Exception:
                    followup.status = FollowupStatus.expired
                    continue

                business_name = _load_business_name(followup.business_id)
                message = _build_followup_message(business_name, followup.summary)

                try:
                    await client.send_message(
                        phone=phone,
                        message=message,
                        metadata={
                            "followup_id": followup.id,
                            "business_id": followup.business_id,
                            "reason": followup.reason.value if followup.reason else None,
                        },
                    )
                except WhatsAppSendError:
                    continue

                followup.status = FollowupStatus.sent
                followup.sent_at = datetime.now(UTC)


class WorkerSettings:
    functions = [send_whatsapp_followup, process_transcript]
    cron_jobs = [
        cron(purge_old_records, hour=3, minute=0),
        cron(retry_failed_whatsapp, minute=0),
    ]
