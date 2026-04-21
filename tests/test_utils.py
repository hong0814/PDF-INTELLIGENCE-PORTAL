"""Tests for pdftablesearch.utils module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pdftablesearch.utils import (
    extract_table_context,
    get_api_key,
    get_env,
    get_logger,
    get_retry_config,
    sanitize_path,
    truncate_text,
    validate_pdf_path,
)


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test_module")
        assert logger.name == "test_module"
        assert logger.level > 0

    def test_custom_level(self):
        logger = get_logger("test_debug", level="DEBUG")
        assert logger.level == 10  # DEBUG

    def test_no_duplicate_handlers(self):
        logger1 = get_logger("unique_test")
        handler_count = len(logger1.handlers)
        logger2 = get_logger("unique_test")
        assert len(logger2.handlers) == handler_count


class TestGetEnv:
    def test_returns_value(self):
        with patch.dict(os.environ, {"TEST_VAR": "hello"}):
            assert get_env("TEST_VAR") == "hello"

    def test_returns_default(self):
        assert get_env("NONEXISTENT_VAR_XYZ", default="default") == "default"

    def test_required_raises(self):
        with pytest.raises(ValueError, match="Required"):
            get_env("NONEXISTENT_VAR_XYZ", required=True)


class TestGetApiKey:
    def test_explicit_key(self):
        assert get_api_key("explicit-key") == "explicit-key"

    def test_env_key(self):
        with patch.dict(os.environ, {"ZAI_API_KEY": "env-key"}):
            assert get_api_key() == "env-key"

    def test_explicit_overrides_env(self):
        with patch.dict(os.environ, {"ZAI_API_KEY": "env-key"}):
            assert get_api_key("explicit") == "explicit"

    def test_missing_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            # Ensure ZAI_API_KEY is not set
            os.environ.pop("ZAI_API_KEY", None)
            with pytest.raises(ValueError, match="API key"):
                get_api_key()


class TestValidatePdfPath:
    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_pdf_path("/nonexistent/file.pdf")

    def test_non_pdf_raises(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        with pytest.raises(ValueError, match="not a PDF"):
            validate_pdf_path(str(txt_file))

    def test_valid_pdf(self, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        result = validate_pdf_path(str(pdf_file))
        assert result.suffix == ".pdf"

    def test_size_limit(self, tmp_path):
        pdf_file = tmp_path / "big.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 " + b"x" * 200)  # Small but test with tiny limit
        with pytest.raises(ValueError, match="exceeds"):
            validate_pdf_path(str(pdf_file), max_size_mb=0)  # 0 MB limit


class TestSanitizePath:
    def test_normal_path(self):
        result = sanitize_path("some/normal/path.pdf")
        assert result.name == "path.pdf"

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            sanitize_path("../../../etc/passwd")

    def test_null_byte_removal(self):
        result = sanitize_path("file\x00name.pdf")
        assert "\x00" not in str(result)


class TestTruncateText:
    def test_short_text_unchanged(self):
        assert truncate_text("short", max_length=100) == "short"

    def test_long_text_truncated(self):
        text = "a" * 200
        result = truncate_text(text, max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_custom_suffix(self):
        text = "a" * 100
        result = truncate_text(text, max_length=20, suffix=" [more]")
        assert result.endswith(" [more]")


class TestExtractTableContext:
    def test_full_table(self):
        table = "| H1 | H2 |\n|---|---|\n| a | b |\n| c | d |\n| e | f |"
        context = extract_table_context(table, max_rows=2)
        lines = context.split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_header_only(self):
        table = "| A | B |\n|---|---|"
        context = extract_table_context(table, max_rows=0)
        lines = context.split("\n")
        assert len(lines) == 1  # header only

    def test_empty_string(self):
        assert extract_table_context("") == ""

    def test_default_max_rows(self):
        table = "| H |\n|-|\n" + "\n".join([f"| {i} |" for i in range(10)])
        context = extract_table_context(table)
        lines = context.split("\n")
        assert len(lines) == 4  # header + 3 data rows (default)


class TestGetRetryConfig:
    def test_defaults(self):
        config = get_retry_config()
        assert config["max_retries"] == 3
        assert config["base_delay"] == 1.0

    def test_env_override(self):
        with patch.dict(os.environ, {"RETRY_MAX_ATTEMPTS": "5"}):
            config = get_retry_config()
            assert config["max_retries"] == 5
