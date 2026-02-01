from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
from sqlalchemy import func, select

from admin.components.auth import require_auth
from admin.components.metrics import display_metrics
from admin.components.tables import call_log_table, reservation_table
from src.db.models import CallLog, CallOutcome, Reservation
from src.db.repositories.calls import CallLogRepository
from src.db.repositories.reservations import ReservationRepository
from src.db.session import get_sync_session

st.set_page_config(page_title="Dashboard | Vartalaap", page_icon="V", layout="wide")


@require_auth
def main() -> None:
    st.title("Dashboard")
    st.caption(f"Date: {date.today().isoformat()}")

    with get_sync_session() as session:
        # Metrics
        total_calls = session.execute(select(func.count(CallLog.id))).scalar() or 0
        resolved_calls = (
            session.execute(
                select(func.count(CallLog.id)).where(CallLog.outcome == CallOutcome.resolved)
            ).scalar()
            or 0
        )
        avg_duration = (
            session.execute(select(func.avg(CallLog.duration_seconds))).scalar() or 0
        )
        reservations_today = (
            session.execute(
                select(func.count(Reservation.id)).where(
                    Reservation.reservation_date == date.today().isoformat()
                )
            ).scalar()
            or 0
        )

        resolved_pct = (resolved_calls / total_calls) if total_calls else 0

        display_metrics(
            total_calls=total_calls,
            resolved_pct=resolved_pct,
            avg_duration=avg_duration,
            reservations_today=reservations_today,
        )

        st.divider()

        # Recent activity tables
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Upcoming Reservations")
            repo = ReservationRepository(session)
            upcoming = repo.list_by_date_range(
                business_id="himalayan_kitchen",
                start=date.today(),
                end=date.today() + timedelta(days=3),
            )
            reservation_table(upcoming)

        with col2:
            st.subheader("Recent Calls")
            calls_repo = CallLogRepository(session)
            recent_calls = calls_repo.list(limit=20)
            call_log_table(recent_calls)


if __name__ == "__main__":
    main()
