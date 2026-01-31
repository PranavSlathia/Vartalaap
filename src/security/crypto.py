"""Cryptographic utilities for phone number handling.

Two methods for two purposes:
1. HMAC-SHA256 with global pepper - for caller deduplication (irreversible)
2. AES-256-GCM encryption - for WhatsApp delivery (reversible)

CRITICAL: Never log plaintext phone numbers. Use mask_phone() for logging.
"""

import base64
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import get_settings


def normalize_phone(phone: str) -> str:
    """Normalize phone number to last 10 digits.

    Handles various formats:
    - +91 98765 43210
    - 9876543210
    - 098765-43210

    Returns:
        Last 10 digits of the phone number.
    """
    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)
    # Take last 10 digits (Indian phone numbers)
    return digits[-10:] if len(digits) >= 10 else digits


def hash_phone_for_dedup(phone: str) -> str:
    """Create consistent hash for deduplication and opt-out tracking.

    Uses HMAC-SHA256 with a global pepper (secret key).
    Same phone always produces the same hash (with same pepper).

    Why HMAC with global pepper (not per-record salt):
    - Per-record salts make matching impossible
    - Global pepper prevents rainbow tables while allowing lookups
    - If pepper leaks: rehash all records with new pepper

    Why NOT plain SHA-256:
    - 10-digit phones = only 10 billion possibilities
    - Plain SHA-256 reversed via rainbow table in minutes

    Args:
        phone: Phone number in any format

    Returns:
        Hex-encoded HMAC-SHA256 hash
    """
    settings = get_settings()
    pepper = bytes.fromhex(settings.phone_hash_pepper.get_secret_value())
    normalized = normalize_phone(phone)

    return hmac.new(pepper, normalized.encode(), hashlib.sha256).hexdigest()


def encrypt_phone(phone: str) -> str:
    """Encrypt phone for later WhatsApp delivery using AES-256-GCM.

    The phone number is encrypted so it can be decrypted later for
    sending WhatsApp confirmations.

    Args:
        phone: Phone number in any format

    Returns:
        Base64-encoded string containing nonce + ciphertext
    """
    settings = get_settings()
    key = bytes.fromhex(settings.phone_encryption_key.get_secret_value())
    normalized = normalize_phone(phone)

    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, normalized.encode(), None)

    # Store nonce + ciphertext together
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_phone(encrypted: str) -> str:
    """Decrypt phone for WhatsApp delivery.

    Args:
        encrypted: Base64-encoded string from encrypt_phone()

    Returns:
        Decrypted phone number (normalized to 10 digits)

    Raises:
        cryptography.exceptions.InvalidTag: If decryption fails
    """
    settings = get_settings()
    key = bytes.fromhex(settings.phone_encryption_key.get_secret_value())

    data = base64.b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]

    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def mask_phone(phone: str) -> str:
    """Mask phone number for display/logging.

    Format: 98XXXX1234 (first 2 + XXXX + last 4)

    CRITICAL: Use this before logging or displaying any phone number.

    Args:
        phone: Phone number in any format

    Returns:
        Masked phone number
    """
    normalized = normalize_phone(phone)
    if len(normalized) < 6:
        return "XXXX"
    return f"{normalized[:2]}XXXX{normalized[-4:]}"


def generate_keys() -> dict[str, str]:
    """Generate new encryption key and hash pepper.

    Use this to generate values for .env file:
        python -c "from src.security.crypto import generate_keys; print(generate_keys())"

    Returns:
        Dict with phone_encryption_key and phone_hash_pepper (hex-encoded)
    """
    return {
        "phone_encryption_key": os.urandom(32).hex(),  # 64 hex chars
        "phone_hash_pepper": os.urandom(32).hex(),  # 64 hex chars
    }
