"""
PDFTableSearch - Semantic table search within PDF documents.

A Python library that enables semantic search of tables within PDF
documents using LLM-powered natural language queries. Built on
LangChain, ChromaDB, opendataloader-pdf, and z.ai API.

Quick start::

    from pdftablesearch import search_tables

    # Single document search
    results = search_tables(
        pdf_path="report.pdf",
        query="quarterly revenue growth",
    )

    for table in results:
        print(f"Page {table.page_number}: {table.table_id}")

    # Multi-document search
    result = search_tables(
        pdf_path=["report1.pdf", "report2.pdf"],
        query="annual revenue",
    )
    print(f"Found {result.total_results} tables")

Advanced usage::

    from pdftablesearch import PDFProcessor, ZaiEmbeddings, TableVectorStore

    # Direct LangChain integration
    processor = PDFProcessor()
    result = processor.load_documents("report.pdf")
    documents = processor.get_documents()

    embeddings = ZaiEmbeddings(api_key="your-key")
    store = TableVectorStore(embeddings=embeddings)
    store.add_documents(documents)
    results = store.similarity_search("financial summary", k=5)
"""

__version__ = "0.1.0"

# Core search API
from pdftablesearch.search import PDFTableSearch
from pdftablesearch.core import search_tables
from pdftablesearch.smart_search import smart_search

# PDF processing
from pdftablesearch.loader import PDFProcessor

# LangChain components
from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings
from pdftablesearch.embeddings import ZaiEmbeddings
from pdftablesearch.embedding_provider import create_embeddings, ProviderType
from pdftablesearch.reranker import ZaiRerankCompressor
from pdftablesearch.vectorstore import TableVectorStore

# LLM client
from pdftablesearch.llm_client import ZaiLLMClient, LLMSelectionResult

# Configuration
from pdftablesearch.config import Settings, get_settings

# Embedding provider
from pdftablesearch.embedding_provider import create_embeddings, ProviderType

# Hybrid search
from pdftablesearch.hybrid_search import hybrid_search

# Table QA
from pdftablesearch.table_qa import ask_table

# Data models
from pdftablesearch.models import (
    BatchProcessingResult,
    MultiDocumentSearchResult,
    ProcessingResult,
    TableSearchResult,
)

# Exceptions
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
    # Core API
    "PDFTableSearch",
    "search_tables",
    "smart_search",
    # Processing
    "PDFProcessor",
    # LangChain components
    "SentenceTransformerEmbeddings",
    "ZaiEmbeddings",
    "ZaiRerankCompressor",
    "TableVectorStore",
    # LLM client
    "ZaiLLMClient",
    "LLMSelectionResult",
    # Configuration
    "Settings",
    "get_settings",
    # Embedding provider
    "create_embeddings",
    "ProviderType",
    # Hybrid search
    "hybrid_search",
    # Table QA
    "ask_table",
    # Data models
    "TableSearchResult",
    "MultiDocumentSearchResult",
    "ProcessingResult",
    "BatchProcessingResult",
    # Exceptions
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
