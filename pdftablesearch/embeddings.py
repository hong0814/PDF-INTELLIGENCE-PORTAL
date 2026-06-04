"""z.ai API 기반 LangChain 임베딩 클래스.

재시도 로직과 배치 처리를 지원하는
:class:`langchain_core.embeddings.Embeddings` 구현체.
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

_DEFAULT_EMBEDDING_ENDPOINT = "https://api.z.ai/api/embeddings"
_DEFAULT_MODEL = "embedding-3"
_DEFAULT_TIMEOUT = 30
_DEFAULT_BATCH_SIZE = 20


class ZaiEmbeddings(Embeddings):
    """z.ai API 기반 LangChain 임베딩 클래스.

    단일 쿼리(``embed_query``) 및 배치 문서(``embed_documents``) 임베딩을 지원하며,
    자동 재시도, 배치 크기 설정, 구조화된 오류 처리를 제공한다.

    매개변수:
        api_key: z.ai API 키. 미지정 시 ``ZAI_API_KEY`` 환경변수 사용.
        model: API에 전달할 임베딩 모델명.
        endpoint: 임베딩 엔드포인트 URL.
        timeout: HTTP 요청 타임아웃(초).
        batch_size: 배치당 최대 텍스트 수.
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

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """z.ai 임베딩 API를 호출한다.

        매개변수:
            texts: 임베딩할 문자열 목록.

        반환:
            임베딩 벡터 목록.

        예외:
            APIAuthenticationError: 401/403 응답 시.
            RateLimitError: 429 응답 시.
            APIConnectionError: 네트워크 장애 시.
            APIError: 기타 HTTP 오류 시.
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
        embedding_data.sort(key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in embedding_data]

    @retry(
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    def _embed_with_retry(self, texts: List[str]) -> List[List[float]]:
        """일시적 장애 시 자동 재시도하며 임베딩한다."""
        return self._call_embedding_api(texts)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """문서 텍스트 목록을 임베딩한다.

        ``self.batch_size`` 단위로 나누어 API를 호출하며,
        각 배치는 독립적으로 재시도된다.

        매개변수:
            texts: 임베딩할 문서 문자열 목록.

        반환:
            입력 텍스트별 임베딩 벡터 목록.

        예외:
            APIError: 재시도 후에도 API 호출 실패 시.
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
        """단일 쿼리 문자열을 임베딩한다.

        매개변수:
            text: 임베딩할 쿼리 텍스트.

        반환:
            단일 임베딩 벡터.

        예외:
            APIError: 재시도 후에도 API 호출 실패 시.
        """
        logger.debug("Embedding query: %s", text[:100])
        embeddings = self._embed_with_retry([text])
        return embeddings[0]
