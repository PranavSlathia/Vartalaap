"""Authentication utilities for admin access."""

from __future__ import annotations

import os
from typing import Any

import bcrypt

from src.logging_config import get_logger

logger: Any = get_logger(__name__)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        logger.exception("Password verification failed")
        return False


def check_admin_credentials(username: str, password: str) -> bool:
    """Validate credentials against env-based admin user."""
    expected_username = os.environ.get("ADMIN_USERNAME", "admin")
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")

    if not password_hash:
        logger.error("ADMIN_PASSWORD_HASH is not set")
        return False

    if username != expected_username:
        return False

    return verify_password(password, password_hash)
