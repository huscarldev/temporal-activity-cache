"""Redis cache backend implementation."""

import json
import logging
from datetime import timedelta
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from .base import CacheBackend

logger = logging.getLogger(__name__)


class RedisCacheBackend(CacheBackend):
    """Redis-based cache backend for distributed caching across Temporal workers.

    This backend stores serialized activity results in Redis, enabling cache sharing
    across different workflow executions and worker instances.

    Args:
        host: Redis host (default: localhost)
        port: Redis port (default: 6379)
        db: Redis database number (default: 0)
        password: Redis password (optional)
        pool: Existing connection pool (optional)
        **kwargs: Additional arguments passed to Redis client
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        pool: Optional[ConnectionPool] = None,
        **kwargs: Any,
    ):
        if pool:
            self._pool = pool
        else:
            self._pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,
                **kwargs,
            )
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = aioredis.Redis(connection_pool=self._pool)
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from Redis cache.

        Args:
            key: Cache key

        Returns:
            Deserialized cached value if found, None otherwise
        """
        try:
            client = await self._get_client()
            value = await client.get(key)

            if value is None:
                logger.debug(f"Cache MISS: {key}")
                return None

            logger.debug(f"Cache HIT: {key}")
            return json.loads(value)

        except Exception as e:
            logger.warning(f"Cache read failed for key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store a value in Redis cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time-to-live for the cached value (timedelta or None for no expiration)

        Note:
            Uses the modern Redis SET command with EX/PX parameters instead of deprecated SETEX.
            - For TTL >= 1 second: uses EX (seconds precision)
            - For TTL < 1 second: uses PX (milliseconds precision)
            This ensures sub-second TTLs work correctly.
        """
        try:
            client = await self._get_client()
            serialized = json.dumps(value)

            # Choose between ex (seconds) and px (milliseconds) based on TTL duration
            if ttl is None:
                # No expiration
                await client.set(key, serialized)
            elif ttl.total_seconds() >= 1:
                # Use EX for second precision (>= 1 second)
                await client.set(key, serialized, ex=int(ttl.total_seconds()))
            else:
                # Use PX for millisecond precision (< 1 second)
                # Convert to milliseconds
                milliseconds = int(ttl.total_seconds() * 1000)
                await client.set(key, serialized, px=milliseconds)

            logger.debug(f"Cache SET: {key} (TTL: {ttl})")

        except Exception as e:
            logger.warning(f"Cache write failed for key {key}: {e}")

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        try:
            client = await self._get_client()
            result = await client.exists(key)
            return bool(result)

        except Exception as e:
            logger.warning(f"Cache exists check failed for key {key}: {e}")
            return False

    async def delete(self, key: str) -> None:
        """Delete a key from Redis.

        Args:
            key: Cache key to delete
        """
        try:
            client = await self._get_client()
            await client.delete(key)
            logger.debug(f"Cache DELETE: {key}")

        except Exception as e:
            logger.warning(f"Cache delete failed for key {key}: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._pool:
            await self._pool.aclose()
