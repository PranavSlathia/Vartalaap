"""Tests for transcript review API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel import SQLModel

from src.db.models import (
    Business,
    CallLog,
    ImprovementSuggestion,
    IssueCategory,
    SuggestionStatus,
    TranscriptReview,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token payload."""
    return {
        "sub": "user-123",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["admin"]},
        "business_ids": ["test_business"],
    }


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Auth headers with mocked JWT."""
    return {
        "Authorization": "Bearer test-token",
        "X-Business-ID": "test_business",
    }


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
    """Create a sample call log."""
    return CallLog(
        id=str(uuid4()),
        business_id=sample_business.id,
        duration_seconds=120,
        transcript="Bot: Namaste!\nCaller: Table book karna hai.",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_review(sample_call_log):
    """Create a sample transcript review."""
    return TranscriptReview(
        id=str(uuid4()),
        call_log_id=sample_call_log.id,
        business_id=sample_call_log.business_id,
        quality_score=4,
        issues_json='[{"category": "ux_issue", "description": "Test issue"}]',
        suggestions_json='[{"category": "ux_issue", "title": "Fix it"}]',
        has_unanswered_query=False,
        has_knowledge_gap=True,
        has_prompt_weakness=False,
        has_ux_issue=True,
        review_latency_ms=1500.0,
        reviewed_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_suggestion(sample_review):
    """Create a sample improvement suggestion."""
    return ImprovementSuggestion(
        id=str(uuid4()),
        review_id=sample_review.id,
        business_id=sample_review.business_id,
        category=IssueCategory.knowledge_gap,
        title="Add vegan menu items",
        description="Customers frequently ask about vegan options.",
        priority=4,
        status=SuggestionStatus.pending,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# =============================================================================
# API Tests
# =============================================================================


class TestReviewsAPI:
    """Tests for /api/reviews endpoints."""

    def test_list_reviews_requires_auth(self, test_client):
        """List reviews requires authentication."""
        response = test_client.get("/api/reviews", params={"business_id": "test"})
        assert response.status_code == 401

    def test_list_reviews_requires_business_id_header(self, test_client, mock_jwt_token):
        """List reviews requires X-Business-ID header."""
        from src.api.auth import TokenPayload

        with patch("src.api.auth.decode_token") as mock_decode:
            mock_decode.return_value = TokenPayload(**mock_jwt_token)
            response = test_client.get(
                "/api/reviews",
                headers={"Authorization": "Bearer test-token"},
                params={"business_id": "test_business"},
            )
            assert response.status_code == 400
            assert "X-Business-ID" in response.json()["detail"]

    def test_trigger_analysis_requires_auth(self, test_client):
        """Trigger analysis requires authentication."""
        response = test_client.post(
            "/api/reviews/analyze",
            json={"call_id": "test-call-id"},
        )
        assert response.status_code == 401


class TestSuggestionStatusUpdate:
    """Tests for updating suggestion status."""

    def test_update_suggestion_requires_auth(self, test_client):
        """Update suggestion requires authentication."""
        response = test_client.patch(
            "/api/reviews/suggestions/some-id",
            json={"status": "implemented"},
        )
        assert response.status_code == 401

    def test_update_suggestion_implemented_returns_404_for_missing(
        self, test_client, mock_jwt_token, auth_headers
    ):
        """Updating non-existent suggestion returns 404."""
        from src.api.auth import TokenPayload

        with patch("src.api.auth.decode_token") as mock_decode:
            mock_decode.return_value = TokenPayload(
                sub="user-456",
                email="admin@example.com",
                preferred_username="admin",
                realm_access={"roles": ["admin"]},
                business_ids=["test_business"],
            )
            response = test_client.patch(
                "/api/reviews/suggestions/nonexistent-id",
                headers=auth_headers,
                json={"status": "implemented"},
            )
            assert response.status_code == 404


# =============================================================================
# Duplicate Review Prevention Tests
# =============================================================================


class TestDuplicateReviewPrevention:
    """Tests for unique constraint on call_log_id."""

    @pytest.mark.asyncio
    async def test_unique_constraint_on_call_log_id(self, async_session, sample_business, sample_call_log):
        """Verify unique constraint prevents duplicate reviews."""
        from sqlalchemy.exc import IntegrityError

        # Add business and call log
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

        # Try to create duplicate review
        review2 = TranscriptReview(
            id=str(uuid4()),
            call_log_id=sample_call_log.id,  # Same call_log_id
            business_id=sample_call_log.business_id,
            quality_score=3,
            reviewed_at=datetime.now(UTC),
        )
        async_session.add(review2)

        with pytest.raises(IntegrityError):
            await async_session.commit()


# =============================================================================
# Statistics Tests
# =============================================================================


class TestReviewStatistics:
    """Tests for review statistics endpoint."""

    def test_stats_requires_auth(self, test_client):
        """Stats endpoint requires authentication."""
        response = test_client.get(
            "/api/reviews/stats",
            params={"business_id": "test_business"},
        )
        assert response.status_code == 401
