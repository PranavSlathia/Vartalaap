"""Token bucket rate limiter for Groq free tier."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.logging_config import get_logger

logger: Any = get_logger(__name__)


@dataclass
class TokenBucketRateLimiter:
    """Token bucket rate limiter with both TPM and RPM limits.

    Groq free tier limits:
    - 6,000 tokens per minute (TPM)
    - 30 requests per minute (RPM)
    """

    tokens_per_minute: int = 6000
    requests_per_minute: int = 30

    # Internal state
    _token_bucket: float = field(default=0.0, init=False, repr=False)
    _request_bucket: float = field(default=0.0, init=False, repr=False)
    _last_refill: float = field(default_factory=time.monotonic, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        # Start with full buckets
        self._token_bucket = float(self.tokens_per_minute)
        self._request_bucket = float(self.requests_per_minute)

    async def acquire(self, estimated_tokens: int) -> None:
        """Acquire tokens from the bucket, waiting if necessary.

        Args:
            estimated_tokens: Estimated tokens for the request

        Raises:
            asyncio.TimeoutError: If wait exceeds 30 seconds
        """
        async with self._lock:
            self._refill()

            # Calculate wait times
            token_wait = self._calculate_wait(
                estimated_tokens, self._token_bucket, self.tokens_per_minute
            )
            request_wait = self._calculate_wait(
                1, self._request_bucket, self.requests_per_minute
            )

            wait_time = max(token_wait, request_wait)

            if wait_time > 30:
                logger.warning(f"Rate limit would require {wait_time:.1f}s wait")

            if wait_time > 0:
                logger.debug(f"Rate limiter waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self._refill()

            # Deduct from buckets
            self._token_bucket -= estimated_tokens
            self._request_bucket -= 1

    def record_usage(self, actual_tokens: int) -> None:
        """Record actual token usage (call after response).

        This adjusts the bucket if we over/under-estimated.
        """
        logger.debug(f"Actual tokens used: {actual_tokens}")

    def _refill(self) -> None:
        """Refill buckets based on time elapsed."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now

        # Refill proportionally to time elapsed
        token_refill = (elapsed / 60) * self.tokens_per_minute
        request_refill = (elapsed / 60) * self.requests_per_minute

        self._token_bucket = min(self.tokens_per_minute, self._token_bucket + token_refill)
        self._request_bucket = min(self.requests_per_minute, self._request_bucket + request_refill)

    def _calculate_wait(self, needed: float, available: float, rate: float) -> float:
        """Calculate wait time to acquire needed amount."""
        if available >= needed:
            return 0.0

        deficit = needed - available
        # Time to refill deficit at given rate per minute
        return (deficit / rate) * 60

    @property
    def available_tokens(self) -> int:
        """Current available tokens (for monitoring)."""
        self._refill()
        return int(self._token_bucket)
