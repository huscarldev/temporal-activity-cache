"""Base cache backend interface."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Optional


class CacheBackend(ABC):
    """Abstract base class for cache backends.

    Backends must implement both async and sync methods to support
    both async and sync Temporal activities.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache (async).

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value if found, None otherwise
        """
        pass

    @abstractmethod
    def get_sync(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache (sync).

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value if found, None otherwise
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store a value in the cache (async).

        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live for the cached value (None = no expiration)
        """
        pass

    @abstractmethod
    def set_sync(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store a value in the cache (sync).

        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live for the cached value (None = no expiration)
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache (async).

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key from the cache (async).

        Args:
            key: Cache key to delete
        """
        pass

    @abstractmethod
    async def acquire_lock(
        self, key: str, timeout: timedelta, ttl: timedelta
    ) -> bool:
        """Acquire a distributed lock (async).

        Args:
            key: Lock key (typically the cache key)
            timeout: Maximum time to wait for acquiring the lock
            ttl: Time-to-live for the lock (auto-release after this duration)

        Returns:
            True if lock was acquired, False if timeout occurred
        """
        pass

    @abstractmethod
    def acquire_lock_sync(
        self, key: str, timeout: timedelta, ttl: timedelta
    ) -> bool:
        """Acquire a distributed lock (sync).

        Args:
            key: Lock key (typically the cache key)
            timeout: Maximum time to wait for acquiring the lock
            ttl: Time-to-live for the lock (auto-release after this duration)

        Returns:
            True if lock was acquired, False if timeout occurred
        """
        pass

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        """Release a distributed lock (async).

        Args:
            key: Lock key to release
        """
        pass

    @abstractmethod
    def release_lock_sync(self, key: str) -> None:
        """Release a distributed lock (sync).

        Args:
            key: Lock key to release
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the cache backend connection."""
        pass
