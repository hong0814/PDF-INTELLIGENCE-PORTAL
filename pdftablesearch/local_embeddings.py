"""로컬 SentenceTransformers 기반 LangChain 임베딩 클래스.

API 키 없이 로컬에서 실행되는
:class:`langchain_core.embeddings.Embeddings` 구현체.
"""

from __future__ import annotations

from typing import List

import os

os.environ["HF_HUB_OFFLINE"] = "1"

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_DEFAULT_MODEL = "BAAI/bge-m3"


class SentenceTransformerEmbeddings(Embeddings):
    """SentenceTransformers 기반 LangChain 임베딩 클래스.

    로컬 머신에서 실행되며 API 키가 필요 없다. 한국어 및 다국어를 지원한다.

    매개변수:
        model_name: SentenceTransformers 모델명.
            기본값 ``BAAI/bge-m3``은 한국어 및 100개 이상 언어의
            검색 성능이 우수하다.
        device: 실행 디바이스 (``cpu`` 또는 ``cuda``). 기본값 ``cpu``.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        device: str = "cpu",
        local_model_path: str = "",
    ) -> None:
        self.model_name = model_name
        self.device = device

        if not local_model_path:
            try:
                from pdftablesearch.config import get_settings
                local_model_path = get_settings().local_embedding_model_path or ""
            except Exception:
                pass

        if local_model_path and os.path.isdir(local_model_path):
            model_path = local_model_path
        else:
            model_path = model_name

        logger.info("Loading SentenceTransformer model: %s", model_path)
        self._model = SentenceTransformer(
            model_path,
            device=device,
            trust_remote_code=True,
        )
        logger.info("Model loaded successfully")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """문서 텍스트 목록을 임베딩한다.

        매개변수:
            texts: 임베딩할 문서 문자열 목록.

        반환:
            입력 텍스트별 임베딩 벡터 목록.
        """
        if not texts:
            return []

        logger.debug("Embedding %d documents", len(texts))

        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        result = embeddings.tolist()
        logger.info("Embedded %d texts successfully", len(result))
        return result

    def embed_query(self, text: str) -> List[float]:
        """단일 쿼리 문자열을 임베딩한다.

        매개변수:
            text: 임베딩할 쿼리 텍스트.

        반환:
            단일 임베딩 벡터.
        """
        logger.debug("Embedding query: %s", text[:100])

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return embedding.tolist()
