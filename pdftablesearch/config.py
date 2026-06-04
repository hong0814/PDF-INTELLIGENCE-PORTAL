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

from typing import Optional

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

    pdf_portal_host: str = "127.0.0.1"
    pdf_portal_port: int = 8111
    pdf_portal_ui_port: int = 8110
    pdf_portal_hybrid_port: int = 8112

    # -- Web Auth -------------------------------------------------------------

    auth_enabled: bool = True
    auth_idle_timeout_seconds: int = 600
    auth_warn_before_seconds: int = 60
    auth_session_ttl_seconds: int = 3600
    auth_cookie_secure: bool = False
    auth_dev_users: str = "123456:1234:Developer User:user,admin:admin:Administrator:admin"
    auth_pre_auth_ttl_seconds: int = 300
    auth_otp_code: str = "123456"

    ldap_server: Optional[str] = None
    ldap_base_dn: str = "DC=hc,DC=com"
    ldap_bind_dn: Optional[str] = None
    ldap_bind_password: Optional[str] = None
    ldap_user_filter: str = "(uid={username})"
    ldap_name_attr: str = "cn"
    ldap_department_attr: str = "departmentNumber"
    ldap_roles_attr: str = "memberOf"

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

    # -- Vector Backend -------------------------------------------------------

    vector_backend: str = "weaviate"

    # -- Weaviate -------------------------------------------------------------

    weaviate_host: str = "127.0.0.1"
    weaviate_port: int = 8113
    weaviate_grpc_port: int = 8114
    weaviate_use_embedded: bool = True
    weaviate_data_dir: str = "./db/weaviate"
    weaviate_cluster_hostname: str = "Embedded_at_50851"
    weaviate_table_collection: str = "PdfTable"
    weaviate_chunk_collection: str = "PdfChunk"
    weaviate_hybrid_alpha: float = 0.6
    weaviate_search_mode: str = "vector"

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
