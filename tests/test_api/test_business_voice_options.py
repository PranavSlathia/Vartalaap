"""Tests for business voice options endpoint."""

from __future__ import annotations

import pytest

from src.api.auth import TokenPayload


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch) -> None:
    """Mock authentication for tenant-scoped business APIs."""
    token = TokenPayload(
        sub="test-user",
        realm_access={"roles": ["admin"]},
        business_ids=["himalayan_kitchen"],
    )
    monkeypatch.setattr("src.api.auth.decode_token", lambda _: token)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Tenant auth headers for business API calls."""
    return {
        "Authorization": "Bearer test-token",
        "X-Business-ID": "himalayan_kitchen",
    }


def test_get_voice_options_success(test_client, auth_headers) -> None:
    """Voice options endpoint returns provider/model/voice catalog."""
    response = test_client.get(
        "/api/business/himalayan_kitchen/voice-options",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()

    assert "providers" in payload
    assert "provider_status" in payload
    assert "recommended_presets" in payload
    assert "piper" in payload["providers"]
    assert isinstance(payload["elevenlabs_models"], list)
    assert isinstance(payload["piper_voices"], list)


def test_get_voice_options_rejects_cross_tenant(test_client, auth_headers) -> None:
    """Business-scoped endpoint must reject unauthorized business paths."""
    response = test_client.get(
        "/api/business/other_business/voice-options",
        headers=auth_headers,
    )

    assert response.status_code == 403
