"""Admin tables with PII masking."""

from __future__ import annotations

import json
from typing import Iterable

import streamlit as st

from src.security.crypto import decrypt_phone, mask_phone


def _mask_encrypted_phone(encrypted_phone: str | None) -> str:
    if not encrypted_phone:
        return "-"
    try:
        phone = decrypt_phone(encrypted_phone)
        return mask_phone(phone)
    except Exception:
        return "[decrypt error]"


def reservation_table(reservations: Iterable) -> None:
    """Render reservations table with masked PII."""
    rows = []
    for r in reservations:
        rows.append(
            {
                "ID": f"{r.id[:8]}...",
                "Date": r.reservation_date,
                "Time": r.reservation_time,
                "Party": r.party_size,
                "Name": r.customer_name or "-",
                "Phone": _mask_encrypted_phone(r.customer_phone_encrypted),
                "Status": r.status.value if hasattr(r.status, "value") else r.status,
                "WhatsApp": "yes" if r.whatsapp_sent else "-",
            }
        )

    if not rows:
        st.info("No reservations found")
        return

    st.dataframe(rows, use_container_width=True, hide_index=True)


def call_log_table(call_logs: Iterable) -> None:
    """Render call logs table."""
    rows = []
    for c in call_logs:
        rows.append(
            {
                "ID": f"{c.id[:8]}...",
                "Start": c.call_start.isoformat(timespec="seconds") if c.call_start else "-",
                "Duration": f"{c.duration_seconds or 0}s",
                "Language": c.detected_language.value if c.detected_language else "-",
                "Outcome": c.outcome.value if c.outcome else "-",
                "Consent": c.consent_type.value if c.consent_type else "-",
            }
        )

    if not rows:
        st.info("No call logs found")
        return

    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_transcript(transcript_json: str | None) -> None:
    """Render transcript from JSON string."""
    if not transcript_json:
        st.info("No transcript available")
        return

    try:
        turns = json.loads(transcript_json)
    except json.JSONDecodeError:
        st.code(transcript_json)
        return

    for turn in turns:
        speaker = turn.get("speaker", "unknown").lower()
        text = turn.get("transcript", "")
        if speaker in {"caller", "user"}:
            st.markdown(f"**Caller:** {text}")
        else:
            st.markdown(f"**Bot:** {text}")
