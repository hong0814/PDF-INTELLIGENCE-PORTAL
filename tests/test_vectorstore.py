"""Tests for pdftablesearch.vectorstore module."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from langchain_core.documents import Document

from pdftablesearch.exceptions import VectorIndexError, VectorSearchError
from pdftablesearch.vectorstores import create_vector_store as TableVectorStore


@pytest.fixture
def mock_embeddings():
    """Create mock ZaiEmbeddings."""
    emb = MagicMock()
    emb.embed_documents.return_value = [[0.1, 0.2, 0.3]]
    emb.embed_query.return_value = [0.1, 0.2, 0.3]
    return emb


@pytest.fixture
def sample_documents():
    return [
        Document(
            page_content="| A | B |\n|---|---|\n| 1 | 2 |",
            metadata={
                "page_number": 0,
                "bounding_box": [0, 0, 500, 200],
                "table_id": "table_0_0",
                "document_name": "test.pdf",
            },
        ),
        Document(
            page_content="| X | Y |\n|---|---|\n| 3 | 4 |",
            metadata={
                "page_number": 1,
                "bounding_box": [0, 0, 500, 200],
                "table_id": "table_1_0",
                "document_name": "test.pdf",
            },
        ),
    ]


class TestTableVectorStoreInit:
    def test_defaults(self, mock_embeddings):
        store = TableVectorStore(embeddings=mock_embeddings)
        assert store.collection_name == "pdf_tables"
        assert store.persist_dir == "./.chroma"

    def test_custom_config(self, mock_embeddings):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir="/tmp/test_chroma",
            collection_name="custom_tables",
        )
        assert store.collection_name == "custom_tables"
        assert store.persist_dir == "/tmp/test_chroma"


class TestTableVectorStoreNotInitialized:
    def test_vectorstore_property_raises(self, mock_embeddings, tmp_path):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir=str(tmp_path / "nonexistent"),
        )
        with pytest.raises(VectorIndexError, match="No vector store found"):
            _ = store.vectorstore

    def test_is_initialized_false(self, mock_embeddings, tmp_path):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir=str(tmp_path / "nonexistent"),
        )
        assert store.is_initialized is False

    def test_get_document_count_returns_zero(self, mock_embeddings, tmp_path):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir=str(tmp_path / "nonexistent"),
        )
        assert store.get_document_count() == 0


class TestTableVectorStoreSearch:
    def test_search_without_init_raises(self, mock_embeddings, tmp_path):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir=str(tmp_path / "nonexistent"),
        )
        with pytest.raises(VectorSearchError, match="not initialized"):
            store.similarity_search("query")


class TestTableVectorStoreStats:
    def test_stats_uninitialized(self, mock_embeddings, tmp_path):
        store = TableVectorStore(
            embeddings=mock_embeddings,
            persist_dir=str(tmp_path / "nonexistent"),
        )
        stats = store.get_stats()
        assert stats["is_initialized"] is False
        assert stats["document_count"] == 0
