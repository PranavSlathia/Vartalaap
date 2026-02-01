"""Prometheus metrics endpoint.

Exposes application metrics for Prometheus scraping.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from src.observability.metrics import get_content_type, get_metrics

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint.

    Exposes metrics in Prometheus text format for scraping.

    Returns:
        Response with metrics in Prometheus exposition format.
    """
    return Response(
        content=get_metrics(),
        media_type=get_content_type(),
    )
