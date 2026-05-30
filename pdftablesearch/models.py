"""
Data models for PDFTableSearch library.

Defines structured result types for search operations, PDF processing,
and batch processing. All models support dictionary serialization
for JSON export and can be constructed from LangChain Document objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document


@dataclass
class TableSearchResult:
    """Represents a single table search result.

    Contains the table content in HTML format along with metadata
    about its location within the source PDF document and relevance scores.

    Attributes:
        page_number: Zero-indexed page number where the table appears.
        bounding_box: Bounding box coordinates ``[x1, y1, x2, y2]``
            relative to the page.
        table_html: Complete table content in HTML format, preserving
            merged cells (colspan/rowspan).
        table_markdown: Markdown fallback representation derived from
            ``table_html``.  Kept for backward compatibility.
        table_id: Unique identifier (e.g. ``"table_3_2"``).
        document_name: Filename of the source PDF document.
        relevance_score: Similarity score from vector search.
        rerank_score: Refined score from optional LLM re-ranking.
        table_title: Optional table title extracted from the document.
    """

    page_number: int
    bounding_box: List[int]
    table_html: str = ""
    table_markdown: str = ""
    table_id: str = ""
    document_name: str = ""
    relevance_score: Optional[float] = None
    rerank_score: Optional[float] = None
    table_title: Optional[str] = None
    table_type: Optional[str] = None
    group_id: Optional[str] = None

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary suitable for JSON serialization.

        Returns:
            Dictionary with all result fields.
        """
        return {
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "table_html": self.table_html,
            "table_markdown": self.table_markdown,
            "table_id": self.table_id,
            "document_name": self.document_name,
            "relevance_score": self.relevance_score,
            "rerank_score": self.rerank_score,
            "table_title": self.table_title,
            "table_type": self.table_type,
            "group_id": self.group_id,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string.

        Args:
            indent: Number of spaces for indentation.

        Returns:
            JSON-formatted string.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TableSearchResult:
        """Construct from a dictionary.

        Args:
            data: Dictionary with result fields.

        Returns:
            New :class:`TableSearchResult` instance.
        """
        return cls(
            page_number=data.get("page_number", 0),
            bounding_box=data.get("bounding_box", []),
            table_html=data.get("table_html", ""),
            table_markdown=data.get("table_markdown", ""),
            table_id=data.get("table_id", ""),
            document_name=data.get("document_name", ""),
            relevance_score=data.get("relevance_score"),
            rerank_score=data.get("rerank_score"),
            table_title=data.get("table_title"),
            table_type=data.get("table_type"),
            group_id=data.get("group_id"),
        )

    @classmethod
    def from_langchain_document(
        cls, document: Document, score: float
    ) -> TableSearchResult:
        """Construct from a LangChain Document and its similarity score.

        Args:
            document: LangChain :class:`Document` with table content and metadata.
            score: Similarity or distance score from vector search.

        Returns:
            New :class:`TableSearchResult` instance populated from the document.
        """
        table_html = document.metadata.get("table_html", "")
        # page_content may contain a title prefix before the actual HTML
        page_content = document.page_content

        # If table_html is not in metadata, try extracting from page_content
        if not table_html and page_content:
            # Check if page_content starts with HTML table
            stripped = page_content.strip()
            if stripped.startswith("<table") or stripped.startswith("<Table"):
                table_html = stripped
            else:
                # Title prefix + HTML: find the first <table
                table_start = page_content.find("<table")
                if table_start < 0:
                    table_start = page_content.find("<Table")
                if table_start >= 0:
                    table_html = page_content[table_start:]

        return cls(
            page_number=document.metadata.get("page_number", 0),
            bounding_box=document.metadata.get("bounding_box", []),
            table_html=table_html,
            table_markdown=page_content,
            table_id=document.metadata.get("table_id", ""),
            document_name=document.metadata.get("document_name", ""),
            relevance_score=score,
            table_title=document.metadata.get("table_title"),
            table_type=document.metadata.get("table_type"),
            group_id=document.metadata.get("group_id"),
        )


@dataclass
class MultiDocumentSearchResult:
    """Result of a multi-document search operation.

    Aggregates results from searching across multiple PDF documents,
    with per-document counts and overall statistics.

    Attributes:
        results: Ordered list of search results across all documents.
        document_counts: Mapping of document name to number of results
            found in that document.
        total_results: Total number of results.
        query: The original search query string.
    """

    results: List[TableSearchResult]
    document_counts: Dict[str, int] = field(default_factory=dict)
    total_results: int = 0
    query: str = ""

    def __post_init__(self) -> None:
        """Derive counts and total from results if not explicitly set."""
        if not self.document_counts and self.results:
            counts: Dict[str, int] = {}
            for r in self.results:
                counts[r.document_name] = counts.get(r.document_name, 0) + 1
            self.document_counts = counts
        if self.total_results == 0 and self.results:
            self.total_results = len(self.results)

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary for JSON serialization.

        Returns:
            Dictionary with all fields.
        """
        return {
            "results": [r.to_dict() for r in self.results],
            "document_counts": self.document_counts,
            "total_results": self.total_results,
            "query": self.query,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string.

        Args:
            indent: Number of spaces for indentation.

        Returns:
            JSON-formatted string.
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # -- Filtering -----------------------------------------------------------

    def filter_by_document(self, document_name: str) -> List[TableSearchResult]:
        """Return results belonging to a specific document.

        Args:
            document_name: Name of the source PDF document.

        Returns:
            Filtered list of results.
        """
        return [r for r in self.results if r.document_name == document_name]


@dataclass
class ProcessingResult:
    """Result of a single PDF processing operation.

    Attributes:
        documents_loaded: Number of LangChain Documents created.
        tables_extracted: Number of tables found in the PDF.
        document_name: Filename of the processed PDF.
    """

    documents_loaded: int
    tables_extracted: int
    document_name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary for JSON serialization."""
        return {
            "documents_loaded": self.documents_loaded,
            "tables_extracted": self.tables_extracted,
            "document_name": self.document_name,
        }


@dataclass
class BatchProcessingResult:
    """Result of a batch PDF processing operation across multiple files.

    Attributes:
        successful: List of :class:`ProcessingResult` for each file that
            was processed without error.
        failed: Mapping of filename to error message for files that failed.
        total_tables: Sum of tables extracted across all successful files.
        total_documents: Total number of files processed (successful + failed).
    """

    successful: List[ProcessingResult]
    failed: Dict[str, str]
    total_tables: int = 0
    total_documents: int = 0

    def __post_init__(self) -> None:
        """Derive totals from component lists if not explicitly set."""
        if self.total_tables == 0 and self.successful:
            self.total_tables = sum(s.tables_extracted for s in self.successful)
        if self.total_documents == 0:
            self.total_documents = len(self.successful) + len(self.failed)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a plain dictionary for JSON serialization."""
        return {
            "successful": [r.to_dict() for r in self.successful],
            "failed": self.failed,
            "total_tables": self.total_tables,
            "total_documents": self.total_documents,
        }
