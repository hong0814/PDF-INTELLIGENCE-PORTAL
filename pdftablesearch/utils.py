"""
Utility functions for PDFTableSearch library.

Provides logging configuration, environment variable loading,
file validation, path sanitization, and other shared helpers.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """Create a configured logger for the library.

    Args:
        name: Logger name (typically ``__name__`` of the calling module).
        level: Logging level string (e.g. ``"DEBUG"``, ``"INFO"``).
            Falls back to the ``LOG_LEVEL`` environment variable or ``"INFO"``.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    effective_level = level or os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, effective_level, logging.INFO))

    # Add a stream handler only if none exists to avoid duplicate logs
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def get_env(key: str, default: Any = None, required: bool = False) -> Any:
    """Retrieve an environment variable with optional validation.

    Args:
        key: Environment variable name.
        default: Default value when the variable is not set.
        required: If ``True``, raises :class:`ValueError`` when the
            variable is missing and no default is provided.

    Returns:
        The environment variable value, or *default*.

    Raises:
        ValueError: When *required* is ``True`` and the variable is absent.
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Please set it in your .env file or environment."
        )
    return value


def get_api_key(provided_key: str | None = None) -> str:
    """Resolve the z.ai API key from explicit value or environment.

    Args:
        provided_key: Explicitly provided API key. Takes precedence.

    Returns:
        The resolved API key string.

    Raises:
        ValueError: When no API key can be found.
    """
    key = provided_key or os.getenv("ZAI_API_KEY")
    if not key:
        raise ValueError(
            "z.ai API key is required. Provide it via the 'api_key' parameter "
            "or set the ZAI_API_KEY environment variable."
        )
    return key


# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

# Allowed maximum file size in bytes (default 100 MB)
_DEFAULT_MAX_FILE_SIZE_MB = 100


def validate_pdf_path(pdf_path: str, max_size_mb: int | None = None) -> Path:
    """Validate that a PDF file exists, is readable, and within size limits.

    Args:
        pdf_path: Path to the PDF file.
        max_size_mb: Maximum allowed file size in megabytes.
            Defaults to the ``MAX_FILE_SIZE_MB`` environment variable or 100.

    Returns:
        Resolved :class:`Path` object for the PDF file.

    Raises:
        FileNotFoundError: When the file does not exist.
        ValueError: When the file is not a PDF or exceeds the size limit.
        PermissionError: When the file is not readable.
    """
    path = Path(pdf_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"File is not a PDF: {path}")

    if not os.access(path, os.R_OK):
        raise PermissionError(f"PDF file is not readable: {path}")

    max_mb = max_size_mb or int(os.getenv("MAX_FILE_SIZE_MB", str(_DEFAULT_MAX_FILE_SIZE_MB)))
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > max_mb:
        raise ValueError(
            f"PDF file size ({file_size_mb:.1f} MB) exceeds the limit "
            f"of {max_mb} MB. Increase MAX_FILE_SIZE_MB if needed."
        )

    return path


def sanitize_path(path_str: str) -> Path:
    """Sanitize a file path to prevent directory traversal attacks.

    Removes ``..`` segments and resolves the path relative to the current
    working directory.

    Args:
        path_str: Raw path string to sanitize.

    Returns:
        Sanitized :class:`Path` object.
    """
    # Remove any null bytes and normalize
    cleaned = path_str.replace("\x00", "")
    resolved = Path(cleaned).resolve()

    # Verify no directory traversal outside of expected scope
    if ".." in Path(cleaned).parts:
        raise ValueError(f"Path contains directory traversal: {path_str}")

    return resolved


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

def get_retry_config() -> dict[str, Any]:
    """Return retry configuration from environment or defaults.

    Returns:
        Dictionary with keys ``max_retries``, ``base_delay``, ``max_delay``,
        and ``exponential_base`` suitable for use with :mod:`tenacity`.
    """
    return {
        "max_retries": int(os.getenv("RETRY_MAX_ATTEMPTS", "3")),
        "base_delay": float(os.getenv("RETRY_BASE_DELAY", "1.0")),
        "max_delay": float(os.getenv("RETRY_MAX_DELAY", "30.0")),
        "exponential_base": float(os.getenv("RETRY_EXPONENTIAL_BASE", "2.0")),
    }


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to a maximum length with a suffix indicator.

    Args:
        text: Input text to potentially truncate.
        max_length: Maximum number of characters to retain.
        suffix: String to append when truncation occurs.

    Returns:
        Truncated or original text.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_table_context(markdown_content: str, max_rows: int = 3) -> str:
    """Extract a concise context string from a markdown table for embedding.

    Includes the header row and up to *max_rows* data rows, which balances
    embedding quality with token budget constraints.

    Args:
        markdown_content: Full markdown table string.
        max_rows: Maximum number of data rows to include.

    Returns:
        Condensed table context suitable for embedding.
    """
    lines = markdown_content.strip().split("\n")
    if not lines:
        return ""

    # Always include header row (first line)
    context_lines = [lines[0]]

    # Skip separator row (second line if it looks like |---|---|)
    data_start = 1
    if len(lines) > 1 and re.match(r"^\|[\s\-:|]+\|$", lines[1].strip()):
        data_start = 2

    # Include up to max_rows data rows
    for line in lines[data_start : data_start + max_rows]:
        stripped = line.strip()
        if stripped and stripped.startswith("|"):
            context_lines.append(stripped)

    return "\n".join(context_lines)
