"""Weaviate vector store backend."""

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
        ...

    @property
    def is_initialized(self) -> bool:
        ...

    def add_documents(self, documents: List[Document], skip_existing: bool = True) -> List[str]:
        ...

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        ...

    def list_documents(self, limit: Optional[int] = None) -> List[Document]:
        ...

    def delete_where(self, filter_metadata: Dict[str, Any]) -> int:
        ...

    def clear_collection(self) -> None:
        ...

    def get_document_count(self) -> int:
        ...

    def get_stats(self) -> Dict[str, Any]:
        ...

    def reset(self) -> None:
        ...


def create_vector_store(
    embeddings: Optional[Any] = None,
    persist_dir: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> Any:
    from pdftablesearch.vectorstores.weaviate_store import WeaviateTableVectorStore
    return WeaviateTableVectorStore(
        embeddings=embeddings,
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
