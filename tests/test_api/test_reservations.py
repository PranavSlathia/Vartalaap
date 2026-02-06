"""Tests for reservations CRUD endpoints."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.api.auth import TokenPayload


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch) -> None:
    """Mock authentication for tenant-scoped reservation APIs."""
    token = TokenPayload(
        sub="test-user",
        realm_access={"roles": ["admin"]},
        business_ids=["himalayan_kitchen"],
    )
    monkeypatch.setattr("src.api.auth.decode_token", lambda _: token)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Tenant auth headers used by reservation APIs."""
    return {
        "Authorization": "Bearer test-token",
        "X-Business-ID": "himalayan_kitchen",
    }


class TestCreateReservation:
    """Tests for POST /api/reservations."""

    def test_create_reservation_success(self, test_client, auth_headers) -> None:
        """Test creating a reservation returns 201."""
        future_date = (date.today() + timedelta(days=7)).isoformat()
        data = {
            "business_id": "himalayan_kitchen",
            "customer_name": "Test Customer",
            "party_size": 4,
            "reservation_date": future_date,
            "reservation_time": "19:00",
        }

        response = test_client.post("/api/reservations", json=data, headers=auth_headers)

        assert response.status_code == 201
        result = response.json()
        assert result["customer_name"] == "Test Customer"
        assert result["party_size"] == 4
        assert result["status"] == "confirmed"
        assert "id" in result

    def test_create_reservation_with_notes(self, test_client, auth_headers) -> None:
        """Test creating a reservation with notes."""
        future_date = (date.today() + timedelta(days=3)).isoformat()
        data = {
            "business_id": "himalayan_kitchen",
            "customer_name": "VIP Guest",
            "party_size": 6,
            "reservation_date": future_date,
            "reservation_time": "20:00",
            "notes": "Birthday celebration",
            "whatsapp_consent": True,
        }

        response = test_client.post("/api/reservations", json=data, headers=auth_headers)

        assert response.status_code == 201
        result = response.json()
        assert result["notes"] == "Birthday celebration"
        assert result["whatsapp_consent"] is True

    def test_create_reservation_invalid_party_size(self, test_client, auth_headers) -> None:
        """Test party size validation."""
        future_date = (date.today() + timedelta(days=1)).isoformat()
        data = {
            "business_id": "himalayan_kitchen",
            "party_size": 0,  # Invalid - must be >= 1
            "reservation_date": future_date,
            "reservation_time": "18:00",
        }

        response = test_client.post("/api/reservations", json=data, headers=auth_headers)

        assert response.status_code == 422  # Validation error

    def test_create_reservation_invalid_time_format(self, test_client, auth_headers) -> None:
        """Test time format validation."""
        future_date = (date.today() + timedelta(days=1)).isoformat()
        data = {
            "business_id": "himalayan_kitchen",
            "party_size": 2,
            "reservation_date": future_date,
            "reservation_time": "7pm",  # Invalid format
        }

        response = test_client.post("/api/reservations", json=data, headers=auth_headers)

        assert response.status_code == 422  # Validation error


class TestListReservations:
    """Tests for GET /api/reservations."""

    def test_list_reservations_empty(self, test_client, auth_headers) -> None:
        """Test listing reservations when none exist."""
        response = test_client.get(
            "/api/reservations",
            params={"business_id": "himalayan_kitchen"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_list_reservations_after_create(self, test_client, auth_headers) -> None:
        """Test listing reservations after creating one."""
        future_date = (date.today() + timedelta(days=5)).isoformat()

        # Create a reservation first
        create_data = {
            "business_id": "himalayan_kitchen",
            "customer_name": "List Test",
            "party_size": 2,
            "reservation_date": future_date,
            "reservation_time": "12:00",
        }
        test_client.post("/api/reservations", json=create_data, headers=auth_headers)

        # List reservations
        response = test_client.get(
            "/api/reservations",
            params={"business_id": "himalayan_kitchen"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        reservations = response.json()
        assert len(reservations) >= 1

    def test_list_reservations_with_filter(self, test_client, auth_headers) -> None:
        """Test filtering enforces tenant access."""
        response = test_client.get(
            "/api/reservations",
            params={"business_id": "nonexistent_business"},
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestGetReservation:
    """Tests for GET /api/reservations/{id}."""

    def test_get_reservation_not_found(self, test_client, auth_headers) -> None:
        """Test getting non-existent reservation returns 404."""
        response = test_client.get("/api/reservations/nonexistent-id-123", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_reservation_after_create(self, test_client, auth_headers) -> None:
        """Test getting a reservation by ID after creating it."""
        future_date = (date.today() + timedelta(days=10)).isoformat()

        # Create
        create_data = {
            "business_id": "himalayan_kitchen",
            "customer_name": "Get Test",
            "party_size": 3,
            "reservation_date": future_date,
            "reservation_time": "13:00",
        }
        create_response = test_client.post(
            "/api/reservations",
            json=create_data,
            headers=auth_headers,
        )
        created_id = create_response.json()["id"]

        # Get
        response = test_client.get(f"/api/reservations/{created_id}", headers=auth_headers)

        assert response.status_code == 200
        result = response.json()
        assert result["id"] == created_id
        assert result["customer_name"] == "Get Test"


class TestUpdateReservation:
    """Tests for PATCH /api/reservations/{id}."""

    def test_update_reservation_not_found(self, test_client, auth_headers) -> None:
        """Test updating non-existent reservation returns 404."""
        response = test_client.patch(
            "/api/reservations/nonexistent-id-456",
            json={"party_size": 5},
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_update_reservation_partial(self, test_client, auth_headers) -> None:
        """Test partial update of a reservation."""
        future_date = (date.today() + timedelta(days=14)).isoformat()

        # Create
        create_data = {
            "business_id": "himalayan_kitchen",
            "customer_name": "Update Test",
            "party_size": 2,
            "reservation_date": future_date,
            "reservation_time": "14:00",
        }
        create_response = test_client.post(
            "/api/reservations",
            json=create_data,
            headers=auth_headers,
        )
        created_id = create_response.json()["id"]

        # Update
        response = test_client.patch(
            f"/api/reservations/{created_id}",
            json={"party_size": 5, "notes": "Updated notes"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["party_size"] == 5
        assert result["notes"] == "Updated notes"
        assert result["customer_name"] == "Update Test"  # Unchanged

    def test_update_reservation_status(self, test_client, auth_headers) -> None:
        """Test updating reservation status."""
        future_date = (date.today() + timedelta(days=7)).isoformat()

        # Create
        create_data = {
            "business_id": "himalayan_kitchen",
            "party_size": 4,
            "reservation_date": future_date,
            "reservation_time": "19:00",
        }
        create_response = test_client.post(
            "/api/reservations",
            json=create_data,
            headers=auth_headers,
        )
        created_id = create_response.json()["id"]

        # Update status to cancelled
        response = test_client.patch(
            f"/api/reservations/{created_id}",
            json={"status": "cancelled"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestDeleteReservation:
    """Tests for DELETE /api/reservations/{id}."""

    def test_delete_reservation_not_found(self, test_client, auth_headers) -> None:
        """Test deleting non-existent reservation returns 404."""
        response = test_client.delete(
            "/api/reservations/nonexistent-id-789",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_delete_reservation_success(self, test_client, auth_headers) -> None:
        """Test successful deletion returns 204."""
        future_date = (date.today() + timedelta(days=21)).isoformat()

        # Create
        create_data = {
            "business_id": "himalayan_kitchen",
            "party_size": 2,
            "reservation_date": future_date,
            "reservation_time": "20:00",
        }
        create_response = test_client.post(
            "/api/reservations",
            json=create_data,
            headers=auth_headers,
        )
        created_id = create_response.json()["id"]

        # Delete
        response = test_client.delete(f"/api/reservations/{created_id}", headers=auth_headers)

        assert response.status_code == 204

        # Verify it's gone
        get_response = test_client.get(f"/api/reservations/{created_id}", headers=auth_headers)
        assert get_response.status_code == 404
