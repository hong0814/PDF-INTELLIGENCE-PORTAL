"""
Smart search: vector similarity + LLM re-ranking for precise table identification.

Provides the :func:`smart_search` entry point that combines vector-based
candidate retrieval with LLM-based selection to find the single most
relevant table for a given query.

Pipeline::

    1. Vector search (top_k candidates)
    2. Candidate formatting for LLM
    3. LLM table selection
    4. Fallback to vector #1 on LLM failure (optional)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from langchain_core.documents import Document

from pdftablesearch.exceptions import (
    APIError,
    TableSearchError,
    VectorSearchError,
)
from pdftablesearch.llm_client import (
    LLMSelectionResult,
    ZaiLLMClient,
    _format_candidates_for_llm,
)
from pdftablesearch.models import TableSearchResult
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 20
_DEFAULT_LLM_MODEL = "glm-4.7"
_DEFAULT_CONTENT_MAX_LENGTH = 500


# ---------------------------------------------------------------------------
# Candidate preparation
# ---------------------------------------------------------------------------

def _prepare_candidates(
    search_results: List[TableSearchResult],
    content_max_length: int = _DEFAULT_CONTENT_MAX_LENGTH,
) -> List[Dict[str, Any]]:
    """Format vector search results into candidate dicts for the LLM.

    Each candidate includes an index, page number, title, and truncated
    content preview.  The index is 1-based to match the LLM prompt
    format.

    Args:
        search_results: Sorted list of :class:`TableSearchResult`
            from vector similarity search.
        content_max_length: Maximum characters of table content to
            include per candidate.

    Returns:
        List of dictionaries with keys ``index``, ``page_number``,
        ``title``, ``content``, ``table_id``.
    """
    candidates: List[Dict[str, Any]] = []

    for i, result in enumerate(search_results, start=1):
        candidates.append({
            "index": i,
            "page_number": result.page_number,
            "title": result.table_title,
            "content": result.table_html or result.table_markdown or "",
            "table_id": result.table_id,
        })

    logger.info("Prepared %d candidates for LLM evaluation", len(candidates))
    return candidates


# ---------------------------------------------------------------------------
# Core smart_search
# ---------------------------------------------------------------------------

def smart_search(
    query: str,
    pdf_path: str,
    top_k: int = _DEFAULT_TOP_K,
    llm_model: str = _DEFAULT_LLM_MODEL,
    api_key: Optional[str] = None,
    use_hybrid: bool = True,
    output_dir: Optional[str] = None,
    fallback_to_vector: bool = True,
    chroma_persist_dir: str = "./.chroma",
    progress_callback: Optional[Callable] = None,
) -> TableSearchResult:
    """Search for the single most relevant table using vector + LLM.

    Combines vector similarity search to retrieve ``top_k`` candidate
    tables with an LLM-based selection step that picks the best match.
    Falls back to the top vector search result if the LLM fails and
    ``fallback_to_vector`` is ``True``.

    Args:
        query: Natural language search query (Korean or English).
        pdf_path: Path to the PDF document.
        top_k: Number of vector search candidates for LLM evaluation.
            Default 20.
        llm_model: LLM model name (``glm-5.1``, ``glm-5.0``, etc.).
        api_key: z.ai API key.  Falls back to ``ZAI_API_KEY`` env var.
        use_hybrid: Whether to use hybrid PDF processing mode.
        output_dir: Override for PDF conversion output directory.
        fallback_to_vector: If ``True``, return vector search #1
            when the LLM fails.  If ``False``, raise an exception.
        chroma_persist_dir: Directory for ChromaDB persistence.
        progress_callback: Optional callable ``(phase, message, pct)``
            invoked at key pipeline stages for UI progress reporting.

    Returns:
        Single :class:`TableSearchResult` with the highest LLM
        confidence, or the best vector match on fallback.

    Raises:
        TableSearchError: If vector search fails, or if LLM fails
            and ``fallback_to_vector`` is ``False``.
        FileNotFoundError: If the PDF file does not exist.

    Example::

        from pdftablesearch.smart_search import smart_search

        result = smart_search(
            query="포괄손익계산서",
            pdf_path="report.pdf",
            top_k=20,
        )
        print(f"Best match: {result.table_title} (page {result.page_number})")
    """
    start_time = time.time()
    logger.info(
        "smart_search: query='%s', pdf='%s', top_k=%d, model=%s",
        query,
        pdf_path,
        top_k,
        llm_model,
    )

    if progress_callback:
        progress_callback("pdf", "PDF 변환 및 테이블 추출 중...", 10)

    # ------------------------------------------------------------------
    # Phase 1: Vector search
    # ------------------------------------------------------------------
    candidates_results = _run_vector_search(
        query=query,
        pdf_path=pdf_path,
        top_k=top_k,
        use_hybrid=use_hybrid,
        output_dir=output_dir,
        chroma_persist_dir=chroma_persist_dir,
    )

    if not candidates_results:
        raise TableSearchError(
            f"No tables found in '{pdf_path}' for query '{query}'",
            details={"pdf_path": pdf_path, "query": query},
        )

    if progress_callback:
        progress_callback("vector", f"벡터 검색 완료: {len(candidates_results)}개 후보", 50)

    logger.info(
        "Vector search returned %d candidates in %.2fs",
        len(candidates_results),
        time.time() - start_time,
    )

    # If only one result, return it directly
    if len(candidates_results) == 1:
        logger.info("Only one candidate found; returning directly")
        if progress_callback:
            progress_callback("done", "검색 완료 (후보 1개)", 100)
        return candidates_results[0]

    # ------------------------------------------------------------------
    # Phase 2: LLM selection
    # ------------------------------------------------------------------
    if progress_callback:
        progress_callback("llm", f"AI 분석 중... ({len(candidates_results)}개 후보 평가)", 70)
    selected_result = _run_llm_selection(
        query=query,
        candidates_results=candidates_results,
        llm_model=llm_model,
        api_key=api_key,
    )

    if selected_result is not None:
        elapsed = time.time() - start_time
        logger.info(
            "LLM selected table '%s' (index %d) in %.2fs",
            selected_result.table_title or selected_result.table_id,
            selected_result.rerank_score,
            elapsed,
        )
        if progress_callback:
            progress_callback("done", f"AI 선택 완료! ({elapsed:.1f}초)", 100)
        return selected_result

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------
    if fallback_to_vector:
        logger.warning(
            "LLM selection failed; falling back to vector search #1: %s",
            candidates_results[0].table_id,
        )
        if progress_callback:
            progress_callback("done", "AI 실패, 벡터 검색 결과로 대체", 100)
        return candidates_results[0]

    if progress_callback:
        progress_callback("error", "AI 분석 실패", 0)
    raise TableSearchError(
        "LLM table selection failed and fallback is disabled",
        details={
            "query": query,
            "pdf_path": pdf_path,
            "num_candidates": len(candidates_results),
        },
    )


# ---------------------------------------------------------------------------
# Vector search phase
# ---------------------------------------------------------------------------

def _run_vector_search(
    query: str,
    pdf_path: str,
    top_k: int,
    use_hybrid: bool,
    output_dir: Optional[str],
    chroma_persist_dir: str,
) -> List[TableSearchResult]:
    """Execute the vector search phase of smart_search.

    Uses :class:`~pdftablesearch.search.PDFTableSearch` to load the PDF,
    build a vector index, and retrieve the top-k candidates.

    Args:
        query: Search query string.
        pdf_path: Path to the PDF document.
        top_k: Number of candidates to retrieve.
        use_hybrid: Whether to use hybrid PDF processing.
        output_dir: Optional output directory override.
        chroma_persist_dir: ChromaDB persistence directory.

    Returns:
        List of :class:`TableSearchResult` sorted by vector similarity.

    Raises:
        VectorSearchError: If the vector search fails.
    """
    from pdftablesearch.search import PDFTableSearch

    try:
        searcher = PDFTableSearch(chroma_persist_dir=chroma_persist_dir)

        results = searcher.search(
            pdf_path=pdf_path,
            query=query,
            max_results=top_k,
            use_hybrid=use_hybrid,
            output_dir=output_dir,
            reset_vector_store=False,  # 새로운 temp_dir이므로 reset 불필요
        )

        return results

    except VectorSearchError:
        raise
    except Exception as exc:
        raise VectorSearchError(
            f"Vector search phase failed: {exc}",
            details={"pdf_path": pdf_path, "query": query[:100]},
        ) from exc


# ---------------------------------------------------------------------------
# LLM selection phase
# ---------------------------------------------------------------------------

def _run_llm_selection(
    query: str,
    candidates_results: List[TableSearchResult],
    llm_model: str,
    api_key: Optional[str],
) -> Optional[TableSearchResult]:
    """Execute the LLM selection phase of smart_search.

    Formats the candidate results and sends them to the LLM for
    selection.  Returns ``None`` on any failure (caller decides
    fallback behavior).

    Args:
        query: Original search query.
        candidates_results: Vector search results.
        llm_model: LLM model name.
        api_key: Optional z.ai API key.

    Returns:
        Selected :class:`TableSearchResult` with ``rerank_score``
        set to the LLM confidence, or ``None`` on failure.
    """
    # Prepare candidates
    candidates = _prepare_candidates(candidates_results)

    # Initialize LLM client
    try:
        client = ZaiLLMClient(
            api_key=api_key,
            model=llm_model,
        )
    except ValueError as exc:
        logger.warning("Cannot initialize LLM client: %s", exc)
        return None

    # Call LLM for selection
    try:
        llm_result = client.select_table_from_candidates(
            query=query,
            candidates=candidates,
        )
    except (APIError, ValueError) as exc:
        logger.warning("LLM selection failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected LLM error: %s", exc)
        return None

    # Map LLM selection back to TableSearchResult
    selected_index = llm_result.selected_index  # 1-based

    if selected_index < 1 or selected_index > len(candidates_results):
        logger.warning(
            "LLM returned out-of-range index %d (have %d candidates)",
            selected_index,
            len(candidates_results),
        )
        return None

    # 1-based to 0-based
    target = candidates_results[selected_index - 1]

    # Attach LLM metadata
    target.rerank_score = llm_result.confidence
    logger.info(
        "LLM selected table %d/%d: %s (confidence=%.2f, reasoning='%s')",
        selected_index,
        len(candidates_results),
        target.table_id,
        llm_result.confidence,
        llm_result.reasoning[:100],
    )

    return target
