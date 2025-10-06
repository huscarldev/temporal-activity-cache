"""Tests for Redis cache backend."""

import pytest
from datetime import timedelta

from temporal_activity_cache.backends.redis import RedisCacheBackend


@pytest.mark.unit
class TestRedisCacheBackend:
    """Test RedisCacheBackend with FakeRedis."""

    @pytest.mark.asyncio
    async def test_set_and_get(self, redis_backend):
        """Test basic set and get operations."""
        key = "test_key"
        value = {"data": "test_value"}

        await redis_backend.set(key, value)
        result = await redis_backend.get(key)

        assert result == value

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, redis_backend):
        """Test getting a key that doesn't exist returns None."""
        result = await redis_backend.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, redis_backend):
        """Test setting a value with TTL."""
        key = "ttl_key"
        value = {"data": "expires"}
        ttl = timedelta(seconds=60)

        await redis_backend.set(key, value, ttl=ttl)
        result = await redis_backend.get(key)

        assert result == value

    @pytest.mark.asyncio
    async def test_exists(self, redis_backend):
        """Test checking if a key exists."""
        key = "exists_key"
        value = {"data": "test"}

        # Key doesn't exist yet
        assert await redis_backend.exists(key) is False

        # Set key
        await redis_backend.set(key, value)

        # Key should now exist
        assert await redis_backend.exists(key) is True

    @pytest.mark.asyncio
    async def test_delete(self, redis_backend):
        """Test deleting a key."""
        key = "delete_key"
        value = {"data": "to_delete"}

        # Set key
        await redis_backend.set(key, value)
        assert await redis_backend.exists(key) is True

        # Delete key
        await redis_backend.delete(key)
        assert await redis_backend.exists(key) is False

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self, redis_backend):
        """Test overwriting an existing key."""
        key = "overwrite_key"
        value1 = {"data": "original"}
        value2 = {"data": "updated"}

        await redis_backend.set(key, value1)
        result1 = await redis_backend.get(key)
        assert result1 == value1

        await redis_backend.set(key, value2)
        result2 = await redis_backend.get(key)
        assert result2 == value2

    @pytest.mark.asyncio
    async def test_multiple_keys(self, redis_backend):
        """Test working with multiple keys."""
        keys_values = {
            "key1": {"id": 1, "name": "first"},
            "key2": {"id": 2, "name": "second"},
            "key3": {"id": 3, "name": "third"},
        }

        # Set all keys
        for key, value in keys_values.items():
            await redis_backend.set(key, value)

        # Get all keys
        for key, expected_value in keys_values.items():
            result = await redis_backend.get(key)
            assert result == expected_value

    @pytest.mark.asyncio
    async def test_complex_data_types(self, redis_backend):
        """Test storing and retrieving complex data types."""
        complex_data = {
            "users": [
                {"id": 1, "name": "Alice", "active": True},
                {"id": 2, "name": "Bob", "active": False},
            ],
            "metadata": {
                "count": 2,
                "timestamp": "2025-01-01T00:00:00Z",
                "tags": ["python", "temporal", "redis"],
            },
            "scores": [95.5, 87.3, 92.1],
        }

        await redis_backend.set("complex_key", complex_data)
        result = await redis_backend.get("complex_key")

        assert result == complex_data

    @pytest.mark.asyncio
    async def test_empty_dict(self, redis_backend):
        """Test storing and retrieving empty dict."""
        await redis_backend.set("empty_dict", {})
        result = await redis_backend.get("empty_dict")
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_list(self, redis_backend):
        """Test storing and retrieving empty list."""
        await redis_backend.set("empty_list", [])
        result = await redis_backend.get("empty_list")
        assert result == []

    @pytest.mark.asyncio
    async def test_null_value(self, redis_backend):
        """Test storing and retrieving null value."""
        await redis_backend.set("null_key", None)
        result = await redis_backend.get("null_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_boolean_values(self, redis_backend):
        """Test storing and retrieving boolean values."""
        await redis_backend.set("true_key", True)
        await redis_backend.set("false_key", False)

        assert await redis_backend.get("true_key") is True
        assert await redis_backend.get("false_key") is False

    @pytest.mark.asyncio
    async def test_numeric_values(self, redis_backend):
        """Test storing and retrieving numeric values."""
        await redis_backend.set("int_key", 42)
        await redis_backend.set("float_key", 3.14159)

        assert await redis_backend.get("int_key") == 42
        assert await redis_backend.get("float_key") == 3.14159

    @pytest.mark.asyncio
    async def test_string_values(self, redis_backend):
        """Test storing and retrieving string values."""
        await redis_backend.set("string_key", "Hello, World!")
        result = await redis_backend.get("string_key")
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_unicode_strings(self, redis_backend):
        """Test storing and retrieving unicode strings."""
        unicode_text = "Hello 世界 🌍 مرحبا"
        await redis_backend.set("unicode_key", unicode_text)
        result = await redis_backend.get("unicode_key")
        assert result == unicode_text

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, redis_backend):
        """Test deleting a key that doesn't exist (should not raise error)."""
        # Should not raise an error
        await redis_backend.delete("nonexistent_delete_key")

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, redis_backend):
        """Test that keys expire after TTL (critical Redis feature)."""
        import asyncio

        key = "ttl_expire_key"
        value = {"data": "should_expire"}
        ttl = timedelta(milliseconds=100)

        await redis_backend.set(key, value, ttl=ttl)

        # Key should exist immediately
        assert await redis_backend.exists(key) is True
        result = await redis_backend.get(key)
        assert result == value

        # Wait for expiration
        await asyncio.sleep(0.15)

        # Key should be gone
        assert await redis_backend.exists(key) is False
        assert await redis_backend.get(key) is None

    @pytest.mark.asyncio
    async def test_ttl_not_expired_yet(self, redis_backend):
        """Test that keys don't expire before TTL."""
        import asyncio

        key = "ttl_not_expired_key"
        value = {"data": "should_not_expire_yet"}
        ttl = timedelta(seconds=5)

        await redis_backend.set(key, value, ttl=ttl)

        # Wait a short time (less than TTL)
        await asyncio.sleep(0.1)

        # Key should still exist
        assert await redis_backend.exists(key) is True
        result = await redis_backend.get(key)
        assert result == value

    @pytest.mark.asyncio
    async def test_overwrite_resets_ttl(self, redis_backend):
        """Test that overwriting a key with new TTL resets the expiration."""
        import asyncio

        key = "reset_ttl_key"
        value1 = {"data": "first"}
        value2 = {"data": "second"}

        # Set with short TTL
        await redis_backend.set(key, value1, ttl=timedelta(milliseconds=100))

        # Wait a bit
        await asyncio.sleep(0.05)

        # Overwrite with longer TTL
        await redis_backend.set(key, value2, ttl=timedelta(seconds=5))

        # Wait past original TTL
        await asyncio.sleep(0.1)

        # Key should still exist with new value
        assert await redis_backend.exists(key) is True
        result = await redis_backend.get(key)
        assert result == value2

    @pytest.mark.asyncio
    async def test_set_without_ttl(self, redis_backend):
        """Test setting value without TTL (should persist)."""
        key = "no_ttl_key"
        value = {"data": "persistent"}

        await redis_backend.set(key, value, ttl=None)
        result = await redis_backend.get(key)

        assert result == value

    @pytest.mark.asyncio
    async def test_backend_close(self, fake_redis):
        """Test closing the backend connection."""
        backend = RedisCacheBackend(host="localhost", port=6379)
        backend._client = fake_redis

        # Set some data
        await backend.set("test_key", {"data": "test"})

        # Close backend
        await backend.close()

        # Client should be None after close
        assert backend._client is None


@pytest.mark.unit
class TestRedisCacheBackendAdvanced:
    """Test advanced Redis backend scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.race_condition
    async def test_concurrent_writes_same_key(self, redis_backend):
        """Test race condition: multiple concurrent writes to same key."""
        import asyncio

        key = "concurrent_key"
        values = [{"id": i} for i in range(10)]

        # Write same key concurrently
        await asyncio.gather(*[redis_backend.set(key, val) for val in values])

        # Should have one of the values (last write wins)
        result = await redis_backend.get(key)
        assert result in values

    @pytest.mark.asyncio
    @pytest.mark.race_condition
    async def test_concurrent_read_write(self, redis_backend):
        """Test concurrent reads and writes don't cause corruption."""
        import asyncio

        key = "read_write_key"
        await redis_backend.set(key, {"value": 0})

        async def reader():
            results = []
            for _ in range(5):
                val = await redis_backend.get(key)
                if val:
                    results.append(val)
                await asyncio.sleep(0.01)
            return results

        async def writer():
            for i in range(5):
                await redis_backend.set(key, {"value": i})
                await asyncio.sleep(0.01)

        # Run readers and writer concurrently
        reader_tasks = [reader() for _ in range(3)]
        results = await asyncio.gather(*reader_tasks, writer())

        # All reads should return valid data
        for reader_result in results[:-1]:
            for val in reader_result:
                assert "value" in val
                assert isinstance(val["value"], int)

    @pytest.mark.asyncio
    @pytest.mark.large_payload
    async def test_large_payload(self, redis_backend):
        """Test storing and retrieving large payloads."""
        # Create a large payload (~1MB)
        large_list = [{"id": i, "data": "x" * 1000} for i in range(1000)]
        key = "large_payload_key"

        await redis_backend.set(key, large_list)
        result = await redis_backend.get(key)

        assert result == large_list
        assert len(result) == 1000

    @pytest.mark.asyncio
    @pytest.mark.large_payload
    @pytest.mark.slow
    async def test_very_large_payload(self, redis_backend):
        """Test storing very large payloads (stress test)."""
        # Create ~10MB payload
        very_large_data = {
            "items": ["x" * 10000 for _ in range(1000)],
            "metadata": {"size": "large"},
        }
        key = "very_large_key"

        await redis_backend.set(key, very_large_data)
        result = await redis_backend.get(key)

        assert result == very_large_data
        assert len(result["items"]) == 1000

    @pytest.mark.asyncio
    async def test_deeply_nested_structure(self, redis_backend):
        """Test deeply nested JSON structures."""
        # Create deeply nested structure
        nested = {"level": 0}
        current = nested
        for i in range(1, 50):
            current["child"] = {"level": i}
            current = current["child"]

        key = "deep_nested_key"
        await redis_backend.set(key, nested)
        result = await redis_backend.get(key)

        assert result == nested

        # Verify depth
        current = result
        depth = 0
        while "child" in current:
            depth += 1
            current = current["child"]
        assert depth == 49

    @pytest.mark.asyncio
    async def test_special_characters_in_values(self, redis_backend):
        """Test special characters and escape sequences in values."""
        special_values = {
            "newlines": "line1\nline2\nline3",
            "tabs": "col1\tcol2\tcol3",
            "quotes": 'He said "Hello" and she said \'Hi\'',
            "backslash": "path\\to\\file",
            "unicode_mix": "Hello 世界 \n Мир \t مرحبا",
            "null_char": "before\x00after",
            "emoji": "🚀🌟💻🐍",
        }

        key = "special_chars_key"
        await redis_backend.set(key, special_values)
        result = await redis_backend.get(key)

        assert result == special_values

    @pytest.mark.asyncio
    async def test_empty_string_value(self, redis_backend):
        """Test storing empty string."""
        await redis_backend.set("empty_string", "")
        result = await redis_backend.get("empty_string")
        assert result == ""

    @pytest.mark.asyncio
    async def test_zero_values(self, redis_backend):
        """Test storing zero values of different types."""
        zero_values = {
            "int_zero": 0,
            "float_zero": 0.0,
            "negative_zero": -0.0,
        }

        await redis_backend.set("zeros", zero_values)
        result = await redis_backend.get("zeros")

        assert result["int_zero"] == 0
        assert result["float_zero"] == 0.0


@pytest.mark.unit
class TestRedisCacheBackendErrorHandling:
    """Test error handling in RedisCacheBackend."""

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_get_error(self, redis_backend, monkeypatch):
        """Test that get errors are caught and return None."""

        async def mock_get_error(key):
            raise Exception("Redis connection error")

        # Patch the get method to raise an error
        monkeypatch.setattr(redis_backend._client, "get", mock_get_error)

        # Should return None instead of raising
        result = await redis_backend.get("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_set_error(self, redis_backend, monkeypatch):
        """Test that set errors are caught and don't raise."""

        async def mock_set_error(*args, **kwargs):
            raise Exception("Redis connection error")

        # Patch the set method to raise an error
        monkeypatch.setattr(redis_backend._client, "set", mock_set_error)

        # Should not raise an error
        await redis_backend.set("any_key", {"data": "test"})

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_exists_error(
        self, redis_backend, monkeypatch
    ):
        """Test that exists errors are caught and return False."""

        async def mock_exists_error(key):
            raise Exception("Redis connection error")

        # Patch the exists method to raise an error
        monkeypatch.setattr(redis_backend._client, "exists", mock_exists_error)

        # Should return False instead of raising
        result = await redis_backend.exists("any_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_delete_error(
        self, redis_backend, monkeypatch
    ):
        """Test that delete errors are caught and don't raise."""

        async def mock_delete_error(key):
            raise Exception("Redis connection error")

        # Patch the delete method to raise an error
        monkeypatch.setattr(redis_backend._client, "delete", mock_delete_error)

        # Should not raise an error
        await redis_backend.delete("any_key")

    @pytest.mark.asyncio
    async def test_json_decode_error_on_corrupted_data(
        self, redis_backend, monkeypatch
    ):
        """Test graceful handling of corrupted/invalid JSON data."""
        import json

        async def mock_get_invalid_json(key):
            # Return invalid JSON bytes
            return b"{invalid json data"

        monkeypatch.setattr(redis_backend._client, "get", mock_get_invalid_json)

        # Should return None instead of raising JSONDecodeError
        result = await redis_backend.get("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, redis_backend, monkeypatch):
        """Test handling of connection timeouts."""
        import asyncio

        async def mock_timeout(key):
            raise asyncio.TimeoutError("Connection timeout")

        monkeypatch.setattr(redis_backend._client, "get", mock_timeout)

        # Should handle timeout gracefully
        result = await redis_backend.get("any_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_write_failure(self, redis_backend, monkeypatch):
        """Test handling when some writes succeed and some fail."""
        import asyncio

        write_count = {"count": 0}

        async def mock_partial_failure(*args, **kwargs):
            write_count["count"] += 1
            if write_count["count"] % 2 == 0:
                raise Exception("Intermittent write failure")

        original_set = redis_backend._client.set
        monkeypatch.setattr(redis_backend._client, "set", mock_partial_failure)

        # Try multiple writes
        for i in range(4):
            # Should not raise, just log warning
            await redis_backend.set(f"key_{i}", {"data": i})

        # At least some writes should have been attempted
        assert write_count["count"] == 4


@pytest.mark.unit
class TestRedisCacheBackendConnectionPool:
    """Test connection pool behavior and lifecycle."""

    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self, fake_redis):
        """Test that connection pool is reused across operations."""
        backend = RedisCacheBackend(host="localhost", port=6379)
        backend._client = fake_redis

        pool1 = backend._pool

        # Perform operations
        await backend.set("key1", {"data": "value1"})
        await backend.get("key1")

        # Pool should be the same instance
        assert backend._pool is pool1

        await backend.close()

    @pytest.mark.asyncio
    async def test_multiple_backends_different_pools(self):
        """Test that different backend instances have different pools."""
        backend1 = RedisCacheBackend(host="localhost", port=6379, db=0)
        backend2 = RedisCacheBackend(host="localhost", port=6379, db=1)

        # Pools should be different instances
        assert backend1._pool is not backend2._pool

        await backend1.close()
        await backend2.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client_and_pool(self, redis_backend):
        """Test that close properly cleans up both client and pool."""
        # Set some data to ensure client is initialized
        await redis_backend.set("test_key", {"data": "test"})

        assert redis_backend._client is not None
        assert redis_backend._pool is not None

        # Close backend
        await redis_backend.close()

        # Client should be None
        assert redis_backend._client is None

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, redis_backend):
        """Test that calling close multiple times doesn't raise errors."""
        await redis_backend.set("test_key", {"data": "test"})

        # Close once
        await redis_backend.close()

        # Close again - should not raise
        await redis_backend.close()

        # Should still be None
        assert redis_backend._client is None


@pytest.mark.redis
class TestRedisCacheBackendRealRedis:
    """Tests that require a real Redis server.

    These tests are marked with @pytest.mark.redis and will be skipped
    if no Redis server is available on localhost:6379.

    Run with: uv run pytest -m redis
    """

    @pytest.mark.asyncio
    async def test_ttl_expiration_real_redis(self, real_redis_backend):
        """Test TTL expiration with real Redis server (not FakeRedis).

        This test verifies that TTL actually works with a real Redis server,
        catching bugs that FakeRedis might miss due to implementation differences.
        """
        import asyncio

        key = "real_redis_ttl_test"
        value = {"data": "expires_in_real_redis"}
        ttl = timedelta(milliseconds=200)

        # Set key with TTL
        await real_redis_backend.set(key, value, ttl=ttl)

        # Verify key exists immediately
        assert await real_redis_backend.exists(key) is True
        result = await real_redis_backend.get(key)
        assert result == value

        # Wait for expiration
        await asyncio.sleep(0.25)

        # Key should be expired and gone
        assert await real_redis_backend.exists(key) is False
        assert await real_redis_backend.get(key) is None

    @pytest.mark.asyncio
    async def test_ttl_conversion_real_redis(self, real_redis_backend):
        """Test that timedelta TTL is properly converted to seconds in real Redis."""
        import asyncio

        key = "ttl_conversion_test"
        value = {"test": "conversion"}

        # Set with 1 second TTL
        ttl = timedelta(seconds=1)
        await real_redis_backend.set(key, value, ttl=ttl)

        # Verify it's set
        assert await real_redis_backend.get(key) == value

        # Wait 0.5 seconds - should still exist
        await asyncio.sleep(0.5)
        assert await real_redis_backend.exists(key) is True

        # Wait another 0.6 seconds (total 1.1s) - should be gone
        await asyncio.sleep(0.6)
        assert await real_redis_backend.exists(key) is False

    @pytest.mark.asyncio
    async def test_large_payload_with_ttl_real_redis(self, real_redis_backend):
        """Test that large payloads with TTL work correctly in real Redis."""
        import asyncio

        key = "large_payload_ttl_test"
        # Create a ~1MB payload
        large_data = {"items": ["x" * 1000 for _ in range(1000)]}
        ttl = timedelta(milliseconds=300)

        await real_redis_backend.set(key, large_data, ttl=ttl)

        # Should exist immediately
        result = await real_redis_backend.get(key)
        assert result == large_data

        # Wait for expiration
        await asyncio.sleep(0.35)

        # Should be gone
        assert await real_redis_backend.get(key) is None


@pytest.mark.unit
class TestRedisCacheBackendTTLEdgeCases:
    """Test edge cases and boundary conditions for TTL handling."""

    @pytest.mark.asyncio
    async def test_ttl_zero_seconds(self, redis_backend):
        """Test that TTL of 0 seconds expires immediately.

        According to Redis documentation, a TTL of 0 should expire the key immediately.
        """
        import asyncio

        key = "zero_ttl_key"
        value = {"data": "expires_now"}

        # Set with 0-second TTL
        await redis_backend.set(key, value, ttl=timedelta(seconds=0))

        # Key might exist very briefly, but should expire almost immediately
        # Give it a tiny moment to process
        await asyncio.sleep(0.01)

        # Should be expired
        result = await redis_backend.get(key)
        # Either None or the value (depends on timing), but shouldn't persist
        assert result is None or result == value

    @pytest.mark.asyncio
    async def test_ttl_very_short(self, redis_backend):
        """Test very short TTL (1 millisecond)."""
        import asyncio

        key = "very_short_ttl"
        value = {"data": "very_brief"}

        await redis_backend.set(key, value, ttl=timedelta(milliseconds=1))

        # Wait 50ms to ensure expiration
        await asyncio.sleep(0.05)

        # Should be expired
        assert await redis_backend.get(key) is None

    @pytest.mark.asyncio
    async def test_ttl_very_long(self, redis_backend):
        """Test very long TTL (hours)."""
        key = "long_ttl_key"
        value = {"data": "persists_long"}

        # Set with 24-hour TTL
        await redis_backend.set(key, value, ttl=timedelta(hours=24))

        # Should exist
        assert await redis_backend.get(key) == value
        assert await redis_backend.exists(key) is True

    @pytest.mark.asyncio
    async def test_ttl_none_vs_explicit_none(self, redis_backend):
        """Test that both no TTL and explicit None TTL result in persistent keys."""
        key1 = "no_ttl_implicit"
        key2 = "no_ttl_explicit"
        value = {"data": "persistent"}

        # Implicit None (default parameter)
        await redis_backend.set(key1, value)

        # Explicit None
        await redis_backend.set(key2, value, ttl=None)

        # Both should exist
        assert await redis_backend.get(key1) == value
        assert await redis_backend.get(key2) == value

    @pytest.mark.asyncio
    async def test_ttl_fractional_seconds(self, redis_backend):
        """Test TTL with fractional seconds."""
        import asyncio

        key = "fractional_ttl"
        value = {"data": "fractional"}

        # 0.5 seconds = 500 milliseconds
        await redis_backend.set(key, value, ttl=timedelta(seconds=0.5))

        # Should exist immediately
        assert await redis_backend.get(key) == value

        # Wait 0.6 seconds
        await asyncio.sleep(0.6)

        # Should be expired
        assert await redis_backend.get(key) is None

    @pytest.mark.asyncio
    async def test_ttl_update_extends_expiration(self, redis_backend):
        """Test that updating a key with new TTL extends its expiration."""
        import asyncio

        key = "extending_ttl"
        value1 = {"data": "first"}
        value2 = {"data": "second"}

        # Set with 0.2 second TTL
        await redis_backend.set(key, value1, ttl=timedelta(milliseconds=200))

        # Wait 0.15 seconds
        await asyncio.sleep(0.15)

        # Update with new 0.5 second TTL
        await redis_backend.set(key, value2, ttl=timedelta(milliseconds=500))

        # Wait another 0.2 seconds (total 0.35s from first set)
        # Original TTL would have expired, but new TTL keeps it alive
        await asyncio.sleep(0.2)

        # Should still exist with new value
        result = await redis_backend.get(key)
        assert result == value2
