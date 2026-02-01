"""API endpoints for transcript reviews and improvement suggestions.

Internal QA system for reviewing call transcripts using AI agents.
Used by admins to identify issues and improve the voice bot.
"""

from datetime import UTC, datetime
from typing import Any

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequireAuth, RequireBusinessAccess
from src.config import get_settings
from src.db.models import (
    CallLog,
    ImprovementSuggestion,
    IssueCategory,
    SuggestionStatus,
    TranscriptReview,
)
from src.db.session import get_session
from src.logging_config import get_logger

logger: Any = get_logger(__name__)

router = APIRouter(prefix="/reviews", tags=["Transcript Reviews"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class TranscriptReviewResponse(BaseModel):
    """Response schema for transcript reviews."""

    id: str
    call_log_id: str
    business_id: str
    quality_score: int
    issues_json: str | None
    suggestions_json: str | None
    has_unanswered_query: bool
    has_knowledge_gap: bool
    has_prompt_weakness: bool
    has_ux_issue: bool
    agent_model: str
    review_latency_ms: float | None
    reviewed_at: str
    reviewed_by: str

    model_config = {"from_attributes": True}


class ImprovementSuggestionResponse(BaseModel):
    """Response schema for improvement suggestions."""

    id: str
    review_id: str
    business_id: str
    category: IssueCategory
    title: str
    description: str
    priority: int
    status: SuggestionStatus
    implemented_at: str | None
    implemented_by: str | None
    rejection_reason: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ReviewStatsResponse(BaseModel):
    """Statistics about transcript reviews."""

    total_reviews: int
    avg_quality_score: float
    reviews_with_issues: int
    knowledge_gaps: int
    prompt_weaknesses: int
    ux_issues: int
    pending_suggestions: int


class TriggerAnalysisRequest(BaseModel):
    """Request to trigger analysis for a call."""

    call_log_id: str = Field(..., description="ID of the call to analyze")


class TriggerAnalysisResponse(BaseModel):
    """Response after triggering analysis."""

    status: str
    message: str
    call_log_id: str


class UpdateSuggestionRequest(BaseModel):
    """Request to update suggestion status."""

    status: SuggestionStatus
    rejection_reason: str | None = Field(None, max_length=500)


# =============================================================================
# Review Endpoints
# =============================================================================


@router.get("", response_model=list[TranscriptReviewResponse])
async def list_reviews(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Business ID for tenant isolation"),
    min_score: int | None = Query(None, ge=1, le=5),
    max_score: int | None = Query(None, ge=1, le=5),
    has_issues: bool | None = Query(None, description="Filter to reviews with issues"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[TranscriptReviewResponse]:
    """List transcript reviews for a business.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    query = select(TranscriptReview).where(
        TranscriptReview.business_id == business_id  # type: ignore[arg-type]
    )

    if min_score is not None:
        query = query.where(TranscriptReview.quality_score >= min_score)  # type: ignore[arg-type]
    if max_score is not None:
        query = query.where(TranscriptReview.quality_score <= max_score)  # type: ignore[arg-type]
    if has_issues is True:
        query = query.where(
            (TranscriptReview.has_unanswered_query == True)  # type: ignore[arg-type]  # noqa: E712
            | (TranscriptReview.has_knowledge_gap == True)  # noqa: E712
            | (TranscriptReview.has_prompt_weakness == True)  # noqa: E712
            | (TranscriptReview.has_ux_issue == True)  # noqa: E712
        )

    query = query.order_by(desc(TranscriptReview.reviewed_at)).offset(skip).limit(limit)  # type: ignore[arg-type]

    result = await session.execute(query)
    reviews = result.scalars().all()

    return [
        TranscriptReviewResponse(
            id=r.id,
            call_log_id=r.call_log_id,
            business_id=r.business_id,
            quality_score=r.quality_score,
            issues_json=r.issues_json,
            suggestions_json=r.suggestions_json,
            has_unanswered_query=r.has_unanswered_query,
            has_knowledge_gap=r.has_knowledge_gap,
            has_prompt_weakness=r.has_prompt_weakness,
            has_ux_issue=r.has_ux_issue,
            agent_model=r.agent_model,
            review_latency_ms=r.review_latency_ms,
            reviewed_at=r.reviewed_at.isoformat(),
            reviewed_by=r.reviewed_by,
        )
        for r in reviews
    ]


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Business ID for tenant isolation"),
) -> ReviewStatsResponse:
    """Get statistics about transcript reviews.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    # Get review stats (type ignores due to SQLAlchemy/SQLModel typing limitations)
    review_stats = await session.execute(
        select(
            func.count(TranscriptReview.id),  # type: ignore[arg-type]
            func.avg(TranscriptReview.quality_score),
            func.sum(
                func.cast(
                    TranscriptReview.has_unanswered_query  # type: ignore[arg-type]
                    | TranscriptReview.has_knowledge_gap
                    | TranscriptReview.has_prompt_weakness
                    | TranscriptReview.has_ux_issue,
                    type_=int,  # type: ignore[arg-type]
                )
            ),
            func.sum(func.cast(TranscriptReview.has_knowledge_gap, type_=int)),  # type: ignore[arg-type]
            func.sum(func.cast(TranscriptReview.has_prompt_weakness, type_=int)),  # type: ignore[arg-type]
            func.sum(func.cast(TranscriptReview.has_ux_issue, type_=int)),  # type: ignore[arg-type]
        ).where(TranscriptReview.business_id == business_id)  # type: ignore[arg-type]
    )
    stats = review_stats.one()

    # Get pending suggestions count
    suggestions_result = await session.execute(
        select(func.count(ImprovementSuggestion.id)).where(  # type: ignore[arg-type]
            ImprovementSuggestion.business_id == business_id,  # type: ignore[arg-type]
            ImprovementSuggestion.status == SuggestionStatus.pending,  # type: ignore[arg-type]
        )
    )
    pending_suggestions = suggestions_result.scalar() or 0

    return ReviewStatsResponse(
        total_reviews=stats[0] or 0,
        avg_quality_score=float(stats[1] or 0),
        reviews_with_issues=int(stats[2] or 0),
        knowledge_gaps=int(stats[3] or 0),
        prompt_weaknesses=int(stats[4] or 0),
        ux_issues=int(stats[5] or 0),
        pending_suggestions=pending_suggestions,
    )


@router.get("/{review_id}", response_model=TranscriptReviewResponse)
async def get_review(
    review_id: str,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> TranscriptReviewResponse:
    """Get a specific transcript review.

    Security: Requires JWT authentication. Review must belong to authorized tenant.
    """
    result = await session.execute(
        select(TranscriptReview).where(TranscriptReview.id == review_id)  # type: ignore[arg-type]
    )
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this review",
        )

    return TranscriptReviewResponse(
        id=review.id,
        call_log_id=review.call_log_id,
        business_id=review.business_id,
        quality_score=review.quality_score,
        issues_json=review.issues_json,
        suggestions_json=review.suggestions_json,
        has_unanswered_query=review.has_unanswered_query,
        has_knowledge_gap=review.has_knowledge_gap,
        has_prompt_weakness=review.has_prompt_weakness,
        has_ux_issue=review.has_ux_issue,
        agent_model=review.agent_model,
        review_latency_ms=review.review_latency_ms,
        reviewed_at=review.reviewed_at.isoformat(),
        reviewed_by=review.reviewed_by,
    )


@router.post("/analyze", response_model=TriggerAnalysisResponse)
async def trigger_analysis(
    request: TriggerAnalysisRequest,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> TriggerAnalysisResponse:
    """Trigger transcript analysis for a specific call.

    Queues a background job to analyze the call using AI agents.
    Security: Requires JWT authentication. Call must belong to authorized tenant.
    """
    # Verify call exists and belongs to business
    result = await session.execute(
        select(CallLog).where(CallLog.id == request.call_log_id)  # type: ignore[arg-type]
    )
    call_log = result.scalar_one_or_none()

    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found")

    if call_log.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to analyze this call",
        )

    if not call_log.transcript:
        raise HTTPException(
            status_code=400,
            detail="Call has no transcript to analyze",
        )

    # Check if already reviewed
    existing = await session.execute(
        select(TranscriptReview).where(
            TranscriptReview.call_log_id == request.call_log_id  # type: ignore[arg-type]
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Call has already been reviewed",
        )

    # Queue the analysis job
    try:
        settings = get_settings()
        redis = await create_pool(settings.redis_settings)
        await redis.enqueue_job("analyze_transcript_quality", request.call_log_id)
        await redis.close()

        return TriggerAnalysisResponse(
            status="queued",
            message="Analysis job queued successfully",
            call_log_id=request.call_log_id,
        )
    except Exception as e:
        logger.error(f"Failed to queue analysis job: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to queue analysis job",
        ) from e


# =============================================================================
# Suggestion Endpoints
# =============================================================================


@router.get("/suggestions", response_model=list[ImprovementSuggestionResponse])
async def list_suggestions(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Business ID for tenant isolation"),
    status: SuggestionStatus | None = Query(None),
    category: IssueCategory | None = Query(None),
    min_priority: int | None = Query(None, ge=1, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[ImprovementSuggestionResponse]:
    """List improvement suggestions for a business.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    query = select(ImprovementSuggestion).where(
        ImprovementSuggestion.business_id == business_id  # type: ignore[arg-type]
    )

    if status is not None:
        query = query.where(ImprovementSuggestion.status == status)  # type: ignore[arg-type]
    if category is not None:
        query = query.where(ImprovementSuggestion.category == category)  # type: ignore[arg-type]
    if min_priority is not None:
        query = query.where(ImprovementSuggestion.priority >= min_priority)  # type: ignore[arg-type]

    query = (
        query.order_by(desc(ImprovementSuggestion.priority))  # type: ignore[arg-type]
        .offset(skip)
        .limit(limit)
    )

    result = await session.execute(query)
    suggestions = result.scalars().all()

    return [
        ImprovementSuggestionResponse(
            id=s.id,
            review_id=s.review_id,
            business_id=s.business_id,
            category=s.category,
            title=s.title,
            description=s.description,
            priority=s.priority,
            status=s.status,
            implemented_at=s.implemented_at.isoformat() if s.implemented_at else None,
            implemented_by=s.implemented_by,
            rejection_reason=s.rejection_reason,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in suggestions
    ]


@router.patch(
    "/suggestions/{suggestion_id}",
    response_model=ImprovementSuggestionResponse,
)
async def update_suggestion(
    suggestion_id: str,
    request: UpdateSuggestionRequest,
    auth_business_id: RequireBusinessAccess,
    current_user: RequireAuth,
    session: AsyncSession = Depends(get_session),
) -> ImprovementSuggestionResponse:
    """Update the status of an improvement suggestion.

    Use this to mark suggestions as implemented or rejected.
    Security: Requires JWT authentication. Suggestion must belong to authorized tenant.
    """
    result = await session.execute(
        select(ImprovementSuggestion).where(
            ImprovementSuggestion.id == suggestion_id  # type: ignore[arg-type]
        )
    )
    suggestion = result.scalar_one_or_none()

    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    if suggestion.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update this suggestion",
        )

    # Update status
    suggestion.status = request.status
    suggestion.updated_at = datetime.now(UTC)

    if request.status == SuggestionStatus.implemented:
        suggestion.implemented_at = datetime.now(UTC)
        suggestion.implemented_by = (
            current_user.email or current_user.preferred_username or current_user.sub
        )
    elif request.status == SuggestionStatus.rejected:
        suggestion.rejection_reason = request.rejection_reason

    await session.flush()
    await session.refresh(suggestion)

    return ImprovementSuggestionResponse(
        id=suggestion.id,
        review_id=suggestion.review_id,
        business_id=suggestion.business_id,
        category=suggestion.category,
        title=suggestion.title,
        description=suggestion.description,
        priority=suggestion.priority,
        status=suggestion.status,
        implemented_at=(
            suggestion.implemented_at.isoformat() if suggestion.implemented_at else None
        ),
        implemented_by=suggestion.implemented_by,
        rejection_reason=suggestion.rejection_reason,
        created_at=suggestion.created_at.isoformat(),
        updated_at=suggestion.updated_at.isoformat(),
    )
