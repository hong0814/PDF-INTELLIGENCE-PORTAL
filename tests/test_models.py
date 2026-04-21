"""Tests for pdftablesearch.models module."""

import json
import pytest

from langchain_core.documents import Document

from pdftablesearch.models import (
    BatchProcessingResult,
    MultiDocumentSearchResult,
    ProcessingResult,
    TableSearchResult,
)


class TestTableSearchResult:
    """Tests for TableSearchResult dataclass."""

    def test_creation_with_defaults(self):
        result = TableSearchResult(
            page_number=1,
            bounding_box=[10, 20, 300, 400],
            table_markdown="| A | B |\n|---|---|\n| 1 | 2 |",
            table_id="table_1_0",
            document_name="report.pdf",
        )
        assert result.page_number == 1
        assert result.bounding_box == [10, 20, 300, 400]
        assert result.table_id == "table_1_0"
        assert result.relevance_score is None
        assert result.rerank_score is None

    def test_to_dict(self):
        result = TableSearchResult(
            page_number=2,
            bounding_box=[0, 0, 100, 100],
            table_markdown="| X |",
            table_id="table_2_0",
            document_name="test.pdf",
            relevance_score=0.85,
            rerank_score=0.92,
        )
        d = result.to_dict()
        assert d["page_number"] == 2
        assert d["bounding_box"] == [0, 0, 100, 100]
        assert d["relevance_score"] == 0.85
        assert d["rerank_score"] == 0.92

    def test_to_json(self):
        result = TableSearchResult(
            page_number=0,
            bounding_box=[],
            table_markdown="test",
            table_id="table_0_0",
            document_name="doc.pdf",
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["table_id"] == "table_0_0"

    def test_from_dict(self):
        data = {
            "page_number": 3,
            "bounding_box": [1, 2, 3, 4],
            "table_markdown": "| H |",
            "table_id": "table_3_1",
            "document_name": "annual.pdf",
            "relevance_score": 0.75,
            "rerank_score": None,
        }
        result = TableSearchResult.from_dict(data)
        assert result.page_number == 3
        assert result.bounding_box == [1, 2, 3, 4]
        assert result.relevance_score == 0.75

    def test_from_langchain_document(self):
        doc = Document(
            page_content="| Col1 | Col2 |\n|---|---|",
            metadata={
                "page_number": 5,
                "bounding_box": [10, 20, 300, 400],
                "table_id": "table_5_0",
                "document_name": "report.pdf",
            },
        )
        result = TableSearchResult.from_langchain_document(doc, score=0.88)
        assert result.page_number == 5
        assert result.relevance_score == 0.88
        assert result.table_markdown == "| Col1 | Col2 |\n|---|---|"
        assert result.document_name == "report.pdf"

    def test_from_dict_missing_fields_use_defaults(self):
        result = TableSearchResult.from_dict({})
        assert result.page_number == 0
        assert result.bounding_box == []
        assert result.table_markdown == ""
        assert result.relevance_score is None


class TestMultiDocumentSearchResult:
    """Tests for MultiDocumentSearchResult dataclass."""

    def test_auto_derived_counts(self):
        results = [
            TableSearchResult(
                page_number=0,
                bounding_box=[],
                table_markdown="",
                table_id="table_0_0",
                document_name="a.pdf",
            ),
            TableSearchResult(
                page_number=0,
                bounding_box=[],
                table_markdown="",
                table_id="table_0_1",
                document_name="a.pdf",
            ),
            TableSearchResult(
                page_number=0,
                bounding_box=[],
                table_markdown="",
                table_id="table_0_0",
                document_name="b.pdf",
            ),
        ]
        multi = MultiDocumentSearchResult(results=results, query="test")
        assert multi.total_results == 3
        assert multi.document_counts == {"a.pdf": 2, "b.pdf": 1}

    def test_filter_by_document(self):
        results = [
            TableSearchResult(
                page_number=i,
                bounding_box=[],
                table_markdown="",
                table_id=f"table_0_{i}",
                document_name="a.pdf" if i % 2 == 0 else "b.pdf",
            )
            for i in range(4)
        ]
        multi = MultiDocumentSearchResult(results=results, query="test")
        filtered = multi.filter_by_document("a.pdf")
        assert len(filtered) == 2
        assert all(r.document_name == "a.pdf" for r in filtered)

    def test_to_dict(self):
        results = [
            TableSearchResult(
                page_number=0,
                bounding_box=[],
                table_markdown="| A |",
                table_id="table_0_0",
                document_name="doc.pdf",
            )
        ]
        multi = MultiDocumentSearchResult(results=results, query="query")
        d = multi.to_dict()
        assert d["query"] == "query"
        assert len(d["results"]) == 1

    def test_empty_results(self):
        multi = MultiDocumentSearchResult(results=[], query="empty")
        assert multi.total_results == 0
        assert multi.document_counts == {}


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""

    def test_creation(self):
        result = ProcessingResult(
            documents_loaded=5,
            tables_extracted=3,
            document_name="test.pdf",
        )
        assert result.documents_loaded == 5
        assert result.tables_extracted == 3

    def test_to_dict(self):
        result = ProcessingResult(
            documents_loaded=2,
            tables_extracted=2,
            document_name="r.pdf",
        )
        d = result.to_dict()
        assert d["documents_loaded"] == 2
        assert d["document_name"] == "r.pdf"


class TestBatchProcessingResult:
    """Tests for BatchProcessingResult dataclass."""

    def test_auto_derived_totals(self):
        successful = [
            ProcessingResult(3, 3, "a.pdf"),
            ProcessingResult(2, 2, "b.pdf"),
        ]
        failed = {"c.pdf": "file not found"}
        batch = BatchProcessingResult(successful=successful, failed=failed)
        assert batch.total_tables == 5
        assert batch.total_documents == 3

    def test_empty_batch(self):
        batch = BatchProcessingResult(successful=[], failed={})
        assert batch.total_tables == 0
        assert batch.total_documents == 0

    def test_to_dict(self):
        batch = BatchProcessingResult(
            successful=[ProcessingResult(1, 1, "x.pdf")],
            failed={},
        )
        d = batch.to_dict()
        assert len(d["successful"]) == 1
        assert d["total_tables"] == 1
