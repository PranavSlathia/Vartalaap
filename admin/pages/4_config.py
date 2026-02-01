from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
import yaml

from admin.components.auth import require_auth
from src.db.models import AuditAction, AuditLog
from src.db.session import get_sync_session

st.set_page_config(page_title="Config | Vartalaap", page_icon="V", layout="wide")

CONFIG_PATH = Path("config/business/himalayan_kitchen.yaml")


@require_auth
def main() -> None:
    st.title("Configuration")
    st.caption("Edit business profile and reservation rules.")

    if not CONFIG_PATH.exists():
        st.error(f"Config file not found: {CONFIG_PATH}")
        return

    with CONFIG_PATH.open() as f:
        config = yaml.safe_load(f) or {}

    original_config = json.loads(json.dumps(config))

    business = config.get("business", {})
    rules = config.get("reservation_rules", {})

    tab1, tab2, tab3 = st.tabs(["Business Info", "Operating Hours", "Reservation Rules"])

    with tab1:
        business["name"] = st.text_input("Business Name", business.get("name", ""))
        business["type"] = st.text_input("Business Type", business.get("type", "restaurant"))
        business["timezone"] = st.text_input("Timezone", business.get("timezone", "Asia/Kolkata"))

    with tab2:
        st.caption("Use 24h format: HH:MM-HH:MM or 'closed'")
        hours = business.get("operating_hours", {})
        for day in [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]:
            hours[day] = st.text_input(day.capitalize(), hours.get(day, "closed"))
        business["operating_hours"] = hours

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            rules["min_advance_booking_mins"] = st.number_input(
                "Min advance booking (mins)",
                value=int(rules.get("min_advance_booking_mins", 30)),
            )
            rules["max_advance_booking_days"] = st.number_input(
                "Max advance booking (days)",
                value=int(rules.get("max_advance_booking_days", 30)),
            )
            rules["min_party_size"] = st.number_input(
                "Min party size",
                value=int(rules.get("min_party_size", 1)),
            )
        with col2:
            rules["max_phone_party_size"] = st.number_input(
                "Max party size (phone)",
                value=int(rules.get("max_phone_party_size", 10)),
            )
            rules["total_seats"] = st.number_input(
                "Total seats",
                value=int(rules.get("total_seats", 40)),
            )
            rules["dining_window_mins"] = st.number_input(
                "Dining window (mins)",
                value=int(rules.get("dining_window_mins", 90)),
            )
            rules["buffer_between_bookings_mins"] = st.number_input(
                "Buffer between bookings (mins)",
                value=int(rules.get("buffer_between_bookings_mins", 15)),
            )

        config["reservation_rules"] = rules

    config["business"] = business

    if st.button("Save Configuration", type="primary"):
        with CONFIG_PATH.open("w") as f:
            yaml.safe_dump(config, f, sort_keys=False)

        with get_sync_session() as session:
            audit = AuditLog(
                action=AuditAction.config_update,
                admin_user=st.session_state.get("username", "admin"),
                timestamp=datetime.now(UTC),
                details=json.dumps({"before": original_config, "after": config}),
            )
            session.add(audit)

        st.success("Configuration saved")


if __name__ == "__main__":
    main()
