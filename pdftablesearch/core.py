"""
Core search pipeline for PDFTableSearch.

Orchestrates the full workflow: PDF loading, vector indexing, similarity
search, optional LLM re-ranking, and result formatting. Exposes the
primary public API function ``search_tables`` which handles both
single-document and multi-document search.

Usage::

    # Single document
    results = search_tables("report.pdf", "quarterly revenue")

    # Multiple documents
    result = search_tables(["r1.pdf", "r2.pdf"], "annual revenue")
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from langchain_core.documents import Document
from tqdm import tqdm

from pdftablesearch.exceptions import TableSearchError, VectorSearchError
from pdftablesearch.loader import PDFProcessor
from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.models import (
    BatchProcessingResult,
    MultiDocumentSearchResult,
    ProcessingResult,
    TableSearchResult,
)
from pdftablesearch.utils import get_logger
from pdftablesearch.vectorstore import TableVectorStore

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Unified search function
# ---------------------------------------------------------------------------

def search_tables(
    pdf_path: Union[str, List[str]],
    query: str,
    max_results: int = 5,
    max_results_per_doc: Optional[int] = None,
    use_llm_rerank: bool = False,
    chroma_persist_dir: str = "./.chroma",
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[..., None]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Union[List[TableSearchResult], MultiDocumentSearchResult]:
    """Search for tables in one or more PDF documents.

    When *pdf_path* is a single string the function operates in
    **single-document mode** and returns a flat ``List[TableSearchResult]``.
    When *pdf_path* is a list of strings it switches to **multi-document
    mode** and returns a :class:`MultiDocumentSearchResult` that
    aggregates results across all documents.

    Args:
        pdf_path: Path to a single PDF file (``str``) or a list of PDF
            file paths (``List[str]``).
        query: Natural language search query (Korean or English).
        max_results: Maximum number of results to return.  In
            single-document mode this is the overall limit.  In
            multi-document mode this acts as ``max_total_results``.
        max_results_per_doc: Maximum results per individual document.
            Only used in multi-document mode.  Defaults to ``None``
            (no per-document limit).
        use_llm_rerank: Whether to apply LLM-based re-ranking after
            vector search.  Defaults to ``False``.
        chroma_persist_dir: Directory for ChromaDB persistence.
        output_dir: Optional override for PDF conversion output.
            Only used in single-document mode.
        progress_callback: Optional callback ``callback(current, total,
            document_name, status)`` invoked during batch processing.
            Only used in multi-document mode.

    Returns:
        *Single document*: ``List[TableSearchResult]`` sorted by
        relevance score (descending).

        *Multiple documents*: :class:`MultiDocumentSearchResult`
        with aggregated results, per-document counts, and total count.

    Raises:
        FileNotFoundError: If any PDF file does not exist.
        TableSearchError: If the search pipeline encounters an error.
        VectorSearchError: If vector search fails.

    Example::

        from pdftablesearch import search_tables

        # Single document
        results = search_tables("financial_report.pdf", "quarterly revenue")
        for table in results:
            print(f"Page {table.page_number}: {table.table_id}")

        # Multiple documents
        result = search_tables(
            ["report1.pdf", "report2.pdf"],
            "annual revenue",
            max_results=10,
            max_results_per_doc=3,
        )
        print(f"Found {result.total_results} tables")
    """
    # Determine mode from input type
    if isinstance(pdf_path, str):
        results = _search_single(
            pdf_path=pdf_path,
            query=query,
            max_results=max_results,
            use_llm_rerank=use_llm_rerank,
            chroma_persist_dir=chroma_persist_dir,
            output_dir=output_dir,
        )
        if filters:
            results = _apply_filters(results, filters)
        return results
    else:
        return _search_multi(
            pdf_paths=pdf_path,
            query=query,
            max_total_results=max_results,
            max_results_per_doc=max_results_per_doc,
            use_llm_rerank=use_llm_rerank,
            chroma_persist_dir=chroma_persist_dir,
            progress_callback=progress_callback,
        )


# ---------------------------------------------------------------------------
# Single-document search
# ---------------------------------------------------------------------------

def _search_single(
    pdf_path: str,
    query: str,
    max_results: int = 5,
    use_llm_rerank: bool = False,
    chroma_persist_dir: str = "./.chroma",
    output_dir: Optional[str] = None,
) -> List[TableSearchResult]:
    """Execute a single-document search pipeline.

    Handles the complete workflow: PDF conversion, table extraction,
    vector indexing, similarity search, and optional LLM re-ranking.

    Args:
        pdf_path: Path to the PDF file to search.
        query: Natural language search query.
        max_results: Maximum number of results to return.
        use_llm_rerank: Whether to apply LLM re-ranking.
        chroma_persist_dir: Directory for ChromaDB persistence.
        api_key: Optional z.ai API key.
        output_dir: Optional override for PDF conversion output.

    Returns:
        List of :class:`TableSearchResult` objects sorted by relevance.
    """
    logger.info(
        "Starting table search: pdf=%s, query='%s', max_results=%d",
        pdf_path,
        query,
        max_results,
    )

    # 1. Load PDF and extract tables
    processor = PDFProcessor()
    processing_result = processor.load_documents(
        pdf_path=pdf_path,
        output_dir=output_dir,
    )
    documents = processor.get_documents()

    if not documents:
        logger.info("No tables found in %s", pdf_path)
        return []

    logger.info(
        "Loaded %d tables from %s", processing_result.tables_extracted, pdf_path
    )

    # 2. Build vector index
    embeddings = SentenceTransformerEmbeddings()
    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir=chroma_persist_dir,
    )
    vector_store.add_documents(documents)

    # 3. Similarity search
    search_results = vector_store.similarity_search(
        query=query,
        k=max_results * 3 if use_llm_rerank else max_results,
    )

    if not search_results:
        logger.info("No matching tables found for query: %s", query)
        return []

    # 4. Optional LLM re-ranking
    results = _execute_search_with_rerank(
        search_results=search_results,
        use_llm_rerank=use_llm_rerank,
        max_results=max_results,
    )

    logger.info("Returning %d search results", len(results))
    return results


# ---------------------------------------------------------------------------
# Multi-document search
# ---------------------------------------------------------------------------

def _search_multi(
    pdf_paths: List[str],
    query: str,
    max_total_results: int = 20,
    max_results_per_doc: Optional[int] = None,
    use_llm_rerank: bool = False,
    chroma_persist_dir: str = "./.chroma",
    progress_callback: Optional[Callable[..., None]] = None,
) -> MultiDocumentSearchResult:
    """Execute a multi-document search pipeline.

    Processes each PDF independently, loads all tables into a shared
    vector store, and performs a unified similarity search across all
    documents.

    Args:
        pdf_paths: List of PDF file paths to search.
        query: Natural language search query.
        max_total_results: Maximum total results across all documents.
        max_results_per_doc: Maximum results per individual document.
            ``None`` means no per-document limit.
        use_llm_rerank: Whether to use LLM re-ranking.
        chroma_persist_dir: ChromaDB persistence directory.
        api_key: Optional z.ai API key.
        progress_callback: Optional progress callback.

    Returns:
        :class:`MultiDocumentSearchResult` with results from all
        documents, sorted by relevance.
    """
    logger.info(
        "Starting multi-document search: %d PDFs, query='%s'",
        len(pdf_paths),
        query,
    )

    # 1. Load all PDFs sequentially
    processor = PDFProcessor()
    all_documents = _load_all_documents_sequential(
        pdf_paths, processor, progress_callback=progress_callback,
    )

    if not all_documents:
        logger.info("No tables found in any of the %d PDFs", len(pdf_paths))
        return MultiDocumentSearchResult(results=[], query=query)

    logger.info(
        "Loaded %d total tables from %d documents",
        len(all_documents),
        len(pdf_paths),
    )

    # 2. Build vector index with all documents
    embeddings = SentenceTransformerEmbeddings()
    vector_store = TableVectorStore(
        embeddings=embeddings,
        persist_dir=chroma_persist_dir,
    )
    vector_store.reset()  # Start fresh for multi-doc search
    vector_store.add_documents(all_documents)

    # 3. Search
    search_k = min(
        max_total_results * 2 if use_llm_rerank else max_total_results,
        len(all_documents),
    )
    search_results = vector_store.similarity_search(
        query=query,
        k=search_k,
    )

    if not search_results:
        return MultiDocumentSearchResult(results=[], query=query)

    # 4. Optional re-ranking
    all_results = _execute_search_with_rerank(
        search_results=search_results,
        use_llm_rerank=use_llm_rerank,
        max_results=max_total_results,
    )

    # 5. Apply per-document limit (if specified)
    if max_results_per_doc is not None:
        all_results = _apply_per_doc_limit(all_results, max_results_per_doc)

    all_results = all_results[:max_total_results]

    # 6. Build result
    return MultiDocumentSearchResult(
        results=all_results,
        query=query,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_all_documents_sequential(
    pdf_paths: List[str],
    processor: PDFProcessor,
    progress_callback: Optional[Callable[..., None]] = None,
) -> List[Document]:
    """Load documents from all PDFs in parallel using ThreadPoolExecutor.

    Each PDF is processed by an independent ``PDFProcessor`` instance to
    avoid shared-state conflicts.  Results are collected and returned in
    the original input order.

    Args:
        pdf_paths: List of PDF paths to load.
        processor: Template ``PDFProcessor`` (used for its configuration).
        progress_callback: Optional callback ``callback(current, total,
            document_name, status)`` invoked after each PDF is processed.

    Returns:
        Accumulated list of all Documents from all PDFs.
    """
    if not pdf_paths:
        return []

    total = len(pdf_paths)
    ordered_results: Dict[int, List[Document]] = {}
    errors: Dict[int, str] = {}

    def _load_one(indexed_path: tuple[int, str]) -> tuple[int, List[Document], Optional[str]]:
        idx, pdf_path = indexed_path
        try:
            local_processor = PDFProcessor(
                parallel_workers=processor.parallel_workers,
                output_dir=processor._output_dir,
            )
            local_processor.load_documents(pdf_path)
            docs = local_processor.get_documents()
            return idx, docs, None
        except Exception as exc:
            return idx, [], str(exc)

    max_workers = min(processor.parallel_workers, len(pdf_paths))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_load_one, (i, p)): i for i, p in enumerate(pdf_paths)
        }

        for future in as_completed(futures):
            idx, docs, error = future.result()
            filename = Path(pdf_paths[idx]).name

            if error:
                logger.error("Failed to load %s: %s", pdf_paths[idx], error)
                errors[idx] = error
                if progress_callback:
                    progress_callback(idx + 1, total, filename, f"error: {error}")
            else:
                ordered_results[idx] = docs
                if progress_callback:
                    progress_callback(idx + 1, total, filename, "ok")

    all_documents: List[Document] = []
    for i in range(len(pdf_paths)):
        if i in ordered_results:
            all_documents.extend(ordered_results[i])

    logger.info(
        "Parallel loading: %d/%d PDFs succeeded, %d total tables",
        len(ordered_results),
        total,
        len(all_documents),
    )

    return all_documents


def _execute_search_with_rerank(
    search_results: List[tuple[Document, float]],
    use_llm_rerank: bool,
    max_results: int,
) -> List[TableSearchResult]:
    """Apply optional LLM re-ranking and format results.

    This helper encapsulates the shared re-ranking logic used by both
    single-document and multi-document search pipelines.

    Args:
        search_results: Raw (Document, score) tuples from vector search.
        use_llm_rerank: Whether to attempt LLM re-ranking.
        max_results: Target number of results (used as ``top_k`` for
            the reranker).
        api_key: Resolved API key for the reranker.

    Returns:
        Formatted list of :class:`TableSearchResult` objects.
    """
    if use_llm_rerank and search_results:
        try:
            from pdftablesearch.reranker import ZaiRerankCompressor

            compressor = ZaiRerankCompressor(
                top_k=max_results,
            )
            candidate_docs = [doc for doc, _score in search_results]
            reranked_docs = compressor.compress_documents(candidate_docs, "")

            # Map reranked docs back to results with rerank scores
            results = _format_reranked_results(reranked_docs, search_results)
        except Exception as exc:
            logger.warning(
                "LLM re-ranking failed, falling back to vector scores: %s", exc
            )
            results = _format_search_results(search_results[:max_results])
    else:
        results = _format_search_results(search_results[:max_results])

    return results


def _format_search_results(
    search_results: List[tuple[Document, float]],
) -> List[TableSearchResult]:
    """Convert raw vector search results to TableSearchResult objects.

    Args:
        search_results: List of (Document, distance_score) tuples.

    Returns:
        Sorted list of TableSearchResult objects.
    """
    results: List[TableSearchResult] = []

    for doc, score in search_results:
        result = TableSearchResult.from_langchain_document(doc, score)
        results.append(result)

    # Sort by relevance score ascending (lower ChromaDB distance = better)
    # and then reverse so best results come first
    results.sort(key=lambda r: r.relevance_score or float("inf"))
    return results


def _format_reranked_results(
    reranked_docs: List[Document],
    original_results: List[tuple[Document, float]],
) -> List[TableSearchResult]:
    """Convert re-ranked documents to TableSearchResult objects.

    Merges the original vector similarity score with the new rerank
    score from the LLM.

    Args:
        reranked_docs: Documents after LLM re-ranking.
        original_results: Original (Document, score) tuples for score
            lookup.

    Returns:
        Sorted list of TableSearchResult objects with both scores.
    """
    # Build lookup: table_id -> vector score
    score_lookup: Dict[str, float] = {}
    for doc, score in original_results:
        table_id = doc.metadata.get("table_id", "")
        score_lookup[table_id] = score

    results: List[TableSearchResult] = []
    for doc in reranked_docs:
        table_id = doc.metadata.get("table_id", "")
        vector_score = score_lookup.get(table_id, 0.0)
        rerank_score = doc.metadata.get("rerank_score")

        result = TableSearchResult(
            page_number=doc.metadata.get("page_number", 0),
            bounding_box=doc.metadata.get("bounding_box", []),
            table_markdown=doc.page_content,
            table_id=table_id,
            document_name=doc.metadata.get("document_name", ""),
            relevance_score=vector_score,
            rerank_score=rerank_score,
        )
        results.append(result)

    # Sort by rerank score descending if available
    results.sort(
        key=lambda r: r.rerank_score if r.rerank_score is not None else 0.0,
        reverse=True,
    )
    return results


def _apply_per_doc_limit(
    results: List[TableSearchResult],
    max_per_doc: int,
) -> List[TableSearchResult]:
    """Apply per-document result limit while preserving ranking.

    Args:
        results: Full result list sorted by relevance.
        max_per_doc: Maximum results allowed per document.

    Returns:
        Filtered list respecting the per-document limit.
    """
    doc_counts: Dict[str, int] = {}
    filtered: List[TableSearchResult] = []

    for result in results:
        doc_name = result.document_name
        current_count = doc_counts.get(doc_name, 0)

        if current_count < max_per_doc:
            filtered.append(result)
            doc_counts[doc_name] = current_count + 1

    return filtered


def _apply_filters(
    results: List[TableSearchResult],
    filters: Dict[str, Any],
) -> List[TableSearchResult]:
    """Apply metadata-based filters to search results.

    Supported filter keys:
        - ``page_range``: Tuple ``(min_page, max_page)`` inclusive.
        - ``min_rows``: Minimum number of data rows in the table.
        - ``table_title_contains``: Substring that must appear in the title.
        - ``document_name``: Exact document name to match.

    Args:
        results: Search results to filter.
        filters: Dictionary of filter criteria.

    Returns:
        Filtered list of results.
    """
    filtered = results

    page_range = filters.get("page_range")
    if page_range:
        min_page, max_page = page_range
        filtered = [r for r in filtered if min_page <= r.page_number <= max_page]

    min_rows = filters.get("min_rows")
    if min_rows:
        filtered = [
            r for r in filtered
            if len(r.table_markdown.split("\n")) >= min_rows + 2
        ]

    title_contains = filters.get("table_title_contains")
    if title_contains:
        filtered = [
            r for r in filtered
            if r.table_title and title_contains.lower() in r.table_title.lower()
        ]

    doc_name = filters.get("document_name")
    if doc_name:
        filtered = [r for r in filtered if r.document_name == doc_name]

    return filtered
