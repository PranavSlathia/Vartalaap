"""Prometheus metrics for Vartalaap voice bot.

Provides metrics for monitoring call quality, latency, and system health.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

# =============================================================================
# Counters
# =============================================================================

CALL_TOTAL = Counter(
    "vartalaap_call_total",
    "Total calls handled by the voice bot",
    ["outcome", "business_id"],
)

RATE_LIMIT_REJECTIONS = Counter(
    "vartalaap_rate_limit_rejections_total",
    "Total rate limit rejections",
    ["service"],
)

BARGE_IN_TOTAL = Counter(
    "vartalaap_barge_in_total",
    "Total barge-in interruptions detected",
    ["business_id"],
)

RAG_HIT_RATE = Counter(
    "vartalaap_rag_hits_total",
    "RAG retrieval hit rate by score quality",
    ["score_bucket", "business_id"],
)

FOLLOWUP_MISSING_PHONE = Counter(
    "vartalaap_followup_missing_phone_total",
    "Operator followup requests skipped due to missing encrypted phone",
    ["business_id"],
)

# =============================================================================
# Gauges
# =============================================================================

ACTIVE_CALLS = Gauge(
    "vartalaap_active_calls",
    "Currently active calls",
    ["business_id"],
)

# =============================================================================
# Histograms
# =============================================================================

CALL_DURATION = Histogram(
    "vartalaap_call_duration_seconds",
    "Call duration in seconds",
    buckets=[10, 30, 60, 120, 300, 600, 900, 1800],
)

STT_LATENCY = Histogram(
    "vartalaap_stt_latency_seconds",
    "Speech-to-text latency (time to first word)",
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

LLM_FIRST_TOKEN = Histogram(
    "vartalaap_llm_first_token_seconds",
    "LLM time to first token",
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

TTS_FIRST_CHUNK = Histogram(
    "vartalaap_tts_first_chunk_seconds",
    "TTS time to first audio chunk",
    buckets=[0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0],
)

RAG_RETRIEVAL_LATENCY = Histogram(
    "vartalaap_rag_retrieval_seconds",
    "Knowledge retrieval latency",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5],
)

# =============================================================================
# Helper Functions
# =============================================================================


def record_call_metrics(
    outcome: str,
    business_id: str,
    duration_seconds: float,
    *,
    stt_latency_ms: float | None = None,
    llm_latency_ms: float | None = None,
    tts_latency_ms: float | None = None,
    barge_in_count: int = 0,
) -> None:
    """Record metrics for a completed call.

    Args:
        outcome: Call outcome (resolved, fallback, dropped, error)
        business_id: Business identifier
        duration_seconds: Total call duration
        stt_latency_ms: Average STT latency in milliseconds
        llm_latency_ms: Average LLM first token latency in milliseconds
        tts_latency_ms: Average TTS first chunk latency in milliseconds
        barge_in_count: Number of barge-in interruptions
    """
    # Record call counter
    CALL_TOTAL.labels(outcome=outcome, business_id=business_id).inc()

    # Record duration
    CALL_DURATION.observe(duration_seconds)

    # Record latencies (convert from ms to seconds)
    if stt_latency_ms is not None and stt_latency_ms > 0:
        STT_LATENCY.observe(stt_latency_ms / 1000)

    if llm_latency_ms is not None and llm_latency_ms > 0:
        LLM_FIRST_TOKEN.observe(llm_latency_ms / 1000)

    if tts_latency_ms is not None and tts_latency_ms > 0:
        TTS_FIRST_CHUNK.observe(tts_latency_ms / 1000)

    # Record barge-ins
    if barge_in_count > 0:
        BARGE_IN_TOTAL.labels(business_id=business_id).inc(barge_in_count)


def record_rag_metrics(
    business_id: str,
    retrieval_time_ms: float,
    top_score: float | None,
    result_count: int,
) -> None:
    """Record metrics for a knowledge retrieval operation.

    Args:
        business_id: Business identifier
        retrieval_time_ms: Retrieval latency in milliseconds
        top_score: Highest similarity score from results (None if no results)
        result_count: Number of results returned
    """
    # Record latency (convert from ms to seconds)
    RAG_RETRIEVAL_LATENCY.observe(retrieval_time_ms / 1000)

    # Record hit quality by score bucket
    if result_count > 0 and top_score is not None:
        if top_score >= 0.7:
            bucket = "high"  # Strong match
        elif top_score >= 0.5:
            bucket = "medium"  # Good match
        elif top_score >= 0.3:
            bucket = "low"  # Weak match
        else:
            bucket = "miss"  # Below threshold
        RAG_HIT_RATE.labels(score_bucket=bucket, business_id=business_id).inc()
    else:
        RAG_HIT_RATE.labels(score_bucket="miss", business_id=business_id).inc()


def record_followup_missing_phone(business_id: str) -> None:
    """Record a followup creation miss due to missing encrypted caller phone."""
    FOLLOWUP_MISSING_PHONE.labels(business_id=business_id).inc()


def get_metrics() -> bytes:
    """Generate Prometheus metrics output.

    Returns:
        Metrics in Prometheus text exposition format.
    """
    return generate_latest()


def get_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content-Type header value for Prometheus metrics.
    """
    return CONTENT_TYPE_LATEST
