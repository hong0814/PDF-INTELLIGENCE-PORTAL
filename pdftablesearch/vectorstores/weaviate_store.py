"""Weaviate vector store backend for PDFTableSearch."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document

from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.exceptions import VectorIndexError, VectorSearchError
from pdftablesearch.utils import get_logger
from pdftablesearch.vectorstores.weaviate_client import (
    get_weaviate_client,
    get_weaviate_config,
)
from pdftablesearch.vectorstores.weaviate_schema import ensure_pdf_collections

logger = get_logger(__name__)

_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "pdftablesearch.weaviate")
_FILTERABLE_PROPERTIES = {
    "doc_hash",
    "session_id",
    "collection_name",
    "document_name",
    "source_pdf",
    "table_id",
    "chunk_index",
    "page_number",
}
_FETCH_LIMIT = 1000


class WeaviateTableVectorStore:
    """Weaviate-backed implementation of the table vector store contract."""

    def __init__(
        self,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.embeddings = embeddings or SentenceTransformerEmbeddings()
        self.persist_dir = persist_dir or os.getenv("WEAVIATE_DATA_DIR", "/tmp/weaviate-data")
        self.collection_name = collection_name or os.getenv(
            "CHROMA_COLLECTION_NAME",
            "pdf_tables",
        )
        self._config = get_weaviate_config()
        self.session_id = os.getenv("PDF_VECTOR_SESSION_ID") or self._derive_session_id(
            self.persist_dir
        )
        self._native_collection_name = self._choose_native_collection(self.collection_name)

    @staticmethod
    def _derive_session_id(persist_dir: str) -> str:
        digest = hashlib.sha256(os.path.abspath(persist_dir).encode()).hexdigest()
        return digest[:16]

    def _choose_native_collection(self, collection_name: str) -> str:
        normalized = collection_name.lower()
        if normalized.startswith("doc_chunks") or "chunk" in normalized:
            return str(self._config["chunk_collection"])
        return str(self._config["table_collection"])

    @property
    def vectorstore(self) -> Any:
        """Return the native Weaviate collection."""
        client = get_weaviate_client()
        if not client.collections.exists(self._native_collection_name):
            raise VectorIndexError(
                "No vector store found. Add documents first using add_documents()."
            )
        return client.collections.get(self._native_collection_name)

    @property
    def is_initialized(self) -> bool:
        """Check whether the native Weaviate collection exists."""
        try:
            client = get_weaviate_client()
            return bool(client.collections.exists(self._native_collection_name))
        except Exception:
            return False

    def add_documents(self, documents: List[Document], skip_existing: bool = True) -> List[str]:
        """Add LangChain documents to Weaviate with self-provided vectors."""
        if not documents:
            logger.warning("No documents to add")
            return []

        try:
            client = get_weaviate_client()
            ensure_pdf_collections(client)
            collection = client.collections.get(self._native_collection_name)
            vectors = self.embeddings.embed_documents(
                [document.page_content for document in documents]
            )

            object_ids: list[str] = []
            for document, vector in zip(documents, vectors):
                object_id = self._object_uuid(document)
                if skip_existing and self._object_exists(collection, object_id):
                    object_ids.append(str(object_id))
                    continue

                if self._object_exists(collection, object_id):
                    self._delete_object(collection, object_id)

                collection.data.insert(
                    uuid=object_id,
                    properties=self._properties_for_document(document),
                    vector=vector,
                )
                object_ids.append(str(object_id))

            logger.info(
                "Added %d documents to Weaviate collection '%s'",
                len(object_ids),
                self._native_collection_name,
            )
            return object_ids
        except Exception as exc:
            raise VectorIndexError(
                f"Failed to add documents to Weaviate vector store: {exc}",
                details={"num_documents": len(documents)},
            ) from exc

    def _object_uuid(self, document: Document) -> uuid.UUID:
        doc_hash = self._document_hash(document)
        payload = (
            f"{self._native_collection_name}:"
            f"{self.collection_name}:"
            f"{self.session_id}:"
            f"{doc_hash}"
        )
        return uuid.uuid5(_UUID_NAMESPACE, payload)

    @staticmethod
    def _document_hash(document: Document) -> str:
        payload = (
            f"{document.page_content}|||"
            f"{json.dumps(document.metadata, sort_keys=True, ensure_ascii=False)}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _properties_for_document(self, document: Document) -> dict[str, Any]:
        metadata = dict(document.metadata or {})
        properties = {
            "doc_hash": self._document_hash(document),
            "session_id": self.session_id,
            "collection_name": self.collection_name,
            "document_name": str(metadata.get("document_name") or ""),
            "source_pdf": str(metadata.get("source_pdf") or ""),
            "table_id": str(metadata.get("table_id") or ""),
            "chunk_index": self._optional_int(metadata.get("chunk_index")),
            "page_number": self._optional_int(metadata.get("page_number")),
            "page_content": document.page_content,
            "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        }
        return {key: value for key, value in properties.items() if value is not None}

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _object_exists(collection: Any, object_id: uuid.UUID) -> bool:
        exists = getattr(collection.data, "exists", None)
        if exists is None:
            return False
        return bool(exists(object_id))

    @staticmethod
    def _delete_object(collection: Any, object_id: uuid.UUID) -> None:
        delete_by_id = getattr(collection.data, "delete_by_id", None)
        if delete_by_id is not None:
            delete_by_id(object_id)
            return
        delete = getattr(collection.data, "delete", None)
        if delete is not None:
            delete(uuid=object_id)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Search Weaviate using a query vector and return lower-is-better distances."""
        try:
            collection = self.vectorstore
        except VectorIndexError as exc:
            raise VectorSearchError(
                "Cannot search: vector store not initialized",
                details={"error": str(exc)},
            ) from exc

        try:
            query_vector = self.embeddings.embed_query(query)
            has_unsupported_filter = self._has_unsupported_filter(filter_metadata)
            search_limit = max(k, 10000) if has_unsupported_filter else k
            if str(self._config.get("search_mode", "vector")).lower() == "hybrid":
                response = collection.query.hybrid(
                    query=query,
                    vector=query_vector,
                    alpha=float(self._config["hybrid_alpha"]),
                    limit=search_limit,
                    query_properties=["page_content"],
                    filters=self._build_filter(filter_metadata),
                    return_metadata=self._metadata_query(),
                    return_properties=self._return_properties(),
                )
            else:
                response = collection.query.near_vector(
                    near_vector=query_vector,
                    limit=search_limit,
                    filters=self._build_filter(filter_metadata),
                    return_metadata=self._metadata_query(),
                    return_properties=self._return_properties(),
                )
            results = [
                (self._document_from_object(obj), self._distance_from_object(obj))
                for obj in getattr(response, "objects", [])
                if self._object_matches(obj, filter_metadata)
            ]
            results.sort(key=lambda item: item[1])
            return results[:k]
        except Exception as exc:
            raise VectorSearchError(
                f"Weaviate vector search failed: {exc}",
                details={"query": query[:100], "k": k},
            ) from exc

    @staticmethod
    def _metadata_query() -> Any:
        from weaviate.classes.query import MetadataQuery

        return MetadataQuery(distance=True, score=True)

    @staticmethod
    def _return_properties() -> list[str]:
        return [
            "doc_hash",
            "session_id",
            "collection_name",
            "document_name",
            "source_pdf",
            "table_id",
            "chunk_index",
            "page_number",
            "page_content",
            "metadata_json",
        ]

    def _build_filter(self, filter_metadata: Optional[Dict[str, Any]] = None) -> Any:
        from weaviate.classes.query import Filter

        filters: list[Any] = [
            Filter.by_property("session_id").equal(self.session_id),
            Filter.by_property("collection_name").equal(self.collection_name),
        ]
        for key, value in (filter_metadata or {}).items():
            if key in _FILTERABLE_PROPERTIES:
                filters.append(Filter.by_property(key).equal(value))

        combined = filters[0]
        for next_filter in filters[1:]:
            combined = combined & next_filter
        return combined

    @staticmethod
    def _has_unsupported_filter(filter_metadata: Optional[Dict[str, Any]]) -> bool:
        return any(key not in _FILTERABLE_PROPERTIES for key in (filter_metadata or {}))

    def _object_matches(
        self,
        obj: Any,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not filter_metadata:
            return True

        properties = dict(getattr(obj, "properties", {}) or {})
        document = self._document_from_object(obj)
        for key, expected in filter_metadata.items():
            actual = properties.get(key, document.metadata.get(key))
            if actual != expected:
                return False
        return True

    @staticmethod
    def _document_from_object(obj: Any) -> Document:
        properties = dict(getattr(obj, "properties", {}) or {})
        metadata_json = properties.get("metadata_json") or "{}"
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            metadata = {}
        return Document(
            page_content=str(properties.get("page_content") or ""),
            metadata=metadata,
        )

    @staticmethod
    def _distance_from_object(obj: Any) -> float:
        metadata = getattr(obj, "metadata", None)
        distance = getattr(metadata, "distance", None)
        if distance is not None:
            return float(distance)
        score = getattr(metadata, "score", None)
        if score is not None:
            return 1.0 - float(score)
        return 1.0

    def list_documents(self, limit: Optional[int] = None) -> List[Document]:
        """Return documents stored in this logical Weaviate collection."""
        try:
            remaining = limit
            documents: list[Document] = []
            for obj in self._iter_objects(
                filters=self._build_filter(),
                return_properties=self._return_properties(),
                limit=limit,
            ):
                documents.append(self._document_from_object(obj))
                if remaining is not None and len(documents) >= remaining:
                    break
            return documents
        except VectorIndexError:
            return []
        except Exception as exc:
            raise VectorIndexError(
                f"Failed to list Weaviate documents: {exc}",
                details={"collection_name": self.collection_name},
            ) from exc

    def delete_where(self, filter_metadata: Dict[str, Any]) -> int:
        """Delete objects matching exact metadata filters."""
        if not filter_metadata:
            return 0
        try:
            collection = self.vectorstore
            object_ids = [
                getattr(obj, "uuid")
                for obj in self._iter_objects(
                    filters=self._build_filter(filter_metadata),
                    return_properties=self._return_properties(),
                )
                if self._object_matches(obj, filter_metadata)
            ]
            for object_id in object_ids:
                self._delete_object(collection, object_id)
            return len(object_ids)
        except VectorIndexError:
            return 0
        except Exception as exc:
            raise VectorIndexError(
                f"Failed to delete Weaviate documents: {exc}",
                details={"filter_metadata": filter_metadata},
            ) from exc

    def clear_collection(self) -> None:
        """Delete all objects in this logical collection/session."""
        self.reset()

    def get_document_count(self) -> int:
        """Return document count for this logical collection/session."""
        return len(self.list_documents(limit=10000))

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the Weaviate vector store."""
        return {
            "backend": "weaviate",
            "document_count": self.get_document_count(),
            "collection_name": self.collection_name,
            "native_collection_name": self._native_collection_name,
            "persist_dir": self.persist_dir,
            "session_id": self.session_id,
            "is_initialized": self.is_initialized,
        }

    def reset(self) -> None:
        """Delete all objects in this logical collection/session."""
        try:
            collection = self.vectorstore
        except VectorIndexError:
            return
        for obj in self._iter_objects(
            filters=self._build_filter(),
            return_properties=["doc_hash"],
        ):
            self._delete_object(collection, getattr(obj, "uuid"))

    def _iter_objects(
        self,
        *,
        filters: Any,
        return_properties: list[str],
        limit: Optional[int] = None,
    ):
        fetched = 0
        after = None
        while True:
            batch_limit = min(_FETCH_LIMIT, limit - fetched) if limit is not None else _FETCH_LIMIT
            if batch_limit <= 0:
                return
            kwargs: dict[str, Any] = {
                "limit": batch_limit,
                "filters": filters,
                "return_properties": return_properties,
            }
            if after is not None:
                kwargs["after"] = after
            response = self.vectorstore.query.fetch_objects(**kwargs)
            objects = list(getattr(response, "objects", []) or [])
            if not objects:
                return
            for obj in objects:
                fetched += 1
                yield obj
            if limit is not None and fetched >= limit:
                return
            if len(objects) < batch_limit:
                return
            after = str(getattr(objects[-1], "uuid"))
