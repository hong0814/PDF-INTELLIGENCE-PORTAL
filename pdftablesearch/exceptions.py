"""
Custom exceptions for PDFTableSearch library.

Provides a structured exception hierarchy for all error conditions
encountered during PDF processing, vector indexing, and search operations.
"""


class TableSearchError(Exception):
    """Base exception for all table search operations.

    All custom exceptions in the library inherit from this class,
    allowing callers to catch any library-specific error with a single
    except clause.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary with additional error context.
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class PDFProcessingError(TableSearchError):
    """Raised when PDF document processing fails.

    Typical causes:
        - Corrupt or password-protected PDF
        - opendataloader-pdf conversion failure
        - Invalid file format
    """

    pass


class TableParsingError(TableSearchError):
    """Raised when table content cannot be parsed from processed output.

    Typical causes:
        - Malformed markdown output from PDF conversion
        - Missing or invalid JSON metadata
        - Unexpected output format changes
    """

    pass


class MetadataMismatchError(TableSearchError):
    """Raised when JSON metadata and Markdown table counts do not align.

    This typically indicates that the PDF converter produced inconsistent
    output, where the number of detected tables differs between the
    structured metadata and the markdown content.
    """

    pass


class APIError(TableSearchError):
    """Base class for all API-related errors.

    Inherits from TableSearchError to maintain the exception hierarchy.

    Attributes:
        status_code: HTTP status code if applicable.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, details)


class APIConnectionError(APIError):
    """Raised when connection to the API endpoint fails.

    Typical causes:
        - Network connectivity issues
        - DNS resolution failure
        - API endpoint unreachable
        - Connection timeout
    """

    pass


class APIAuthenticationError(APIError):
    """Raised when API authentication fails.

    Typical causes:
        - Invalid API key
        - Expired API key
        - Missing API key
    """

    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded.

    Attributes:
        retry_after: Suggested number of seconds to wait before retrying.
    """

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: float | None = None,
        status_code: int | None = 429,
        details: dict | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code, details)


class VectorIndexError(TableSearchError):
    """Raised when vector index operations fail.

    Typical causes:
        - Embedding generation failure
        - ChromaDB initialization failure
        - Document insertion failure
    """

    pass


class VectorSearchError(TableSearchError):
    """Raised when vector similarity search fails.

    Typical causes:
        - Query embedding generation failure
        - ChromaDB query failure
        - Empty or corrupted index
    """

    pass


class ResultFormattingError(TableSearchError):
    """Raised when search results cannot be formatted properly.

    Typical causes:
        - Missing required fields in search results
        - Incompatible metadata format
        - Serialization failure
    """

    pass
