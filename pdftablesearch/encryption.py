"""ChromaDB 콘텐츠 암호화 레이어.

ChromaDB에 저장되는 문서 page_content에 대한 Fernet 암호화/복호화를 제공한다.
암호화는 기본적으로 활성화되어 있으며, 비활성화하려면 환경변수
``PDFTABLE_ENCRYPTION_ENABLED=false`` 를 설정한다.

암호화 키는 다음 순서로 확인된다:
1. ``PDFTABLE_ENCRYPTION_KEY`` 환경변수
2. ``~/.pdftablesearch/fernet.key`` 파일 (최초 사용 시 자동 생성)

암호화 활성화 시 문서는 다음과 같이 저장된다:
- ``page_content``: 암호화된 암호문
- ``metadata._encrypted``: ``True`` 마커

검색 결과는 자동으로 복호화된다. 암호화 비활성화 시에도
기존 평문 문서는 그대로 사용할 수 있다.
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
    """콘텐츠 암호화 활성화 여부를 반환한다. 기본값: 활성화.

    비활성화하려면 ``PDFTABLE_ENCRYPTION_ENABLED=false`` 설정.
    """
    val = os.getenv(_ENV_ENABLED, "true").strip().lower()
    return val in ("1", "true", "yes", "on")


def is_encrypted_metadata(metadata: dict) -> bool:
    """문서 메타데이터가 암호화된 콘텐츠임을 나타내는지 확인한다."""
    return bool(metadata.get(_METADATA_MARKER))


def encrypt_text(text: str) -> str:
    """설정된 Fernet 키로 *text*를 암호화한다.

    암호화가 활성화되었으나 키가 없으면 RuntimeError 발생.
    """
    return _get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_text(encrypted_text: str) -> str:
    """``encrypt_text`` 로 암호화된 *encrypted_text*를 복호화한다."""
    return _get_fernet().decrypt(encrypted_text.encode("utf-8")).decode("utf-8")


def ensure_encryption_key() -> str:
    """Fernet 키가 없으면 새로 생성하여 저장한다.

    키 문자열을 반환한다. 개발 환경용이며, 프로덕션에서는
    ``PDFTABLE_ENCRYPTION_KEY`` 환경변수로 키를 제공해야 한다.
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
# 내부 함수
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
