"""Tests for rate limiter."""

import time

import pytest

from src.services.llm.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Test suite for rate limiter."""

    @pytest.fixture
    def limiter(self):
        """Create rate limiter with test settings."""
        return TokenBucketRateLimiter(
            tokens_per_minute=100,
            requests_per_minute=10,
        )

    def test_init_full_buckets(self, limiter):
        """Test that buckets start full."""
        assert limiter.available_tokens == 100

    def test_available_tokens(self, limiter):
        """Test checking available tokens."""
        initial = limiter.available_tokens
        assert initial == 100

    def test_record_usage(self, limiter):
        """Test recording actual usage."""
        # Should not raise
        limiter.record_usage(50)

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self, limiter):
        """Test acquiring tokens within limit."""
        start = time.monotonic()
        await limiter.acquire(50)
        elapsed = time.monotonic() - start

        # Should not wait
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_acquire_depletes_bucket(self, limiter):
        """Test that acquiring depletes the bucket."""
        await limiter.acquire(80)
        # Bucket should have ~20 tokens left
        assert limiter.available_tokens < 30

    @pytest.mark.asyncio
    async def test_multiple_acquires(self, limiter):
        """Test multiple sequential acquires."""
        await limiter.acquire(30)
        await limiter.acquire(30)
        await limiter.acquire(30)

        # Should have depleted most of the bucket
        assert limiter.available_tokens < 20

    @pytest.mark.asyncio
    async def test_request_limit_tracking(self, limiter):
        """Test that request limits are tracked."""
        # Make several small requests
        for _ in range(5):
            await limiter.acquire(1)

        # Should still have tokens but fewer requests available
        # (request bucket should be at ~5)
        assert limiter.available_tokens > 90

    def test_calculate_wait_no_deficit(self, limiter):
        """Test wait calculation when no deficit."""
        wait = limiter._calculate_wait(50, 100, 100)
        assert wait == 0.0

    def test_calculate_wait_with_deficit(self, limiter):
        """Test wait calculation with deficit."""
        # Need 60, have 40, rate is 100/min
        wait = limiter._calculate_wait(60, 40, 100)
        # Deficit of 20 at 100/min = 12 seconds
        assert 11 < wait < 13

    def test_refill_over_time(self, limiter):
        """Test that bucket refills based on elapsed time."""
        # Manually deplete the bucket
        limiter._token_bucket = 50.0

        # Simulate 30 seconds passing
        limiter._last_refill = time.monotonic() - 30

        # Refill should add ~50 tokens (30s = 0.5min, 0.5 * 100 = 50)
        limiter._refill()

        assert limiter._token_bucket > 90  # Should be near 100


class TestRateLimiterEdgeCases:
    """Edge case tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_zero_tokens_request(self):
        """Test requesting zero tokens."""
        limiter = TokenBucketRateLimiter(tokens_per_minute=100, requests_per_minute=10)
        await limiter.acquire(0)
        # Should complete without waiting

    @pytest.mark.asyncio
    async def test_bucket_cap(self):
        """Test that bucket doesn't exceed max capacity."""
        limiter = TokenBucketRateLimiter(tokens_per_minute=100, requests_per_minute=10)

        # Simulate long time passing
        limiter._last_refill = time.monotonic() - 600  # 10 minutes ago
        limiter._refill()

        # Should be capped at max
        assert limiter._token_bucket == 100

    def test_default_values(self):
        """Test default Groq limits."""
        limiter = TokenBucketRateLimiter()
        assert limiter.tokens_per_minute == 6000
        assert limiter.requests_per_minute == 30
