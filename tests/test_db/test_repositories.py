"""Tests for database repositories."""

from __future__ import annotations

import pytest

from src.db.models import CallOutcome, DetectedLanguage, FollowupStatus
from src.db.repositories.calls import (
    AsyncCallLogRepository,
    parse_consent,
    parse_language,
    parse_outcome,
)


class TestAsyncCallLogRepository:
    """Tests for AsyncCallLogRepository."""

    @pytest.mark.asyncio
    async def test_upsert_creates_new(self, async_session) -> None:
        """Test upsert creates new call log when none exists."""
        repo = AsyncCallLogRepository(async_session)

        call_log = await repo.upsert_call_log(
            "test-call-001",
            business_id="himalayan_kitchen",
            duration_seconds=120,
        )

        assert call_log.id == "test-call-001"
        assert call_log.business_id == "himalayan_kitchen"
        assert call_log.duration_seconds == 120

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, async_session) -> None:
        """Test upsert updates existing call log."""
        repo = AsyncCallLogRepository(async_session)

        # Create
        await repo.upsert_call_log(
            "test-call-002",
            business_id="himalayan_kitchen",
            duration_seconds=60,
        )
        await async_session.flush()

        # Update
        call_log = await repo.upsert_call_log(
            "test-call-002",
            duration_seconds=180,
            transcript="Hello, I want to make a reservation",
        )

        assert call_log.id == "test-call-002"
        assert call_log.duration_seconds == 180
        assert call_log.transcript == "Hello, I want to make a reservation"

    @pytest.mark.asyncio
    async def test_get_by_id(self, async_session) -> None:
        """Test getting call log by ID."""
        repo = AsyncCallLogRepository(async_session)

        # Create
        await repo.upsert_call_log(
            "test-call-003",
            business_id="himalayan_kitchen",
        )
        await async_session.flush()

        # Get
        call_log = await repo.get_by_id("test-call-003")

        assert call_log is not None
        assert call_log.id == "test-call-003"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, async_session) -> None:
        """Test getting non-existent call log returns None."""
        repo = AsyncCallLogRepository(async_session)

        call_log = await repo.get_by_id("nonexistent-call")

        assert call_log is None


class TestCallerPreferences:
    """Tests for caller preferences management."""

    @pytest.mark.asyncio
    async def test_record_preferences_creates_new(self, async_session) -> None:
        """Test recording preferences creates new entry."""
        repo = AsyncCallLogRepository(async_session)

        prefs = await repo.record_preferences(
            "hash-001",
            transcript_opt_out=True,
            whatsapp_opt_out=False,
        )

        assert prefs.caller_id_hash == "hash-001"
        assert prefs.transcript_opt_out is True
        assert prefs.whatsapp_opt_out is False

    @pytest.mark.asyncio
    async def test_record_preferences_updates_existing(self, async_session) -> None:
        """Test recording preferences updates existing entry."""
        repo = AsyncCallLogRepository(async_session)

        # Create
        await repo.record_preferences("hash-002", transcript_opt_out=False)
        await async_session.flush()

        # Update
        prefs = await repo.record_preferences("hash-002", whatsapp_opt_out=True)

        assert prefs.transcript_opt_out is False
        assert prefs.whatsapp_opt_out is True


class TestWhatsappFollowup:
    """Tests for WhatsApp followup management."""

    @pytest.mark.asyncio
    async def test_create_followup(self, async_session) -> None:
        """Test creating a followup entry."""
        repo = AsyncCallLogRepository(async_session)

        followup = await repo.create_followup(
            business_id="himalayan_kitchen",
            call_log_id=None,
            customer_phone_encrypted="encrypted-phone",
            summary="Customer wants callback about reservation",
            reason="reservation_inquiry",
            whatsapp_consent=True,
        )

        assert followup.business_id == "himalayan_kitchen"
        assert followup.customer_phone_encrypted == "encrypted-phone"
        assert followup.status == FollowupStatus.pending
        assert followup.whatsapp_consent is True


class TestAuditLog:
    """Tests for audit logging."""

    @pytest.mark.asyncio
    async def test_record_audit(self, async_session) -> None:
        """Test recording an audit log entry."""
        repo = AsyncCallLogRepository(async_session)

        audit = await repo.record_audit(
            action="config_update",
            admin_user="admin@example.com",
            details="Updated operating hours",
            ip_address="192.168.1.1",
        )

        assert audit.action == "config_update"
        assert audit.admin_user == "admin@example.com"
        assert audit.details == "Updated operating hours"


class TestParseHelpers:
    """Tests for enum parsing helpers."""

    def test_parse_outcome_valid(self) -> None:
        """Test parsing valid outcome."""
        assert parse_outcome("resolved") == CallOutcome.resolved
        assert parse_outcome("fallback") == CallOutcome.fallback
        assert parse_outcome("error") == CallOutcome.error

    def test_parse_outcome_invalid(self) -> None:
        """Test parsing invalid outcome returns None."""
        assert parse_outcome("invalid") is None
        assert parse_outcome(None) is None
        assert parse_outcome("") is None

    def test_parse_language_valid(self) -> None:
        """Test parsing valid language."""
        assert parse_language("hindi") == DetectedLanguage.hindi
        assert parse_language("english") == DetectedLanguage.english
        assert parse_language("hinglish") == DetectedLanguage.hinglish

    def test_parse_language_invalid(self) -> None:
        """Test parsing invalid language returns None."""
        assert parse_language("spanish") is None
        assert parse_language(None) is None

    def test_parse_consent_valid(self) -> None:
        """Test parsing valid consent type."""
        from src.db.models import ConsentType

        assert parse_consent("none") == ConsentType.none
        assert parse_consent("transcript") == ConsentType.transcript
        assert parse_consent("whatsapp") == ConsentType.whatsapp

    def test_parse_consent_invalid(self) -> None:
        """Test parsing invalid consent returns None."""
        assert parse_consent("invalid") is None
        assert parse_consent(None) is None
