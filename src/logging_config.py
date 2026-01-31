"""Logging configuration using Loguru.

Provides structured logging with:
- Console output for development
- File rotation for production
- No PII in logs (critical for compliance)
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    enable_file: bool = True,
) -> None:
    """Configure application logging.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        enable_file: Whether to enable file logging
    """
    # Remove default handler
    logger.remove()

    # Console handler (always enabled)
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,  # Disable in production for security
    )

    # File handler (production)
    if enable_file:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)

        # Main application log
        logger.add(
            log_path / "vartalaap_{time:YYYY-MM-DD}.log",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}"
            ),
            level=level,
            rotation="100 MB",
            retention="30 days",
            compression="gz",
            backtrace=True,
            diagnose=False,  # Disabled for security in files
        )

        # Error-only log for quick debugging
        logger.add(
            log_path / "errors_{time:YYYY-MM-DD}.log",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}\n{exception}"
            ),
            level="ERROR",
            rotation="50 MB",
            retention="90 days",
            compression="gz",
            backtrace=True,
            diagnose=False,
        )

    logger.info(f"Logging initialized at {level} level")


def get_logger(name: str) -> "logger":
    """Get a logger instance with the given name.

    Usage:
        from src.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Message")
    """
    return logger.bind(name=name)


# PII filtering utilities
def mask_phone(phone: str) -> str:
    """Mask phone number for logging: 98XXXXXXXX -> 98XXXX1234.

    CRITICAL: Use this before logging any phone number.
    """
    if not phone or len(phone) < 6:
        return "XXXX"
    return f"{phone[:2]}XXXX{phone[-4:]}"


def sanitize_for_log(data: dict) -> dict:
    """Remove or mask PII from a dict before logging.

    Removes: customer_phone_encrypted, caller_id_hash
    Masks: Any field containing 'phone'
    """
    sensitive_fields = {"customer_phone_encrypted", "caller_id_hash", "phone_hash_pepper"}
    result = {}

    for key, value in data.items():
        if key in sensitive_fields:
            result[key] = "[REDACTED]"
        elif "phone" in key.lower() and isinstance(value, str):
            result[key] = mask_phone(value)
        elif isinstance(value, dict):
            result[key] = sanitize_for_log(value)
        else:
            result[key] = value

    return result
