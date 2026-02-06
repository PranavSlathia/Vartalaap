"""Tests for Plivo webhook endpoints."""

from __future__ import annotations

import pytest

from src.db.models import Business, BusinessStatus, BusinessType


@pytest.fixture
def mock_business_phone_mapping(monkeypatch) -> None:
    """Mock phone-to-business routing for answer webhook tests."""

    async def mock_get_by_phone_number(_, phone_number: str):
        if phone_number != "+918888888888":
            return None
        return Business(
            id="himalayan_kitchen",
            name="Himalayan Kitchen",
            type=BusinessType.restaurant,
            status=BusinessStatus.active,
            timezone="Asia/Kolkata",
            greeting_text="Namaste! Himalayan Kitchen mein aapka swagat hai.",
        )

    monkeypatch.setattr(
        "src.db.repositories.businesses.AsyncBusinessRepository.get_by_phone_number",
        mock_get_by_phone_number,
    )


class TestPlivoAnswerWebhook:
    """Tests for POST /api/plivo/webhook/answer."""

    def test_answer_webhook_returns_xml(self, test_client, mock_business_phone_mapping) -> None:
        """Test answer webhook returns XML with Stream element."""
        form_data = {
            "CallUUID": "test-uuid-123",
            "From": "+919999999999",
            "To": "+918888888888",
            "Direction": "inbound",
            "CallStatus": "answered",
        }

        response = test_client.post("/api/plivo/webhook/answer", data=form_data)

        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        assert "<Stream" in response.text
        assert "bidirectional" in response.text

    def test_answer_webhook_includes_websocket_url(
        self, test_client, mock_business_phone_mapping
    ) -> None:
        """Test answer webhook XML contains websocket URL."""
        form_data = {
            "CallUUID": "test-call-456",
            "From": "+919999999999",
            "To": "+918888888888",
            "Direction": "inbound",
            "CallStatus": "answered",
        }

        response = test_client.post("/api/plivo/webhook/answer", data=form_data)

        assert response.status_code == 200
        # WebSocket URL should contain the call UUID
        assert "test-call-456" in response.text
        assert "ws://" in response.text or "wss://" in response.text

    def test_answer_webhook_minimal_data(self, test_client) -> None:
        """Test answer webhook handles minimal form data."""
        form_data = {
            "CallUUID": "minimal-call-789",
        }

        response = test_client.post("/api/plivo/webhook/answer", data=form_data)

        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        assert "<Hangup" in response.text


class TestPlivoHangupWebhook:
    """Tests for POST /api/plivo/webhook/hangup."""

    def test_hangup_webhook_returns_ok(self, test_client) -> None:
        """Test hangup webhook returns ok=True."""
        form_data = {
            "CallUUID": "test-hangup-123",
            "Duration": "60",
            "HangupCause": "normal",
        }

        response = test_client.post("/api/plivo/webhook/hangup", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_hangup_webhook_handles_missing_session(self, test_client) -> None:
        """Test hangup webhook handles calls not in registry."""
        form_data = {
            "CallUUID": "nonexistent-call-999",
            "Duration": "30",
            "HangupCause": "unknown",
        }

        response = test_client.post("/api/plivo/webhook/hangup", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


class TestPlivoFallbackWebhook:
    """Tests for POST /api/plivo/webhook/fallback."""

    def test_fallback_webhook_returns_hangup_xml(self, test_client) -> None:
        """Test fallback webhook returns Hangup XML."""
        form_data = {
            "CallUUID": "fallback-call-123",
            "ErrorMessage": "Connection timeout",
        }

        response = test_client.post("/api/plivo/webhook/fallback", data=form_data)

        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        # Should contain apology message elements
        assert "<Speak" in response.text or "<Hangup" in response.text


class TestPlivoRingingWebhook:
    """Tests for POST /api/plivo/webhook/ringing."""

    def test_ringing_webhook_returns_ok(self, test_client) -> None:
        """Test ringing webhook returns ok=True."""
        form_data = {
            "CallUUID": "ringing-call-123",
        }

        response = test_client.post("/api/plivo/webhook/ringing", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


class TestPlivoHealth:
    """Tests for GET /api/plivo/health."""

    def test_plivo_health_endpoint(self, test_client) -> None:
        """Test Plivo health check endpoint returns structure."""
        response = test_client.get("/api/plivo/health")

        assert response.status_code == 200
        data = response.json()
        assert "healthy" in data
        assert "active_calls" in data
        assert isinstance(data["active_calls"], int)
        assert data["active_calls"] >= 0
