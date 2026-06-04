"""LLM 기반 리랭킹 컴프레서.

z.ai LLM API를 사용하여 벡터 유사도 검색 결과를 리랭킹하는
``ZaiRerankCompressor``와 로컬 CrossEncoder 기반 ``CrossEncoderReranker``를 제공한다.
API 장애 시 원래 순서로 graceful fallback한다.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Sequence

from langchain_core.callbacks import Callbacks
from langchain_core.documents import Document
from langchain_core.language_models import BaseLanguageModel
from langchain_openai import ChatOpenAI

from pdftablesearch.exceptions import APIError
from pdftablesearch.utils import get_api_key, get_logger, truncate_text

logger = get_logger(__name__)

_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
_cross_encoder_instance = None

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_LLM_ENDPOINT = "https://api.z.ai/api/coding/paas/v4"
_DEFAULT_LLM_MODEL = "glm-4.7"
_DEFAULT_TOP_K = 10
_DEFAULT_TIMEOUT = 10
_RERANK_PROMPT_TEMPLATE = """You are a table search re-ranking assistant. Given a user query and a list of table descriptions, rank the tables by relevance to the query.

Query: {query}

Tables:
{table_contexts}

Return ONLY a JSON array with the ranked results. Each entry must have:
- "index": the original table number (1-based)
- "score": relevance score between 0.0 and 1.0

Sort by score in descending order. Example format:
[
  {{"index": 3, "score": 0.95}},
  {{"index": 1, "score": 0.82}},
  {{"index": 5, "score": 0.71}}
]

Respond with ONLY the JSON array, no additional text."""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_rerank_response(response_text: str) -> List[dict[str, Any]]:
    """LLM 리랭킹 응답을 구조화된 결과로 파싱한다.

    마크다운 코드 블록이나 JSON 배열 주변 여분 텍스트 등
    다양한 응답 형식을 처리한다.
    """
    content = response_text.strip()

    # Strip markdown code blocks if present
    if "```" in content:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()

    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "results" in parsed:
            return parsed["results"]
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM rerank response as JSON")

    # Last resort: try to find JSON array in the text
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.error("Could not parse rerank response: %s", truncate_text(content, 200))
    return []


class ZaiRerankCompressor:
    """LLM 기반 문서 리랭커 — 검색 결과 정제.

    z.ai LLM API로 벡터 유사도 검색 후보 문서를 재평가·재정렬한다.
    LangChain 호환 ``compress_documents`` 인터페이스를 구현한다.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        llm_endpoint: Optional[str] = None,
        model: Optional[str] = None,
        top_k: int = _DEFAULT_TOP_K,
        timeout: int = _DEFAULT_TIMEOUT,
        llm: Optional[BaseLanguageModel] = None,
    ) -> None:
        self.top_k = top_k

        if llm is not None:
            self._llm = llm
        else:
            resolved_key = get_api_key(api_key)
            self._llm = ChatOpenAI(
                base_url=llm_endpoint or _DEFAULT_LLM_ENDPOINT,
                api_key=resolved_key,
                model=model or _DEFAULT_LLM_MODEL,
                temperature=0.1,
                request_timeout=timeout,
            )

    def _build_table_contexts(self, documents: List[Document]) -> str:
        """리랭킹 프롬프트용 번호가 매겨진 표 설명을 생성한다."""
        contexts: List[str] = []
        for i, doc in enumerate(documents, 1):
            table_id = doc.metadata.get("table_id", f"unknown_{i}")
            page = doc.metadata.get("page_number", "?")
            content_preview = truncate_text(doc.page_content, 300)
            contexts.append(
                f"Table {i} (ID: {table_id}, Page: {page}):\n{content_preview}"
            )
        return "\n\n".join(contexts)

    def compress_documents(
        self,
        documents: Sequence[Document],
        query: str,
        callbacks: Optional[Callbacks] = None,
    ) -> Sequence[Document]:
        """z.ai LLM API로 문서를 리랭킹한다.

        쿼리와 후보 문서를 LLM에 보내 관련성 점수가 매겨진 순위 목록을 받는다.
        실패 시 원래 문서 순서를 그대로 반환한다.
        """
        if not documents:
            return []

        # Limit candidates to a reasonable number
        candidates = list(documents)[: self.top_k * 2]

        logger.info(
            "Re-ranking %d candidate documents for query: %s",
            len(candidates),
            query[:100],
        )

        # Build prompt
        table_contexts = self._build_table_contexts(candidates)
        prompt = _RERANK_PROMPT_TEMPLATE.format(
            query=query, table_contexts=table_contexts
        )

        # Call LLM
        try:
            response = self._llm.invoke(prompt)
            response_text = (
                response.content if hasattr(response, "content") else str(response)
            )
        except Exception as exc:
            logger.warning(
                "LLM re-ranking failed, returning original order: %s", exc
            )
            return documents

        # Parse response
        rankings = _parse_rerank_response(response_text)
        if not rankings:
            logger.warning("No valid rankings parsed from LLM response")
            return documents

        # Build reordered list
        indexed_candidates = list(enumerate(candidates))
        reranked: List[Document] = []

        for rank_entry in rankings:
            idx = rank_entry.get("index", 0) - 1  # Convert 1-based to 0-based
            score = rank_entry.get("score", 0.0)

            if 0 <= idx < len(candidates):
                doc = candidates[idx]
                # Create a new Document with rerank_score in metadata
                updated_metadata = {**doc.metadata, "rerank_score": score}
                reranked.append(
                    Document(page_content=doc.page_content, metadata=updated_metadata)
                )

        # If re-ranking produced fewer results than expected, pad with
        # remaining candidates in original order
        reranked_ids = {doc.metadata.get("table_id") for doc in reranked}
        for doc in candidates:
            if doc.metadata.get("table_id") not in reranked_ids:
                reranked.append(doc)

        result = reranked[: self.top_k]
        logger.info("Re-ranking complete: %d documents returned", len(result))
        return result


def _get_cross_encoder():
    global _cross_encoder_instance
    if _cross_encoder_instance is None:
        from sentence_transformers import CrossEncoder
        logger.info("Loading CrossEncoder model: %s", _CROSS_ENCODER_MODEL)
        _cross_encoder_instance = CrossEncoder(_CROSS_ENCODER_MODEL)
        logger.info("CrossEncoder model loaded")
    return _cross_encoder_instance


class CrossEncoderReranker:
    """로컬 CrossEncoder 리랭커 (msmarco-MiniLM-L-6-v2).

    CPU 기반 빠른 리랭킹 (~45ms/30후보)으로 벡터/BM25 검색 후
    결과 품질을 향상시킨다.
    """

    def __init__(self, top_k: int = 10) -> None:
        self.top_k = top_k
        self._model = None

    def rerank(
        self,
        documents: List[Document],
        query: str,
    ) -> List[Document]:
        if not documents:
            return []

        self._model = _get_cross_encoder()

        pairs = [(query, doc.page_content) for doc in documents]

        try:
            scores = self._model.predict(pairs)
        except Exception as exc:
            logger.warning("CrossEncoder reranking failed: %s", exc)
            return documents[: self.top_k]

        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[: self.top_k]:
            updated_meta = {**doc.metadata, "rerank_score": float(score)}
            results.append(Document(page_content=doc.page_content, metadata=updated_meta))

        logger.info(
            "CrossEncoder reranked %d docs, top score: %.4f",
            len(documents),
            scored[0][1] if scored else 0,
        )
        return results
