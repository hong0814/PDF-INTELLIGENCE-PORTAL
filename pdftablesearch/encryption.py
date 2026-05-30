"""ChromaDB content encryption layer for PDFTableSearch.

Provides optional Fernet encryption/decryption for document page_content
stored in ChromaDB. Encryption is disabled by default — set the env var
``PDFTABLE_ENCRYPTION_ENABLED=true`` to activate.

The encryption key is resolved from:
1. ``PDFTABLE_ENCRYPTION_KEY`` environment variable
2. ``~/.pdftablesearch/fernet.key`` file (auto-generated on first use)

When encryption is enabled, documents are stored with:
- ``page_content``: encrypted ciphertext
- ``metadata._encrypted``: ``True`` marker

Search results are automatically decrypted.  If encryption is disabled all
existing plaintext documents continue to work.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet

_ENV_ENABLED = "PDFTABLE_ENCRYPTION_ENABLED"
_ENV_KEY = "PDFTABLE_ENCRYPTION_KEY"
_METADATA_MARKER = "_encrypted"
_KEY_DIR = Path.home() / ".pdftablesearch"
_KEY_FILE = _KEY_DIR / "fernet.key"


def is_encryption_enabled() -> bool:
    """Return True when content encryption is active (default: on).

    Set ``PDFTABLE_ENCRYPTION_ENABLED=false`` to disable.
    """
    val = os.getenv(_ENV_ENABLED, "true").strip().lower()
    return val in ("1", "true", "yes", "on")


def is_encrypted_metadata(metadata: dict) -> bool:
    """Check whether a document's metadata indicates encrypted content."""
    return bool(metadata.get(_METADATA_MARKER))


def encrypt_text(text: str) -> str:
    """Encrypt *text* with the configured Fernet key.

    Raises RuntimeError when encryption is enabled but no key is configured.
    """
    return _get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(encrypted_text: str) -> str:
    """Decrypt *encrypted_text* (must have been produced by ``encrypt_text``)."""
    return _get_fernet().decrypt(encrypted_text.encode("utf-8")).decode("utf-8")


def ensure_encryption_key() -> str:
    """Generate and persist a new Fernet key if none exists.

    Returns the key string.  Intended for development setup; in production
    the key should be provided via ``PDFTABLE_ENCRYPTION_KEY`` env var.
    """
    key = _resolve_key()
    if key is not None:
        return key
    key = Fernet.generate_key().decode("utf-8")
    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key, encoding="utf-8")
    _KEY_FILE.chmod(0o600)
    return key


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _resolve_key() -> str | None:
    env_key = os.getenv(_ENV_KEY)
    if env_key:
        return env_key.strip()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text(encoding="utf-8").strip()
    if is_encryption_enabled():
        key = Fernet.generate_key().decode("utf-8")
        _KEY_DIR.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_text(key, encoding="utf-8")
        _KEY_FILE.chmod(0o600)
        return key
    return None


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    if not is_encryption_enabled():
        raise RuntimeError("Encryption is not enabled. Set PDFTABLE_ENCRYPTION_ENABLED=true")
    key = _resolve_key()
    if key is None:
        raise RuntimeError(
            "No encryption key configured. Set PDFTABLE_ENCRYPTION_KEY or run "
            "pdftablesearch.encryption.ensure_encryption_key() to generate one."
        )
    _fernet = Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    return _fernet
