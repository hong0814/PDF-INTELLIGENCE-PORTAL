"""
LLM-based re-ranking compressor for LangChain retrieval.

Provides ``ZaiRerankCompressor``, which uses the z.ai LLM API to re-rank
candidate documents retrieved by vector similarity search. Falls back
gracefully to the original ordering on API failures.
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
    """Parse the LLM re-ranking response into structured results.

    Handles various response formats including markdown code blocks
    and extra text around the JSON array.

    Args:
        response_text: Raw LLM response text.

    Returns:
        List of dictionaries with ``index`` and ``score`` keys.
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
    """LLM-based document re-ranker for search result refinement.

    Uses the z.ai LLM API to re-score and re-order candidate documents
    from vector similarity search. Implements a LangChain-compatible
    ``compress_documents`` interface.

    Args:
        api_key: z.ai API key. Falls back to ``ZAI_API_KEY`` env var.
        llm_endpoint: URL of the LLM API endpoint.
        model: LLM model name.
        top_k: Maximum number of documents to return after re-ranking.
        timeout: LLM API timeout in seconds.
        llm: Pre-configured LangChain LLM instance. If provided,
            *api_key*, *llm_endpoint*, and *model* are ignored.

    Example::

        from pdftablesearch.reranker import ZaiRerankCompressor

        compressor = ZaiRerankCompressor(api_key="your-key")
        reranked = compressor.compress_documents(candidates, "search query")
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
        """Build numbered table descriptions for the re-ranking prompt.

        Args:
            documents: Candidate documents to describe.

        Returns:
            Formatted string with numbered table summaries.
        """
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
        """Re-rank documents using the z.ai LLM API.

        Sends the query and candidate documents to the LLM, which returns
        a ranked list with relevance scores. On any failure, returns the
        original documents unchanged.

        Args:
            documents: Candidate documents from vector search.
            query: Original search query.
            callbacks: Optional LangChain callbacks (currently unused).

        Returns:
            Re-ordered (and potentially filtered) documents with updated
            ``rerank_score`` in metadata.
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
