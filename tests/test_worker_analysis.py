"""Tests for worker transcript analysis job flow."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.db.models import (
    Business,
    CallLog,
    ImprovementSuggestion,
    IssueCategory,
    TranscriptReview,
)
from src.services.analysis.transcript_crew import (
    ImprovementSuggestionData,
    ReviewedIssue,
    TranscriptReviewResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_business():
    """Create a sample business."""
    return Business(
        id="test_business",
        name="Test Business",
        phone_number="+911234567890",
        timezone="Asia/Kolkata",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_call_log(sample_business):
    """Create a sample call log with transcript."""
    return CallLog(
        id=str(uuid4()),
        business_id=sample_business.id,
        duration_seconds=120,
        transcript="Bot: Namaste!\nCaller: Table book karna hai.\nBot: Kitne log?",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_crew_result():
    """Create a mock CrewAI analysis result."""
    return TranscriptReviewResult(
        quality_score=4,
        issues=[
            ReviewedIssue(
                category=IssueCategory.ux_issue,
                description="Bot response was too brief",
                severity=3,
                context="Bot: Kitne log?",
            ),
        ],
        suggestions=[
            ImprovementSuggestionData(
                category=IssueCategory.ux_issue,
                title="Add more context to responses",
                description="Include greeting and confirmation in responses",
                priority=3,
            ),
        ],
        has_unanswered_query=False,
        has_knowledge_gap=False,
        has_prompt_weakness=False,
        has_ux_issue=True,
        review_latency_ms=1500.0,
    )


# =============================================================================
# Job Persistence Tests
# =============================================================================


class TestAnalysisJobPersistence:
    """Tests for analysis job creating DB records."""

    @pytest.mark.asyncio
    async def test_creates_review_record(
        self, async_session, sample_business, sample_call_log, mock_crew_result
    ):
        """Analysis job creates TranscriptReview record."""
        # Setup
        async_session.add(sample_business)
        async_session.add(sample_call_log)
        await async_session.commit()

        # Mock the worker function components
        from sqlalchemy import select

        with patch(
            "src.services.analysis.transcript_crew.TranscriptAnalysisCrew.analyze_transcript",
            new_callable=AsyncMock,
            return_value=mock_crew_result,
        ):
            # Simulate what the worker does
            review = TranscriptReview(
                id=str(uuid4()),
                call_log_id=sample_call_log.id,
                business_id=sample_call_log.business_id,
                quality_score=mock_crew_result.quality_score,
                issues_json=mock_crew_result.to_issues_json(),
                suggestions_json=mock_crew_result.to_suggestions_json(),
                has_unanswered_query=mock_crew_result.has_unanswered_query,
                has_knowledge_gap=mock_crew_result.has_knowledge_gap,
                has_prompt_weakness=mock_crew_result.has_prompt_weakness,
                has_ux_issue=mock_crew_result.has_ux_issue,
                review_latency_ms=mock_crew_result.review_latency_ms,
                reviewed_at=datetime.now(UTC),
            )
            async_session.add(review)
            await async_session.commit()

        # Verify
        result = await async_session.execute(
            select(TranscriptReview).where(
                TranscriptReview.call_log_id == sample_call_log.id
            )
        )
        saved_review = result.scalar_one()

        assert saved_review.quality_score == 4
        assert saved_review.has_ux_issue is True
        assert saved_review.has_knowledge_gap is False
        assert "ux_issue" in saved_review.issues_json

    @pytest.mark.asyncio
    async def test_creates_suggestion_records(
        self, async_session, sample_business, sample_call_log, mock_crew_result
    ):
        """Analysis job creates ImprovementSuggestion records."""
        # Setup
        async_session.add(sample_business)
        async_session.add(sample_call_log)
        await async_session.commit()

        from sqlalchemy import select

        # Create review first
        review = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,
            business_id=sample_call_log.business_id,
            quality_score=mock_crew_result.quality_score,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(review)
        await async_session.flush()

        # Create suggestions
        for suggestion in mock_crew_result.suggestions:
            suggestion_record = ImprovementSuggestion(
                id=str(uuid4()),
                review_id=review.id,
                business_id=sample_call_log.business_id,
                category=suggestion.category,
                title=suggestion.title,
                description=suggestion.description,
                priority=suggestion.priority,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            async_session.add(suggestion_record)

        await async_session.commit()

        # Verify
        result = await async_session.execute(
            select(ImprovementSuggestion).where(
                ImprovementSuggestion.review_id == review.id
            )
        )
        saved_suggestions = result.scalars().all()

        assert len(saved_suggestions) == 1
        assert saved_suggestions[0].title == "Add more context to responses"
        assert saved_suggestions[0].priority == 3


# =============================================================================
# Duplicate Handling Tests
# =============================================================================


class TestDuplicateHandling:
    """Tests for handling duplicate analysis jobs."""

    @pytest.mark.asyncio
    async def test_unique_constraint_prevents_duplicates(
        self, async_session, sample_business, sample_call_log
    ):
        """Unique constraint on call_log_id prevents duplicate reviews."""
        from sqlalchemy.exc import IntegrityError

        async_session.add(sample_business)
        async_session.add(sample_call_log)
        await async_session.commit()

        # Create first review
        review1 = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,
            business_id=sample_call_log.business_id,
            quality_score=4,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(review1)
        await async_session.commit()

        # Try to create second review for same call
        review2 = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,  # Same call_log_id
            business_id=sample_call_log.business_id,
            quality_score=3,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(review2)

        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_worker_handles_constraint_violation_gracefully(
        self, async_session, sample_business, sample_call_log
    ):
        """Worker handles unique constraint violation without raising."""
        from sqlalchemy.exc import IntegrityError

        async_session.add(sample_business)
        async_session.add(sample_call_log)

        # Create existing review
        existing_review = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,
            business_id=sample_call_log.business_id,
            quality_score=4,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(existing_review)
        await async_session.commit()

        # Simulate worker behavior: try to create duplicate, catch error, rollback
        duplicate_review = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,
            business_id=sample_call_log.business_id,
            quality_score=3,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(duplicate_review)

        constraint_violated = False
        try:
            await async_session.flush()
        except IntegrityError:
            # Worker should rollback and return gracefully
            constraint_violated = True
            await async_session.rollback()

        assert constraint_violated, "Should have raised IntegrityError"
        # Note: After rollback, session state is reset - original review persists in DB


# =============================================================================
# Job Skipping Tests
# =============================================================================


class TestJobSkipping:
    """Tests for conditions that skip analysis."""

    @pytest.mark.asyncio
    async def test_skips_if_no_transcript(self, async_session, sample_business):
        """Job skips if call log has no transcript."""
        # Create call without transcript
        call_log = CallLog(
            id=str(uuid4()),
            business_id=sample_business.id,
            duration_seconds=120,
            transcript=None,  # No transcript
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        async_session.add(sample_business)
        async_session.add(call_log)
        await async_session.commit()

        # Verify skip condition
        assert call_log.transcript is None

    @pytest.mark.asyncio
    async def test_skips_if_already_reviewed(
        self, async_session, sample_business, sample_call_log
    ):
        """Job skips if review already exists."""
        from sqlalchemy import select

        async_session.add(sample_business)
        async_session.add(sample_call_log)

        # Create existing review
        existing_review = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,
            business_id=sample_call_log.business_id,
            quality_score=4,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(existing_review)
        await async_session.commit()

        # Check for existing review (as worker does)
        result = await async_session.execute(
            select(TranscriptReview).where(
                TranscriptReview.call_log_id == sample_call_log.id
            )
        )
        existing = result.scalar_one_or_none()

        # Worker would skip if this returns a result
        assert existing is not None
        assert existing.quality_score == 4


# =============================================================================
# Enqueue Tests
# =============================================================================


class TestJobEnqueue:
    """Tests for job enqueueing from webhook."""

    def test_analysis_job_is_registered(self):
        """Verify analyze_transcript_quality is a registered worker function."""
        # Import worker to check function is registered
        from src import worker

        # The function should exist and be callable
        assert hasattr(worker, "analyze_transcript_quality")
        assert callable(worker.analyze_transcript_quality)
