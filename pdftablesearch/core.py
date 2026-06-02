"""PDFTableSearch 핵심 검색 파이프라인.

PDF 로딩, 벡터 인덱싱, 유사도 검색, LLM 리랭킹(선택), 결과 포매팅의
전체 워크플로우를 오케스트레이션한다. 단일/다중 문서 검색을 모두
지원하는 기본 공개 API ``search_tables``를 제공한다.

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
from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

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
    persist_dir: str = "./.chroma",
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[..., None]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Union[List[TableSearchResult], MultiDocumentSearchResult]:
    """
    하나 이상의 PDF 문서에서 표를 검색한다.
    
    *pdf_path*가 단일 문자열이면 단일 문서 검색,
    리스트면 다중 문서 검색을 수행한다.
    """
    # Determine mode from input type
    if isinstance(pdf_path, str):
        results = _search_single(
            pdf_path=pdf_path,
            query=query,
            max_results=max_results,
            use_llm_rerank=use_llm_rerank,
            persist_dir=persist_dir,
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
            persist_dir=persist_dir,
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
    persist_dir: str = "./.chroma",
    output_dir: Optional[str] = None,
) -> List[TableSearchResult]:
    """
    단일 문서 검색 파이프라인을 실행한다.
    
    PDF 변환, 벡터 인덱싱, 검색, 결과 포매팅의 전체 워크플로우를 처리한다.
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
        persist_dir=persist_dir,
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
    persist_dir: str = "./.chroma",
    progress_callback: Optional[Callable[..., None]] = None,
) -> MultiDocumentSearchResult:
    """
    다중 문서 검색 파이프라인을 실행한다.
    
    각 PDF를 독립적으로 처리하고 결과를 병합한다.
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
        persist_dir=persist_dir,
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
    """ThreadPoolExecutor로 모든 PDF에서 문서를 병렬 로딩한다."""
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
    """선택적 LLM 리랭킹을 적용하고 결과를 포매팅한다."""
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
    """벡터 검색 원시 결과를 ``TableSearchResult`` 객체로 변환한다."""
    results: List[TableSearchResult] = []

    for doc, score in search_results:
        result = TableSearchResult.from_langchain_document(doc, score)
        results.append(result)

    # Sort by relevance score ascending (lower 벡터 거리 = better)
    # and then reverse so best results come first
    results.sort(key=lambda r: r.relevance_score or float("inf"))
    return results


def _format_reranked_results(
    reranked_docs: List[Document],
    original_results: List[tuple[Document, float]],
) -> List[TableSearchResult]:
    """리랭킹된 문서를 ``TableSearchResult`` 객체로 변환한다."""
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
    """순위를 유지하면서 문서당 결과 제한을 적용한다."""
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
    """메타데이터 기반 필터를 검색 결과에 적용한다."""
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
