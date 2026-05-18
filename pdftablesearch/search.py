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
    """Efficient PDF table search with reusable model and vector store.

    Loads the SentenceTransformer model once during initialization,
    allowing multiple searches without reloading the model each time.

    Args:
        model_name: SentenceTransformers model name to use.
            Defaults to ``distiluse-base-multilingual-cased-v2``.
        chroma_persist_dir: Directory for ChromaDB persistence.
            Defaults to ``./.chroma``.
        device: Device to run on (``cpu`` or ``cuda``).
            Defaults to ``cpu``.

    Example::

        from pdftablesearch import PDFTableSearch

        # Initialize once (loads model)
        searcher = PDFTableSearch()

        # Multiple searches without reloading model
        results1 = searcher.search("report.pdf", "revenue")
        results2 = searcher.search("report.pdf", "expenses")

        # Multi-document search
        results3 = searcher.search_many(
            ["doc1.pdf", "doc2.pdf"],
            "annual growth"
        )
    """

    def __init__(
        self,
        model_name: str = "distiluse-base-multilingual-cased-v2",
        chroma_persist_dir: str = "./.chroma",
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.chroma_persist_dir = chroma_persist_dir
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
        """Search for tables in a single PDF document.

        Args:
            pdf_path: Path to the PDF file.
            query: Natural language search query (Korean or English).
            max_results: Maximum number of results to return.
            use_llm_rerank: Whether to apply LLM-based re-ranking.
            output_dir: Optional override for PDF conversion output.
            use_hybrid: Whether to use hybrid mode for better table extraction.
            reset_vector_store: Whether to reset vector store before searching.
                Defaults to False (preserves existing data).

        Returns:
            List of :class:`TableSearchResult` objects sorted by relevance.
        """
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
        from pdftablesearch.vectorstore import TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self.chroma_persist_dir,
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
        """Search for tables across multiple PDF documents.

        Args:
            pdf_paths: List of PDF file paths.
            query: Natural language search query.
            max_total_results: Maximum total results across all documents.
            max_results_per_doc: Maximum results per individual document.
            use_llm_rerank: Whether to use LLM re-ranking.
            progress_callback: Optional progress callback.
            use_hybrid: Whether to use hybrid mode for better table extraction.

        Returns:
            :class:`MultiDocumentSearchResult` with aggregated results.
        """
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
        from pdftablesearch.vectorstore import TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self.chroma_persist_dir,
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
        """Convert raw vector search results to TableSearchResult objects."""
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
        """Apply per-document result limit while preserving ranking."""
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
        """Clear the cached documents."""
        self._cached_documents.clear()
        logger.info("Cleared document cache")

    def reset_vector_store(self) -> None:
        """Delete the vector store and all its data."""
        from pdftablesearch.vectorstore import TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self.chroma_persist_dir,
        )
        vector_store.reset()
        self._loaded_pdfs.clear()
        logger.info("Reset vector store and cache")

    # -----------------------------------------------------------------------
    # Vector Store Inspection
    # -----------------------------------------------------------------------

    def get_vector_store_stats(self) -> dict:
        """Get statistics about the current vector store.

        Returns:
            Dictionary with keys:
            - document_count: Number of documents in the store
            - collection_name: Name of the ChromaDB collection
            - persist_dir: Directory where data is stored
            - loaded_pdfs: Set of PDF names currently loaded
        """
        from pdftablesearch.vectorstore import TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self.chroma_persist_dir,
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
                "persist_dir": self.chroma_persist_dir,
                "loaded_pdfs": [],
                "cached_documents": [],
            }

    def list_stored_tables(self) -> List[dict]:
        """List all tables currently stored in the vector store.

        Returns:
            List of dictionaries, each containing:
            - table_id: Table identifier
            - page_number: Page number
            - document_name: Document filename
            - content_preview: First 200 characters of table content
        """
        from pdftablesearch.vectorstore import TableVectorStore

        vector_store = TableVectorStore(
            embeddings=self.embeddings,
            persist_dir=self.chroma_persist_dir,
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
        """Search for the single most relevant table using vector + LLM.

        Combines vector similarity search with LLM-based table selection.
        Retrieves ``top_k`` candidates via vector search, then sends them
        to the LLM to pick the best match.

        Falls back to the top vector result if the LLM fails and
        ``fallback_to_vector`` is ``True``.

        Args:
            pdf_path: Path to the PDF document.
            query: Natural language search query (Korean or English).
            top_k: Number of vector search candidates for LLM evaluation.
                Default 20.
            llm_model: LLM model name (``glm-5.1``, ``glm-5.0``).
            api_key: z.ai API key.  Falls back to ``ZAI_API_KEY`` env var.
            fallback_to_vector: If ``True``, return vector search #1
                when the LLM fails.

        Returns:
            Single :class:`TableSearchResult` with the highest relevance.

        Raises:
            TableSearchError: If both vector search and LLM fail, or if
                LLM fails and fallback is disabled.

        Example::

            searcher = PDFTableSearch()
            result = searcher.smart_search(
                pdf_path="report.pdf",
                query="포괄손익계산서",
            )
        """
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
            chroma_persist_dir=self.chroma_persist_dir,
        )

    def inspect_vector_store(self) -> None:
        """Print detailed information about the vector store to console.

        Displays:
        - Document count
        - Loaded PDFs
        - Cached documents
        - All stored tables with preview
        """
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
