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
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to add Prefect-style caching to Temporal activities.

    This decorator wraps a Temporal activity function to add caching capabilities.
    Cache keys are computed based on the cache policy and function inputs.

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

            # Check cache
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

            # Helper to run async operations in event loop
            def run_async(coro):
                try:
                    # Try to get the running event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're in a thread pool - use run_coroutine_threadsafe
                        future = asyncio.run_coroutine_threadsafe(coro, loop)
                        return future.result()
                    else:
                        # No running loop - run synchronously
                        return loop.run_until_complete(coro)
                except RuntimeError:
                    # No event loop exists - create a new one
                    return asyncio.run(coro)

            # Check cache
            try:
                cached_result = run_async(backend.get(cache_key))
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
                run_async(backend.set(cache_key, serialized, ttl))
            except Exception as e:
                logger.warning(f"Failed to cache result for {cache_key}: {e}")

            return result

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
