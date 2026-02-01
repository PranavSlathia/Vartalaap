"""Custom exceptions for LLM services."""


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""

    pass


class LLMRateLimitError(LLMServiceError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: float = 60.0):
        super().__init__(message)
        self.retry_after = retry_after


class LLMConnectionError(LLMServiceError):
    """Raised when unable to connect to LLM API."""

    pass


class LLMAuthenticationError(LLMServiceError):
    """Raised when API key is invalid."""

    pass


class LLMContextTooLongError(LLMServiceError):
    """Raised when context exceeds model limits."""

    pass
