"""Tests for the cached_activity decorator."""

import asyncio
import pytest
from datetime import timedelta

from temporal_activity_cache import (
    CachePolicy,
    cached_activity,
    get_cache_backend,
    invalidate_cache,
    set_cache_backend,
)
from temporal_activity_cache.cache import _global_cache_backend


@pytest.mark.unit
class TestCachedActivityDecorator:
    """Test the cached_activity decorator."""

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, cache_backend_configured):
        """Test that first call is cache miss, second is cache hit."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
        async def test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate work
            return {"user_id": user_id, "name": f"User {user_id}"}

        # First call - cache miss
        result1 = await test_activity(123)
        assert result1 == {"user_id": 123, "name": "User 123"}
        assert call_count == 1

        # Second call - cache hit
        result2 = await test_activity(123)
        assert result2 == {"user_id": 123, "name": "User 123"}
        assert call_count == 1  # Function not called again

    @pytest.mark.asyncio
    async def test_different_inputs_different_cache(self, cache_backend_configured):
        """Test that different inputs create different cache entries."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id}

        # Call with different inputs
        result1 = await test_activity(123)
        result2 = await test_activity(456)

        assert result1 == {"user_id": 123}
        assert result2 == {"user_id": 456}
        assert call_count == 2  # Both calls executed

    @pytest.mark.asyncio
    async def test_cache_with_multiple_args(self, cache_backend_configured):
        """Test caching with multiple arguments."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(x: int, y: str, z: bool) -> str:
            nonlocal call_count
            call_count += 1
            return f"{x}_{y}_{z}"

        # First call
        result1 = await test_activity(1, "test", True)
        assert call_count == 1

        # Same args - cache hit
        result2 = await test_activity(1, "test", True)
        assert result1 == result2
        assert call_count == 1  # No additional call

        # Different args - cache miss
        result3 = await test_activity(2, "test", True)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_cache_with_kwargs(self, cache_backend_configured):
        """Test caching with keyword arguments."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(user_id: int, active: bool = True) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id, "active": active}

        # Call with kwargs
        result1 = await test_activity(user_id=123, active=True)
        assert call_count == 1

        # Same kwargs - cache hit
        result2 = await test_activity(user_id=123, active=True)
        assert result1 == result2
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_cache_policy(self, cache_backend_configured):
        """Test that NO_CACHE policy disables caching."""
        call_count = 0

        @cached_activity(policy=CachePolicy.NO_CACHE)
        async def test_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = await test_activity(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should execute again (no caching)
        result2 = await test_activity(5)
        assert result2 == 10
        assert call_count == 2  # Called again!

    @pytest.mark.asyncio
    async def test_task_source_policy(self, cache_backend_configured):
        """Test TASK_SOURCE cache policy."""

        @cached_activity(policy=CachePolicy.TASK_SOURCE)
        async def test_activity_v1(x: int) -> int:
            return x * 2

        # First call
        result1 = await test_activity_v1(5)
        assert result1 == 10

        # Same function, same input - cache hit
        result2 = await test_activity_v1(5)
        assert result2 == 10

    @pytest.mark.asyncio
    async def test_cache_complex_return_types(self, cache_backend_configured):
        """Test caching with complex return types."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {
                "user": {"id": user_id, "name": "Test"},
                "items": [1, 2, 3],
                "metadata": {"active": True, "score": 95.5},
            }

        result1 = await test_activity(123)
        result2 = await test_activity(123)

        assert result1 == result2
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cache_with_ttl(self, cache_backend_configured):
        """Test that TTL is passed to backend."""

        @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(seconds=30))
        async def test_activity(x: int) -> int:
            return x * 2

        result = await test_activity(5)
        assert result == 10

        # Verify the value is in cache
        backend = get_cache_backend()
        from temporal_activity_cache.utils import compute_cache_key

        cache_key = compute_cache_key(test_activity, CachePolicy.INPUTS, (5,), {})
        cached_value = await backend.get(cache_key)
        assert cached_value == 10

    @pytest.mark.asyncio
    async def test_no_backend_configured_error(self):
        """Test that error is raised if no backend is configured."""
        # Reset global backend
        from temporal_activity_cache import cache

        original_backend = cache._global_cache_backend
        cache._global_cache_backend = None

        try:

            @cached_activity(policy=CachePolicy.INPUTS)
            async def test_activity(x: int) -> int:
                return x * 2

            # Should raise RuntimeError when trying to execute
            with pytest.raises(RuntimeError, match="No cache backend configured"):
                await test_activity(5)

        finally:
            # Restore backend
            cache._global_cache_backend = original_backend

    @pytest.mark.asyncio
    async def test_cache_with_per_activity_backend(self, redis_backend):
        """Test using a specific backend for an activity."""
        call_count = 0

        # Use specific backend (not global)
        @cached_activity(
            policy=CachePolicy.INPUTS, cache_backend=redis_backend
        )
        async def test_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = await test_activity(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - cache hit
        result2 = await test_activity(5)
        assert result2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_non_serializable_input_fallback(self, cache_backend_configured):
        """Test that non-serializable inputs fall back to execution."""
        call_count = 0

        class NonSerializable:
            pass

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(obj: object) -> str:
            nonlocal call_count
            call_count += 1
            return "executed"

        # Should execute despite non-serializable input
        result = await test_activity(NonSerializable())
        assert result == "executed"
        assert call_count == 1


@pytest.mark.unit
class TestInvalidateCache:
    """Test manual cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, cache_backend_configured):
        """Test manually invalidating a cached result."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id, "count": call_count}

        # First call - cache miss
        result1 = await test_activity(123)
        assert result1["count"] == 1
        assert call_count == 1

        # Second call - cache hit
        result2 = await test_activity(123)
        assert result2["count"] == 1  # Same cached value
        assert call_count == 1

        # Invalidate cache
        await invalidate_cache(test_activity, CachePolicy.INPUTS, 123)

        # Third call - cache miss again
        result3 = await test_activity(123)
        assert result3["count"] == 2  # New execution
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_specific_key(self, cache_backend_configured):
        """Test that invalidation only affects specific key."""

        @cached_activity(policy=CachePolicy.INPUTS)
        async def test_activity(x: int) -> int:
            return x * 2

        # Cache two different values
        result1 = await test_activity(5)
        result2 = await test_activity(10)

        assert result1 == 10
        assert result2 == 20

        # Invalidate only one
        await invalidate_cache(test_activity, CachePolicy.INPUTS, 5)

        # Check backend directly
        backend = get_cache_backend()
        from temporal_activity_cache.utils import compute_cache_key

        key1 = compute_cache_key(test_activity, CachePolicy.INPUTS, (5,), {})
        key2 = compute_cache_key(test_activity, CachePolicy.INPUTS, (10,), {})

        # First key should be gone
        assert await backend.get(key1) is None

        # Second key should still exist
        assert await backend.get(key2) == 20


@pytest.mark.unit
class TestSyncActivityCaching:
    """Test caching with synchronous activities."""

    def test_sync_cache_miss_then_hit(self, cache_backend_configured):
        """Test that sync activities work with caching."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
        def sync_test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id, "name": f"User {user_id}"}

        # First call - cache miss
        result1 = sync_test_activity(123)
        assert result1 == {"user_id": 123, "name": "User 123"}
        assert call_count == 1

        # Second call - cache hit
        result2 = sync_test_activity(123)
        assert result2 == {"user_id": 123, "name": "User 123"}
        assert call_count == 1  # Function not called again

    def test_sync_different_inputs_different_cache(self, cache_backend_configured):
        """Test that different inputs create different cache entries for sync activities."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        def sync_test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id}

        # Call with different inputs
        result1 = sync_test_activity(123)
        result2 = sync_test_activity(456)

        assert result1 == {"user_id": 123}
        assert result2 == {"user_id": 456}
        assert call_count == 2  # Both calls executed

    def test_sync_cache_with_multiple_args(self, cache_backend_configured):
        """Test sync caching with multiple arguments."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        def sync_test_activity(x: int, y: str, z: bool) -> str:
            nonlocal call_count
            call_count += 1
            return f"{x}_{y}_{z}"

        # First call
        result1 = sync_test_activity(1, "test", True)
        assert call_count == 1

        # Same args - cache hit
        result2 = sync_test_activity(1, "test", True)
        assert result1 == result2
        assert call_count == 1  # No additional call

        # Different args - cache miss
        result3 = sync_test_activity(2, "test", True)
        assert call_count == 2

    def test_sync_no_cache_policy(self, cache_backend_configured):
        """Test that NO_CACHE policy disables caching for sync activities."""
        call_count = 0

        @cached_activity(policy=CachePolicy.NO_CACHE)
        def sync_test_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call
        result1 = sync_test_activity(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should execute again (no caching)
        result2 = sync_test_activity(5)
        assert result2 == 10
        assert call_count == 2  # Called again!

    def test_sync_task_source_policy(self, cache_backend_configured):
        """Test TASK_SOURCE cache policy with sync activities."""

        @cached_activity(policy=CachePolicy.TASK_SOURCE)
        def sync_test_activity(x: int) -> int:
            return x * 2

        # First call
        result1 = sync_test_activity(5)
        assert result1 == 10

        # Same function, same input - cache hit
        result2 = sync_test_activity(5)
        assert result2 == 10

    def test_sync_cache_complex_return_types(self, cache_backend_configured):
        """Test sync caching with complex return types."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        def sync_test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {
                "user": {"id": user_id, "name": "Test"},
                "items": [1, 2, 3],
                "metadata": {"active": True, "score": 95.5},
            }

        result1 = sync_test_activity(123)
        result2 = sync_test_activity(123)

        assert result1 == result2
        assert call_count == 1

    def test_sync_non_serializable_input_fallback(self, cache_backend_configured):
        """Test that sync activities with non-serializable inputs fall back to execution."""
        call_count = 0

        class NonSerializable:
            pass

        @cached_activity(policy=CachePolicy.INPUTS)
        def sync_test_activity(obj: object) -> str:
            nonlocal call_count
            call_count += 1
            return "executed"

        # Should execute despite non-serializable input
        result = sync_test_activity(NonSerializable())
        assert result == "executed"
        assert call_count == 1


@pytest.mark.unit
class TestSyncActivityThreadPool:
    """Test sync activities running in thread pools (Temporal's default behavior)."""

    def test_sync_activity_in_thread_pool(self, cache_backend_configured):
        """Test that sync activities work correctly when executed in thread pool.

        This simulates how Temporal executes sync activities in a ThreadPoolExecutor.
        """
        import concurrent.futures

        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
        def sync_test_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id, "name": f"User {user_id}"}

        # Execute in thread pool like Temporal does
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # First call - cache miss
            future1 = executor.submit(sync_test_activity, 123)
            result1 = future1.result()
            assert result1 == {"user_id": 123, "name": "User 123"}
            assert call_count == 1

            # Second call - cache hit
            future2 = executor.submit(sync_test_activity, 123)
            result2 = future2.result()
            assert result2 == {"user_id": 123, "name": "User 123"}
            assert call_count == 1  # Should still be 1 (cache hit)

    def test_sync_activity_concurrent_thread_pool(self, cache_backend_configured):
        """Test concurrent sync activities in thread pool with different inputs.

        With distributed locking enabled (default), duplicate concurrent executions
        should only execute once.
        """
        import concurrent.futures

        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS)
        def process_user(user_id: int) -> int:
            nonlocal call_count
            call_count += 1
            import time
            time.sleep(0.01)  # Simulate work
            return user_id * 2

        # Execute multiple tasks concurrently in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(process_user, 1),
                executor.submit(process_user, 2),
                executor.submit(process_user, 1),  # Duplicate (locking prevents double exec)
                executor.submit(process_user, 3),
            ]

            results = [f.result() for f in futures]

        # Results should be correct
        assert results == [2, 4, 2, 6]
        # With distributed locking, duplicate should not execute twice
        assert call_count == 3


@pytest.mark.unit
class TestSetAndGetCacheBackend:
    """Test cache backend management functions."""

    def test_set_cache_backend(self, redis_backend):
        """Test setting the global cache backend."""
        set_cache_backend(redis_backend)
        backend = get_cache_backend()
        assert backend is redis_backend

    def test_get_cache_backend_not_configured(self):
        """Test error when getting backend that's not configured."""
        from temporal_activity_cache import cache

        original = cache._global_cache_backend
        cache._global_cache_backend = None

        try:
            with pytest.raises(RuntimeError, match="No cache backend configured"):
                get_cache_backend()
        finally:
            cache._global_cache_backend = original
