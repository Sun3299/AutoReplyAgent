"""
Rate Limiting Middleware for API Gateway

Implements Token Bucket algorithm for per-user rate limiting at 100 QPS.
"""

import time
import threading
from typing import Dict, Optional
from dataclasses import dataclass, field

from fastapi import HTTPException, status


# Default rate: 100 requests per second
DEFAULT_RATE = 100


@dataclass
class TokenBucket:
    """
    Token Bucket algorithm implementation for rate limiting.
    
    Tokens are added to the bucket at a constant rate (refill_rate).
    Each request consumes one token. If no tokens are available,
    the request is rejected.
    """
    tokens: float
    refill_rate: float  # tokens per second
    last_update: float
    locked: bool = False
    
    def __init__(self, capacity: float, refill_rate: float):
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_update = time.time()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(
            self.tokens + elapsed * self.refill_rate,
            self.tokens  # Don't exceed capacity (tokens is capacity)
        )
        self.last_update = now
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """
    Per-user rate limiter using Token Bucket algorithm.
    
    Maintains a separate bucket for each user_id.
    Thread-safe for concurrent access.
    """
    
    def __init__(self, rate: int = DEFAULT_RATE):
        """
        Initialize rate limiter.
        
        Args:
            rate: Maximum requests per second per user
        """
        self.rate = rate
        self.buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
    
    def _get_or_create_bucket(self, user_id: str) -> TokenBucket:
        """Get or create a bucket for the given user_id."""
        if user_id not in self.buckets:
            self.buckets[user_id] = TokenBucket(
                capacity=self.rate,
                refill_rate=self.rate
            )
        return self.buckets[user_id]
    
    def allow(self, user_id: str, tokens: int = 1) -> bool:
        """
        Check if request is allowed for the given user.
        
        Args:
            user_id: User identifier for per-user limiting
            tokens: Number of tokens to consume (default 1)
            
        Returns:
            True if request is allowed, False if rate limited
        """
        with self._lock:
            bucket = self._get_or_create_bucket(user_id)
            return bucket.consume(tokens)
    
    def get_wait_time(self, user_id: str) -> float:
        """
        Get estimated wait time until a token is available.
        
        Args:
            user_id: User identifier
            
        Returns:
            Seconds to wait for a token (0 if available now)
        """
        with self._lock:
            if user_id not in self.buckets:
                return 0.0
            
            bucket = self.buckets[user_id]
            if bucket.tokens >= 1:
                return 0.0
            
            tokens_needed = 1 - bucket.tokens
            return tokens_needed / bucket.refill_rate
    
    def cleanup_inactive_buckets(self, max_idle_seconds: float = 3600) -> int:
        """
        Remove buckets that haven't been used recently.
        
        Args:
            max_idle_seconds: Maximum idle time before cleanup
            
        Returns:
            Number of buckets removed
        """
        now = time.time()
        removed = 0
        
        with self._lock:
            inactive = [
                user_id for user_id, bucket in self.buckets.items()
                if now - bucket.last_update > max_idle_seconds
            ]
            
            for user_id in inactive:
                del self.buckets[user_id]
                removed += 1
        
        return removed


class RateLimitMiddleware:
    """
    FastAPI middleware for rate limiting.
    
    Usage:
        rate_limiter = RateLimiter(rate=100)
        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    """
    
    def __init__(self, app, rate_limiter: RateLimiter):
        self.app = app
        self.rate_limiter = rate_limiter
    
    async def __call__(self, scope, receive, send):
        # Rate limiting is handled per-endpoint via dependency injection
        # Middleware passes through to allow endpoint-level user_id extraction
        await self.app(scope, receive, send)


async def check_rate_limit(
    rate_limiter: RateLimiter,
    user_id: str,
    raise_on_limit: bool = True
) -> bool:
    """
    FastAPI dependency to check rate limit for a user.
    
    Args:
        rate_limiter: RateLimiter instance
        user_id: User identifier from JWT
        raise_on_limit: If True, raise HTTPException when limited
        
    Returns:
        True if allowed
        
    Raises:
        HTTPException: 429 Too Many Requests if limited and raise_on_limit=True
    """
    if not rate_limiter.allow(user_id):
        if raise_on_limit:
            wait_time = rate_limiter.get_wait_time(user_id)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {wait_time:.2f} seconds.",
                headers={"Retry-After": str(int(wait_time) + 1)}
            )
        return False
    return True


# Global rate limiter instance (can be shared across requests)
rate_limiter = RateLimiter(rate=DEFAULT_RATE)
