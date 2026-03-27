"""
context/cache.py - Redis cache interface

Provides Redis-backed caching with graceful degradation.
If Redis is unavailable, operations return None/False without crashing.
"""

import json
import logging
import os
from typing import Any, Optional

import redis

logger = logging.getLogger(__name__)


class RedisCache:
    """
    Redis cache interface with graceful degradation.
    
    If Redis is unavailable, all operations return None/False gracefully
    without raising exceptions.
    
    Attributes:
        redis_url: Redis connection URL
        default_ttl: Default time-to-live in seconds
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 3600,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.default_ttl = default_ttl
        self._client: Optional[redis.Redis] = None
        self._connected = False
        self._connect()
    
    def _connect(self) -> None:
        """Establish Redis connection with graceful degradation."""
        try:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self._client.ping()
            self._connected = True
            logger.info(f"Redis connected: {self.redis_url}")
        except redis.RedisError as e:
            logger.warning(f"Redis connection failed, running without cache: {e}")
            self._client = None
            self._connected = False
    
    def _ensure_connection(self) -> bool:
        """Ensure Redis is connected, attempt reconnect if not."""
        if self._connected and self._client is not None:
            try:
                self._client.ping()
                return True
            except redis.RedisError:
                self._connected = False
        
        # Try to reconnect
        try:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
            self._connected = True
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis reconnect failed: {e}")
            self._client = None
            self._connected = False
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized from JSON) or None if not found/unavailable
        """
        if not self._ensure_connection():
            return None
        
        try:
            value: Optional[str] = self._client.get(key)  # type: ignore[assignment]
            if value is None:
                return None
            return json.loads(value)
        except (redis.RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get failed for key '{key}': {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (default: 3600)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connection():
            return False
        
        try:
            ttl = ttl if ttl is not None else self.default_ttl
            serialized = json.dumps(value, ensure_ascii=False)
            client = self._client
            if client is not None:
                client.setex(key, ttl, serialized)
            return True
        except (redis.RedisError, TypeError) as e:
            logger.warning(f"Cache set failed for key '{key}': {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False otherwise
        """
        if not self._ensure_connection():
            return False
        
        try:
            result: int = self._client.delete(key)  # type: ignore[assignment]
            return result > 0
        except redis.RedisError as e:
            logger.warning(f"Cache delete failed for key '{key}': {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self._ensure_connection():
            return False
        
        try:
            result: int = self._client.exists(key)  # type: ignore[assignment]
            return result > 0
        except redis.RedisError as e:
            logger.warning(f"Cache exists check failed for key '{key}': {e}")
            return False
    
    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            try:
                self._client.close()
            except redis.RedisError:
                pass
            self._client = None
            self._connected = False
