"""Tests for pdftablesearch.embeddings module."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

import requests

from pdftablesearch.embeddings import ZaiEmbeddings
from pdftablesearch.exceptions import (
    APIAuthenticationError,
    APIConnectionError,
    RateLimitError,
)


@pytest.fixture
def mock_response():
    """Create a mock requests response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
        ]
    }
    return resp


@pytest.fixture
def mock_multi_response():
    """Create a mock response for multiple texts."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
            {"embedding": [0.4, 0.5, 0.6], "index": 1},
            {"embedding": [0.7, 0.8, 0.9], "index": 2},
        ]
    }
    return resp


@pytest.fixture
def embeddings():
    """Create ZaiEmbeddings with test API key."""
    return ZaiEmbeddings(api_key="test-key-12345")


class TestZaiEmbeddingsInit:
    def test_init_with_key(self):
        emb = ZaiEmbeddings(api_key="test-key")
        assert emb.api_key == "test-key"

    def test_init_with_env_key(self):
        import os
        with patch.dict(os.environ, {"ZAI_API_KEY": "env-key"}):
            emb = ZaiEmbeddings()
            assert emb.api_key == "env-key"

    def test_custom_endpoint(self):
        emb = ZaiEmbeddings(api_key="k", endpoint="https://custom.api/embed")
        assert emb.endpoint == "https://custom.api/embed"

    def test_custom_model(self):
        emb = ZaiEmbeddings(api_key="k", model="custom-model")
        assert emb.model == "custom-model"


class TestEmbedQuery:
    def test_single_query(self, embeddings, mock_response):
        with patch.object(embeddings._session, "post", return_value=mock_response):
            result = embeddings.embed_query("test query")
            assert result == [0.1, 0.2, 0.3]

    def test_empty_string_query(self, embeddings, mock_response):
        mock_response.json.return_value = {
            "data": [{"embedding": [0.0, 0.0, 0.0], "index": 0}]
        }
        with patch.object(embeddings._session, "post", return_value=mock_response):
            result = embeddings.embed_query("")
            assert len(result) == 3


class TestEmbedDocuments:
    def test_multiple_documents(self, embeddings, mock_multi_response):
        with patch.object(embeddings._session, "post", return_value=mock_multi_response):
            results = embeddings.embed_documents(["a", "b", "c"])
            assert len(results) == 3
            assert results[0] == [0.1, 0.2, 0.3]

    def test_empty_list(self, embeddings):
        results = embeddings.embed_documents([])
        assert results == []

    def test_batch_processing(self, embeddings):
        """Test that documents are processed in batches."""
        emb = ZaiEmbeddings(api_key="k", batch_size=2)

        single_batch_resp = MagicMock()
        single_batch_resp.status_code = 200
        single_batch_resp.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2], "index": 0},
                {"embedding": [0.3, 0.4], "index": 1},
            ]
        }

        with patch.object(emb._session, "post", return_value=single_batch_resp) as mock_post:
            results = emb.embed_documents(["a", "b", "c", "d"])
            assert len(results) == 4
            assert mock_post.call_count == 2  # 2 batches


class TestAPIErrors:
    def test_authentication_error(self, embeddings):
        resp = MagicMock()
        resp.status_code = 401

        with patch.object(embeddings._session, "post", return_value=resp):
            with pytest.raises(APIAuthenticationError):
                embeddings.embed_query("test")

    def test_forbidden_error(self, embeddings):
        resp = MagicMock()
        resp.status_code = 403

        with patch.object(embeddings._session, "post", return_value=resp):
            with pytest.raises(APIAuthenticationError):
                embeddings.embed_query("test")

    def test_rate_limit_error(self, embeddings):
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "5"}

        with patch.object(embeddings._session, "post", return_value=resp):
            with pytest.raises(RateLimitError) as exc_info:
                embeddings.embed_query("test")
            assert exc_info.value.retry_after == 5.0

    def test_connection_error(self, embeddings):
        with patch.object(
            embeddings._session, "post",
            side_effect=requests.exceptions.ConnectionError("timeout")
        ):
            with pytest.raises(APIConnectionError):
                embeddings.embed_query("test")

    def test_timeout_error(self, embeddings):
        with patch.object(
            embeddings._session, "post",
            side_effect=requests.exceptions.Timeout("timed out")
        ):
            with pytest.raises(APIConnectionError):
                embeddings.embed_query("test")

    def test_server_error(self, embeddings):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"

        with patch.object(embeddings._session, "post", return_value=resp):
            with pytest.raises(Exception):  # APIError
                embeddings.embed_query("test")
