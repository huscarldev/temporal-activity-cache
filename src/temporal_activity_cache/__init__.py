"""Temporal Activity Cache - Prefect-style caching for Temporal activities.

This library provides Prefect-style activity caching for Temporal workflows using Redis.
It enables distributed caching across workers, allowing activity results to be reused
across different workflow executions.

Basic Usage:
    >>> from temporalio import activity
    >>> from temporal_activity_cache import (
    ...     cached_activity,
    ...     CachePolicy,
    ...     set_cache_backend,
    ...     RedisCacheBackend,
    ... )
    >>> from datetime import timedelta
    >>>
    >>> # Configure cache backend once at startup
    >>> backend = RedisCacheBackend(host="localhost", port=6379)
    >>> set_cache_backend(backend)
    >>>
    >>> # Use cached_activity decorator on activities
    >>> @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
    >>> @activity.defn(name="fetch_user")
    >>> async def fetch_user(user_id: int) -> dict:
    ...     return await expensive_database_call(user_id)
"""

from .backends import CacheBackend, RedisCacheBackend
from .cache import cached_activity, get_cache_backend, invalidate_cache, set_cache_backend
from .enums import CachePolicy

__all__ = [
    # Main decorator
    "cached_activity",
    # Cache management
    "set_cache_backend",
    "get_cache_backend",
    "invalidate_cache",
    # Backends
    "CacheBackend",
    "RedisCacheBackend",
    # Enums
    "CachePolicy",
]

__version__ = "0.1.0"
