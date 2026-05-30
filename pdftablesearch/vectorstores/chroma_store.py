"""ChromaDB vector store backend for PDFTableSearch."""

from __future__ import annotations

import gc
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from pdftablesearch.embeddings import ZaiEmbeddings
from pdftablesearch.encryption import (
    decrypt_text,
    encrypt_text,
    is_encrypted_metadata,
    is_encryption_enabled,
)
from pdftablesearch.exceptions import VectorIndexError, VectorSearchError
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

DEFAULT_PERSIST_DIR = "./.chroma"
DEFAULT_COLLECTION_NAME = "pdf_tables"


class ChromaTableVectorStore:
    """Chroma-backed implementation of the table vector store contract."""

    def __init__(
        self,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.embeddings = embeddings or ZaiEmbeddings()
        self.persist_dir = persist_dir or os.getenv("CHROMA_PERSIST_DIR", DEFAULT_PERSIST_DIR)
        self.collection_name = collection_name or os.getenv(
            "CHROMA_COLLECTION_NAME",
            DEFAULT_COLLECTION_NAME,
        )
        self._vectorstore: Optional[Chroma] = None
        self._indexed_hashes: set[str] = set()

    @property
    def vectorstore(self) -> Chroma:
        """Lazy-initialized LangChain Chroma vector store."""
        if self._vectorstore is not None:
            return self._vectorstore

        persist_path = Path(self.persist_dir)
        if persist_path.exists() and any(persist_path.iterdir()):
            try:
                self._vectorstore = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=self.persist_dir,
                )
                return self._vectorstore
            except Exception as exc:
                raise VectorIndexError(
                    f"Failed to load existing vector store from {self.persist_dir}",
                    details={"error": str(exc)},
                ) from exc

        raise VectorIndexError(
            "No vector store found. Add documents first using add_documents()."
        )

    @property
    def is_initialized(self) -> bool:
        """Check whether the vector store has been created or loaded."""
        try:
            _ = self.vectorstore
            return True
        except VectorIndexError:
            return False

    def add_documents(self, documents: List[Document], skip_existing: bool = True) -> List[str]:
        """Add LangChain documents to the Chroma collection."""
        if not documents:
            logger.warning("No documents to add")
            return []

        use_encryption = is_encryption_enabled()

        if skip_existing:
            new_docs: List[Document] = []
            for doc in documents:
                doc_hash = self._document_hash(doc)
                if doc_hash not in self._indexed_hashes:
                    new_docs.append(doc)
                    self._indexed_hashes.add(doc_hash)
            skipped = len(documents) - len(new_docs)
            if skipped:
                logger.info("Skipped %d already-indexed documents", skipped)
            documents = new_docs

        if not documents:
            logger.info("All documents already indexed; nothing to add")
            return []

        logger.info(
            "Adding %d documents to collection '%s'%s",
            len(documents),
            self.collection_name,
            " (encrypted)" if use_encryption else "",
        )

        plaintexts = [doc.page_content for doc in documents]
        metadatas = [dict(doc.metadata) for doc in documents]

        if use_encryption:
            pre_embeddings = self.embeddings.embed_documents(plaintexts)
            store_texts = [encrypt_text(text) for text in plaintexts]
            for metadata in metadatas:
                metadata["_encrypted"] = True
        else:
            pre_embeddings = None
            store_texts = plaintexts

        if self._vectorstore is not None:
            self._vectorstore = None
            gc.collect()

        persist_path = Path(self.persist_dir)
        exists = persist_path.exists() and any(persist_path.iterdir())

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                if exists:
                    self._vectorstore = Chroma(
                        collection_name=self.collection_name,
                        embedding_function=self.embeddings,
                        persist_directory=self.persist_dir,
                    )
                else:
                    persist_path.mkdir(parents=True, exist_ok=True)
                    self._vectorstore = Chroma(
                        collection_name=self.collection_name,
                        embedding_function=self.embeddings,
                        persist_directory=self.persist_dir,
                    )

                ids = [
                    f"doc_{index}_{hashlib.md5(text.encode()).hexdigest()[:8]}"
                    for index, text in enumerate(store_texts)
                ]

                if pre_embeddings is not None:
                    # LangChain Chroma.add_texts() ignores explicit embeddings,
                    # so use the native collection to avoid double embedding.
                    self._vectorstore._collection.upsert(
                        ids=ids,
                        documents=store_texts,
                        embeddings=pre_embeddings,
                        metadatas=metadatas,
                    )
                    logger.info(
                        "Stored %d documents (pre-embedded)%s",
                        len(store_texts),
                        " + encrypted" if use_encryption else "",
                    )
                else:
                    self._vectorstore.add_texts(
                        texts=store_texts,
                        metadatas=metadatas,
                        ids=ids,
                    )
                    logger.info("Stored %d documents", len(store_texts))

                self._persist()
                return list(self._vectorstore.get()["ids"])

            except Exception as exc:
                err_msg = str(exc)
                is_readonly = "readonly" in err_msg.lower() or "1032" in err_msg
                if is_readonly and attempt < max_attempts - 1:
                    logger.warning(
                        "ChromaDB readonly error; recreating store in %s (attempt %d/%d)",
                        self.persist_dir,
                        attempt + 1,
                        max_attempts,
                    )
                    self._vectorstore = None
                    gc.collect()
                    if persist_path.exists():
                        shutil.rmtree(persist_path, ignore_errors=True)
                    exists = False
                    self._indexed_hashes.clear()
                    continue
                raise VectorIndexError(
                    f"Failed to add documents to vector store: {exc}",
                    details={"num_documents": len(documents)},
                ) from exc

        return []

    @staticmethod
    def _document_hash(document: Document) -> str:
        """Return a stable SHA-256 hash for a Document based on content + metadata."""
        payload = (
            f"{document.page_content}|||"
            f"{json.dumps(document.metadata, sort_keys=True, ensure_ascii=False)}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _persist(self) -> None:
        """Persist the Chroma store to disk when the backend exposes persist()."""
        if self._vectorstore is not None:
            try:
                self._vectorstore.persist()
                logger.debug("Vector store persisted to %s", self.persist_dir)
            except AttributeError:
                pass

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """Search for similar documents using Chroma distance scores."""
        try:
            store = self.vectorstore
        except VectorIndexError as exc:
            raise VectorSearchError(
                "Cannot search: vector store not initialized",
                details={"error": str(exc)},
            ) from exc

        logger.info("Searching for '%s' (k=%d, filter=%s)", query[:100], k, filter_metadata)

        try:
            search_kwargs: Dict[str, Any] = {"k": k}
            if filter_metadata:
                search_kwargs["filter"] = filter_metadata

            results = store.similarity_search_with_score(query=query, **search_kwargs)
            if is_encryption_enabled():
                results = [
                    (
                        Document(
                            page_content=decrypt_text(document.page_content),
                            metadata=document.metadata,
                        )
                        if is_encrypted_metadata(document.metadata)
                        else document,
                        score,
                    )
                    for document, score in results
                ]
            logger.info("Found %d results", len(results))
            return results

        except Exception as exc:
            raise VectorSearchError(
                f"Vector search failed: {exc}",
                details={"query": query[:100], "k": k},
            ) from exc

    def list_documents(self, limit: Optional[int] = None) -> List[Document]:
        """Return documents stored in the Chroma collection."""
        try:
            collection = self.vectorstore._collection
            kwargs: Dict[str, Any] = {"include": ["documents", "metadatas"]}
            if limit is not None:
                kwargs["limit"] = limit
            results = collection.get(**kwargs)
        except VectorIndexError:
            return []
        except Exception as exc:
            raise VectorIndexError(
                f"Failed to list vector store documents: {exc}",
                details={"collection_name": self.collection_name},
            ) from exc

        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        listed: list[Document] = []
        for document, metadata in zip(documents, metadatas):
            metadata = metadata or {}
            content = document or ""
            if is_encryption_enabled() and is_encrypted_metadata(metadata):
                content = decrypt_text(content)
            listed.append(Document(page_content=content, metadata=metadata))
        return listed

    def delete_where(self, filter_metadata: Dict[str, Any]) -> int:
        """Delete documents matching exact Chroma metadata filters."""
        if not filter_metadata:
            return 0
        try:
            collection = self.vectorstore._collection
            matches = collection.get(where=filter_metadata, include=[])
            ids = list(matches.get("ids") or [])
            if ids:
                collection.delete(ids=ids)
                self._persist()
            return len(ids)
        except VectorIndexError:
            return 0
        except Exception as exc:
            raise VectorIndexError(
                f"Failed to delete vector store documents: {exc}",
                details={"filter_metadata": filter_metadata},
            ) from exc

    def clear_collection(self) -> None:
        """Delete the Chroma collection and local persistence directory."""
        self.reset()

    def get_document_count(self) -> int:
        """Return the number of documents in the vector store."""
        try:
            collection = self.vectorstore._collection
            return int(collection.count())
        except (VectorIndexError, Exception):
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the vector store."""
        return {
            "backend": "chroma",
            "document_count": self.get_document_count(),
            "collection_name": self.collection_name,
            "persist_dir": self.persist_dir,
            "is_initialized": self.is_initialized,
        }

    def reset(self) -> None:
        """Delete the vector store and all its persisted data."""
        if self._vectorstore is not None:
            try:
                self._vectorstore.delete_collection()
            except Exception:
                pass
            self._vectorstore = None

        persist_path = Path(self.persist_dir)
        if persist_path.exists():
            shutil.rmtree(persist_path)
            logger.info("Deleted vector store at %s", persist_path)
        self._indexed_hashes.clear()
