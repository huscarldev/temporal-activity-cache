# temporal-activity-cache

Prefect-style activity caching for Temporal workflows using Redis.

> **⚠️ Early Release Notice**
> This is an early-stage release. While functional, the API may change and there may be bugs. Use with caution in production environments. This software is provided "as is" without warranty of any kind. See the LICENSE file for details.

## Overview

`temporal-activity-cache` brings Prefect-style caching to Temporal activities. It enables distributed caching across workers by storing activity results in Redis, allowing results to be reused across different workflow executions and worker instances.

### Key Features

- 🚀 **Cross-workflow caching** - Reuse activity results across different workflow executions
- 🔄 **Distributed workers** - Cache shared via Redis across multiple worker instances
- ⚡ **Multiple cache policies** - Cache by inputs, source code, or disable caching
- ⏱️ **Configurable TTL** - Set expiration times for cached results
- 🛡️ **Graceful degradation** - Activities still work if Redis is unavailable
- 🎯 **Type-safe** - Full type hints and mypy support

## Installation

```bash
pip install temporal-activity-cache
```

Or with uv:

```bash
uv add temporal-activity-cache
```

## Quick Start

### 1. Set up cache backend (once at startup)

```python
from temporal_activity_cache import set_cache_backend, RedisCacheBackend

# Configure Redis backend
backend = RedisCacheBackend(host="localhost", port=6379)
set_cache_backend(backend)
```

### 2. Add caching to activities

```python
from datetime import timedelta
from temporalio import activity
from temporal_activity_cache import cached_activity, CachePolicy

@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn(name="fetch_user")
async def fetch_user(user_id: int) -> dict:
    """This activity will be cached for 1 hour based on user_id."""
    return await expensive_database_call(user_id)
```

### 3. Use in workflows (no changes needed!)

```python
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MyWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        # Activity results are automatically cached
        user = await workflow.execute_activity(
            fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=30)
        )
        return user
```

## How It Works

### Traditional Temporal Event History

Temporal's Event History provides replay capability **within a single workflow execution**, but doesn't cache across workflows:

```python
# Workflow execution 1
result1 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,
    id="workflow-1",
    task_queue="my-queue"
)
# Activity executes → Result stored in workflow-1's Event History

# Workflow execution 2 (different workflow!)
result2 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,  # ← Same input!
    id="workflow-2",
    task_queue="my-queue"
)
# ❌ Activity executes AGAIN (separate Event History)
```

### With temporal-activity-cache

```python
# Workflow execution 1
result1 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,
    id="workflow-1",
    task_queue="my-queue"
)
# Activity executes → Result cached in Redis

# Workflow execution 2
result2 = await client.execute_workflow(
    MyWorkflow.run,
    user_id=123,  # ← Same input!
    id="workflow-2",
    task_queue="my-queue"
)
# ✅ Cache HIT! Activity skipped, result from Redis
```

## Cache Policies

### `CachePolicy.INPUTS` (Default)

Cache based on function inputs only:

```python
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn
async def fetch_data(user_id: int) -> dict:
    return await db.query(user_id)

# Same user_id = cache hit
await fetch_data(123)  # Cache MISS - executes
await fetch_data(123)  # Cache HIT - returns cached result
await fetch_data(456)  # Cache MISS - different input
```

### `CachePolicy.TASK_SOURCE`

Cache based on function source code AND inputs:

```python
@cached_activity(policy=CachePolicy.TASK_SOURCE, ttl=timedelta(hours=1))
@activity.defn
async def calculate(x: int) -> int:
    return x * 2

# If you change the function code, cache is invalidated
```

### `CachePolicy.NO_CACHE`

Disable caching entirely:

```python
@cached_activity(policy=CachePolicy.NO_CACHE)
@activity.defn
async def send_email(to: str) -> None:
    # Always executes, never cached
    await email_service.send(to)
```

## Sync Activity Support

Both synchronous and asynchronous activities are fully supported:

```python
# Async activity (recommended)
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn
async def fetch_data_async(user_id: int) -> dict:
    return await db.query(user_id)

# Sync activity (for CPU-bound or blocking operations)
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn
def fetch_data_sync(user_id: int) -> dict:
    # Runs in thread pool executor
    return blocking_database_call(user_id)
```

**Note:** When using sync activities with caching, the cache backend operations (get/set) are automatically bridged to work with the async cache backend from the sync context.

## Advanced Usage

### Custom Cache Backend

```python
from temporal_activity_cache import CacheBackend

class MyCustomBackend(CacheBackend):
    async def get(self, key: str):
        # Your implementation
        pass

    async def set(self, key: str, value: Any, ttl: timedelta = None):
        # Your implementation
        pass

    # ... implement other methods

# Use custom backend
set_cache_backend(MyCustomBackend())
```

### Manual Cache Invalidation

```python
from temporal_activity_cache import invalidate_cache, CachePolicy

# Invalidate specific cached result
await invalidate_cache(
    fetch_user,
    CachePolicy.INPUTS,
    user_id=123  # Same args used when caching
)
```

### Per-Activity Backend

```python
# Use different cache backend for specific activity
redis_backend = RedisCacheBackend(host="localhost", port=6379)

@cached_activity(
    policy=CachePolicy.INPUTS,
    ttl=timedelta(hours=1),
    cache_backend=redis_backend  # Override global backend
)
@activity.defn
async def special_activity(data: str) -> str:
    return process(data)
```

## Complete Example

```python
import asyncio
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from temporal_activity_cache import (
    cached_activity,
    CachePolicy,
    set_cache_backend,
    RedisCacheBackend,
)

# 1. Configure cache backend
def setup_cache():
    backend = RedisCacheBackend(host="localhost", port=6379)
    set_cache_backend(backend)

# 2. Define cached activities
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(hours=1))
@activity.defn(name="fetch_user")
async def fetch_user(user_id: int) -> dict:
    """Expensive database call - cached for 1 hour."""
    await asyncio.sleep(2)  # Simulate slow query
    return {"user_id": user_id, "name": f"User {user_id}"}

@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(minutes=30))
@activity.defn(name="process_data")
async def process_data(data: dict) -> dict:
    """Data processing - cached for 30 minutes."""
    await asyncio.sleep(1)
    return {"processed": True, "user": data["name"]}

# 3. Define workflow
@workflow.defn
class UserWorkflow:
    @workflow.run
    async def run(self, user_id: int) -> dict:
        # Both activities use caching automatically
        user = await workflow.execute_activity(
            fetch_user,
            user_id,
            start_to_close_timeout=timedelta(seconds=10)
        )

        result = await workflow.execute_activity(
            process_data,
            user,
            start_to_close_timeout=timedelta(seconds=10)
        )

        return result

# 4. Run worker
async def run_worker():
    setup_cache()

    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="my-queue",
        workflows=[UserWorkflow],
        activities=[fetch_user, process_data]
    )
    await worker.run()

# 5. Execute workflow
async def execute_workflow():
    client = await Client.connect("localhost:7233")

    # First execution - cache miss (slow)
    result1 = await client.execute_workflow(
        UserWorkflow.run,
        123,
        id="workflow-1",
        task_queue="my-queue"
    )

    # Second execution - cache hit (fast!)
    result2 = await client.execute_workflow(
        UserWorkflow.run,
        123,
        id="workflow-2",
        task_queue="my-queue"
    )

if __name__ == "__main__":
    asyncio.run(run_worker())
```

## Configuration

### Redis Connection

```python
from temporal_activity_cache import RedisCacheBackend

# Basic connection
backend = RedisCacheBackend(
    host="localhost",
    port=6379,
    db=0
)

# With authentication
backend = RedisCacheBackend(
    host="redis.example.com",
    port=6379,
    password="secret",
    db=0
)

# With custom connection pool
from redis.asyncio.connection import ConnectionPool

pool = ConnectionPool(
    host="localhost",
    port=6379,
    max_connections=50,
    decode_responses=False
)

backend = RedisCacheBackend(pool=pool)
```

## Requirements

- Python >= 3.10
- Temporal Python SDK >= 1.8.0
- Redis server
- redis[hiredis] >= 5.0.0

## Comparison: Event History vs Caching

| Feature | Event History | temporal-activity-cache |
|---------|--------------|------------------------|
| **Scope** | Per workflow execution | Cross-workflow, cross-worker |
| **Purpose** | Reliability & replay | Performance optimization |
| **Reuse** | Only within same workflow | Across different workflows |
| **Storage** | Temporal server | Redis (external) |
| **Automatic** | Yes (always on) | Opt-in per activity |
| **Expiration** | Workflow retention | Configurable TTL |

## Best Practices

### 1. Cache Read-Heavy Operations

✅ **Good candidates for caching:**
- Database queries
- External API calls
- File I/O operations
- Expensive computations

❌ **Don't cache:**
- Operations with side effects (emails, payments, etc.)
- Non-deterministic operations
- Operations that must always run

### 2. Set Appropriate TTLs

```python
# Short TTL for frequently changing data
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(minutes=5))
async def get_stock_price(symbol: str) -> float:
    pass

# Long TTL for stable data
@cached_activity(policy=CachePolicy.INPUTS, ttl=timedelta(days=1))
async def get_user_profile(user_id: int) -> dict:
    pass

# No expiration for immutable data
@cached_activity(policy=CachePolicy.TASK_SOURCE, ttl=None)
async def calculate_hash(data: str) -> str:
    pass
```

### 3. Handle Cache Failures Gracefully

The library automatically falls back to executing activities if Redis is unavailable. Your workflows will continue to work without caching.

### 4. Monitor Cache Effectiveness

```python
import logging

# Enable debug logging to see cache hits/misses
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("temporal_activity_cache")
```

### 5. Use Appropriate Cache Policies

- **INPUTS**: For pure functions where output depends only on inputs
- **TASK_SOURCE**: When you want cache invalidation on code changes
- **NO_CACHE**: For operations that shouldn't be cached

## Limitations

- Activity results must be JSON serializable
- Cache invalidation is manual (no automatic invalidation on data changes)

## Testing

The library includes comprehensive tests using pytest, fakeredis, and Temporal's WorkflowEnvironment:

```bash
# Install dev dependencies
uv sync --extra dev

# Run all tests
pytest

# Run only unit tests (fast)
pytest -m unit

# Run with coverage
pytest --cov=src/temporal_activity_cache --cov-report=html

# Run integration tests
pytest -m integration
```

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

## Related Resources

- [Temporal Documentation](https://docs.temporal.io)
- [Temporal Python SDK](https://github.com/temporalio/sdk-python)
- [Prefect Caching Documentation](https://docs.prefect.io/concepts/tasks/#caching)

## Changelog

### 0.1.0 (2025-01-04)

- Initial release
- Redis cache backend
- Support for INPUTS and TASK_SOURCE cache policies
- Configurable TTL
- Async activity support
- Comprehensive test suite with pytest, fakeredis, and Temporal testing
- Complete example and documentation
