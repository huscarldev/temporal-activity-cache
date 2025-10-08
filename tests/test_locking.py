"""Tests for distributed locking functionality."""

import asyncio
import pytest
from datetime import timedelta

from temporal_activity_cache import (
    CachePolicy,
    cached_activity,
    get_cache_backend,
)


@pytest.mark.unit
class TestDistributedLocking:
    """Test distributed locking to prevent concurrent duplicate execution."""

    @pytest.mark.asyncio
    async def test_concurrent_execution_with_locking(self, cache_backend_configured):
        """Test that concurrent activities with same inputs only execute once with locking."""
        call_count = 0

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=True,
            lock_timeout=timedelta(seconds=5),
        )
        async def slow_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate slow work
            return {"user_id": user_id, "count": call_count}

        # Launch 3 concurrent executions with same input
        results = await asyncio.gather(
            slow_activity(123),
            slow_activity(123),
            slow_activity(123),
        )

        # All should get the same result
        assert results[0] == results[1] == results[2]
        # Activity should only execute once (not 3 times)
        assert call_count == 1
        assert results[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_execution_different_inputs_with_locking(
        self, cache_backend_configured
    ):
        """Test that concurrent activities with different inputs execute independently."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS, enable_locking=True)
        async def slow_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return {"user_id": user_id}

        # Launch concurrent executions with different inputs
        results = await asyncio.gather(
            slow_activity(123),
            slow_activity(456),
            slow_activity(789),
        )

        # All should execute (different inputs)
        assert call_count == 3
        assert results[0]["user_id"] == 123
        assert results[1]["user_id"] == 456
        assert results[2]["user_id"] == 789

    @pytest.mark.asyncio
    async def test_locking_disabled(self, cache_backend_configured):
        """Test that disabling locking allows duplicate execution."""
        call_count = 0

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=False,  # Disable locking
        )
        async def slow_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return {"user_id": user_id, "count": call_count}

        # Launch concurrent executions
        results = await asyncio.gather(
            slow_activity(123),
            slow_activity(123),
            slow_activity(123),
        )

        # Without locking, multiple executions may occur (race condition)
        # At minimum, we should have at least 2 executions due to race
        # The exact number depends on timing, but should be > 1
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_lock_timeout_and_retry(self, cache_backend_configured):
        """Test that lock timeout allows execution to proceed."""
        call_count = 0
        backend = get_cache_backend()

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=True,
            lock_timeout=timedelta(seconds=1),
            lock_acquire_timeout=timedelta(milliseconds=100),  # Very short timeout
        )
        async def test_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Manually acquire lock to simulate stuck lock
        from temporal_activity_cache.utils import compute_cache_key

        cache_key = compute_cache_key(test_activity, CachePolicy.INPUTS, (5,), {})
        await backend.acquire_lock(
            cache_key, timedelta(seconds=10), timedelta(seconds=10)
        )

        # Try to execute - should timeout and execute anyway
        result = await test_activity(5)
        assert result == 10
        assert call_count == 1

        # Clean up lock
        await backend.release_lock(cache_key)

    @pytest.mark.asyncio
    async def test_lock_release_on_exception(self, cache_backend_configured):
        """Test that locks are released even when activity raises exception."""
        backend = get_cache_backend()

        @cached_activity(policy=CachePolicy.INPUTS, enable_locking=True)
        async def failing_activity(x: int) -> int:
            raise ValueError("Simulated error")

        # Try to execute and catch exception
        with pytest.raises(ValueError, match="Simulated error"):
            await failing_activity(5)

        # Verify lock was released
        from temporal_activity_cache.utils import compute_cache_key

        cache_key = compute_cache_key(failing_activity, CachePolicy.INPUTS, (5,), {})
        lock_key = f"{cache_key}:lock"

        # Lock should not exist
        assert not await backend.exists(lock_key)

    @pytest.mark.asyncio
    async def test_sync_concurrent_execution_with_locking(
        self, cache_backend_configured
    ):
        """Test that concurrent sync activities with same inputs only execute once."""
        import concurrent.futures

        call_count = 0

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=True,
            lock_timeout=timedelta(seconds=5),
        )
        def slow_sync_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            import time

            time.sleep(0.1)  # Simulate slow work
            return {"user_id": user_id, "count": call_count}

        # Execute in thread pool like Temporal does
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(slow_sync_activity, 123),
                executor.submit(slow_sync_activity, 123),
                executor.submit(slow_sync_activity, 123),
            ]
            results = [f.result() for f in futures]

        # All should get the same result
        assert results[0] == results[1] == results[2]
        # Activity should only execute once
        assert call_count == 1
        assert results[0]["count"] == 1

    def test_sync_locking_disabled(self, cache_backend_configured):
        """Test that disabling locking allows duplicate sync execution."""
        import concurrent.futures

        call_count = 0

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=False,  # Disable locking
        )
        def slow_sync_activity(user_id: int) -> dict:
            nonlocal call_count
            call_count += 1
            import time

            time.sleep(0.05)
            return {"user_id": user_id, "count": call_count}

        # Execute in thread pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(slow_sync_activity, 123),
                executor.submit(slow_sync_activity, 123),
                executor.submit(slow_sync_activity, 123),
            ]
            results = [f.result() for f in futures]

        # Without locking, multiple executions may occur
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_lock_prevents_cache_overwrite_race(self, cache_backend_configured):
        """Test that locking prevents the last-writer-wins cache overwrite issue."""
        execution_order = []

        @cached_activity(policy=CachePolicy.INPUTS, enable_locking=True)
        async def tracked_activity(x: int) -> dict:
            execution_order.append(f"start-{x}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end-{x}")
            return {"value": x, "order": len(execution_order)}

        # Launch concurrent executions with same input
        results = await asyncio.gather(
            tracked_activity(42),
            tracked_activity(42),
            tracked_activity(42),
        )

        # All results should be identical
        assert results[0] == results[1] == results[2]

        # Only one execution should have occurred
        start_count = sum(1 for e in execution_order if e.startswith("start"))
        assert start_count == 1

    @pytest.mark.asyncio
    async def test_lock_with_cache_hit_skips_execution(self, cache_backend_configured):
        """Test that cache hits don't acquire locks."""
        call_count = 0

        @cached_activity(policy=CachePolicy.INPUTS, enable_locking=True)
        async def test_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - executes and caches
        result1 = await test_activity(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - cache hit, should not acquire lock or execute
        result2 = await test_activity(5)
        assert result2 == 10
        assert call_count == 1  # Still 1, not incremented

    @pytest.mark.asyncio
    async def test_lock_double_check_pattern(self, cache_backend_configured):
        """Test that the double-check pattern works correctly after acquiring lock."""
        call_count = 0
        backend = get_cache_backend()

        @cached_activity(
            policy=CachePolicy.INPUTS,
            enable_locking=True,
            lock_timeout=timedelta(seconds=5),
            lock_acquire_timeout=timedelta(seconds=10),
        )
        async def slow_activity(x: int) -> int:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.2)
            return x * 2

        # Start first execution
        task1 = asyncio.create_task(slow_activity(5))
        # Give it time to acquire lock and start
        await asyncio.sleep(0.05)

        # Start second execution - should wait for lock
        task2 = asyncio.create_task(slow_activity(5))

        # Wait for both
        results = await asyncio.gather(task1, task2)

        # Both should return same result
        assert results[0] == results[1] == 10
        # But only one execution should occur (double-check prevents second)
        assert call_count == 1
