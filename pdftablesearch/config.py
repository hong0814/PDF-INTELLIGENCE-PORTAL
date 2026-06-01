"""Unified configuration for PDFTableSearch.

Loads settings from environment variables and ``.env`` files using
`pydantic-settings <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>`_.
Every field has a sensible default matching the existing hardcoded values
scattered across the codebase so that the migration is fully backward-compatible.

Usage::

    from pdftablesearch.config import get_settings

    settings = get_settings()
    print(settings.zai_llm_model)
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for PDFTableSearch.

    All fields can be overridden via environment variables of the same name
    (case-insensitive) or through a ``.env`` file in the project root.

    Attributes are grouped by subsystem for readability.
    """

    # -- API Configuration ----------------------------------------------------

    zai_api_key: Optional[str] = None
    zai_embedding_endpoint: str = "https://api.z.ai/api/embeddings"
    zai_embedding_model: str = "embedding-3"

    # -- Ollama LLM -----------------------------------------------------------
    ollama_api_key: Optional[str] = None
    zai_llm_endpoint: str = "https://ollama.com/v1"
    zai_llm_model: str = "gpt-oss:120b"
    zai_llm_rerank_model: str = "gpt-oss:120b"

    # -- Local Embeddings -----------------------------------------------------

    local_embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"

    # -- ChromaDB -------------------------------------------------------------

    chroma_persist_dir: str = "./.chroma"
    chroma_collection_name: str = "pdf_tables"

    # -- Processing -----------------------------------------------------------

    max_file_size_mb: int = 100
    api_timeout_seconds: int = 30
    api_max_retries: int = 3
    embedding_batch_size: int = 20
    parallel_workers: int = 4

    # -- Search ---------------------------------------------------------------

    smart_search_top_k: int = 20
    reranker_top_k: int = 10
    content_max_length: int = 500

    # -- Caching --------------------------------------------------------------

    cache_enabled: bool = True
    cache_dir: str = "./.cache"
    llm_cache_ttl_seconds: int = 86400

    # -- Logging --------------------------------------------------------------

    log_level: str = "INFO"

    # -- Runtime --------------------------------------------------------------

    app_env: str = "dev"
    cors_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    # -- Authentication / LDAP -----------------------------------------------

    ldap_server_url: str = ""
    ldap_use_tls: bool = False
    ldap_base_dn: str = ""
    ldap_service_bind_dn: str = ""
    ldap_service_bind_password: str = ""
    ldap_user_filter: str = "(uid={username})"
    ldap_attr_name: str = "cn"
    ldap_attr_email: str = "mail"
    ldap_attr_department: str = "departmentNumber"
    ldap_attr_role: str = "title"
    auth_secret_key: str = "dev-secret-change-me"
    auth_token_expire_hours: int = 8
    auth_cookie_name: str = "auth_token"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton.

    Creates the instance on the first call; subsequent calls return the
    same object so that ``.env`` is parsed only once.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
