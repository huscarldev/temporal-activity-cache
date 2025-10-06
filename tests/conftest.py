"""Shared pytest fixtures for temporal-activity-cache tests."""

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis

from temporal_activity_cache import set_cache_backend
from temporal_activity_cache.backends.redis import RedisCacheBackend


@pytest_asyncio.fixture(scope="function")
async def fake_redis():
    """Provide a fake Redis client for testing.

    Uses fakeredis to simulate Redis without requiring a real server.
    Each test gets a fresh instance to ensure proper isolation.
    """
    client = FakeAsyncRedis(decode_responses=False)
    yield client
    # Ensure all data is flushed between tests for proper isolation
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def redis_backend(fake_redis):
    """Provide a Redis cache backend using FakeRedis.

    This fixture creates a RedisCacheBackend instance connected to FakeRedis.
    The backend is automatically closed after the test.
    Each test gets a fresh backend with isolated data.
    """
    # Create backend with the fake redis connection pool
    backend = RedisCacheBackend(
        host="localhost",  # Won't be used with fake redis
        port=6379,
    )
    # Replace the client with our fake one
    backend._client = fake_redis

    yield backend

    # Cleanup - ensure backend is properly closed
    try:
        await backend.close()
    except Exception:
        # Backend may already be closed in some tests
        pass


@pytest_asyncio.fixture(scope="function")
async def cache_backend_configured(redis_backend):
    """Configure the global cache backend for testing.

    This fixture sets up the global cache backend and cleans it up after the test.
    Ensures proper cleanup to prevent test pollution.
    """
    # Store the original backend if any
    from temporal_activity_cache import cache
    original_backend = cache._global_cache_backend

    # Set our test backend
    set_cache_backend(redis_backend)

    yield redis_backend

    # Reset global backend after test to original state
    cache._global_cache_backend = original_backend


@pytest.fixture
def sample_activity_inputs():
    """Provide sample inputs for activity testing."""
    return {
        "simple": (123,),
        "multiple_args": (123, "test", True),
        "with_kwargs": {"user_id": 123, "name": "test"},
        "complex": ({"nested": {"data": [1, 2, 3]}},),
    }


@pytest.fixture
def sample_activity_results():
    """Provide sample results for activity caching tests."""
    return {
        "simple": {"user_id": 123, "name": "User 123"},
        "list": [1, 2, 3, 4, 5],
        "complex": {
            "data": {"nested": True, "values": [1, 2, 3]},
            "metadata": {"timestamp": "2025-01-01"},
        },
    }


@pytest.fixture
def execution_tracker():
    """Provide an ExecutionTracker instance for integration tests.

    This fixture ensures proper test isolation by providing a fresh
    tracker instance for each test. The tracker is automatically reset
    after each test.
    """
    from tests.test_integration import ExecutionTracker

    tracker = ExecutionTracker()
    yield tracker
    # Cleanup - reset after test
    tracker.reset()


@pytest.fixture(scope="session")
def real_redis_available():
    """Check if a real Redis server is available for integration tests.

    Returns:
        bool: True if Redis is available, False otherwise
    """
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6379))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest_asyncio.fixture(scope="function")
async def real_redis_backend(real_redis_available):
    """Provide a real Redis backend for integration tests.

    This fixture is skipped if no Redis server is available.
    """
    if not real_redis_available:
        pytest.skip("Real Redis server not available")

    import redis.asyncio as aioredis

    # Create backend connected to real Redis
    backend = RedisCacheBackend(
        host="localhost",
        port=6379,
        db=15,  # Use a high DB number to avoid conflicts
    )

    # Ensure client is initialized
    client = await backend._get_client()

    # Clean the test database before test
    await client.flushdb()

    yield backend

    # Clean up after test
    try:
        await client.flushdb()
        await backend.close()
    except Exception:
        pass
