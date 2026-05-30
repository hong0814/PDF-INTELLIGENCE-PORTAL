"""Backend-selecting vector store facade for PDFTableSearch."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Type

from pdftablesearch.config import get_settings
from pdftablesearch.vectorstores.base import VectorStoreBackend
from pdftablesearch.vectorstores.chroma_store import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_PERSIST_DIR,
    ChromaTableVectorStore,
)

_store_cache: Dict[str, VectorStoreBackend] = {}


def _selected_backend() -> str:
    return os.getenv("VECTOR_BACKEND", get_settings().vector_backend).strip().lower()


def _backend_class() -> Type[VectorStoreBackend]:
    backend = _selected_backend()
    if backend == "chroma":
        return ChromaTableVectorStore
    if backend == "weaviate":
        from pdftablesearch.vectorstores.weaviate_store import WeaviateTableVectorStore

        return WeaviateTableVectorStore
    raise ValueError(f"Unsupported vector backend: {backend}")


class TableVectorStore:
    """Compatibility facade returning the configured vector store backend."""

    def __new__(
        cls,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> VectorStoreBackend:
        backend_cls = _backend_class()
        return backend_cls(
            embeddings=embeddings,
            persist_dir=persist_dir,
            collection_name=collection_name,
        )

    @classmethod
    def get_or_create(
        cls,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> VectorStoreBackend:
        """Return a cached vector store for the backend and logical location."""
        backend = _selected_backend()
        effective_persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", DEFAULT_PERSIST_DIR)
        effective_collection = collection_name or os.getenv(
            "CHROMA_COLLECTION_NAME",
            DEFAULT_COLLECTION_NAME,
        )
        key = f"{backend}:{effective_persist_dir}:{effective_collection}"
        if key not in _store_cache:
            _store_cache[key] = cls(
                embeddings=embeddings,
                persist_dir=persist_dir,
                collection_name=collection_name,
            )
        return _store_cache[key]


__all__ = ["TableVectorStore"]
