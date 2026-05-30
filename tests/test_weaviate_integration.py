"""Optional integration tests for a local Weaviate server."""

from __future__ import annotations

from urllib.error import URLError
from urllib.request import urlopen

import pytest
from langchain_core.documents import Document

from pdftablesearch.config import get_settings
from pdftablesearch.vectorstores.weaviate_client import close_weaviate_client
from pdftablesearch.vectorstores.weaviate_store import WeaviateTableVectorStore

pytestmark = pytest.mark.weaviate


class DummyEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "alpha" in text:
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 1.0, 0.0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _weaviate_ready() -> bool:
    settings = get_settings()
    url = f"http://{settings.weaviate_host}:{settings.weaviate_port}/v1/.well-known/ready"
    try:
        with urlopen(url, timeout=0.5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def test_local_weaviate_insert_search_filter_and_reset(monkeypatch, tmp_path):
    if not _weaviate_ready():
        pytest.skip("local Weaviate is not running")

    monkeypatch.setenv("VECTOR_BACKEND", "weaviate")
    monkeypatch.setenv("WEAVIATE_SEARCH_MODE", "vector")
    close_weaviate_client()

    store = WeaviateTableVectorStore(
        embeddings=DummyEmbeddings(),
        persist_dir=str(tmp_path),
        collection_name="pdf_tables",
    )
    documents = [
        Document(
            page_content="alpha table",
            metadata={"table_id": "alpha", "document_name": "a.pdf", "page_number": 1},
        ),
        Document(
            page_content="beta table",
            metadata={"table_id": "beta", "document_name": "b.pdf", "page_number": 2},
        ),
    ]

    try:
        object_ids = store.add_documents(documents, skip_existing=False)
        results = store.similarity_search(
            query="alpha",
            k=2,
            filter_metadata={"document_name": "a.pdf"},
        )

        assert len(object_ids) == 2
        assert results
        assert results[0][0].metadata["table_id"] == "alpha"
    finally:
        store.reset()
        close_weaviate_client()
