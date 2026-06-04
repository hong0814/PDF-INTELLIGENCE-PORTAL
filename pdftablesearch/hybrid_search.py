"""하이브리드 검색 — BM25 키워드 매칭 + 벡터 유사도 결합.

Reciprocal Rank Fusion (RRF)으로 두 검색 결과를 병합하여
정확한 매칭(숫자, 고유명사)과 의미적 이해를 동시에 제공한다.

사용법::

    from pdftablesearch.hybrid_search import hybrid_search

    results = hybrid_search(
        query="PF대출 연체율",
        pdf_path="report.pdf",
    )
"""

from __future__ import annotations

from typing import List, Optional

from langchain_core.documents import Document

from pdftablesearch.models import TableSearchResult
from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

_RRF_K = 60  # RRF 상수 (원논문 표준값)


def _bm25_search(
    documents: List[Document],
    query: str,
    k: int = 20,
) -> List[tuple[Document, int]]:
    """토큰 오버랩 기반 키워드 검색. 최대 *k*개의 (Document, rank) 튜플을 반환한다."""
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return [(doc, idx + 1) for idx, doc in enumerate(documents[:k])]

    scored: List[tuple[Document, float]] = []
    for doc in documents:
        content_tokens = set(doc.page_content.lower().split())
        title = doc.metadata.get("table_title", "") or ""
        title_tokens = set(title.lower().split())

        content_overlap = len(query_tokens & content_tokens)
        title_overlap = len(query_tokens & title_tokens) * 2
        score = content_overlap + title_overlap

        if score > 0:
            scored.append((doc, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [(doc, rank + 1) for rank, (doc, _) in enumerate(scored[:k])]


def _rrf_merge(
    bm25_results: List[tuple[Document, int]],
    vector_results: List[tuple[Document, float]],
    k: int = _RRF_K,
) -> List[Document]:
    """Reciprocal Rank Fusion으로 BM25/벡터 결과를 병합한다.

    각 문서의 RRF 점수 = ``sum(1 / (k + rank))``.
    두 결과에 모두 등장하는 문서가 더 높은 점수를 받는다.
    """
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for doc, rank in bm25_results:
        doc_id = doc.metadata.get("table_id", id(doc))
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        doc_map[doc_id] = doc

    for doc, _score in vector_results:
        doc_id = doc.metadata.get("table_id", id(doc))
        rank = len([d for d, _ in vector_results if d.metadata.get("table_id", id(d)) == doc_id])
        rank = max(rank, 1)
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        doc_map[doc_id] = doc

    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    return [doc_map[doc_id] for doc_id in sorted_ids]


def hybrid_search(
    query: str,
    pdf_path: str,
    max_results: int = 5,
    use_hybrid: bool = True,
    output_dir: Optional[str] = None,
    persist_dir: str = "./.chroma",
) -> List[TableSearchResult]:
    """BM25 키워드 매칭 + 벡터 유사도를 결합한 검색.

    매개변수:
        query: 자연어 검색 쿼리.
        pdf_path: PDF 문서 경로.
        max_results: 최대 결과 수.
        use_hybrid: 하이브리드 PDF 처리 사용 여부.
        output_dir: 출력 디렉토리 오버라이드.
        persist_dir: 벡터 스토어 데이터 디렉토리.

    반환:
        RRF 융합 점수로 정렬된 :class:`TableSearchResult` 목록.
    """
    from pdftablesearch.loader import PDFProcessor
    from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
    from pdftablesearch.vectorstores import create_vector_store as TableVectorStore

    logger.info("Hybrid search: query='%s', pdf='%s'", query[:50], pdf_path)

    processor = PDFProcessor()
    processor.load_documents(pdf_path, use_hybrid=use_hybrid, output_dir=output_dir)
    documents = processor.get_documents()

    if not documents:
        return []

    bm25_results = _bm25_search(documents, query, k=max_results * 3)

    embeddings = SentenceTransformerEmbeddings()
    vector_store = TableVectorStore(embeddings=embeddings, persist_dir=persist_dir)
    vector_store.add_documents(documents)
    vector_results = vector_store.similarity_search(query=query, k=max_results * 3)

    merged = _rrf_merge(bm25_results, vector_results)
    merged = merged[:max_results]

    results: List[TableSearchResult] = []
    for doc in merged:
        result = TableSearchResult(
            page_number=doc.metadata.get("page_number", 0),
            bounding_box=doc.metadata.get("bounding_box", []),
            table_html=doc.metadata.get("table_html", ""),
            table_markdown=doc.page_content,
            table_id=doc.metadata.get("table_id", ""),
            document_name=doc.metadata.get("document_name", ""),
            table_title=doc.metadata.get("table_title"),
        )
        results.append(result)

    logger.info("Hybrid search returned %d results", len(results))
    return results
