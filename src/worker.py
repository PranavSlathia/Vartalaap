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
    CallCategory,
    CallLog,
    FollowupStatus,
    ImprovementSuggestion,
    Reservation,
    TranscriptReview,
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


async def generate_call_summary(ctx, call_id: str) -> None:
    """Generate summary and category from call transcript using LLM.

    This runs as a background job after call hangup to avoid blocking.
    """
    from src.services.llm.groq import GroqService

    async with get_session_context() as session:
        call_log = await session.get(CallLog, call_id)
        if not call_log:
            logger.warning(f"Call log not found for summary: {call_id}")
            return

        # Skip if no transcript or already summarized
        if not call_log.transcript:
            logger.debug(f"No transcript for call {call_id}, skipping summary")
            return

        if call_log.call_summary:
            logger.debug(f"Call {call_id} already has summary, skipping")
            return

        try:
            llm = GroqService()

            # Build prompt for summary extraction
            system_prompt = """You are an expert at summarizing customer service calls.
Analyze the transcript and provide:
1. A 1-2 sentence summary focusing on the caller's intent and outcome
2. A category for the call

Respond in JSON format:
{
    "summary": "Brief summary here",
    "category": "booking|inquiry|complaint|spam|other"
}

Categories:
- booking: Caller wanted to make/modify/cancel a reservation
- inquiry: Caller asked about menu, hours, location, prices, etc.
- complaint: Caller reported an issue or expressed dissatisfaction
- spam: Unsolicited call, wrong number, or irrelevant
- other: Doesn't fit other categories"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Transcript:\n{call_log.transcript}"},
            ]

            result = await llm.extract_json(
                messages=messages,
                max_tokens=150,
                temperature=0.0,
            )

            # Update call log with summary
            summary = result.get("summary", "")[:500]  # Enforce max length
            category_str = result.get("category", "other")

            # Parse category enum
            try:
                category = CallCategory(category_str)
            except ValueError:
                category = CallCategory.other

            call_log.call_summary = summary
            call_log.call_category = category

            await session.commit()
            logger.info(f"Generated summary for call {call_id}: {category.value}")

            await llm.close()

        except Exception as e:
            logger.error(f"Failed to generate summary for {call_id}: {e}")
            # Don't raise - this is a non-critical background job


async def analyze_transcript_quality(ctx, call_id: str) -> None:
    """Analyze call transcript quality using AI agent crew.

    Runs CrewAI agents to:
    1. Review the transcript for quality issues
    2. Classify issues by category
    3. Generate actionable improvement suggestions

    Results are stored in transcript_reviews and improvement_suggestions tables.
    This is internal QA tooling, not caller-facing.
    """
    from uuid import uuid4

    from src.services.analysis.transcript_crew import TranscriptAnalysisCrew

    async with get_session_context() as session:
        call_log = await session.get(CallLog, call_id)
        if not call_log:
            logger.warning(f"Call log not found for analysis: {call_id}")
            return

        # Skip if no transcript
        if not call_log.transcript:
            logger.debug(f"No transcript for call {call_id}, skipping analysis")
            return

        # Check if already reviewed
        existing_review = await session.execute(
            select(TranscriptReview).where(
                TranscriptReview.call_log_id == call_id  # type: ignore[arg-type]
            )
        )
        if existing_review.scalar_one_or_none():
            logger.debug(f"Call {call_id} already reviewed, skipping")
            return

        try:
            # Build business context from call log
            business_context = f"Business: {call_log.business_id}"
            if call_log.call_category:
                business_context += f"\nCall Category: {call_log.call_category.value}"
            if call_log.call_summary:
                business_context += f"\nCall Summary: {call_log.call_summary}"

            # Run the analysis crew
            crew = TranscriptAnalysisCrew()
            result = await crew.analyze_transcript(
                transcript=call_log.transcript,
                business_context=business_context,
            )

            # Create transcript review record
            review = TranscriptReview(
                id=str(uuid4()),
                call_log_id=call_id,
                business_id=call_log.business_id,
                quality_score=result.quality_score,
                issues_json=result.to_issues_json() if result.issues else None,
                suggestions_json=result.to_suggestions_json() if result.suggestions else None,
                has_unanswered_query=result.has_unanswered_query,
                has_knowledge_gap=result.has_knowledge_gap,
                has_prompt_weakness=result.has_prompt_weakness,
                has_ux_issue=result.has_ux_issue,
                review_latency_ms=result.review_latency_ms,
                reviewed_at=datetime.now(UTC),
            )
            session.add(review)

            # Flush to detect unique constraint violation early
            try:
                await session.flush()
            except Exception as flush_err:
                # Unique constraint violation = another job already created review
                if "UNIQUE constraint" in str(flush_err) or "unique" in str(flush_err).lower():
                    logger.debug(f"Review already exists for {call_id} (concurrent job)")
                    await session.rollback()  # Clean up failed session state
                    return
                raise

            # Create improvement suggestion records
            for suggestion in result.suggestions:
                suggestion_record = ImprovementSuggestion(
                    id=str(uuid4()),
                    review_id=review.id,
                    business_id=call_log.business_id,
                    category=suggestion.category,
                    title=suggestion.title,
                    description=suggestion.description,
                    priority=suggestion.priority,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(suggestion_record)

            await session.commit()

            logger.info(
                f"Analyzed call {call_id}: score={result.quality_score}, "
                f"issues={len(result.issues)}, suggestions={len(result.suggestions)}"
            )

        except Exception as e:
            logger.error(f"Failed to analyze transcript for {call_id}: {e}")
            # Don't raise - this is a non-critical background job


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
    functions = [
        send_whatsapp_followup,
        process_transcript,
        generate_call_summary,
        analyze_transcript_quality,
    ]
    cron_jobs = [
        cron(purge_old_records, hour=3, minute=0),
        cron(retry_failed_whatsapp, minute=0),
    ]
