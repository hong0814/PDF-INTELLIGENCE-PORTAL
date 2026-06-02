"""PDFTableSearch ChromaDB 벡터 저장소 관리.

``TableVectorStore`` — LangChain Chroma 통합 래퍼로
컬렉션 생성, 문서 삽입, 유사도 검색, 영속화를 처리한다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

from pdftablesearch.embeddings import ZaiEmbeddings
from pdftablesearch.exceptions import VectorIndexError, VectorSearchError
from pdftablesearch.utils import get_logger
from pdftablesearch.encryption import (
    is_encryption_enabled,
    is_encrypted_metadata,
    encrypt_text,
    decrypt_text,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_PERSIST_DIR = "./.chroma"
_DEFAULT_COLLECTION_NAME = "pdf_tables"

# Module-level cache: reuse Chroma instances for the same persist_dir
_store_cache: Dict[str, "TableVectorStore"] = {}


class TableVectorStore:
    """
    표 문서용 ChromaDB 벡터 저장소 관리.
    
    LangChain Chroma 통합 래퍼로 컬렉션 생성, 문서 삽입,
    유사도 검색, 영속화를 처리한다.
    """

    def __init__(
        self,
        embeddings: Optional[ZaiEmbeddings] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        self.embeddings = embeddings or ZaiEmbeddings()
        self.persist_dir = persist_dir or os.getenv(
            "CHROMA_PERSIST_DIR", _DEFAULT_PERSIST_DIR
        )
        self.collection_name = collection_name or os.getenv(
            "CHROMA_COLLECTION_NAME", _DEFAULT_COLLECTION_NAME
        )

        self._vectorstore: Optional[Chroma] = None
        self._indexed_hashes: set[str] = set()

    @classmethod
    def get_or_create(
        cls,
        embeddings: Optional[Any] = None,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> "TableVectorStore":
        """
        주어진 *persist_dir*에 대해 캐시된 ``TableVectorStore``를 반환한다.
        
        중복 생성을 방지한다.
        """
        key = persist_dir or os.getenv("CHROMA_PERSIST_DIR", _DEFAULT_PERSIST_DIR)
        if key not in _store_cache:
            _store_cache[key] = cls(
                embeddings=embeddings,
                persist_dir=persist_dir,
                collection_name=collection_name,
            )
        return _store_cache[key]

    # -- Properties ----------------------------------------------------------

    @property
    def vectorstore(self) -> Chroma:
        """지연 초기화 LangChain Chroma 벡터 저장소."""
        if self._vectorstore is not None:
            return self._vectorstore

        # Try to load existing persisted store
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
        """벡터 저장소가 생성 또는 로드되었는지 확인한다."""
        try:
            _ = self.vectorstore
            return True
        except VectorIndexError:
            return False

    # -- Document management -------------------------------------------------

    def add_documents(self, documents: List[Document], skip_existing: bool = True) -> List[str]:
        """
        LangChain Document를 벡터 저장소에 추가한다.
        
        저장소가 아직 초기화되지 않았으면 먼저 생성한다.
        """
        import shutil

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
            encrypted_texts = [encrypt_text(pt) for pt in plaintexts]
            for meta in metadatas:
                meta["_encrypted"] = True
            store_texts = encrypted_texts
        else:
            pre_embeddings = None
            store_texts = plaintexts

        # Free any prior Chroma connection before creating/appending
        if self._vectorstore is not None:
            try:
                del self._vectorstore
            except Exception:
                pass
            self._vectorstore = None
            import gc
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

                ids = [f"doc_{i}_{hashlib.md5((store_texts[i] if isinstance(store_texts[i], str) else str(store_texts[i])).encode()).hexdigest()[:8]}" for i in range(len(store_texts))]

                if pre_embeddings is not None:
                    # Use pre-computed embeddings directly — avoids double
                    # embedding since LangChain Chroma.add_texts() ignores the
                    # embeddings kwarg and always calls embedding_function.
                    self._vectorstore._collection.upsert(
                        ids=ids,
                        documents=store_texts,
                        embeddings=pre_embeddings,
                        metadatas=metadatas,
                    )
                    logger.info(
                        "Stored %d documents (pre-embedded)%s", len(store_texts),
                        " + encrypted" if use_encryption else "",
                    )
                else:
                    self._vectorstore.add_texts(
                        texts=store_texts,
                        metadatas=metadatas,
                    )
                    logger.info("Stored %d documents", len(store_texts))

                self._persist()
                return self._vectorstore.get()["ids"]

            except Exception as exc:
                err_msg = str(exc)
                is_readonly = "readonly" in err_msg.lower() or "1032" in err_msg
                if is_readonly and attempt < max_attempts - 1:
                    logger.warning(
                        "ChromaDB readonly error; recreating store in %s (attempt %d/%d)",
                        self.persist_dir, attempt + 1, max_attempts,
                    )
                    self._vectorstore = None
                    import gc
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

    @staticmethod
    def _document_hash(document: Document) -> str:
        """Document 내용 + 메타데이터 기반 안정적인 SHA-256 해시를 반환한다."""
        payload = f"{document.page_content}|||{json.dumps(document.metadata, sort_keys=True, ensure_ascii=False)}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def _persist(self) -> None:
        """벡터 저장소를 디스크에 영속화한다."""
        if self._vectorstore is not None:
            try:
                self._vectorstore.persist()
                logger.debug("Vector store persisted to %s", self.persist_dir)
            except AttributeError:
                # Newer ChromaDB versions may not have .persist()
                pass

    # -- Search --------------------------------------------------------------

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """벡터 유사도로 유사한 표를 검색한다."""
        try:
            store = self.vectorstore
        except VectorIndexError as exc:
            raise VectorSearchError(
                "Cannot search: vector store not initialized",
                details={"error": str(exc)},
            ) from exc

        logger.info(
            "Searching for '%s' (k=%d, filter=%s)",
            query[:100],
            k,
            filter_metadata,
        )

        try:
            search_kwargs: Dict[str, Any] = {"k": k}
            if filter_metadata:
                search_kwargs["filter"] = filter_metadata

            results = store.similarity_search_with_score(
                query=query, **search_kwargs
            )

            if is_encryption_enabled():
                results = [
                    (
                        Document(
                            page_content=decrypt_text(doc.page_content),
                            metadata=doc.metadata,
                        )
                        if is_encrypted_metadata(doc.metadata)
                        else doc,
                        score,
                    )
                    for doc, score in results
                ]

            logger.info("Found %d results", len(results))
            return results
            return results

        except Exception as exc:
            raise VectorSearchError(
                f"Vector search failed: {exc}",
                details={"query": query[:100], "k": k},
            ) from exc

    # -- Statistics ----------------------------------------------------------

    def get_document_count(self) -> int:
        """벡터 저장소의 문서 수를 반환한다."""
        try:
            store = self.vectorstore
            collection = store._collection
            return collection.count()
        except (VectorIndexError, Exception):
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """벡터 저장소 통계를 반환한다."""
        return {
            "document_count": self.get_document_count(),
            "collection_name": self.collection_name,
            "persist_dir": self.persist_dir,
            "is_initialized": self.is_initialized,
        }

    # -- Reset ---------------------------------------------------------------

    def reset(self) -> None:
        """
        벡터 저장소와 모든 데이터를 삭제한다.
        
        영속화된 파일을 제거하고 내부 상태를 초기화한다.
        """
        import shutil

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
