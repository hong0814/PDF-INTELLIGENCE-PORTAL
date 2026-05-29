"""Tests for the Weaviate vector store backend using a fake client."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from langchain_core.documents import Document

from pdftablesearch.vectorstores.weaviate_store import WeaviateTableVectorStore


class DummyEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 0.0, 0.0] for index, _ in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeData:
    def __init__(self, collection: "FakeCollection") -> None:
        self.collection = collection

    def exists(self, object_id: UUID) -> bool:
        return str(object_id) in self.collection.objects

    def insert(self, *, uuid: UUID, properties: dict, vector: list[float]) -> None:
        self.collection.objects[str(uuid)] = SimpleNamespace(
            uuid=uuid,
            properties=properties,
            vector=vector,
            metadata=SimpleNamespace(distance=0.2, score=None),
        )

    def delete_by_id(self, object_id: UUID) -> None:
        self.collection.objects.pop(str(object_id), None)


class FakeQuery:
    def __init__(self, collection: "FakeCollection") -> None:
        self.collection = collection

    def near_vector(self, **_kwargs):
        objects = list(self.collection.objects.values())
        for index, obj in enumerate(objects):
            obj.metadata = SimpleNamespace(distance=0.3 - (index * 0.2), score=None)
        return SimpleNamespace(objects=objects)

    def fetch_objects(self, **_kwargs):
        return SimpleNamespace(objects=list(self.collection.objects.values()))


class FakeCollection:
    def __init__(self) -> None:
        self.objects: dict[str, SimpleNamespace] = {}
        self.data = FakeData(self)
        self.query = FakeQuery(self)


class FakeCollections:
    def __init__(self) -> None:
        self.collection = FakeCollection()

    def exists(self, _name: str) -> bool:
        return True

    def get(self, _name: str) -> FakeCollection:
        return self.collection


class FakeClient:
    def __init__(self) -> None:
        self.collections = FakeCollections()


def _patch_weaviate(monkeypatch, fake_client: FakeClient) -> None:
    monkeypatch.setattr(
        "pdftablesearch.vectorstores.weaviate_store.get_weaviate_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "pdftablesearch.vectorstores.weaviate_store.ensure_pdf_collections",
        lambda _client: None,
    )
    monkeypatch.setattr(
        WeaviateTableVectorStore,
        "_build_filter",
        lambda self, filter_metadata=None: filter_metadata,
    )
    monkeypatch.setattr(
        WeaviateTableVectorStore,
        "_metadata_query",
        staticmethod(lambda: object()),
    )


def test_weaviate_backend_adds_and_lists_documents(monkeypatch, tmp_path):
    fake_client = FakeClient()
    _patch_weaviate(monkeypatch, fake_client)
    store = WeaviateTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="pdf_tables",
    )
    documents = [
        Document(page_content="table one", metadata={"table_id": "t1"}),
        Document(page_content="table two", metadata={"table_id": "t2"}),
    ]

    object_ids = store.add_documents(documents)
    listed = store.list_documents()

    assert len(object_ids) == 2
    assert [doc.page_content for doc in listed] == ["table one", "table two"]
    assert [doc.metadata["table_id"] for doc in listed] == ["t1", "t2"]


def test_weaviate_backend_search_normalizes_lower_distance_first(monkeypatch, tmp_path):
    fake_client = FakeClient()
    _patch_weaviate(monkeypatch, fake_client)
    store = WeaviateTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="pdf_tables",
    )
    store.add_documents(
        [
            Document(page_content="table one", metadata={"table_id": "t1"}),
            Document(page_content="table two", metadata={"table_id": "t2"}),
        ]
    )

    results = store.similarity_search("table", k=2)

    assert [doc.metadata["table_id"] for doc, _score in results] == ["t2", "t1"]
    assert [score for _doc, score in results] == [0.09999999999999998, 0.3]


def test_weaviate_backend_delete_where_deletes_matching_objects(monkeypatch, tmp_path):
    fake_client = FakeClient()
    _patch_weaviate(monkeypatch, fake_client)
    store = WeaviateTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="pdf_tables",
    )
    store.add_documents([Document(page_content="table one", metadata={"table_id": "t1"})])

    deleted = store.delete_where({"table_id": "t1"})

    assert deleted == 1
    assert fake_client.collections.collection.objects == {}


def test_weaviate_backend_delete_where_honors_unindexed_metadata(monkeypatch, tmp_path):
    fake_client = FakeClient()
    _patch_weaviate(monkeypatch, fake_client)
    store = WeaviateTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="pdf_tables",
    )
    store.add_documents(
        [
            Document(
                page_content="table one",
                metadata={"table_id": "t1", "custom_tag": "keep"},
            ),
            Document(
                page_content="table two",
                metadata={"table_id": "t2", "custom_tag": "delete"},
            ),
        ]
    )

    deleted = store.delete_where({"custom_tag": "delete"})
    remaining = store.list_documents()

    assert deleted == 1
    assert [doc.metadata["table_id"] for doc in remaining] == ["t1"]
