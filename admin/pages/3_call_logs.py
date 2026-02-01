from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from admin.components.auth import require_auth
from admin.components.tables import call_log_table, render_transcript
from src.db.models import CallOutcome, DetectedLanguage
from src.db.repositories.calls import CallLogRepository
from src.db.session import get_sync_session

st.set_page_config(page_title="Call Logs | Vartalaap", page_icon="V", layout="wide")


@require_auth
def main() -> None:
    st.title("Call Logs")

    col1, col2, col3 = st.columns(3)
    with col1:
        outcome_filter = st.selectbox(
            "Outcome",
            ["all", *[o.value for o in CallOutcome]],
        )
    with col2:
        language_filter = st.selectbox(
            "Language",
            ["all", *[l.value for l in DetectedLanguage]],
        )
    with col3:
        date_range = st.date_input(
            "Date Range",
            [date.today() - timedelta(days=7), date.today()],
        )

    start_date = None
    end_date = None
    if isinstance(date_range, (list, tuple)) and date_range:
        start_date = date_range[0]
        if len(date_range) > 1:
            end_date = date_range[1]

    with get_sync_session() as session:
        repo = CallLogRepository(session)
        call_logs = repo.list(
            outcome=None if outcome_filter == "all" else CallOutcome(outcome_filter),
            language=None if language_filter == "all" else DetectedLanguage(language_filter),
            start_date=start_date,
            end_date=end_date,
            limit=200,
        )

        call_log_table(call_logs)

        st.divider()
        st.subheader("Call Details")
        if call_logs:
            call_ids = [c.id for c in call_logs]
            selected_id = st.selectbox("Select Call", call_ids)
            selected = repo.get_by_id(selected_id)

            if selected:
                outcome_label = selected.outcome.value if selected.outcome else "-"
                st.caption(
                    f"Outcome: {outcome_label} | Duration: {selected.duration_seconds or 0}s"
                )
                st.subheader("Transcript")
                render_transcript(selected.transcript)
                st.subheader("Extracted Info")
                st.json(selected.extracted_info or "{}")
        else:
            st.info("No calls found for the selected filters.")


if __name__ == "__main__":
    main()
