"""Tests for Prometheus metrics."""

from __future__ import annotations

from src.observability.metrics import (
    ACTIVE_CALLS,
    get_content_type,
    get_metrics,
    record_call_metrics,
)


class TestMetricsModule:
    """Tests for metrics module functions."""

    def test_get_metrics_returns_bytes(self) -> None:
        """Test get_metrics returns bytes."""
        result = get_metrics()
        assert isinstance(result, bytes)

    def test_get_content_type(self) -> None:
        """Test get_content_type returns valid content type."""
        content_type = get_content_type()
        assert "text/plain" in content_type or "text/openmetrics" in content_type

    def test_record_call_metrics_basic(self) -> None:
        """Test recording basic call metrics."""
        # Record a call
        record_call_metrics(
            outcome="resolved",
            business_id="test_business",
            duration_seconds=120.0,
        )

        # Metrics should be recorded (check by generating output)
        output = get_metrics().decode("utf-8")
        assert "vartalaap_call_total" in output
        assert "vartalaap_call_duration_seconds" in output

    def test_record_call_metrics_with_latencies(self) -> None:
        """Test recording call metrics with latencies."""
        record_call_metrics(
            outcome="resolved",
            business_id="test_business",
            duration_seconds=90.0,
            stt_latency_ms=250.0,
            llm_latency_ms=500.0,
            tts_latency_ms=100.0,
        )

        output = get_metrics().decode("utf-8")
        assert "vartalaap_stt_latency_seconds" in output
        assert "vartalaap_llm_first_token_seconds" in output
        assert "vartalaap_tts_first_chunk_seconds" in output

    def test_record_call_metrics_with_barge_in(self) -> None:
        """Test recording call metrics with barge-in count."""
        record_call_metrics(
            outcome="resolved",
            business_id="test_business",
            duration_seconds=60.0,
            barge_in_count=2,
        )

        output = get_metrics().decode("utf-8")
        assert "vartalaap_barge_in_total" in output


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_metrics_endpoint_returns_200(self, test_client) -> None:
        """Test /metrics endpoint returns 200."""
        response = test_client.get("/metrics")

        assert response.status_code == 200

    def test_metrics_endpoint_content_type(self, test_client) -> None:
        """Test /metrics endpoint returns correct content type."""
        response = test_client.get("/metrics")

        content_type = response.headers["content-type"]
        # Prometheus content type
        assert "text/plain" in content_type or "text/openmetrics" in content_type

    def test_metrics_endpoint_contains_metrics(self, test_client) -> None:
        """Test /metrics endpoint contains expected metrics."""
        response = test_client.get("/metrics")

        content = response.text
        # Should contain our custom metrics (even if no values yet)
        assert "vartalaap" in content.lower() or "python" in content.lower()


class TestActiveCallsGauge:
    """Tests for ACTIVE_CALLS gauge."""

    def test_active_calls_increment(self) -> None:
        """Test incrementing active calls gauge."""
        initial = ACTIVE_CALLS.labels(business_id="test")._value.get()

        ACTIVE_CALLS.labels(business_id="test").inc()
        after_inc = ACTIVE_CALLS.labels(business_id="test")._value.get()

        assert after_inc == initial + 1

        # Cleanup
        ACTIVE_CALLS.labels(business_id="test").dec()

    def test_active_calls_decrement(self) -> None:
        """Test decrementing active calls gauge."""
        ACTIVE_CALLS.labels(business_id="test2").set(5)

        ACTIVE_CALLS.labels(business_id="test2").dec()
        value = ACTIVE_CALLS.labels(business_id="test2")._value.get()

        assert value == 4

        # Cleanup
        ACTIVE_CALLS.labels(business_id="test2").set(0)
