"""Tests for health check endpoints."""

from __future__ import annotations


class TestHealthEndpoints:
    """Tests for /health and /health/detailed endpoints."""

    def test_health_basic(self, test_client) -> None:
        """Test GET /health returns 200 with status=healthy."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_detailed_structure(self, test_client) -> None:
        """Test GET /health/detailed returns expected structure."""
        response = test_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_health_detailed_checks_services(self, test_client) -> None:
        """Test /health/detailed includes service configuration checks."""
        response = test_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        checks = data["checks"]

        # Verify service configuration checks are present
        assert "groq" in checks
        assert "deepgram" in checks
        assert "plivo" in checks
        assert "edge_tts" in checks

        # With test settings, services should show as configured
        assert checks["groq"] == "configured"
        assert checks["deepgram"] == "configured"
        assert checks["plivo"] == "configured"


class TestHealthDegraded:
    """Tests for degraded health scenarios."""

    def test_health_basic_always_healthy(self, test_client_no_db) -> None:
        """Test basic health check always returns healthy even without DB."""
        response = test_client_no_db.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
