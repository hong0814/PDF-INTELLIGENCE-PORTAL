"""z.ai LLM 클라이언트 — 스마트 표 선택.

``ZaiLLMClient`` — z.ai ChatOpenAI 호환 API 래퍼로
후보 표 설명을 LLM에 보내 가장 관련성 높은 표의 구조화된 선택 결과를 받는다.

처리 항목:

- Prompt construction for table selection
- LLM API invocation with retry logic
- Structured JSON response parsing
- Graceful degradation on API failures
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

from pdftablesearch.config import get_settings
from pdftablesearch.exceptions import APIError, APIConnectionError
from pdftablesearch.utils import get_api_key, get_logger, truncate_text

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_LLM_ENDPOINT = "https://ollama.com/v1"
_DEFAULT_LLM_MODEL = "gpt-oss:120b"
_DEFAULT_TIMEOUT = 30
_DEFAULT_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# LLM Response Cache
# ---------------------------------------------------------------------------


class LLMCache:
    """
    LLM 표 선택 응답의 디스크 기반 캐시.
    
    캐시 키당 하나의 JSON 파일을 저장한다.
    """

    def __init__(
        self,
        cache_dir: str = "./.cache/llm",
        enabled: bool = True,
        ttl: int = 86400,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.ttl = ttl
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- key helpers ---------------------------------------------------------

    @staticmethod
    def _cache_key(query: str, table_descriptions: str) -> str:
        content = f"{query}|||{table_descriptions}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    # -- public API ----------------------------------------------------------

    def get(self, query: str, table_descriptions: str) -> Optional[LLMSelectionResult]:
        """캐시된 결과를 반환하거나 미스/만료 시 ``None``을 반환한다."""
        if not self.enabled:
            return None

        key = self._cache_key(query, table_descriptions)
        path = self._cache_path(key)

        if not path.exists():
            return None

        if time.time() - path.stat().st_mtime > self.ttl:
            path.unlink(missing_ok=True)
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LLMSelectionResult(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def put(
        self, query: str, table_descriptions: str, result: LLMSelectionResult
    ) -> None:
        """LLM 선택 결과를 디스크에 영속화한다."""
        if not self.enabled:
            return

        key = self._cache_key(query, table_descriptions)
        path = self._cache_path(key)
        path.write_text(
            json.dumps(
                {
                    "selected_index": result.selected_index,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "raw_response": result.raw_response,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SMART_SEARCH_SYSTEM_PROMPT = """You are a financial table search expert. \
Your task is to analyze a list of HTML tables from a financial report and select \
the single most relevant table for a given user query.

The table content is provided in HTML format (<table> elements). Analyze the \
HTML structure to understand cell relationships including merged cells \
(colspan/rowspan), headers (<th>), and data cells (<td>).

Rules:
1. Analyze the user's search intent carefully
2. Match against table titles and HTML content
3. Consider Korean financial terminology (e.g., 포괄손익계산서, 재무상태표, 현금흐름표)
4. Select the ONE table that best matches the query
5. Respond with ONLY a JSON object, no additional text"""

_SMART_SEARCH_USER_PROMPT = """User Query: {query}

Available Tables:
{table_descriptions}

Respond with ONLY a JSON object in this exact format:
{{
  "selected_index": <1-based index of best table>,
  "confidence": <0.0 to 1.0 confidence score>,
  "reasoning": "<brief explanation in Korean>"
}}"""


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

@dataclass
class LLMSelectionResult:
    """LLM 표 선택의 구조화된 결과."""

    selected_index: int
    confidence: float = 0.0
    reasoning: str = ""
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ZaiLLMClient:
    """
    z.ai LLM 클라이언트 — 표 선택.
    
    z.ai ChatOpenAI 호환 API 래퍼로 후보 표 설명을 LLM에 보내
    가장 관련성 높은 표의 구조화된 선택 결과를 받는다.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        llm_endpoint: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        cache_enabled: Optional[bool] = None,
        cache_dir: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        resolved_key = (
            api_key
            or settings.ollama_api_key
            or get_api_key(None)
        )
        self.model = model or settings.zai_llm_model
        self.max_retries = max_retries

        endpoint = llm_endpoint or settings.zai_llm_endpoint or _DEFAULT_LLM_ENDPOINT

        self._llm = ChatOpenAI(
            base_url=endpoint,
            api_key=resolved_key,
            model=self.model,
            temperature=0.1,
            request_timeout=timeout,
            max_retries=max_retries,
        )
        self._cache = LLMCache(
            cache_dir=cache_dir or f"{settings.cache_dir}/llm",
            enabled=cache_enabled if cache_enabled is not None else settings.cache_enabled,
            ttl=cache_ttl if cache_ttl is not None else settings.llm_cache_ttl_seconds,
        )

        logger.info(
            "ZaiLLMClient initialized: model=%s, endpoint=%s, cache=%s",
            self.model,
            endpoint,
            self._cache.enabled,
        )

    # -- Public API ----------------------------------------------------------

    def select_table(
        self,
        query: str,
        table_descriptions: str,
    ) -> LLMSelectionResult:
        """후보 표를 LLM에 보내 최적 선택을 받는다."""
        logger.info(
            "Calling LLM for table selection: query='%s', desc_length=%d",
            query[:100],
            len(table_descriptions),
        )

        cached = self._cache.get(query, table_descriptions)
        if cached is not None:
            logger.info("LLM cache hit for query: %s", query[:50])
            return cached

        # Build messages
        user_prompt = _SMART_SEARCH_USER_PROMPT.format(
            query=query,
            table_descriptions=table_descriptions,
        )

        messages = [
            {"role": "system", "content": _SMART_SEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Call LLM
        try:
            response = self._llm.invoke(messages)
            response_text = (
                response.content if hasattr(response, "content") else str(response)
            )
        except Exception as exc:
            logger.error("LLM API call failed: %s", exc)
            raise APIError(
                f"LLM API call failed: {exc}",
                details={"query": query[:100], "model": self.model},
            ) from exc

        # Parse response
        result = _parse_selection_response(response_text)
        self._cache.put(query, table_descriptions, result)
        return result

    def select_table_from_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        content_max_length: int = 500,
    ) -> LLMSelectionResult:
        """편의 메서드: 후보를 포맷하고 최적 표를 선택한다."""
        descriptions = _format_candidates_for_llm(
            candidates, content_max_length=content_max_length
        )
        return self.select_table(query=query, table_descriptions=descriptions)


# ---------------------------------------------------------------------------
# Candidate formatting
# ---------------------------------------------------------------------------

def _truncate_html_safe(html_content: str, max_length: int = 500) -> str:
    """열린 태그를 끊지 않고 HTML 콘텐츠를 자른다."""
    if len(html_content) <= max_length:
        return html_content

    # Cut at max_length, then back up to avoid splitting a tag
    cut = html_content[:max_length]
    last_open = cut.rfind("<")
    last_close = cut.rfind(">")

    if last_open > last_close:
        # We're inside a tag -- back up to before the opening bracket
        cut = cut[:last_open]

    return cut.rstrip() + "..."


def _format_candidates_for_llm(
    candidates: List[Dict[str, Any]],
    content_max_length: int = 500,
) -> str:
    """후보 표를 LLM용 구조화된 설명으로 포맷한다."""
    parts: List[str] = []

    for candidate in candidates:
        idx = candidate.get("index", 0)
        page = candidate.get("page_number", "?")
        title = candidate.get("title") or "(No title)"
        content = candidate.get("content", "")
        content_preview = _truncate_html_safe(content, max_length=content_max_length)

        block = (
            f"Table {idx} (Page {page})\n"
            f"Title: {title}\n"
            f"Content: {content_preview}"
        )
        parts.append(block)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_selection_response(response_text: str) -> LLMSelectionResult:
    """LLM JSON 응답을 구조화된 결과로 파싱한다."""
    content = response_text.strip()

    # Strip markdown code blocks if present
    if "```" in content:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()

    # Try direct JSON parse
    parsed = _try_parse_json(content)

    if parsed is None:
        # Try to find JSON object in text
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            parsed = _try_parse_json(match.group(0))

    if parsed is None:
        logger.error(
            "Could not parse LLM selection response: %s",
            truncate_text(content, 200),
        )
        raise ValueError(
            f"Failed to parse LLM response as JSON. "
            f"Raw response: {truncate_text(content, 200)}"
        )

    # Extract required fields
    selected_index = parsed.get("selected_index")
    if selected_index is None:
        # Try alternate field names
        selected_index = parsed.get("selectedIndex") or parsed.get("selected")

    if selected_index is None:
        raise ValueError(
            f"LLM response missing 'selected_index' field. "
            f"Parsed JSON: {parsed}"
        )

    confidence = float(parsed.get("confidence", 0.0))
    reasoning = str(parsed.get("reasoning", ""))

    # Clamp confidence to [0, 1]
    confidence = max(0.0, min(1.0, confidence))

    return LLMSelectionResult(
        selected_index=int(selected_index),
        confidence=confidence,
        reasoning=reasoning,
        raw_response=response_text,
    )


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """텍스트를 JSON으로 파싱을 시도하고 실패 시 None을 반환한다."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    return None
