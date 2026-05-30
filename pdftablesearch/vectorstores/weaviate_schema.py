"""Weaviate collection schema helpers."""

from __future__ import annotations

from typing import Any

from pdftablesearch.vectorstores.weaviate_client import get_weaviate_config
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


def _vector_create_kwargs() -> dict[str, Any]:
    """Return collection-create kwargs for self-provided vectors."""
    from weaviate.classes.config import Configure

    vectors = getattr(Configure, "Vectors", None)
    if vectors is not None and hasattr(vectors, "self_provided"):
        return {"vector_config": vectors.self_provided()}
    return {"vectorizer_config": Configure.Vectorizer.none()}


def _property(name: str, data_type: Any, *, searchable: bool = False) -> Any:
    from weaviate.classes.config import Property

    return Property(
        name=name,
        data_type=data_type,
        index_filterable=True,
        index_searchable=searchable,
    )


def _common_properties() -> list[Any]:
    from weaviate.classes.config import DataType

    return [
        _property("doc_hash", DataType.TEXT),
        _property("session_id", DataType.TEXT),
        _property("collection_name", DataType.TEXT),
        _property("document_name", DataType.TEXT),
        _property("source_pdf", DataType.TEXT),
        _property("table_id", DataType.TEXT),
        _property("chunk_index", DataType.INT),
        _property("page_number", DataType.INT),
        _property("page_content", DataType.TEXT, searchable=True),
        _property("metadata_json", DataType.TEXT),
    ]


def ensure_pdf_collections(client: Any | None = None) -> None:
    """Create PDF table/chunk collections if they do not already exist."""
    from pdftablesearch.vectorstores.weaviate_client import get_weaviate_client

    config = get_weaviate_config()
    _client = client or get_weaviate_client()
    for collection_name in (config["table_collection"], config["chunk_collection"]):
        if _client.collections.exists(collection_name):
            continue

        create_kwargs: dict[str, Any] = {
            "name": collection_name,
            "properties": _common_properties(),
        }
        create_kwargs.update(_vector_create_kwargs())

        _client.collections.create(**create_kwargs)
        logger.info("Created Weaviate collection %s", collection_name)
