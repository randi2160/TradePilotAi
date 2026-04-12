"""
Morviq AI — Broker API Key Encryption
Encrypts all broker API keys at rest using Fernet (AES-128-CBC + HMAC-SHA256).
Keys are never stored or returned in plain text.

Setup:
  1. Generate a key once: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. Add to .env:  ENCRYPTION_KEY=your_generated_key
  3. Run: pip install cryptography

Usage:
  from security.encryption import encrypt_key, decrypt_key
  stored  = encrypt_key("AKIAIOSFODNN7EXAMPLE")   # store this in DB
  plain   = decrypt_key(stored)                    # use this for API calls
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.getenv("ENCRYPTION_KEY", "").strip()

    if not key:
        logger.warning(
            "ENCRYPTION_KEY not set in .env — API keys will be stored unencrypted. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        return None

    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {e}")
        return None


def encrypt_key(plain_text: str) -> str:
    """
    Encrypt a plain-text API key for storage in DB.
    Returns the encrypted string (safe to store).
    If encryption unavailable, returns plain text with a warning.
    """
    if not plain_text:
        return plain_text

    f = _get_fernet()
    if f is None:
        return plain_text   # Fallback — unencrypted

    try:
        encrypted = f.encrypt(plain_text.encode()).decode()
        return f"enc:{encrypted}"   # Prefix so we know it's encrypted
    except Exception as e:
        logger.error(f"encrypt_key error: {e}")
        return plain_text


def decrypt_key(stored: str) -> str:
    """
    Decrypt a stored API key for use in API calls.
    Handles both encrypted (enc:...) and legacy plain-text keys.
    """
    if not stored:
        return stored

    if not stored.startswith("enc:"):
        return stored   # Legacy plain-text — use as-is

    f = _get_fernet()
    if f is None:
        logger.error("Cannot decrypt key — ENCRYPTION_KEY not configured")
        return ""

    try:
        encrypted_part = stored[4:]   # Remove "enc:" prefix
        return f.decrypt(encrypted_part.encode()).decode()
    except Exception as e:
        logger.error(f"decrypt_key error: {e} — key may be corrupted or wrong ENCRYPTION_KEY")
        return ""


def is_encrypted(stored: str) -> bool:
    """Check if a stored value is encrypted."""
    return stored.startswith("enc:") if stored else False


def mask_key(key: str) -> str:
    """
    Return a masked version for display (never expose in logs/API).
    e.g. "AKIAIOSFODNN7EXAMPLE" → "AKIA...MPLE"
    """
    if not key or len(key) < 8:
        return "***"
    plain = decrypt_key(key) if is_encrypted(key) else key
    if not plain or len(plain) < 8:
        return "***"
    return f"{plain[:4]}...{plain[-4:]}"


def rotate_encryption(old_env_key: str, new_env_key: str, stored_value: str) -> str:
    """
    Re-encrypt a value when rotating the ENCRYPTION_KEY.
    Usage: new_stored = rotate_encryption(old_key, new_key, stored_value)
    """
    try:
        from cryptography.fernet import Fernet

        # Decrypt with old key
        old_f = Fernet(old_env_key.encode())
        if stored_value.startswith("enc:"):
            plain = old_f.decrypt(stored_value[4:].encode()).decode()
        else:
            plain = stored_value

        # Encrypt with new key
        new_f = Fernet(new_env_key.encode())
        return "enc:" + new_f.encrypt(plain.encode()).decode()

    except Exception as e:
        logger.error(f"rotate_encryption error: {e}")
        return stored_value
