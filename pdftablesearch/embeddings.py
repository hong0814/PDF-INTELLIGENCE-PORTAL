"""
Custom LangChain Embeddings class for z.ai API.

Provides ``ZaiEmbeddings``, an implementation of
:class:`langchain_core.embeddings.Embeddings` that calls the z.ai embedding
endpoint with retry logic and batch support.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional

import requests
from langchain_core.embeddings import Embeddings
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pdftablesearch.exceptions import (
    APIAuthenticationError,
    APIConnectionError,
    APIError,
    RateLimitError,
)
from pdftablesearch.utils import get_api_key, get_logger, get_retry_config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_EMBEDDING_ENDPOINT = "https://api.z.ai/api/embeddings"
_DEFAULT_MODEL = "embedding-3"
_DEFAULT_TIMEOUT = 30
_DEFAULT_BATCH_SIZE = 20


class ZaiEmbeddings(Embeddings):
    """LangChain-compatible Embeddings class backed by the z.ai API.

    Supports both single-query embedding (``embed_query``) and batch
    document embedding (``embed_documents``) with automatic retries,
    configurable batch sizes, and structured error handling.

    Args:
        api_key: z.ai API key. Falls back to the ``ZAI_API_KEY``
            environment variable.
        model: Embedding model name to pass to the API.
        endpoint: URL of the embeddings endpoint.
        timeout: HTTP request timeout in seconds.
        batch_size: Maximum number of texts per batch request.

    Example::

        from pdftablesearch.embeddings import ZaiEmbeddings

        emb = ZaiEmbeddings(api_key="your-key")
        vectors = emb.embed_documents(["hello", "world"])
        query_vec = emb.embed_query("search term")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        endpoint: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        self.api_key = get_api_key(api_key)
        self.model = model
        self.endpoint = endpoint or _DEFAULT_EMBEDDING_ENDPOINT
        self.timeout = timeout
        self.batch_size = batch_size

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    # -- Internal helpers ----------------------------------------------------

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """Call the z.ai embedding API for a list of texts.

        Sends texts in a single request and returns the corresponding
        embedding vectors.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (one per input text).

        Raises:
            APIAuthenticationError: On 401/403 responses.
            RateLimitError: On 429 responses.
            APIConnectionError: On network failures.
            APIError: On other HTTP errors.
        """
        payload: dict[str, Any] = {
            "input": texts if len(texts) > 1 else texts[0],
            "model": self.model,
        }

        try:
            response = self._session.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise APIConnectionError(
                f"Failed to connect to embedding API at {self.endpoint}: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise APIConnectionError(
                f"Embedding API request timed out after {self.timeout}s: {exc}"
            ) from exc

        # Handle HTTP errors
        if response.status_code == 401 or response.status_code == 403:
            raise APIAuthenticationError(
                "Authentication failed. Check your ZAI_API_KEY.",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                retry_after=float(retry_after) if retry_after else None,
            )
        if response.status_code != 200:
            raise APIError(
                f"Embedding API returned status {response.status_code}: "
                f"{response.text[:500]}",
                status_code=response.status_code,
            )

        data = response.json()
        embedding_data = data.get("data", [])

        # Sort by index to maintain order
        embedding_data.sort(key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in embedding_data]

    @retry(
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def _embed_with_retry(self, texts: List[str]) -> List[List[float]]:
        """Embed texts with automatic retry on transient failures.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors.
        """
        return self._call_embedding_api(texts)

    # -- LangChain Embeddings interface --------------------------------------

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document texts.

        Texts are processed in batches of ``self.batch_size`` to avoid
        overwhelming the API. Each batch is retried independently on
        transient failures.

        Args:
            texts: List of document strings to embed.

        Returns:
            List of embedding vectors, one per input text.

        Raises:
            APIError: If the embedding API fails after retries.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.debug(
                "Embedding batch %d/%d (%d texts)",
                batch_num,
                total_batches,
                len(batch),
            )

            try:
                batch_embeddings = self._embed_with_retry(batch)
                all_embeddings.extend(batch_embeddings)
            except APIError:
                logger.error(
                    "Failed to embed batch %d/%d after retries", batch_num, total_batches
                )
                raise

        logger.info("Embedded %d texts successfully", len(all_embeddings))
        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string.

        Args:
            text: Query text to embed.

        Returns:
            Single embedding vector.

        Raises:
            APIError: If the embedding API fails after retries.
        """
        logger.debug("Embedding query: %s", text[:100])
        embeddings = self._embed_with_retry([text])
        return embeddings[0]
