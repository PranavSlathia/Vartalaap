# /admin - Streamlit Admin UI Development

## Context

You are working on **Vartalaap**, a voice bot platform for local Indian businesses.

**Tech Stack Reference:** `docs/TECH_STACK.md` (Section 10)
**PRD Reference:** `docs/PRD.md` (Section 8.3, 8.4)

## Stack Summary

- **Framework:** Streamlit 1.41.x
- **Extras:** streamlit-extras 0.4.x (metrics, cards)
- **Auth:** streamlit-authenticator 0.3.x
- **Deployment:** Subdomain `admin.vartalaap.yourdomain.com` (NOT /admin/* path)

## File Structure

```
admin/
├── __init__.py
├── app.py                      # Main entry point
├── pages/
│   ├── 1_dashboard.py          # Overview metrics
│   ├── 2_reservations.py       # Reservation management
│   ├── 3_call_logs.py          # Call history viewer
│   └── 4_config.py             # Business configuration
└── components/
    ├── __init__.py
    ├── auth.py                 # Authentication wrapper
    ├── metrics.py              # Reusable metric cards
    └── tables.py               # PII-masked data tables
```

## Deployment Note

**IMPORTANT:** Streamlit runs on its own subdomain, not under /admin/* path.

```caddyfile
# Caddyfile
admin.vartalaap.yourdomain.com {
    reverse_proxy admin:8501
}
```

This avoids Streamlit's WebSocket/static asset path issues.

## Authentication Pattern

**From PRD Section 8.4:**
- Single admin user (MVP)
- Password hashed with bcrypt in `.env`
- 30-minute session timeout

```python
# admin/components/auth.py
import streamlit as st
import streamlit_authenticator as stauth
import bcrypt
import os

def check_auth() -> bool:
    """Check if user is authenticated. Returns True if logged in."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Show login form
    with st.form("login"):
        st.subheader("Vartalaap Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if _verify_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid credentials")

    return False

def _verify_credentials(username: str, password: str) -> bool:
    """Verify against env var credentials."""
    expected_username = os.environ.get("ADMIN_USERNAME", "admin")
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")

    if username != expected_username:
        return False

    return bcrypt.checkpw(password.encode(), password_hash.encode())

def require_auth(func):
    """Decorator to require authentication."""
    def wrapper(*args, **kwargs):
        if not check_auth():
            st.stop()
        return func(*args, **kwargs)
    return wrapper
```

## Page Template

```python
# admin/pages/2_reservations.py
import streamlit as st
from admin.components.auth import require_auth
from admin.components.tables import reservation_table
from src.db.session import get_sync_session
from src.db.repositories.reservations import ReservationRepository
from datetime import date, timedelta

st.set_page_config(
    page_title="Reservations | Vartalaap Admin",
    page_icon="📅",
    layout="wide",
)

@require_auth
def main():
    st.title("📅 Reservations")

    # Date filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From", date.today())
    with col2:
        end_date = st.date_input("To", date.today() + timedelta(days=7))

    # Fetch data
    with get_sync_session() as session:
        repo = ReservationRepository(session)
        reservations = repo.get_by_date_range(
            business_id=st.session_state.get("business_id", "default"),
            start=start_date,
            end=end_date,
        )

    # Display with PII masking
    reservation_table(reservations)

if __name__ == "__main__":
    main()
```

## PII Masking (CRITICAL)

**From PRD Section 8.4 & 9.4:**

Phone numbers MUST be masked in UI: `98XXXX1234` (first 2 + last 4 digits)

```python
# admin/components/tables.py
import streamlit as st
import pandas as pd
from src.security.crypto import decrypt_phone

def mask_phone(encrypted_phone: str | None) -> str:
    """Decrypt and mask phone for display."""
    if not encrypted_phone:
        return "—"

    try:
        phone = decrypt_phone(encrypted_phone)
        # Mask: show first 2 and last 4 digits
        if len(phone) >= 6:
            return f"{phone[:2]}XXXX{phone[-4:]}"
        return "XXXX"
    except Exception:
        return "[decrypt error]"

def reservation_table(reservations: list) -> None:
    """Display reservations with masked PII."""
    if not reservations:
        st.info("No reservations found")
        return

    # Convert to DataFrame
    df = pd.DataFrame([
        {
            "ID": r.id[:8] + "...",
            "Date": r.reservation_date,
            "Time": r.reservation_time,
            "Party": r.party_size,
            "Name": r.customer_name or "—",
            "Phone": mask_phone(r.customer_phone_encrypted),
            "Status": r.status,
            "WhatsApp": "✓" if r.whatsapp_sent else "—",
        }
        for r in reservations
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)
```

## Metric Cards

```python
# admin/components/metrics.py
import streamlit as st
from streamlit_extras.metric_cards import style_metric_cards

def display_metrics(
    total_calls: int,
    resolved_pct: float,
    avg_duration: float,
    reservations_today: int,
) -> None:
    """Display dashboard metric cards."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Calls", total_calls, delta="+12 today")
    with col2:
        st.metric("Resolved", f"{resolved_pct:.0%}", delta="+2%")
    with col3:
        st.metric("Avg Duration", f"{avg_duration:.0f}s")
    with col4:
        st.metric("Reservations Today", reservations_today)

    style_metric_cards()
```

## Dashboard Page

```python
# admin/pages/1_dashboard.py
import streamlit as st
from admin.components.auth import require_auth
from admin.components.metrics import display_metrics
from datetime import date, timedelta
import plotly.express as px

st.set_page_config(
    page_title="Dashboard | Vartalaap Admin",
    page_icon="📊",
    layout="wide",
)

@require_auth
def main():
    st.title("📊 Dashboard")
    st.caption(f"Business: Himalayan Kitchen | {date.today()}")

    # Metrics row
    display_metrics(
        total_calls=156,
        resolved_pct=0.87,
        avg_duration=45,
        reservations_today=12,
    )

    st.divider()

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Calls by Outcome")
        # Pie chart of call outcomes
        outcomes = {"Resolved": 87, "Fallback": 10, "Dropped": 3}
        fig = px.pie(values=list(outcomes.values()), names=list(outcomes.keys()))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Calls Over Time")
        # Line chart of daily calls
        # ...

if __name__ == "__main__":
    main()
```

## Call Logs Page (with Transcript Viewer)

```python
# admin/pages/3_call_logs.py
import streamlit as st
from admin.components.auth import require_auth
import json

@require_auth
def main():
    st.title("📞 Call Logs")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        outcome_filter = st.selectbox(
            "Outcome",
            ["All", "resolved", "fallback", "dropped", "error"]
        )
    with col2:
        language_filter = st.selectbox(
            "Language",
            ["All", "hindi", "english", "hinglish"]
        )
    with col3:
        date_range = st.date_input("Date Range", [])

    # Call list
    # ... fetch calls with filters

    # Selected call detail
    if selected_call:
        with st.expander("Transcript", expanded=True):
            transcript = json.loads(selected_call.transcript or "[]")
            for turn in transcript:
                speaker = turn.get("speaker", "unknown")
                text = turn.get("transcript", "")

                if speaker == "caller":
                    st.markdown(f"**🧑 Caller:** {text}")
                else:
                    st.markdown(f"**🤖 Bot:** {text}")

        # Extracted info
        st.subheader("Extracted Information")
        info = json.loads(selected_call.extracted_info or "{}")
        st.json(info)

if __name__ == "__main__":
    main()
```

## Config Editor Page

```python
# admin/pages/4_config.py
import streamlit as st
from admin.components.auth import require_auth
import yaml

@require_auth
def main():
    st.title("⚙️ Configuration")

    # Load current config
    with open("config/business/himalayan_kitchen.yaml") as f:
        config = yaml.safe_load(f)

    # Tabs for different config sections
    tab1, tab2, tab3 = st.tabs(["Business Info", "Reservation Rules", "Greeting"])

    with tab1:
        st.subheader("Business Information")
        config["name"] = st.text_input("Name", config.get("name", ""))
        config["phone"] = st.text_input("Phone", config.get("phone", ""))
        config["address"] = st.text_area("Address", config.get("address", ""))

    with tab2:
        st.subheader("Reservation Rules")
        rules = config.get("reservation_rules", {})

        col1, col2 = st.columns(2)
        with col1:
            rules["min_advance_booking_mins"] = st.number_input(
                "Min advance booking (mins)",
                value=rules.get("min_advance_booking_mins", 30)
            )
            rules["max_phone_party_size"] = st.number_input(
                "Max party size (phone booking)",
                value=rules.get("max_phone_party_size", 10)
            )
        with col2:
            rules["total_seats"] = st.number_input(
                "Total seats",
                value=rules.get("total_seats", 40)
            )
            rules["dining_window_mins"] = st.number_input(
                "Dining window (mins)",
                value=rules.get("dining_window_mins", 90)
            )

        config["reservation_rules"] = rules

    with tab3:
        st.subheader("Greeting Message")
        config["greeting"] = st.text_area(
            "Greeting",
            config.get("greeting", ""),
            height=150,
        )
        st.info("Include transcription notice for consent compliance")

    # Save button
    if st.button("Save Configuration", type="primary"):
        with open("config/business/himalayan_kitchen.yaml", "w") as f:
            yaml.dump(config, f, allow_unicode=True)
        st.success("Configuration saved!")

        # Log audit
        # ... log to audit_logs table

if __name__ == "__main__":
    main()
```

## Running Locally

```bash
# Development
cd admin
uv run streamlit run app.py --server.port 8501

# With hot reload
uv run streamlit run app.py --server.runOnSave true
```

## Docker Setup

```dockerfile
# Dockerfile.admin
FROM python:3.12.8-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra admin

COPY src/ ./src/
COPY admin/ ./admin/
COPY config/ ./config/

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "admin/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true"]
```

## Features Checklist (from PRD 8.3)

- [ ] Business profile editor
- [ ] Menu/services manager
- [ ] Operating hours configuration
- [ ] Voice settings (accent, style)
- [ ] Greeting message customization
- [ ] Fallback rules configuration
- [ ] Call logs viewer (with PII masking)
- [ ] Basic analytics dashboard
- [ ] Reservation management view

## Security Reminders

1. **PII Masking:** Always mask phone numbers as `98XXXX1234`
2. **Auth Required:** Every page must use `@require_auth` decorator
3. **Session Timeout:** 30 minutes (handled by Streamlit session)
4. **Audit Logging:** Log all config changes to `audit_logs` table
5. **No API Keys in UI:** Never display API keys, only show "configured" status
