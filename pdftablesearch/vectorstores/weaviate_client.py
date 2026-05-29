"""Weaviate client connection management."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pdftablesearch.config import get_settings
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


def get_weaviate_config() -> dict[str, Any]:
    """Return Weaviate settings with environment overrides applied."""
    settings = get_settings()
    return {
        "host": os.getenv("WEAVIATE_HOST", settings.weaviate_host),
        "port": int(os.getenv("WEAVIATE_PORT", str(settings.weaviate_port))),
        "grpc_port": int(
            os.getenv("WEAVIATE_GRPC_PORT", str(settings.weaviate_grpc_port))
        ),
        "use_embedded": os.getenv(
            "WEAVIATE_USE_EMBEDDED",
            str(settings.weaviate_use_embedded),
        ).lower()
        == "true",
        "data_dir": os.getenv("WEAVIATE_DATA_DIR", settings.weaviate_data_dir),
        "table_collection": os.getenv(
            "WEAVIATE_TABLE_COLLECTION",
            settings.weaviate_table_collection,
        ),
        "chunk_collection": os.getenv(
            "WEAVIATE_CHUNK_COLLECTION",
            settings.weaviate_chunk_collection,
        ),
        "hybrid_alpha": float(
            os.getenv("WEAVIATE_HYBRID_ALPHA", str(settings.weaviate_hybrid_alpha))
        ),
        "search_mode": os.getenv("WEAVIATE_SEARCH_MODE", settings.weaviate_search_mode),
        "cluster_hostname": os.getenv(
            "WEAVIATE_CLUSTER_HOSTNAME",
            settings.weaviate_cluster_hostname,
        ),
    }


@lru_cache(maxsize=1)
def get_weaviate_client() -> Any:
    """Return a cached Weaviate client for the configured instance."""
    import weaviate
    from weaviate.classes.init import Auth

    config = get_weaviate_config()
    host = config["host"]
    port = config["port"]
    grpc_port = config["grpc_port"]

    if config["use_embedded"]:
        logger.info(
            "Connecting to local Weaviate at %s:%d (gRPC %d)",
            host,
            port,
            grpc_port,
        )
        return weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)

    connect_kwargs: dict[str, Any] = {
        "http_host": host,
        "http_port": port,
        "http_secure": False,
        "grpc_host": host,
        "grpc_port": grpc_port,
        "grpc_secure": False,
    }
    api_key = os.getenv("WEAVIATE_API_KEY", "").strip()
    if api_key:
        connect_kwargs["auth_credentials"] = Auth.api_key(api_key)

    logger.info("Connecting to Weaviate at %s:%d (gRPC %d)", host, port, grpc_port)
    return weaviate.connect_to_custom(**connect_kwargs)


def close_weaviate_client() -> None:
    """Close and clear the cached Weaviate client."""
    client = None
    if get_weaviate_client.cache_info().currsize:
        client = get_weaviate_client()
    if client is not None:
        try:
            client.close()
        except Exception:
            logger.debug("Ignoring Weaviate close failure", exc_info=True)
    get_weaviate_client.cache_clear()
