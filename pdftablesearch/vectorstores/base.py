"""Shared vector store backend contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple

from langchain_core.documents import Document


class VectorStoreBackend(Protocol):
    """Protocol implemented by all table vector store backends."""

    embeddings: Any
    persist_dir: str
    collection_name: str

    @property
    def vectorstore(self) -> Any:
        """Return the backend-native vector store object."""
        ...

    @property
    def is_initialized(self) -> bool:
        """Return whether the backend has an initialized collection."""
        ...

    def add_documents(self, documents: List[Document], skip_existing: bool = True) -> List[str]:
        """Add documents and return backend object IDs."""
        ...

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Return matching documents with lower-is-better distance scores."""
        ...

    def list_documents(self, limit: Optional[int] = None) -> List[Document]:
        """Return documents stored in the logical collection."""
        ...

    def delete_where(self, filter_metadata: Dict[str, Any]) -> int:
        """Delete documents matching exact metadata filters and return a count."""
        ...

    def clear_collection(self) -> None:
        """Delete all objects in the logical collection."""
        ...

    def get_document_count(self) -> int:
        """Return the number of documents in the logical collection."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return backend collection stats."""
        ...

    def reset(self) -> None:
        """Delete the vector store and all indexed data for this logical collection."""
        ...
