"""Reusable metric cards for admin dashboard."""

from __future__ import annotations

import streamlit as st

try:
    from streamlit_extras.metric_cards import style_metric_cards
except Exception:  # pragma: no cover - optional dependency
    style_metric_cards = None


def display_metrics(
    total_calls: int,
    resolved_pct: float,
    avg_duration: float,
    reservations_today: int,
) -> None:
    """Render the main metrics row."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Calls", f"{total_calls}")
    with col2:
        st.metric("Resolved", f"{resolved_pct:.0%}")
    with col3:
        st.metric("Avg Duration", f"{avg_duration:.0f}s")
    with col4:
        st.metric("Reservations Today", f"{reservations_today}")

    if style_metric_cards:
        style_metric_cards()
