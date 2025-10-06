"""Basic example of using temporal-activity-cache with Temporal workflows.

This example demonstrates:
1. Setting up the cache backend
2. Creating cached activities
3. Running a workflow that uses cached activities
4. Observing cache hits/misses

Prerequisites:
- Temporal server running on localhost:7233
- Redis server running on localhost:6379

Run this example:
1. Start Temporal: temporal server start-dev
2. Start Redis: redis-server
3. Run worker: python examples/basic_usage.py worker
4. Run workflow: python examples/basic_usage.py workflow
"""

import asyncio
import sys
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

# Import caching functionality
from temporal_activity_cache import (
    CachePolicy,
    RedisCacheBackend,
    cached_activity,
    set_cache_backend,
)


# Configure cache backend (do this once at startup)
def setup_cache():
    """Initialize the cache backend."""
    backend = RedisCacheBackend(host="localhost", port=6379, db=0)
    set_cache_backend(backend)
    print("✓ Cache backend configured (Redis)")


# Define cached activities
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn(name="fetch_user_data")
async def fetch_user_data(user_id: int) -> dict:
    """Simulate expensive database call to fetch user data.

    This activity will be cached based on user_id for 1 hour.
    """
    activity.logger.info(f"Fetching user data for user_id={user_id} (EXPENSIVE OPERATION)")

    # Simulate slow database query
    await asyncio.sleep(2)

    return {
        "user_id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com",
        "created_at": "2025-01-01",
    }


@cached_activity(policy=CachePolicy.TASK_SOURCE, ttl=timedelta(minutes=30))
@activity.defn(name="process_data")
async def process_data(data: dict) -> dict:
    """Process user data (cached by both inputs AND source code).

    If you change this function's code, the cache will be invalidated.
    """
    activity.logger.info(f"Processing data: {data}")

    await asyncio.sleep(1)

    return {
        "processed": True,
        "user_name": data["name"],
        "result": "success",
    }


@activity.defn(name="send_notification")
async def send_notification(message: str) -> str:
    """Activity without caching (always executes)."""
    activity.logger.info(f"Sending notification: {message}")
    await asyncio.sleep(0.5)
    return f"Notification sent: {message}"


# Define workflow
@workflow.defn
class UserProcessingWorkflow:
    """Example workflow that uses cached activities."""

    @workflow.run
    async def run(self, user_id: int) -> dict:
        workflow.logger.info(f"Starting workflow for user_id={user_id}")

        # Fetch user data (will be cached)
        user_data = await workflow.execute_activity(
            fetch_user_data,
            user_id,
            start_to_close_timeout=timedelta(seconds=10),
        )
        workflow.logger.info(f"Got user data: {user_data}")

        # Process data (will be cached)
        processed = await workflow.execute_activity(
            process_data,
            user_data,
            start_to_close_timeout=timedelta(seconds=10),
        )
        workflow.logger.info(f"Processed: {processed}")

        # Send notification (NOT cached)
        notification = await workflow.execute_activity(
            send_notification,
            f"User {user_data['name']} processed successfully",
            start_to_close_timeout=timedelta(seconds=10),
        )

        return {
            "user_data": user_data,
            "processed": processed,
            "notification": notification,
        }


async def run_worker():
    """Start the Temporal worker."""
    print("Starting worker...")

    # Setup cache
    setup_cache()

    # Connect to Temporal
    client = await Client.connect("localhost:7233")
    print("✓ Connected to Temporal server")

    # Create worker
    worker = Worker(
        client,
        task_queue="cache-demo-queue",
        workflows=[UserProcessingWorkflow],
        activities=[fetch_user_data, process_data, send_notification],
    )

    print("✓ Worker ready on task queue: cache-demo-queue")
    print("\nWaiting for workflows... (Ctrl+C to stop)\n")

    # Run worker
    await worker.run()


async def run_workflow(user_id: int = 123):
    """Execute a workflow."""
    print(f"\nExecuting workflow for user_id={user_id}...")

    # Connect to Temporal
    client = await Client.connect("localhost:7233")

    # Execute workflow
    result = await client.execute_workflow(
        UserProcessingWorkflow.run,
        user_id,
        id=f"user-workflow-{user_id}",
        task_queue="cache-demo-queue",
    )

    print(f"\n✓ Workflow completed!")
    print(f"Result: {result}")
    return result


async def demo():
    """Run a complete demo showing cache behavior."""
    print("=" * 60)
    print("Temporal Activity Cache Demo")
    print("=" * 60)

    print("\nThis demo will run the same workflow 3 times:")
    print("1. First run - Cache MISS (slow)")
    print("2. Second run - Cache HIT (fast)")
    print("3. Third run with different user - Cache MISS (slow)\n")

    # Run workflow 3 times
    print("\n--- Run 1: user_id=123 (First time - cache MISS) ---")
    await run_workflow(123)

    print("\n\nWaiting 2 seconds...\n")
    await asyncio.sleep(2)

    print("\n--- Run 2: user_id=123 (Second time - cache HIT!) ---")
    await run_workflow(123)

    print("\n\nWaiting 2 seconds...\n")
    await asyncio.sleep(2)

    print("\n--- Run 3: user_id=456 (Different user - cache MISS) ---")
    await run_workflow(456)

    print("\n" + "=" * 60)
    print("Demo completed!")
    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python basic_usage.py worker    - Start worker")
        print("  python basic_usage.py workflow  - Execute workflow")
        print("  python basic_usage.py demo      - Run complete demo")
        sys.exit(1)

    command = sys.argv[1]

    if command == "worker":
        asyncio.run(run_worker())
    elif command == "workflow":
        user_id = int(sys.argv[2]) if len(sys.argv) > 2 else 123
        asyncio.run(run_workflow(user_id))
    elif command == "demo":
        asyncio.run(demo())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
