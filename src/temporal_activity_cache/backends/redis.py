"""Redis cache backend implementation."""

import asyncio
import json
import logging
import time
from datetime import timedelta
from typing import Any, Optional

import redis
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from .base import CacheBackend

logger = logging.getLogger(__name__)


class RedisCacheBackend(CacheBackend):
    """Redis-based cache backend for distributed caching across Temporal workers.

    This backend stores serialized activity results in Redis, enabling cache sharing
    across different workflow executions and worker instances.

    Supports both async and sync operations for use with async and sync Temporal activities.

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
        # Store connection parameters
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._kwargs = kwargs

        # Async client setup
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

        # Sync client (lazy initialized)
        self._sync_client: Optional[redis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        """Get or create async Redis client."""
        if self._client is None:
            self._client = aioredis.Redis(connection_pool=self._pool)
        return self._client

    def _get_sync_client(self) -> redis.Redis:
        """Get or create sync Redis client."""
        if self._sync_client is None:
            self._sync_client = redis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                decode_responses=False,
                **self._kwargs,
            )
        return self._sync_client

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

    def get_sync(self, key: str) -> Optional[Any]:
        """Retrieve a value from Redis cache (sync).

        Args:
            key: Cache key

        Returns:
            Deserialized cached value if found, None otherwise
        """
        try:
            client = self._get_sync_client()
            value = client.get(key)

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

    def set_sync(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store a value in Redis cache (sync).

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
            client = self._get_sync_client()
            serialized = json.dumps(value)

            # Choose between ex (seconds) and px (milliseconds) based on TTL duration
            if ttl is None:
                # No expiration
                client.set(key, serialized)
            elif ttl.total_seconds() >= 1:
                # Use EX for second precision (>= 1 second)
                client.set(key, serialized, ex=int(ttl.total_seconds()))
            else:
                # Use PX for millisecond precision (< 1 second)
                # Convert to milliseconds
                milliseconds = int(ttl.total_seconds() * 1000)
                client.set(key, serialized, px=milliseconds)

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

    async def acquire_lock(
        self, key: str, timeout: timedelta, ttl: timedelta
    ) -> bool:
        """Acquire a distributed lock using Redis SET NX.

        Args:
            key: Lock key (typically the cache key with :lock suffix)
            timeout: Maximum time to wait for acquiring the lock
            ttl: Time-to-live for the lock (auto-release after this duration)

        Returns:
            True if lock was acquired, False if timeout occurred
        """
        lock_key = f"{key}:lock"
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = timeout.total_seconds()
        ttl_seconds = int(ttl.total_seconds())

        # Exponential backoff parameters
        wait_time = 0.01  # Start with 10ms
        max_wait = 0.5  # Cap at 500ms

        try:
            client = await self._get_client()

            while True:
                # Try to acquire lock using SET NX (set if not exists) with expiration
                acquired = await client.set(lock_key, "1", nx=True, ex=ttl_seconds)

                if acquired:
                    logger.debug(f"Lock acquired: {lock_key}")
                    return True

                # Check if timeout exceeded
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout_seconds:
                    logger.debug(
                        f"Lock acquisition timeout after {elapsed:.2f}s: {lock_key}"
                    )
                    return False

                # Exponential backoff
                await asyncio.sleep(wait_time)
                wait_time = min(wait_time * 2, max_wait)

        except Exception as e:
            logger.warning(f"Lock acquisition failed for {lock_key}: {e}")
            return False

    def acquire_lock_sync(
        self, key: str, timeout: timedelta, ttl: timedelta
    ) -> bool:
        """Acquire a distributed lock using Redis SET NX (sync).

        Args:
            key: Lock key (typically the cache key with :lock suffix)
            timeout: Maximum time to wait for acquiring the lock
            ttl: Time-to-live for the lock (auto-release after this duration)

        Returns:
            True if lock was acquired, False if timeout occurred
        """
        lock_key = f"{key}:lock"
        start_time = time.time()
        timeout_seconds = timeout.total_seconds()
        ttl_seconds = int(ttl.total_seconds())

        # Exponential backoff parameters
        wait_time = 0.01  # Start with 10ms
        max_wait = 0.5  # Cap at 500ms

        try:
            client = self._get_sync_client()

            while True:
                # Try to acquire lock using SET NX (set if not exists) with expiration
                acquired = client.set(lock_key, "1", nx=True, ex=ttl_seconds)

                if acquired:
                    logger.debug(f"Lock acquired: {lock_key}")
                    return True

                # Check if timeout exceeded
                elapsed = time.time() - start_time
                if elapsed >= timeout_seconds:
                    logger.debug(
                        f"Lock acquisition timeout after {elapsed:.2f}s: {lock_key}"
                    )
                    return False

                # Exponential backoff
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, max_wait)

        except Exception as e:
            logger.warning(f"Lock acquisition failed for {lock_key}: {e}")
            return False

    async def release_lock(self, key: str) -> None:
        """Release a distributed lock.

        Args:
            key: Lock key to release
        """
        lock_key = f"{key}:lock"
        try:
            client = await self._get_client()
            await client.delete(lock_key)
            logger.debug(f"Lock released: {lock_key}")
        except Exception as e:
            logger.warning(f"Lock release failed for {lock_key}: {e}")

    def release_lock_sync(self, key: str) -> None:
        """Release a distributed lock (sync).

        Args:
            key: Lock key to release
        """
        lock_key = f"{key}:lock"
        try:
            client = self._get_sync_client()
            client.delete(lock_key)
            logger.debug(f"Lock released: {lock_key}")
        except Exception as e:
            logger.warning(f"Lock release failed for {lock_key}: {e}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._pool:
            await self._pool.aclose()
