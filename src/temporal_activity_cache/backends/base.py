"""Base cache backend interface."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, Optional


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache.

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
        """Store a value in the cache.

        Args:
            key: Cache key
            value: Value to store
            ttl: Time-to-live for the cached value (None = no expiration)
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key from the cache.

        Args:
            key: Cache key to delete
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the cache backend connection."""
        pass
