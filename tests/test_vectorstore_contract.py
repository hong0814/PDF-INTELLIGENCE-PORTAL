"""Backend-neutral vector store contract tests."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.documents import Document

from pdftablesearch.config import Settings
from pdftablesearch.vectorstore import TableVectorStore
from pdftablesearch.vectorstores.chroma_store import ChromaTableVectorStore
from pdftablesearch.vectorstores.weaviate_store import WeaviateTableVectorStore


class DummyEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 0.0, 0.0] for index, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeChromaCollection:
    def __init__(self) -> None:
        self.deleted_ids: list[str] = []

    def get(self, **kwargs):
        if "where" in kwargs:
            return {"ids": ["doc-1"]}
        return {
            "ids": ["doc-1"],
            "documents": ["table body"],
            "metadatas": [{"table_id": "t1", "document_name": "a.pdf"}],
        }

    def delete(self, ids):
        self.deleted_ids.extend(ids)

    def count(self):
        return 1


def test_settings_default_vector_backend_is_weaviate():
    assert Settings.model_fields["vector_backend"].default == "weaviate"


def test_table_vector_store_facade_uses_weaviate_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_BACKEND", "weaviate")

    store = TableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="custom_tables",
    )

    assert isinstance(store, WeaviateTableVectorStore)
    assert store.collection_name == "custom_tables"
    assert store.persist_dir == str(tmp_path)


def test_table_vector_store_facade_uses_chroma_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_BACKEND", "chroma")

    store = TableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="custom_tables",
    )

    assert isinstance(store, ChromaTableVectorStore)
    assert store.collection_name == "custom_tables"
    assert store.persist_dir == str(tmp_path)


def test_chroma_backend_lists_documents_from_public_wrapper(tmp_path):
    collection = FakeChromaCollection()
    store = ChromaTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
    )
    store._vectorstore = SimpleNamespace(_collection=collection)

    documents = store.list_documents()

    assert documents == [
        Document(
            page_content="table body",
            metadata={"table_id": "t1", "document_name": "a.pdf"},
        )
    ]


def test_chroma_backend_delete_where_returns_deleted_count(tmp_path):
    collection = FakeChromaCollection()
    store = ChromaTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
    )
    store._vectorstore = SimpleNamespace(_collection=collection)

    deleted = store.delete_where({"document_name": "a.pdf"})

    assert deleted == 1
    assert collection.deleted_ids == ["doc-1"]
