"""CRUD endpoints for call logs.

Read-only API for viewing call history. Calls are created by the voice pipeline.
Security: All endpoints require JWT authentication and tenant authorization.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequireBusinessAccess
from src.db.models import (
    CallCategory,
    CallLog,
    CallOutcome,
    ConsentType,
    DetectedLanguage,
    RatingMethod,
)
from src.db.session import get_session

router = APIRouter(prefix="/call-logs", tags=["Call Logs"])


# =============================================================================
# Response Schemas
# =============================================================================


class CallLogResponse(BaseModel):
    """Response schema for call logs."""

    id: str
    business_id: str
    caller_id_hash: str | None
    call_start: str
    call_end: str | None
    duration_seconds: int | None
    detected_language: DetectedLanguage | None
    transcript: str | None
    extracted_info: str | None
    outcome: CallOutcome | None
    consent_type: ConsentType | None
    created_at: str

    # Performance metrics
    stt_latency_p50_ms: float | None = None
    llm_latency_p50_ms: float | None = None
    tts_latency_p50_ms: float | None = None
    barge_in_count: int = 0
    total_turns: int = 0

    # Rating and feedback
    call_rating: int | None = None
    caller_feedback: str | None = None
    rating_method: RatingMethod | None = None

    # Summary
    call_summary: str | None = None
    call_category: CallCategory | None = None

    model_config = {"from_attributes": True}


class CallLogSummary(BaseModel):
    """Summary stats for call logs."""

    total_calls: int
    total_duration_seconds: int
    avg_duration_seconds: float
    calls_by_outcome: dict[str, int]
    calls_by_language: dict[str, int]


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("", response_model=list[CallLogResponse])
async def list_call_logs(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Required for tenant isolation"),
    outcome: CallOutcome | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[CallLogResponse]:
    """List call logs with optional filters.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    # Verify tenant access matches requested business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )
    query = select(CallLog)

    # Required: always scope by business_id
    query = query.where(CallLog.business_id == business_id)  # type: ignore[arg-type]
    if outcome:
        query = query.where(CallLog.outcome == outcome)  # type: ignore[arg-type]
    if date_from:
        query = query.where(CallLog.call_start >= date_from.isoformat())  # type: ignore[arg-type]
    if date_to:
        query = query.where(CallLog.call_start <= f"{date_to.isoformat()}T23:59:59")  # type: ignore[arg-type]

    query = query.offset(skip).limit(limit).order_by(desc(CallLog.call_start))

    result = await session.execute(query)
    logs = result.scalars().all()

    return [
        CallLogResponse(
            id=log.id,
            business_id=log.business_id,
            caller_id_hash=log.caller_id_hash,
            call_start=log.call_start.isoformat(),
            call_end=log.call_end.isoformat() if log.call_end else None,
            duration_seconds=log.duration_seconds,
            detected_language=log.detected_language,
            transcript=log.transcript,
            extracted_info=log.extracted_info,
            outcome=log.outcome,
            consent_type=log.consent_type,
            created_at=log.created_at.isoformat(),
            stt_latency_p50_ms=log.stt_latency_p50_ms,
            llm_latency_p50_ms=log.llm_latency_p50_ms,
            tts_latency_p50_ms=log.tts_latency_p50_ms,
            barge_in_count=log.barge_in_count,
            total_turns=log.total_turns,
            call_rating=log.call_rating,
            caller_feedback=log.caller_feedback,
            rating_method=log.rating_method,
            call_summary=log.call_summary,
            call_category=log.call_category,
        )
        for log in logs
    ]


@router.get("/summary", response_model=CallLogSummary)
async def get_call_log_summary(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Required for tenant isolation"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> CallLogSummary:
    """Get summary statistics for call logs.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    # Verify tenant access matches requested business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )
    base_query = select(CallLog)

    # Required: always scope by business_id
    base_query = base_query.where(CallLog.business_id == business_id)  # type: ignore[arg-type]
    if date_from:
        base_query = base_query.where(CallLog.call_start >= date_from.isoformat())  # type: ignore[arg-type]
    if date_to:
        base_query = base_query.where(CallLog.call_start <= f"{date_to.isoformat()}T23:59:59")  # type: ignore[arg-type]

    # Get all matching logs
    result = await session.execute(base_query)
    logs = result.scalars().all()

    # Calculate stats
    total_calls = len(logs)
    total_duration = sum(log.duration_seconds or 0 for log in logs)
    avg_duration = total_duration / total_calls if total_calls > 0 else 0

    # Count by outcome
    calls_by_outcome: dict[str, int] = {}
    for log in logs:
        outcome_key = log.outcome.value if log.outcome else "unknown"
        calls_by_outcome[outcome_key] = calls_by_outcome.get(outcome_key, 0) + 1

    # Count by language
    calls_by_language: dict[str, int] = {}
    for log in logs:
        lang_key = log.detected_language.value if log.detected_language else "unknown"
        calls_by_language[lang_key] = calls_by_language.get(lang_key, 0) + 1

    return CallLogSummary(
        total_calls=total_calls,
        total_duration_seconds=total_duration,
        avg_duration_seconds=round(avg_duration, 1),
        calls_by_outcome=calls_by_outcome,
        calls_by_language=calls_by_language,
    )


@router.get("/{call_log_id}", response_model=CallLogResponse)
async def get_call_log(
    call_log_id: str,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> CallLogResponse:
    """Get a call log by ID.

    Security: Requires JWT authentication. Call log must belong to authorized tenant.
    """
    result = await session.execute(
        select(CallLog).where(CallLog.id == call_log_id)  # type: ignore[arg-type]
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Call log not found")

    # Verify tenant access
    if log.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this call log",
        )

    return CallLogResponse(
        id=log.id,
        business_id=log.business_id,
        caller_id_hash=log.caller_id_hash,
        call_start=log.call_start.isoformat(),
        call_end=log.call_end.isoformat() if log.call_end else None,
        duration_seconds=log.duration_seconds,
        detected_language=log.detected_language,
        transcript=log.transcript,
        extracted_info=log.extracted_info,
        outcome=log.outcome,
        consent_type=log.consent_type,
        created_at=log.created_at.isoformat(),
        stt_latency_p50_ms=log.stt_latency_p50_ms,
        llm_latency_p50_ms=log.llm_latency_p50_ms,
        tts_latency_p50_ms=log.tts_latency_p50_ms,
        barge_in_count=log.barge_in_count,
        total_turns=log.total_turns,
        call_rating=log.call_rating,
        caller_feedback=log.caller_feedback,
        rating_method=log.rating_method,
        call_summary=log.call_summary,
        call_category=log.call_category,
    )


@router.patch("/{call_log_id}/rating", response_model=CallLogResponse)
async def rate_call(
    call_log_id: str,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    rating: int = Query(..., ge=1, le=5, description="Rating from 1-5 stars"),
    feedback: str | None = Query(None, max_length=500, description="Optional feedback text"),
    method: RatingMethod = Query(RatingMethod.admin, description="How rating was collected"),
) -> CallLogResponse:
    """Rate a completed call.

    Allows admin to add a rating and optional feedback for call quality tracking.

    Security: Requires JWT authentication. Call log must belong to authorized tenant.
    """
    result = await session.execute(
        select(CallLog).where(CallLog.id == call_log_id)  # type: ignore[arg-type]
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Call log not found")

    # Verify tenant access
    if log.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this call log",
        )

    # Update rating fields
    log.call_rating = rating
    log.caller_feedback = feedback
    log.rating_method = method

    await session.commit()
    await session.refresh(log)

    return CallLogResponse(
        id=log.id,
        business_id=log.business_id,
        caller_id_hash=log.caller_id_hash,
        call_start=log.call_start.isoformat(),
        call_end=log.call_end.isoformat() if log.call_end else None,
        duration_seconds=log.duration_seconds,
        detected_language=log.detected_language,
        transcript=log.transcript,
        extracted_info=log.extracted_info,
        outcome=log.outcome,
        consent_type=log.consent_type,
        created_at=log.created_at.isoformat(),
        stt_latency_p50_ms=log.stt_latency_p50_ms,
        llm_latency_p50_ms=log.llm_latency_p50_ms,
        tts_latency_p50_ms=log.tts_latency_p50_ms,
        barge_in_count=log.barge_in_count,
        total_turns=log.total_turns,
        call_rating=log.call_rating,
        caller_feedback=log.caller_feedback,
        rating_method=log.rating_method,
        call_summary=log.call_summary,
        call_category=log.call_category,
    )
