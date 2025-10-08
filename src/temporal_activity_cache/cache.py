"""Main caching decorator for Temporal activities."""

import asyncio
import functools
import logging
from datetime import timedelta
from typing import Any, Callable, Optional, TypeVar, cast

from temporalio import activity

from .backends.base import CacheBackend
from .backends.redis import RedisCacheBackend
from .enums import CachePolicy
from .utils import compute_cache_key, deserialize_result, serialize_result

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Global cache backend instance
_global_cache_backend: Optional[CacheBackend] = None


def set_cache_backend(backend: CacheBackend) -> None:
    """Set the global cache backend.

    This should be called once at application startup before any activities are executed.

    Args:
        backend: Cache backend instance to use globally

    Example:
        >>> from temporal_activity_cache import set_cache_backend, RedisCacheBackend
        >>> backend = RedisCacheBackend(host="localhost", port=6379)
        >>> set_cache_backend(backend)
    """
    global _global_cache_backend
    _global_cache_backend = backend


def get_cache_backend() -> CacheBackend:
    """Get the global cache backend.

    Returns:
        The configured cache backend

    Raises:
        RuntimeError: If no cache backend has been configured
    """
    if _global_cache_backend is None:
        raise RuntimeError(
            "No cache backend configured. Call set_cache_backend() before using cached activities."
        )
    return _global_cache_backend


def cached_activity(
    policy: CachePolicy = CachePolicy.INPUTS,
    ttl: Optional[timedelta] = None,
    cache_backend: Optional[CacheBackend] = None,
    enable_locking: bool = True,
    lock_timeout: timedelta = timedelta(seconds=30),
    lock_acquire_timeout: timedelta = timedelta(seconds=60),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to add Prefect-style caching to Temporal activities.

    This decorator wraps a Temporal activity function to add caching capabilities.
    Cache keys are computed based on the cache policy and function inputs.

    Uses distributed locking to prevent duplicate execution when concurrent activities
    have identical inputs. When locking is enabled, if multiple activities start with
    the same inputs, only one executes while others wait for the result.

    IMPORTANT: This decorator should be applied BEFORE the @activity.defn decorator:

    Example:
        >>> from temporalio import activity
        >>> from temporal_activity_cache import cached_activity, CachePolicy
        >>>
        >>> @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
        >>> @activity.defn(name="fetch_user")
        >>> async def fetch_user(user_id: int) -> dict:
        >>>     return await db.fetch_user(user_id)

    Args:
        policy: Cache policy for key generation (default: INPUTS)
        ttl: Time-to-live for cached results (None = no expiration)
        cache_backend: Specific cache backend to use (default: global backend)
        enable_locking: Enable distributed locking to prevent duplicate execution (default: True)
        lock_timeout: TTL for locks to auto-expire (default: 30s)
        lock_acquire_timeout: Max time to wait to acquire a lock (default: 60s)

    Returns:
        Decorated function with caching capability

    Raises:
        RuntimeError: If no cache backend is configured
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Skip caching if policy is NO_CACHE
        if policy == CachePolicy.NO_CACHE:
            return func

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            # Get cache backend
            backend = cache_backend or get_cache_backend()

            # Compute cache key
            try:
                cache_key = compute_cache_key(func, policy, args, kwargs)
            except ValueError as e:
                logger.warning(f"Failed to compute cache key: {e}. Executing without cache.")
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)

            # Check cache first (before acquiring lock)
            cached_result = await backend.get(cache_key)
            if cached_result is not None:
                # Log cache hit
                try:
                    info = activity.info()
                    logger.info(
                        f"Cache HIT for activity {info.activity_type} "
                        f"in workflow {info.workflow_id}: {cache_key}"
                    )
                except RuntimeError:
                    # Not in activity context (e.g., testing)
                    logger.info(f"Cache HIT: {cache_key}")

                return deserialize_result(cached_result)

            # Cache miss - acquire lock if enabled
            lock_acquired = False
            if enable_locking:
                try:
                    lock_acquired = await backend.acquire_lock(
                        cache_key, lock_acquire_timeout, lock_timeout
                    )
                except Exception as e:
                    logger.warning(f"Lock acquisition failed: {e}. Proceeding without lock.")
                    lock_acquired = False

                if not lock_acquired:
                    # Failed to acquire lock - another execution is in progress
                    # Check cache again as the other execution might have completed
                    cached_result = await backend.get(cache_key)
                    if cached_result is not None:
                        logger.info(f"Cache HIT after lock timeout: {cache_key}")
                        return deserialize_result(cached_result)

                    # Still no cache - execute anyway (lock timeout might mean stale lock)
                    logger.warning(
                        f"Lock acquisition timeout for {cache_key}. Executing anyway."
                    )

            try:
                # Double-check cache after acquiring lock
                if lock_acquired:
                    cached_result = await backend.get(cache_key)
                    if cached_result is not None:
                        logger.info(f"Cache HIT after acquiring lock: {cache_key}")
                        return deserialize_result(cached_result)

                # Cache miss - execute function
                try:
                    info = activity.info()
                    logger.info(
                        f"Cache MISS for activity {info.activity_type} "
                        f"in workflow {info.workflow_id}: {cache_key}"
                    )
                except RuntimeError:
                    # Not in activity context
                    logger.info(f"Cache MISS: {cache_key}")

                # Execute activity
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Store in cache
                try:
                    serialized = serialize_result(result)
                    await backend.set(cache_key, serialized, ttl)
                except Exception as e:
                    logger.warning(f"Failed to cache result for {cache_key}: {e}")

                return result

            finally:
                # Always release lock if we acquired it
                if lock_acquired:
                    try:
                        await backend.release_lock(cache_key)
                    except Exception as e:
                        logger.warning(f"Failed to release lock for {cache_key}: {e}")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            # For sync functions, we need to run the async cache operations in event loop
            # Get cache backend
            backend = cache_backend or get_cache_backend()

            # Compute cache key
            try:
                cache_key = compute_cache_key(func, policy, args, kwargs)
            except ValueError as e:
                logger.warning(f"Failed to compute cache key: {e}. Executing without cache.")
                return func(*args, **kwargs)

            # Check cache first (before acquiring lock)
            try:
                cached_result = backend.get_sync(cache_key)
                if cached_result is not None:
                    # Log cache hit
                    try:
                        info = activity.info()
                        logger.info(
                            f"Cache HIT for activity {info.activity_type} "
                            f"in workflow {info.workflow_id}: {cache_key}"
                        )
                    except RuntimeError:
                        # Not in activity context
                        logger.info(f"Cache HIT: {cache_key}")

                    return deserialize_result(cached_result)
            except Exception as e:
                logger.warning(f"Cache read failed: {e}. Executing without cache.")

            # Cache miss - acquire lock if enabled
            lock_acquired = False
            if enable_locking:
                try:
                    lock_acquired = backend.acquire_lock_sync(
                        cache_key, lock_acquire_timeout, lock_timeout
                    )
                except Exception as e:
                    logger.warning(f"Lock acquisition failed: {e}. Proceeding without lock.")
                    lock_acquired = False

                if not lock_acquired:
                    # Failed to acquire lock - another execution is in progress
                    # Check cache again as the other execution might have completed
                    try:
                        cached_result = backend.get_sync(cache_key)
                        if cached_result is not None:
                            logger.info(f"Cache HIT after lock timeout: {cache_key}")
                            return deserialize_result(cached_result)
                    except Exception as e:
                        logger.warning(f"Cache read after lock timeout failed: {e}")

                    # Still no cache - execute anyway (lock timeout might mean stale lock)
                    logger.warning(
                        f"Lock acquisition timeout for {cache_key}. Executing anyway."
                    )

            try:
                # Double-check cache after acquiring lock
                if lock_acquired:
                    try:
                        cached_result = backend.get_sync(cache_key)
                        if cached_result is not None:
                            logger.info(f"Cache HIT after acquiring lock: {cache_key}")
                            return deserialize_result(cached_result)
                    except Exception as e:
                        logger.warning(f"Cache read after acquiring lock failed: {e}")

                # Cache miss - execute function
                try:
                    info = activity.info()
                    logger.info(
                        f"Cache MISS for activity {info.activity_type} "
                        f"in workflow {info.workflow_id}: {cache_key}"
                    )
                except RuntimeError:
                    # Not in activity context
                    logger.info(f"Cache MISS: {cache_key}")

                # Execute activity
                result = func(*args, **kwargs)

                # Store in cache
                try:
                    serialized = serialize_result(result)
                    backend.set_sync(cache_key, serialized, ttl)
                except Exception as e:
                    logger.warning(f"Failed to cache result for {cache_key}: {e}")

                return result

            finally:
                # Always release lock if we acquired it
                if lock_acquired:
                    try:
                        backend.release_lock_sync(cache_key)
                    except Exception as e:
                        logger.warning(f"Failed to release lock for {cache_key}: {e}")

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[..., T], async_wrapper)
        else:
            return cast(Callable[..., T], sync_wrapper)

    return decorator


async def invalidate_cache(
    func: Callable[..., Any],
    policy: CachePolicy,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Manually invalidate a cached result.

    Args:
        func: The activity function
        policy: Cache policy used when caching
        *args: Positional arguments that were passed to function
        **kwargs: Keyword arguments that were passed to function

    Example:
        >>> await invalidate_cache(fetch_user, CachePolicy.INPUTS, user_id=123)
    """
    backend = get_cache_backend()
    cache_key = compute_cache_key(func, policy, args, kwargs)
    await backend.delete(cache_key)
    logger.info(f"Cache invalidated: {cache_key}")
