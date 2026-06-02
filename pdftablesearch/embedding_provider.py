"""임베딩 제공자 팩토리.

로컬 SentenceTransformers 및 원격 z.ai API 제공자를 지원하는
통합 임베딩 인스턴스 생성 진입점.
"""

from __future__ import annotations

from typing import Literal, Optional

from langchain_core.embeddings import Embeddings

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

ProviderType = Literal["local", "remote"]


def create_embeddings(
    provider: ProviderType = "local",
    *,
    # 원격(z.ai) 설정
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
    batch_size: int = 20,
    # 로컬(SentenceTransformers) 설정
    local_model: str = "BAAI/bge-m3",
    device: str = "cpu",
) -> Embeddings:
    """지정된 제공자에 맞는 임베딩 인스턴스를 생성한다.

    매개변수:
        provider: 임베딩 제공자 유형.
            ``"local"``은 SentenceTransformers 사용 (API 키 불필요).
            ``"remote"``는 z.ai API 사용 (API 키 필요).
        api_key: z.ai API 키 (``"remote"`` 전용).
            미지정 시 ``ZAI_API_KEY`` 환경변수 사용.
        endpoint: 임베딩 API 엔드포인트 오버라이드.
        model: 임베딩 모델명 오버라이드.
        timeout: API 요청 타임아웃(초).
        batch_size: 원격 API 호출 시 최대 텍스트 수.
        local_model: SentenceTransformers 모델명.
        device: 로컬 모델 실행 디바이스 (``"cpu"`` 또는 ``"cuda"``).

    반환:
        LangChain 호환 Embeddings 인스턴스.
    """
    if provider == "local":
        from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings

        actual_model = model or local_model
        logger.info(
            "Creating local embedding provider: model=%s, device=%s",
            actual_model,
            device,
        )
        return SentenceTransformerEmbeddings(
            model_name=actual_model,
            device=device,
        )

    if provider == "remote":
        from pdftablesearch.embeddings import ZaiEmbeddings

        logger.info(
            "Creating remote embedding provider: model=%s",
            model or "embedding-3",
        )
        return ZaiEmbeddings(
            api_key=api_key,
            model=model or "embedding-3",
            endpoint=endpoint,
            timeout=timeout,
            batch_size=batch_size,
        )

    raise ValueError(
        f"Unknown embedding provider: {provider!r}. "
        f"Must be 'local' or 'remote'."
    )
