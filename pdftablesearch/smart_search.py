"""스마트 검색 — 벡터 유사도 + LLM 리랭킹으로 정밀한 표 식별.

:func:`smart_search` 진입점은 벡터 기반 후보 검색과 LLM 기반 선택을
결합하여 주어진 쿼리에 가장 관련성 높은 단일 표를 찾는다.

파이프라인::

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
    """벡터 검색 결과를 LLM용 후보 딕셔너리로 포맷한다.

    인덱스는 1-based로 LLM 프롬프트 형식에 맞춘다.
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
    persist_dir: str = "./.chroma",
    progress_callback: Optional[Callable] = None,
) -> TableSearchResult:
    """벡터 검색 + LLM으로 가장 관련성 높은 표 하나를 찾는다.

    ``top_k``개 후보를 벡터 검색으로 가져오고 LLM이 최적 표를 선택한다.
    LLM 실패 시 ``fallback_to_vector``가 ``True``면 벡터 #1 결과를 반환한다.
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
        persist_dir=persist_dir,
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
    persist_dir: str,
) -> List[TableSearchResult]:
    """smart_search의 벡터 검색 단계를 실행한다.

    PDF 로딩, 벡터 인덱스 구축, top-k 후보 검색을 수행한다.
    """
    from pdftablesearch.search import PDFTableSearch

    try:
        searcher = PDFTableSearch(persist_dir=persist_dir)

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
    """smart_search의 LLM 선택 단계를 실행한다.

    후보 결과를 포맷하여 LLM에 보내고 선택 결과를 받는다.
    실패 시 ``None``을 반환한다 (호출자가 fallback 결정).
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
