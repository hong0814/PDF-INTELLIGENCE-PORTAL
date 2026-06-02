"""
PDFTableSearch - PDF 문서 내 표 의미 검색 라이브러리.

빠른 시작::

    from pdftablesearch import search_tables

    results = search_tables(
        pdf_path="report.pdf",
        query="분기별 매출 성장률",
    )

    for table in results:
        print(f"Page {table.page_number}: {table.table_id}")
"""

__version__ = "0.2.0"

from pdftablesearch.search import PDFTableSearch
from pdftablesearch.core import search_tables
from pdftablesearch.smart_search import smart_search
from pdftablesearch.loader import PDFProcessor
from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.embeddings import ZaiEmbeddings
from pdftablesearch.embedding_provider import create_embeddings, ProviderType
from pdftablesearch.reranker import ZaiRerankCompressor
from pdftablesearch.vectorstores import create_vector_store as TableVectorStore
from pdftablesearch.llm_client import ZaiLLMClient, LLMSelectionResult
from pdftablesearch.config import Settings, get_settings
from pdftablesearch.hybrid_search import hybrid_search
from pdftablesearch.table_qa import ask_table
from pdftablesearch.models import (
    BatchProcessingResult,
    MultiDocumentSearchResult,
    ProcessingResult,
    TableSearchResult,
)
from pdftablesearch.exceptions import (
    APIAuthenticationError,
    APIConnectionError,
    APIError,
    MetadataMismatchError,
    PDFProcessingError,
    RateLimitError,
    ResultFormattingError,
    TableParsingError,
    TableSearchError,
    VectorIndexError,
    VectorSearchError,
)

__all__ = [
    "PDFTableSearch",
    "search_tables",
    "smart_search",
    "PDFProcessor",
    "SentenceTransformerEmbeddings",
    "ZaiEmbeddings",
    "ZaiRerankCompressor",
    "TableVectorStore",
    "ZaiLLMClient",
    "LLMSelectionResult",
    "Settings",
    "get_settings",
    "create_embeddings",
    "ProviderType",
    "hybrid_search",
    "ask_table",
    "TableSearchResult",
    "MultiDocumentSearchResult",
    "ProcessingResult",
    "BatchProcessingResult",
    "TableSearchError",
    "PDFProcessingError",
    "TableParsingError",
    "MetadataMismatchError",
    "APIError",
    "APIConnectionError",
    "APIAuthenticationError",
    "RateLimitError",
    "VectorIndexError",
    "VectorSearchError",
    "ResultFormattingError",
]
