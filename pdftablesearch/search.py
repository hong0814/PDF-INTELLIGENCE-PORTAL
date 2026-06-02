"""
PDFTableSearch class for efficient table search with reusable components.

Provides ``PDFTableSearch`` class that loads the embedding model once
and reuses it across multiple search operations, improving performance
for repeated searches.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from langchain_core.documents import Document

from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.loader import PDFProcessor
from pdftablesearch.models import (
    MultiDocumentSearchResult,
    TableSearchResult,
)
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)


class PDFTableSearch:
    """
    재사용 모델과 벡터 저장소를 활용한 효율적인 PDF 표 검색 클래스.
    
    ``SentenceTransformer`` 임베딩 모델을 한 번만 로드하여
    여러 검색에 재사용한다.
    """

    def __init__(
        self,
        model_name: str = "distiluse-base-multilingual-cased-v2",
        persist_dir: str = "./.chroma",
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self._persist_dir = persist_dir
        self.device = device

        logger.info("Initializing PDFTableSearch with model: %s", model_name)

        # Load embedding model once
        self.embeddings = SentenceTransformerEmbeddings(
            model_name=model_name,
            device=device,
        )

        # Create PDF processor
        self.processor = PDFProcessor()

        # Cache for loaded documents (optional optimization)
        self._cached_documents: dict[str, List[Document]] = {}

        # Track loaded PDFs in vector store
        self._loaded_pdfs: set[str] = set()

        logger.info("PDFTableSearch initialized successfully")

    def search(
        self,
        pdf_path: str,
        query: str,
        max_results: int = 5,
        use_llm_rerank: bool = False,
        output_dir: Optional[str] = None,
        use_hybrid: bool = True,
        reset_vector_store: bool = False,
    ) -> List[TableSearchResult]:
        """단일 PDF 문서에서 표를 검색한다."""
        logger.info(
            "Searching in %s for: %s (hybrid=%s, reset=%s)",
            pdf_path,
            query,
            use_hybrid,
            reset_vector_store,
        )

        # Check if PDF is already loaded
        pdf_name = Path(pdf_path).name
        documents = []

        if pdf_name in self._cached_documents and not reset_vector_store:
            # Use cached documents
            documents = self._cached_documents[pdf_name]
            logger.info("Using cached documents for %s (%d tables)", pdf_name, len(documents))
        else:
            # Load PDF and extract tables
            result = self.processor.load_documents(
                pdf_path=pdf_path,
                output_dir=output_dir,
                use_hybrid=use_hybrid,
            )
            documents = self.processor.get_documents()

            if not documents:
                logger.info("No tables found in %s", pdf_path)
                return []

            # Cache documents
            self._cached_documents[pdf_name] = documents
            logger.info("Loaded %d tables from %s", len(documents), pdf_path)

        # Build vector index and search
        from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self._persist_dir,
        )

        # Only add documents if not already in vector store
        if pdf_name not in self._loaded_pdfs or reset_vector_store:
            if reset_vector_store:
                vector_store.reset()
                self._loaded_pdfs.clear()

            vector_store.add_documents(documents)
            self._loaded_pdfs.add(pdf_name)
            logger.info("Added %d documents to vector store", len(documents))
        else:
            logger.info("Using existing vector store for %s", pdf_name)

        search_results = vector_store.similarity_search(
            query=query,
            k=max_results,
        )

        if not search_results:
            logger.info("No matching tables found for query: %s", query)
            return []

        # Format results
        results = self._format_search_results(search_results[:max_results])
        logger.info("Returning %d search results", len(results))
        return results

    def search_many(
        self,
        pdf_paths: List[str],
        query: str,
        max_total_results: int = 20,
        max_results_per_doc: Optional[int] = None,
        use_llm_rerank: bool = False,
        progress_callback: Optional = None,
        use_hybrid: bool = True,
    ) -> MultiDocumentSearchResult:
        """여러 PDF 문서에서 표를 검색한다."""
        logger.info(
            "Multi-document search: %d PDFs, query='%s' (hybrid=%s)",
            len(pdf_paths),
            query,
            use_hybrid,
        )

        # Load all documents
        all_documents: List[Document] = []
        for idx, pdf_path in enumerate(pdf_paths):
            try:
                self.processor.load_documents(pdf_path, use_hybrid=use_hybrid)
                docs = self.processor.get_documents()
                all_documents.extend(docs)
                if progress_callback:
                    progress_callback(idx + 1, len(pdf_paths), Path(pdf_path).name, "ok")
            except Exception as exc:
                logger.error("Failed to load %s: %s", pdf_path, exc)
                if progress_callback:
                    progress_callback(idx + 1, len(pdf_paths), Path(pdf_path).name, f"error: {exc}")

        if not all_documents:
            logger.info("No tables found in any of the %d PDFs", len(pdf_paths))
            return MultiDocumentSearchResult(results=[], query=query)

        logger.info("Loaded %d total tables from %d documents", len(all_documents), len(pdf_paths))

        # Build vector index
        from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self._persist_dir,
        )
        vector_store.reset()  # Start fresh
        vector_store.add_documents(all_documents)

        # Search
        search_k = min(max_total_results, len(all_documents))
        search_results = vector_store.similarity_search(query=query, k=search_k)

        if not search_results:
            return MultiDocumentSearchResult(results=[], query=query)

        # Format results
        all_results = self._format_search_results(search_results[:max_total_results])

        # Apply per-document limit if specified
        if max_results_per_doc is not None:
            all_results = self._apply_per_doc_limit(all_results, max_results_per_doc)

        return MultiDocumentSearchResult(results=all_results, query=query)

    def _format_search_results(
        self, search_results: List[tuple[Document, float]]
    ) -> List[TableSearchResult]:
        """벡터 검색 원시 결과를 ``TableSearchResult`` 객체로 변환한다."""
        results: List[TableSearchResult] = []

        for doc, score in search_results:
            result = TableSearchResult.from_langchain_document(doc, score)
            results.append(result)

        # Sort by relevance score ascending (lower distance = better)
        results.sort(key=lambda r: r.relevance_score or float("inf"))
        return results

    def _apply_per_doc_limit(
        self, results: List[TableSearchResult], max_per_doc: int
    ) -> List[TableSearchResult]:
        """순위를 유지하면서 문서당 결과 제한을 적용한다."""
        doc_counts: dict[str, int] = {}
        filtered: List[TableSearchResult] = []

        for result in results:
            doc_name = result.document_name
            current_count = doc_counts.get(doc_name, 0)

            if current_count < max_per_doc:
                filtered.append(result)
                doc_counts[doc_name] = current_count + 1

        return filtered

    def clear_cache(self) -> None:
        """캐시된 문서를 초기화한다."""
        self._cached_documents.clear()
        logger.info("Cleared document cache")

    def reset_vector_store(self) -> None:
        """벡터 저장소와 모든 데이터를 삭제한다."""
        from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self._persist_dir,
        )
        vector_store.reset()
        self._loaded_pdfs.clear()
        logger.info("Reset vector store and cache")

    # -----------------------------------------------------------------------
    # Vector Store Inspection
    # -----------------------------------------------------------------------

    def get_vector_store_stats(self) -> dict:
        """현재 벡터 저장소 통계를 반환한다."""
        from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self._persist_dir,
        )

        try:
            stats = vector_store.get_stats()
            stats["loaded_pdfs"] = list(self._loaded_pdfs)
            stats["cached_documents"] = list(self._cached_documents.keys())
            return stats
        except Exception as exc:
            logger.warning("Could not get vector store stats: %s", exc)
            return {
                "document_count": 0,
                "collection_name": "N/A",
                "persist_dir": self._persist_dir,
                "loaded_pdfs": [],
                "cached_documents": [],
            }

    def list_stored_tables(self) -> List[dict]:
        """벡터 저장소에 저장된 모든 표를 나열한다."""
        from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self._persist_dir,
        )

        try:
            # Get all documents from the collection
            store = vector_store.vectorstore
            collection = store._collection

            # Get all documents with metadata
            results = collection.get(include=["documents", "metadatas"])

            tables = []
            for doc_id, metadata, document in zip(
                results["ids"],
                results["metadatas"],
                results["documents"]
            ):
                tables.append({
                    "table_id": metadata.get("table_id", "N/A"),
                    "page_number": metadata.get("page_number", 0),
                    "document_name": metadata.get("document_name", "N/A"),
                    "content_preview": document[:200] if document else "N/A",
                })

            return tables
        except Exception as exc:
            logger.warning("Could not list stored tables: %s", exc)
            return []

    def smart_search(
        self,
        pdf_path: str,
        query: str,
        top_k: int = 20,
        llm_model: str = "glm-4.7",
        api_key: Optional[str] = None,
        fallback_to_vector: bool = True,
    ) -> TableSearchResult:
        """벡터 + LLM으로 가장 관련성 높은 표 하나를 검색한다."""
        from pdftablesearch.smart_search import smart_search as _smart_search

        return _smart_search(
            query=query,
            pdf_path=pdf_path,
            top_k=top_k,
            llm_model=llm_model,
            api_key=api_key,
            use_hybrid=True,
            output_dir=None,
            fallback_to_vector=fallback_to_vector,
            persist_dir=self._persist_dir,
        )

    def inspect_vector_store(self) -> None:
        """벡터 저장소 상세 정보를 콘솔에 출력한다."""
        stats = self.get_vector_store_stats()

        print("=" * 60)
        print("Vector Store Information")
        print("=" * 60)
        print(f"Document Count: {stats.get('document_count', 0)}")
        print(f"Collection Name: {stats.get('collection_name', 'N/A')}")
        print(f"Persist Directory: {stats.get('persist_dir', 'N/A')}")
        print()

        print(f"Loaded PDFs ({len(stats.get('loaded_pdfs', []))}):")
        for pdf in stats.get("loaded_pdfs", []):
            print(f"  - {pdf}")
        print()

        print(f"Cached Documents ({len(stats.get('cached_documents', []))}):")
        for doc in stats.get("cached_documents", []):
            print(f"  - {doc}")
        print()

        tables = self.list_stored_tables()
        print(f"Stored Tables ({len(tables)}):")
        for i, table in enumerate(tables, 1):
            print(f"\n  [{i}] {table['table_id']}")
            print(f"      Page: {table['page_number']}")
            print(f"      Document: {table['document_name']}")
            print(f"      Preview: {table['content_preview'][:100]}...")

        print("=" * 60)
