"""Tests for pdftablesearch.exceptions module."""

import pytest

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


class TestExceptionHierarchy:
    """Verify the exception inheritance chain."""

    def test_base_exception(self):
        exc = TableSearchError("test error")
        assert str(exc) == "test error"
        assert isinstance(exc, Exception)

    def test_base_exception_with_details(self):
        exc = TableSearchError("error", details={"key": "value"})
        assert "key" in str(exc)
        assert exc.details == {"key": "value"}

    def test_pdf_processing_error_is_table_search_error(self):
        exc = PDFProcessingError("pdf failed")
        assert isinstance(exc, TableSearchError)

    def test_table_parsing_error_is_table_search_error(self):
        exc = TableParsingError("parse failed")
        assert isinstance(exc, TableSearchError)

    def test_metadata_mismatch_error(self):
        exc = MetadataMismatchError("count mismatch")
        assert isinstance(exc, TableSearchError)

    def test_api_error_hierarchy(self):
        exc = APIError("api failed", status_code=500)
        assert isinstance(exc, TableSearchError)
        assert exc.status_code == 500

    def test_api_connection_error(self):
        exc = APIConnectionError("connection failed")
        assert isinstance(exc, APIError)
        assert isinstance(exc, TableSearchError)

    def test_api_authentication_error(self):
        exc = APIAuthenticationError("auth failed", status_code=401)
        assert isinstance(exc, APIError)
        assert exc.status_code == 401

    def test_rate_limit_error(self):
        exc = RateLimitError(retry_after=5.0)
        assert isinstance(exc, APIError)
        assert exc.retry_after == 5.0
        assert exc.status_code == 429

    def test_rate_limit_error_defaults(self):
        exc = RateLimitError()
        assert exc.retry_after is None
        assert "rate limit" in str(exc).lower()

    def test_vector_index_error(self):
        exc = VectorIndexError("index failed")
        assert isinstance(exc, TableSearchError)

    def test_vector_search_error(self):
        exc = VectorSearchError("search failed")
        assert isinstance(exc, TableSearchError)

    def test_result_formatting_error(self):
        exc = ResultFormattingError("format failed")
        assert isinstance(exc, TableSearchError)

    def test_catch_all_with_base(self):
        """All library exceptions can be caught with TableSearchError."""
        exceptions = [
            PDFProcessingError("a"),
            TableParsingError("b"),
            APIConnectionError("c"),
            RateLimitError(),
            VectorIndexError("d"),
        ]
        for exc in exceptions:
            with pytest.raises(TableSearchError):
                raise exc
