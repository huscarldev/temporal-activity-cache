"""Utility functions for cache key generation and serialization."""

import hashlib
import inspect
import json
from typing import Any, Callable

from .enums import CachePolicy


def compute_cache_key(
    func: Callable[..., Any],
    policy: CachePolicy,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Compute a deterministic cache key based on function and inputs.

    Args:
        func: The activity function
        policy: Cache policy determining key generation strategy
        args: Positional arguments passed to function
        kwargs: Keyword arguments passed to function

    Returns:
        SHA256 hash representing the cache key

    Raises:
        ValueError: If policy is invalid or inputs are not serializable
    """
    if policy == CachePolicy.NO_CACHE:
        raise ValueError("Cannot compute cache key for NO_CACHE policy")

    # Build the key data structure
    key_data: dict[str, Any] = {
        "function": func.__name__,
        "args": args,
        "kwargs": kwargs,
    }

    # Include source code for TASK_SOURCE policy
    if policy == CachePolicy.TASK_SOURCE:
        try:
            source = inspect.getsource(func)
            key_data["source"] = source
        except (OSError, TypeError):
            # Fallback if source not available (e.g., built-in functions)
            key_data["source"] = func.__name__

    # Serialize to JSON with sorted keys for deterministic hashing
    try:
        serialized = json.dumps(key_data, sort_keys=True, default=str)
    except TypeError as e:
        raise ValueError(f"Cache key inputs must be JSON serializable: {e}")

    # Generate SHA256 hash
    hash_bytes = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    # Return key with function name prefix for readability in Redis
    return f"temporal_cache:{func.__name__}:{hash_bytes}"


def serialize_result(result: Any) -> Any:
    """Serialize activity result for caching.

    Currently uses JSON serialization. Can be extended to support
    more complex serialization formats.

    Args:
        result: Activity result to serialize

    Returns:
        Serialized result (JSON-compatible)

    Raises:
        ValueError: If result cannot be serialized
    """
    # For JSON backend, we just validate serializability
    try:
        json.dumps(result)
        return result
    except TypeError as e:
        raise ValueError(f"Activity result must be JSON serializable: {e}")


def deserialize_result(data: Any) -> Any:
    """Deserialize cached activity result.

    Args:
        data: Serialized result from cache

    Returns:
        Deserialized result
    """
    # For JSON backend, no transformation needed
    return data
