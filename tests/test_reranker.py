"""Tests for pdftablesearch.reranker module."""

import json
import pytest
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from pdftablesearch.reranker import ZaiRerankCompressor, _parse_rerank_response


class TestParseRerankResponse:
    """Tests for _parse_rerank_response helper."""

    def test_valid_json(self):
        response = '[{"index": 3, "score": 0.95}, {"index": 1, "score": 0.80}]'
        result = _parse_rerank_response(response)
        assert len(result) == 2
        assert result[0]["index"] == 3
        assert result[0]["score"] == 0.95

    def test_json_with_markdown_block(self):
        response = '```json\n[{"index": 1, "score": 0.9}]\n```'
        result = _parse_rerank_response(response)
        assert len(result) == 1

    def test_json_with_surrounding_text(self):
        response = 'Here are the results:\n[{"index": 2, "score": 0.7}]\nDone.'
        result = _parse_rerank_response(response)
        assert len(result) == 1

    def test_dict_with_results_key(self):
        response = '{"results": [{"index": 1, "score": 0.5}]}'
        result = _parse_rerank_response(response)
        assert len(result) == 1

    def test_invalid_json(self):
        result = _parse_rerank_response("not json at all")
        assert result == []

    def test_empty_string(self):
        result = _parse_rerank_response("")
        assert result == []


class TestZaiRerankCompressor:
    """Tests for ZaiRerankCompressor."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM that returns a valid ranking."""
        llm = MagicMock()
        response = MagicMock()
        response.content = json.dumps([
            {"index": 2, "score": 0.95},
            {"index": 1, "score": 0.80},
            {"index": 3, "score": 0.60},
        ])
        llm.invoke.return_value = response
        return llm

    @pytest.fixture
    def sample_documents(self):
        return [
            Document(
                page_content="| Revenue | $1M |",
                metadata={"table_id": "table_0_0", "page_number": 0, "document_name": "a.pdf"},
            ),
            Document(
                page_content="| Profit | $200K |",
                metadata={"table_id": "table_0_1", "page_number": 0, "document_name": "a.pdf"},
            ),
            Document(
                page_content="| Growth | 15% |",
                metadata={"table_id": "table_1_0", "page_number": 1, "document_name": "a.pdf"},
            ),
        ]

    def test_rerank_success(self, mock_llm, sample_documents):
        compressor = ZaiRerankCompressor(llm=mock_llm, top_k=3)
        result = compressor.compress_documents(sample_documents, "revenue growth")

        assert len(result) == 3
        # First result should be the one with index 2 (score 0.95)
        assert result[0].metadata.get("rerank_score") == 0.95
        assert result[0].metadata["table_id"] == "table_1_0"

    def test_rerank_empty_documents(self, mock_llm):
        compressor = ZaiRerankCompressor(llm=mock_llm)
        result = compressor.compress_documents([], "query")
        assert result == []

    def test_rerank_llm_failure_fallback(self, sample_documents):
        failing_llm = MagicMock()
        failing_llm.invoke.side_effect = Exception("API error")

        compressor = ZaiRerankCompressor(llm=failing_llm)
        result = compressor.compress_documents(sample_documents, "query")

        # Should return original documents on failure
        assert len(result) == len(sample_documents)

    def test_rerank_top_k_limit(self, mock_llm, sample_documents):
        compressor = ZaiRerankCompressor(llm=mock_llm, top_k=2)
        result = compressor.compress_documents(sample_documents, "query")

        assert len(result) <= 2

    def test_rerank_preserves_content(self, mock_llm, sample_documents):
        compressor = ZaiRerankCompressor(llm=mock_llm, top_k=3)
        result = compressor.compress_documents(sample_documents, "query")

        # Check content is preserved
        contents = [doc.page_content for doc in result]
        assert any("Revenue" in c for c in contents)
        assert any("Profit" in c for c in contents)

    def test_rerank_adds_score_to_metadata(self, mock_llm, sample_documents):
        compressor = ZaiRerankCompressor(llm=mock_llm, top_k=3)
        result = compressor.compress_documents(sample_documents, "query")

        for doc in result:
            assert "rerank_score" in doc.metadata

    def test_build_table_contexts(self, mock_llm, sample_documents):
        compressor = ZaiRerankCompressor(llm=mock_llm)
        contexts = compressor._build_table_contexts(sample_documents)

        assert "Table 1" in contexts
        assert "table_0_0" in contexts
        assert "Revenue" in contexts
        assert "Table 3" in contexts
