"""Hybrid search combining BM25 keyword matching with vector similarity.

Uses Reciprocal Rank Fusion (RRF) to merge results from both retrieval
methods, providing better recall for exact matches (numbers, proper nouns)
while retaining semantic understanding from vector search.

Usage::

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

_RRF_K = 60  # RRF constant (standard value from original paper)


def _bm25_search(
    documents: List[Document],
    query: str,
    k: int = 20,
) -> List[tuple[Document, int]]:
    """Simple keyword-based search using token overlap scoring.

    Returns up to *k* (Document, rank) tuples sorted by relevance.
    """
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
    """Merge BM25 and vector results using Reciprocal Rank Fusion.

    Each document's RRF score = ``sum(1 / (k + rank))`` across both
    result lists.  Documents appearing in both lists get higher scores.
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
    chroma_persist_dir: str = "./.chroma",
) -> List[TableSearchResult]:
    """Search combining BM25 keyword matching and vector similarity.

    Args:
        query: Natural language search query.
        pdf_path: Path to the PDF document.
        max_results: Maximum number of results.
        use_hybrid: Whether to use hybrid PDF processing.
        output_dir: Optional output directory override.
        chroma_persist_dir: ChromaDB persistence directory.

    Returns:
        List of :class:`TableSearchResult` sorted by fused relevance.
    """
    from pdftablesearch.loader import PDFProcessor
    from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
    from pdftablesearch.vectorstore import TableVectorStore

    logger.info("Hybrid search: query='%s', pdf='%s'", query[:50], pdf_path)

    processor = PDFProcessor()
    processor.load_documents(pdf_path, use_hybrid=use_hybrid, output_dir=output_dir)
    documents = processor.get_documents()

    if not documents:
        return []

    bm25_results = _bm25_search(documents, query, k=max_results * 3)

    embeddings = SentenceTransformerEmbeddings()
    vector_store = TableVectorStore(embeddings=embeddings, persist_dir=chroma_persist_dir)
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
