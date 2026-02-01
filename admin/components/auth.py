"""Streamlit authentication helpers for admin UI."""

from __future__ import annotations

import os
import time
from typing import Callable

import bcrypt
import streamlit as st

from src.config import get_settings
from src.logging_config import get_logger

logger = get_logger(__name__)

SESSION_TIMEOUT_SECONDS = 30 * 60


def _verify_credentials(username: str, password: str) -> bool:
    """Verify username/password against env vars."""
    expected_username = os.environ.get("ADMIN_USERNAME", "admin")
    settings = get_settings()
    password_hash = settings.admin_password_hash

    if not password_hash:
        logger.error("ADMIN_PASSWORD_HASH not configured for admin UI")
        return False

    if username != expected_username:
        return False

    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        logger.exception("Failed to verify admin password hash")
        return False


def _is_session_expired() -> bool:
    """Check if the current session has expired."""
    last_active = st.session_state.get("last_active")
    if not last_active:
        return False
    return (time.time() - last_active) > SESSION_TIMEOUT_SECONDS


def _touch_session() -> None:
    """Update last-active timestamp."""
    st.session_state.last_active = time.time()


def _logout(reason: str | None = None) -> None:
    """Clear session auth state."""
    st.session_state.authenticated = False
    st.session_state.pop("username", None)
    st.session_state.pop("last_active", None)
    if reason:
        st.info(reason)


def render_auth_sidebar() -> None:
    """Render auth info + logout in sidebar."""
    if not st.session_state.get("authenticated"):
        return
    with st.sidebar:
        st.caption(f"Logged in as {st.session_state.get('username', 'admin')}")
        if st.button("Logout", type="secondary"):
            _logout("Logged out")
            st.rerun()


def check_auth() -> bool:
    """Check if user is authenticated, render login if not."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        if _is_session_expired():
            _logout("Session expired. Please log in again.")
            return False
        _touch_session()
        return True

    with st.form("login"):
        st.subheader("Vartalaap Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if _verify_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                _touch_session()
                logger.info("Admin login successful")
                st.rerun()
            else:
                logger.warning("Admin login failed")
                st.error("Invalid credentials")

    return False


def require_auth(func: Callable) -> Callable:
    """Decorator to require authentication."""

    def wrapper(*args, **kwargs):
        if not check_auth():
            st.stop()
        render_auth_sidebar()
        return func(*args, **kwargs)

    return wrapper
