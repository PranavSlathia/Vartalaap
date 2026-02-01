from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from admin.components.auth import require_auth
from admin.components.tables import reservation_table
from src.db.models import ReservationStatus
from src.db.repositories.reservations import ReservationRepository
from src.db.session import get_sync_session

st.set_page_config(page_title="Reservations | Vartalaap", page_icon="V", layout="wide")


@require_auth
def main() -> None:
    st.title("Reservations")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("From", date.today())
    with col2:
        end_date = st.date_input("To", date.today() + timedelta(days=7))
    with col3:
        status_filter = st.selectbox(
            "Status",
            ["all", *[status.value for status in ReservationStatus]],
        )

    with get_sync_session() as session:
        repo = ReservationRepository(session)
        reservations = repo.list_by_date_range(
            business_id="himalayan_kitchen",
            start=start_date,
            end=end_date,
            status=None if status_filter == "all" else ReservationStatus(status_filter),
        )

        reservation_table(reservations)

        st.divider()
        st.subheader("Update Reservation Status")
        if reservations:
            ids = [r.id for r in reservations]
            selected_id = st.selectbox("Reservation ID", ids)
            new_status = st.selectbox(
                "New Status",
                [status.value for status in ReservationStatus],
            )
            if st.button("Update Status", type="primary"):
                updated = repo.update_status(selected_id, ReservationStatus(new_status))
                if updated:
                    session.commit()
                    st.success("Reservation updated")
                    st.rerun()
                else:
                    st.error("Reservation not found")
        else:
            st.info("No reservations in the selected range.")


if __name__ == "__main__":
    main()
