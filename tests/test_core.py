"""Tests for pdftablesearch.core module."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from langchain_core.documents import Document

from pdftablesearch.core import (
    _apply_per_doc_limit,
    _format_reranked_results,
    _format_search_results,
    search_tables,
)
from pdftablesearch.models import TableSearchResult, MultiDocumentSearchResult


class TestFormatSearchResults:
    """Tests for _format_search_results helper."""

    def test_basic_formatting(self):
        doc = Document(
            page_content="| A | B |",
            metadata={
                "page_number": 0,
                "bounding_box": [0, 0, 100, 100],
                "table_id": "table_0_0",
                "document_name": "test.pdf",
            },
        )
        results = _format_search_results([(doc, 0.85)])
        assert len(results) == 1
        assert results[0].page_number == 0
        assert results[0].relevance_score == 0.85
        assert results[0].document_name == "test.pdf"

    def test_sorted_by_score(self):
        docs = [
            (
                Document(
                    page_content="table1",
                    metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "a.pdf"},
                ),
                0.5,
            ),
            (
                Document(
                    page_content="table2",
                    metadata={"page_number": 1, "bounding_box": [], "table_id": "t2", "document_name": "a.pdf"},
                ),
                0.9,
            ),
        ]
        results = _format_search_results(docs)
        # ChromaDB distance: lower = better, so 0.5 comes first
        assert results[0].relevance_score == 0.5

    def test_empty_input(self):
        results = _format_search_results([])
        assert results == []


class TestFormatRerankedResults:
    """Tests for _format_reranked_results helper."""

    def test_with_rerank_scores(self):
        original = [
            (
                Document(
                    page_content="table1",
                    metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "a.pdf"},
                ),
                0.5,
            ),
        ]
        reranked = [
            Document(
                page_content="table1",
                metadata={
                    "page_number": 0,
                    "bounding_box": [],
                    "table_id": "t1",
                    "document_name": "a.pdf",
                    "rerank_score": 0.95,
                },
            ),
        ]
        results = _format_reranked_results(reranked, original)
        assert len(results) == 1
        assert results[0].relevance_score == 0.5  # Original vector score
        assert results[0].rerank_score == 0.95

    def test_sorted_by_rerank_score(self):
        original = [
            (
                Document(
                    page_content="t1",
                    metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "a.pdf"},
                ),
                0.5,
            ),
            (
                Document(
                    page_content="t2",
                    metadata={"page_number": 1, "bounding_box": [], "table_id": "t2", "document_name": "a.pdf"},
                ),
                0.3,
            ),
        ]
        reranked = [
            Document(
                page_content="t2",
                metadata={
                    "page_number": 1, "bounding_box": [], "table_id": "t2",
                    "document_name": "a.pdf", "rerank_score": 0.9,
                },
            ),
            Document(
                page_content="t1",
                metadata={
                    "page_number": 0, "bounding_box": [], "table_id": "t1",
                    "document_name": "a.pdf", "rerank_score": 0.7,
                },
            ),
        ]
        results = _format_reranked_results(reranked, original)
        assert results[0].table_id == "t2"  # Higher rerank score first
        assert results[0].rerank_score == 0.9


class TestApplyPerDocLimit:
    """Tests for _apply_per_doc_limit helper."""

    def test_within_limit(self):
        results = [
            TableSearchResult(0, [], "", "t1", "a.pdf"),
            TableSearchResult(1, [], "", "t2", "a.pdf"),
        ]
        filtered = _apply_per_doc_limit(results, max_per_doc=3)
        assert len(filtered) == 2

    def test_exceeds_limit(self):
        results = [
            TableSearchResult(i, [], "", f"t{i}", "a.pdf")
            for i in range(5)
        ]
        filtered = _apply_per_doc_limit(results, max_per_doc=2)
        assert len(filtered) == 2

    def test_mixed_documents(self):
        results = [
            TableSearchResult(0, [], "", "t1", "a.pdf"),
            TableSearchResult(1, [], "", "t2", "b.pdf"),
            TableSearchResult(2, [], "", "t3", "a.pdf"),
            TableSearchResult(3, [], "", "t4", "b.pdf"),
            TableSearchResult(4, [], "", "t5", "a.pdf"),
        ]
        filtered = _apply_per_doc_limit(results, max_per_doc=2)
        # a.pdf: t1, t3 (2 results), b.pdf: t2, t4 (2 results), t5 excluded
        assert len(filtered) == 4
        assert all(r.document_name != "a.pdf" or i < 2 for i, r in enumerate(filtered) if False)

    def test_empty_input(self):
        filtered = _apply_per_doc_limit([], max_per_doc=5)
        assert filtered == []


class TestSearchTablesSingleDocument:
    """Tests for search_tables with a single PDF path (str)."""

    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_single_doc_no_tables(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls
    ):
        mock_processor = MagicMock()
        mock_processor.load_documents.return_value = MagicMock(tables_extracted=0)
        mock_processor.get_documents.return_value = []
        mock_processor_cls.return_value = mock_processor

        result = search_tables("test.pdf", "query")
        assert result == []
        assert isinstance(result, list)

    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_single_doc_with_results(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls
    ):
        docs = [
            Document(
                page_content="| A | B |",
                metadata={
                    "page_number": 0,
                    "bounding_box": [0, 0, 100, 100],
                    "table_id": "table_0_0",
                    "document_name": "test.pdf",
                },
            ),
        ]

        mock_processor = MagicMock()
        mock_processor.load_documents.return_value = MagicMock(tables_extracted=1)
        mock_processor.get_documents.return_value = docs
        mock_processor_cls.return_value = mock_processor

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [(docs[0], 0.85)]
        mock_store_cls.return_value = mock_store

        results = search_tables("test.pdf", "revenue", max_results=3)
        assert len(results) == 1
        assert isinstance(results, list)
        assert results[0].table_id == "table_0_0"

    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_single_doc_with_reranking(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls
    ):
        docs = [
            Document(
                page_content="| A |",
                metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "test.pdf"},
            ),
        ]

        mock_processor = MagicMock()
        mock_processor.load_documents.return_value = MagicMock(tables_extracted=1)
        mock_processor.get_documents.return_value = docs
        mock_processor_cls.return_value = mock_processor

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [(docs[0], 0.5)]
        mock_store_cls.return_value = mock_store

        with patch("pdftablesearch.core.ZaiRerankCompressor") as mock_reranker_cls:
            mock_reranker = MagicMock()
            reranked_doc = Document(
                page_content="| A |",
                metadata={
                    "page_number": 0, "bounding_box": [], "table_id": "t1",
                    "document_name": "test.pdf", "rerank_score": 0.95,
                },
            )
            mock_reranker.compress_documents.return_value = [reranked_doc]
            mock_reranker_cls.return_value = mock_reranker

            results = search_tables(
                "test.pdf", "query", use_llm_rerank=True
            )
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0].rerank_score == 0.95


class TestSearchTablesMultiDocument:
    """Tests for search_tables with multiple PDF paths (List[str])."""

    @patch("pdftablesearch.core._load_all_documents_sequential", return_value=[])
    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_multi_doc_no_documents_found(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls, mock_load
    ):
        mock_processor = MagicMock()
        mock_processor.load_documents_batch.return_value = MagicMock(
            successful=[], failed={}
        )
        mock_processor_cls.return_value = mock_processor

        result = search_tables(["a.pdf"], "query")
        assert isinstance(result, MultiDocumentSearchResult)
        assert result.total_results == 0

    @patch("pdftablesearch.core._load_all_documents_sequential")
    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_multi_doc_with_results(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls, mock_load
    ):
        docs = [
            Document(
                page_content="| A |",
                metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "a.pdf"},
            ),
            Document(
                page_content="| B |",
                metadata={"page_number": 1, "bounding_box": [], "table_id": "t2", "document_name": "b.pdf"},
            ),
        ]
        mock_load.return_value = docs

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [(docs[0], 0.8), (docs[1], 0.6)]
        mock_store_cls.return_value = mock_store

        result = search_tables(["a.pdf", "b.pdf"], "query")
        assert isinstance(result, MultiDocumentSearchResult)
        assert result.total_results == 2
        assert len(result.document_counts) == 2

    @patch("pdftablesearch.core._load_all_documents_sequential")
    @patch("pdftablesearch.core.TableVectorStore")
    @patch("pdftablesearch.core.ZaiEmbeddings")
    @patch("pdftablesearch.core.PDFProcessor")
    @patch("pdftablesearch.core.get_api_key", return_value="test-key")
    def test_multi_doc_with_per_doc_limit(
        self, mock_key, mock_processor_cls, mock_emb_cls, mock_store_cls, mock_load
    ):
        docs = [
            Document(
                page_content="| A |",
                metadata={"page_number": 0, "bounding_box": [], "table_id": "t1", "document_name": "a.pdf"},
            ),
            Document(
                page_content="| B |",
                metadata={"page_number": 1, "bounding_box": [], "table_id": "t2", "document_name": "a.pdf"},
            ),
            Document(
                page_content="| C |",
                metadata={"page_number": 2, "bounding_box": [], "table_id": "t3", "document_name": "a.pdf"},
            ),
        ]
        mock_load.return_value = docs

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [
            (docs[0], 0.8), (docs[1], 0.6), (docs[2], 0.4)
        ]
        mock_store_cls.return_value = mock_store

        result = search_tables(
            ["a.pdf"], "query",
            max_results=10,
            max_results_per_doc=2,
        )
        assert isinstance(result, MultiDocumentSearchResult)
        assert result.total_results == 2
