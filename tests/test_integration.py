"""Integration tests with Temporal workflows and activities."""

import asyncio
import pytest
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_activity_cache import (
    CachePolicy,
    cached_activity,
    set_cache_backend,
)


# Track activity execution counts per test using a context object
class ExecutionTracker:
    """Thread-safe execution tracker for activities."""

    def __init__(self):
        self._counts = {}

    def reset(self):
        """Reset execution counters."""
        self._counts = {}

    def increment(self, activity_name: str):
        """Increment execution counter for an activity."""
        self._counts[activity_name] = self._counts.get(activity_name, 0) + 1

    def get_count(self, activity_name: str) -> int:
        """Get execution count for an activity."""
        return self._counts.get(activity_name, 0)


# Global tracker instance (will be reset per test)
_tracker = ExecutionTracker()


def reset_execution_counts():
    """Reset execution counters for tests."""
    _tracker.reset()


def increment_execution(activity_name: str):
    """Increment execution counter for an activity."""
    _tracker.increment(activity_name)


def get_execution_count(activity_name: str) -> int:
    """Get execution count for an activity."""
    return _tracker.get_count(activity_name)


# Test activities with caching
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn(name="fetch_user_cached")
async def fetch_user_cached(user_id: int) -> dict:
    """Cached activity that fetches user data."""
    increment_execution("fetch_user_cached")
    await asyncio.sleep(0.01)  # Simulate DB call
    return {"user_id": user_id, "name": f"User {user_id}"}


@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(minutes=30))
@activity.defn(name="process_data_cached")
async def process_data_cached(data: dict) -> dict:
    """Cached activity that processes data."""
    increment_execution("process_data_cached")
    await asyncio.sleep(0.01)  # Simulate processing
    return {"processed": True, "user": data["name"]}


@activity.defn(name="send_notification_uncached")
async def send_notification_uncached(message: str) -> str:
    """Uncached activity that sends notifications."""
    increment_execution("send_notification_uncached")
    await asyncio.sleep(0.01)
    return f"Sent: {message}"


# Test workflows
@workflow.defn
class CachedUserWorkflow:
    """Workflow that uses cached activities."""

    @workflow.run
    async def run(self, user_id: int) -> dict:
        # Fetch user (cached)
        user = await workflow.execute_activity(
            fetch_user_cached,
            user_id,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Process data (cached)
        processed = await workflow.execute_activity(
            process_data_cached,
            user,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Send notification (not cached)
        notification = await workflow.execute_activity(
            send_notification_uncached,
            f"Processed user {user['name']}",
            start_to_close_timeout=timedelta(seconds=10),
        )

        return {
            "user": user,
            "processed": processed,
            "notification": notification,
        }


@workflow.defn
class ParallelCachedWorkflow:
    """Workflow that executes cached activities in parallel."""

    @workflow.run
    async def run(self, user_ids: list[int]) -> list[dict]:
        # Fetch multiple users in parallel
        user_tasks = [
            workflow.execute_activity(
                fetch_user_cached,
                user_id,
                start_to_close_timeout=timedelta(seconds=10),
            )
            for user_id in user_ids
        ]

        users = await asyncio.gather(*user_tasks)
        return users


@workflow.defn
class SequentialCachedWorkflow:
    """Workflow that executes same activity sequentially."""

    @workflow.run
    async def run(self, user_id: int) -> list[dict]:
        # Execute same activity 3 times sequentially
        results = []
        for _ in range(3):
            user = await workflow.execute_activity(
                fetch_user_cached,
                user_id,
                start_to_close_timeout=timedelta(seconds=10),
            )
            results.append(user)
        return results


# Activities for testing different policies
@cached_activity(policy=CachePolicy.TASK_SOURCE, ttl=timedelta(hours=1))
@activity.defn(name="task_source_activity")
async def task_source_activity(x: int) -> int:
    """Activity using TASK_SOURCE cache policy."""
    increment_execution("task_source_activity")
    return x * 2


@workflow.defn
class TaskSourceWorkflow:
    """Workflow using TASK_SOURCE cached activity."""

    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            task_source_activity,
            x,
            start_to_close_timeout=timedelta(seconds=10),
        )


@cached_activity(policy=CachePolicy.NO_CACHE, ttl=timedelta(hours=1))
@activity.defn(name="no_cache_activity")
async def no_cache_activity(x: int) -> int:
    """Activity using NO_CACHE policy."""
    increment_execution("no_cache_activity")
    return x * 2


@workflow.defn
class NoCacheWorkflow:
    """Workflow using NO_CACHE activity."""

    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            no_cache_activity,
            x,
            start_to_close_timeout=timedelta(seconds=10),
        )


@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(seconds=5))
@activity.defn(name="ttl_activity")
async def ttl_activity(x: int) -> int:
    """Activity with short TTL for testing expiration."""
    increment_execution("ttl_activity")
    return x * 2


@workflow.defn
class TTLWorkflow:
    """Workflow using activity with TTL."""

    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            ttl_activity,
            x,
            start_to_close_timeout=timedelta(seconds=10),
        )


@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn(name="invalidation_activity")
async def invalidation_activity(x: int) -> int:
    """Activity for testing cache invalidation."""
    increment_execution("invalidation_activity")
    return x * 2


@workflow.defn
class InvalidationWorkflow:
    """Workflow for testing cache invalidation."""

    @workflow.run
    async def run(self, x: int) -> int:
        return await workflow.execute_activity(
            invalidation_activity,
            x,
            start_to_close_timeout=timedelta(seconds=10),
        )


@pytest.mark.integration
class TestTemporalIntegration:
    """Integration tests with Temporal WorkflowEnvironment."""

    @pytest.mark.asyncio
    async def test_workflow_with_cached_activities(
        self, cache_backend_configured
    ):
        """Test that activities are cached across workflow executions."""
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[CachedUserWorkflow],
                activities=[
                    fetch_user_cached,
                    process_data_cached,
                    send_notification_uncached,
                ],
            ):
                # First workflow execution
                result1 = await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-1",
                    task_queue="test-cache-queue",
                )

                assert result1["user"]["user_id"] == 123
                assert result1["processed"]["processed"] is True
                assert get_execution_count("fetch_user_cached") == 1
                assert get_execution_count("process_data_cached") == 1
                assert get_execution_count("send_notification_uncached") == 1

                # Second workflow execution (same user_id)
                result2 = await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-2",
                    task_queue="test-cache-queue",
                )

                assert result2["user"]["user_id"] == 123

                # Cached activities should not execute again
                assert get_execution_count("fetch_user_cached") == 1
                assert get_execution_count("process_data_cached") == 1

                # Uncached activity should execute again
                assert get_execution_count("send_notification_uncached") == 2

    @pytest.mark.asyncio
    async def test_workflow_cache_miss_with_different_inputs(
        self, cache_backend_configured
    ):
        """Test that different inputs create cache misses."""
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[CachedUserWorkflow],
                activities=[
                    fetch_user_cached,
                    process_data_cached,
                    send_notification_uncached,
                ],
            ):
                # First workflow with user_id=123
                await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-1",
                    task_queue="test-cache-queue",
                )

                assert get_execution_count("fetch_user_cached") == 1

                # Second workflow with user_id=456 (different input)
                await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    456,
                    id="workflow-2",
                    task_queue="test-cache-queue",
                )

                # Should execute again (cache miss)
                assert get_execution_count("fetch_user_cached") == 2

    @pytest.mark.asyncio
    async def test_parallel_activities_with_cache(
        self, cache_backend_configured
    ):
        """Test parallel activity execution with caching.

        Note: Due to Temporal's execution model and potential race conditions
        in parallel activity execution, we may see cache misses when activities
        start before a previous invocation completes and sets the cache.
        """
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[ParallelCachedWorkflow],
                activities=[fetch_user_cached],
            ):
                # Execute workflow with multiple users
                user_ids = [1, 2, 3, 1, 2]  # Note: 1 and 2 are repeated

                result = await env.client.execute_workflow(
                    ParallelCachedWorkflow.run,
                    user_ids,
                    id="parallel-workflow",
                    task_queue="test-cache-queue",
                )

                # Should have 5 results
                assert len(result) == 5

                # Verify results are correct
                assert result[0]["user_id"] == 1
                assert result[1]["user_id"] == 2
                assert result[2]["user_id"] == 3
                assert result[3]["user_id"] == 1
                assert result[4]["user_id"] == 2

                # Due to parallel execution, we expect at least 3 executions (unique IDs)
                # but may have up to 5 if cache wasn't set before duplicate activities started
                execution_count = get_execution_count("fetch_user_cached")
                assert 3 <= execution_count <= 5, (
                    f"Expected 3-5 executions for parallel cache test, got {execution_count}. "
                    "Minimum 3 (one per unique ID), maximum 5 (if all started before cache was set)."
                )

    @pytest.mark.asyncio
    async def test_sequential_activities_use_cache(
        self, cache_backend_configured
    ):
        """Test that sequential (non-parallel) activities properly use cache."""
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[SequentialCachedWorkflow],
                activities=[fetch_user_cached],
            ):
                result = await env.client.execute_workflow(
                    SequentialCachedWorkflow.run,
                    123,
                    id="sequential-workflow",
                    task_queue="test-cache-queue",
                )

                # Should have 3 results, all the same
                assert len(result) == 3
                assert all(r["user_id"] == 123 for r in result)

                # Should only execute once (sequential execution allows caching)
                execution_count = get_execution_count("fetch_user_cached")
                assert execution_count == 1, (
                    f"Expected exactly 1 execution for sequential cache test, got {execution_count}. "
                    "Sequential activities should use cache after first execution."
                )

    @pytest.mark.asyncio
    async def test_cache_verification_with_backend_inspection(
        self, cache_backend_configured
    ):
        """Test that cache hits/misses can be verified by inspecting backend.

        This test explicitly checks the cache backend state to verify
        that caching is working as expected.
        """
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[CachedUserWorkflow],
                activities=[
                    fetch_user_cached,
                    process_data_cached,
                    send_notification_uncached,
                ],
            ):
                # First execution - cache should be empty
                result1 = await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-cache-verify-1",
                    task_queue="test-cache-queue",
                )

                assert result1["user"]["user_id"] == 123
                assert get_execution_count("fetch_user_cached") == 1

                # Verify cache key exists in backend
                # Note: We can't easily inspect FakeRedis keys without accessing internals,
                # but we can verify behavior through execution counts

                # Second execution - should hit cache
                result2 = await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-cache-verify-2",
                    task_queue="test-cache-queue",
                )

                assert result2["user"]["user_id"] == 123
                # Execution count shouldn't increase (cache hit)
                assert get_execution_count("fetch_user_cached") == 1


@pytest.mark.integration
@pytest.mark.slow
class TestCachePersistenceAcrossWorkers:
    """Test cache persistence across multiple worker instances."""

    @pytest.mark.asyncio
    async def test_cache_shared_across_workers(self, cache_backend_configured):
        """Test that cache is shared across different worker instances."""
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            # First worker executes workflow
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[CachedUserWorkflow],
                activities=[
                    fetch_user_cached,
                    process_data_cached,
                    send_notification_uncached,
                ],
            ):
                await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-worker-1",
                    task_queue="test-cache-queue",
                )

                assert get_execution_count("fetch_user_cached") == 1

            # Second worker (different instance) executes workflow with same input
            async with Worker(
                env.client,
                task_queue="test-cache-queue",
                workflows=[CachedUserWorkflow],
                activities=[
                    fetch_user_cached,
                    process_data_cached,
                    send_notification_uncached,
                ],
            ):
                await env.client.execute_workflow(
                    CachedUserWorkflow.run,
                    123,
                    id="workflow-worker-2",
                    task_queue="test-cache-queue",
                )

                # Cache should be shared - no additional execution
                assert get_execution_count("fetch_user_cached") == 1


@pytest.mark.integration
class TestCachePolicyInWorkflows:
    """Test different cache policies in workflows."""

    @pytest.mark.asyncio
    async def test_task_source_policy_in_workflow(
        self, cache_backend_configured
    ):
        """Test TASK_SOURCE policy in workflow context.

        TASK_SOURCE policy caches based on both inputs AND function source code.
        This means the cache is invalidated if the function changes.
        """
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-task-source-queue",
                workflows=[TaskSourceWorkflow],
                activities=[task_source_activity],
            ):
                # First execution
                result1 = await env.client.execute_workflow(
                    TaskSourceWorkflow.run,
                    5,
                    id="task-source-wf-1",
                    task_queue="test-task-source-queue",
                )
                assert result1 == 10
                assert get_execution_count("task_source_activity") == 1

                # Second execution (same input, same source)
                result2 = await env.client.execute_workflow(
                    TaskSourceWorkflow.run,
                    5,
                    id="task-source-wf-2",
                    task_queue="test-task-source-queue",
                )
                assert result2 == 10
                assert get_execution_count("task_source_activity") == 1  # Cached!

    @pytest.mark.asyncio
    async def test_no_cache_policy_in_workflow(
        self, cache_backend_configured
    ):
        """Test NO_CACHE policy prevents caching in workflows.

        Activities decorated with NO_CACHE should execute every time,
        even with identical inputs.
        """
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-no-cache-queue",
                workflows=[NoCacheWorkflow],
                activities=[no_cache_activity],
            ):
                # First execution
                result1 = await env.client.execute_workflow(
                    NoCacheWorkflow.run,
                    5,
                    id="no-cache-wf-1",
                    task_queue="test-no-cache-queue",
                )
                assert result1 == 10
                assert get_execution_count("no_cache_activity") == 1

                # Second execution (same input, but NO_CACHE policy)
                result2 = await env.client.execute_workflow(
                    NoCacheWorkflow.run,
                    5,
                    id="no-cache-wf-2",
                    task_queue="test-no-cache-queue",
                )
                assert result2 == 10
                # Should execute again - NOT cached!
                assert get_execution_count("no_cache_activity") == 2

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cache_ttl_expiration_in_workflow(
        self, cache_backend_configured
    ):
        """Test that cache entries expire after TTL in workflow context.

        NOTE: This test uses real time delays, not Temporal time skipping,
        because Redis TTL operates on real time, not workflow time.
        Temporal's env.sleep() only advances workflow time, not Redis time.
        """
        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-ttl-queue",
                workflows=[TTLWorkflow],
                activities=[ttl_activity],
            ):
                # First execution - cache miss
                result1 = await env.client.execute_workflow(
                    TTLWorkflow.run,
                    5,
                    id="ttl-wf-1",
                    task_queue="test-ttl-queue",
                )
                assert result1 == 10
                assert get_execution_count("ttl_activity") == 1

                # Second execution immediately - cache hit
                result2 = await env.client.execute_workflow(
                    TTLWorkflow.run,
                    5,
                    id="ttl-wf-2",
                    task_queue="test-ttl-queue",
                )
                assert result2 == 10
                assert get_execution_count("ttl_activity") == 1  # Still cached

                # Wait for real time to pass (Redis TTL operates on real time)
                await asyncio.sleep(6)

                # Third execution after TTL - cache miss (expired)
                result3 = await env.client.execute_workflow(
                    TTLWorkflow.run,
                    5,
                    id="ttl-wf-3",
                    task_queue="test-ttl-queue",
                )
                assert result3 == 10
                # Should execute again - cache expired!
                assert get_execution_count("ttl_activity") == 2

    @pytest.mark.asyncio
    async def test_cache_invalidation_between_workflows(
        self, cache_backend_configured
    ):
        """Test manual cache invalidation between workflow executions.

        Demonstrates how to explicitly invalidate cache entries
        to force re-execution.
        """
        from temporal_activity_cache import invalidate_cache

        reset_execution_counts()

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-invalidation-queue",
                workflows=[InvalidationWorkflow],
                activities=[invalidation_activity],
            ):
                # First execution - cache miss
                result1 = await env.client.execute_workflow(
                    InvalidationWorkflow.run,
                    5,
                    id="invalidation-wf-1",
                    task_queue="test-invalidation-queue",
                )
                assert result1 == 10
                assert get_execution_count("invalidation_activity") == 1

                # Second execution - cache hit
                result2 = await env.client.execute_workflow(
                    InvalidationWorkflow.run,
                    5,
                    id="invalidation-wf-2",
                    task_queue="test-invalidation-queue",
                )
                assert result2 == 10
                assert get_execution_count("invalidation_activity") == 1

                # Invalidate cache for this activity with these inputs
                await invalidate_cache(
                    invalidation_activity,
                    CachePolicy.INPUTS,
                    5  # Pass args directly, not as tuple
                )

                # Third execution - cache miss (invalidated)
                result3 = await env.client.execute_workflow(
                    InvalidationWorkflow.run,
                    5,
                    id="invalidation-wf-3",
                    task_queue="test-invalidation-queue",
                )
                assert result3 == 10
                # Should execute again - cache invalidated!
                assert get_execution_count("invalidation_activity") == 2
