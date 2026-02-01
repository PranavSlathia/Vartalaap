"""LLM services (Groq)."""

from src.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMContextTooLongError,
    LLMRateLimitError,
    LLMServiceError,
)
from src.services.llm.groq import GroqService
from src.services.llm.protocol import (
    ConversationContext,
    LLMService,
    Message,
    Role,
    StreamMetadata,
)
from src.services.llm.rate_limiter import TokenBucketRateLimiter
from src.services.llm.token_counter import estimate_llama_tokens

__all__ = [
    # Protocol and types
    "LLMService",
    "Message",
    "Role",
    "ConversationContext",
    "StreamMetadata",
    # Implementation
    "GroqService",
    # Utilities
    "TokenBucketRateLimiter",
    "estimate_llama_tokens",
    # Exceptions
    "LLMServiceError",
    "LLMRateLimitError",
    "LLMConnectionError",
    "LLMAuthenticationError",
    "LLMContextTooLongError",
]
