"""PDFTableSearch 환경설정 (pydantic-settings 기반)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PDFTableSearch 중앙 설정.

    모든 필드는 동일 이름의 환경변수(대소문자 구분 없음) 또는
    프로젝트 루트의 ``.env`` 파일로 오버라이드할 수 있다.
    """

    # -- API 설정 ------------------------------------------------------------

    zai_api_key: Optional[str] = None
    zai_embedding_endpoint: str = "https://api.z.ai/api/embeddings"
    zai_embedding_model: str = "embedding-3"

    # -- Ollama LLM ----------------------------------------------------------

    ollama_api_key: Optional[str] = None
    zai_llm_endpoint: str = "https://ollama.com/v1"
    zai_llm_model: str = "gpt-oss:120b"
    zai_llm_rerank_model: str = "gpt-oss:120b"

    # -- 로컬 임베딩 ---------------------------------------------------------

    local_embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"

    # -- ChromaDB ------------------------------------------------------------

    chroma_persist_dir: str = "./.chroma"
    chroma_collection_name: str = "pdf_tables"

    # -- 처리 설정 -----------------------------------------------------------

    max_file_size_mb: int = 100
    api_timeout_seconds: int = 30
    api_max_retries: int = 3
    embedding_batch_size: int = 20
    parallel_workers: int = 4

    # -- 검색 설정 -----------------------------------------------------------

    smart_search_top_k: int = 20
    reranker_top_k: int = 10
    content_max_length: int = 500

    # -- 캐시 설정 -----------------------------------------------------------

    cache_enabled: bool = True
    cache_dir: str = "./.cache"
    llm_cache_ttl_seconds: int = 86400

    # -- 로깅 설정 -----------------------------------------------------------

    log_level: str = "INFO"

    # -- 런타임 --------------------------------------------------------------

    app_env: str = "dev"
    cors_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    # -- 인증 / LDAP ---------------------------------------------------------

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

    # -- Weaviate ------------------------------------------------------------

    weaviate_host: str = "localhost"
    weaviate_port: int = 8079
    weaviate_grpc_port: int = 50050
    weaviate_use_embedded: bool = True
    weaviate_data_dir: str = "/tmp/weaviate-data"
    weaviate_table_collection: str = "PdfTables"
    weaviate_chunk_collection: str = "DocChunks"
    weaviate_hybrid_alpha: float = 0.5
    weaviate_search_mode: str = "vector"
    weaviate_cluster_hostname: str = "pdf-portal-weaviate"

    # -- 벡터 스토어 백엔드 --------------------------------------------------

    vector_backend: str = "chroma"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """캐시된 :class:`Settings` 싱글톤을 반환한다.

    첫 호출 시 인스턴스를 생성하고, 이후 호출은 동일 객체를 반환한다.
    ``.env`` 파일은 한 번만 파싱된다.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
