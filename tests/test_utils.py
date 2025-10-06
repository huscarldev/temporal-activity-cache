"""Tests for utility functions."""

import pytest

from temporal_activity_cache.enums import CachePolicy
from temporal_activity_cache.utils import (
    compute_cache_key,
    deserialize_result,
    serialize_result,
)
import io


@pytest.mark.unit
class TestComputeCacheKey:
    """Test cache key computation."""

    def test_compute_key_with_inputs_policy(self):
        """Test cache key generation with INPUTS policy."""

        def sample_func(x: int, y: str) -> str:
            return f"{x}_{y}"

        key1 = compute_cache_key(sample_func, CachePolicy.INPUTS, (1, "test"), {})
        key2 = compute_cache_key(sample_func, CachePolicy.INPUTS, (1, "test"), {})

        # Same inputs should produce same key
        assert key1 == key2
        assert key1.startswith("temporal_cache:sample_func:")

    def test_compute_key_different_inputs(self):
        """Test that different inputs produce different keys."""

        def sample_func(x: int) -> int:
            return x * 2

        key1 = compute_cache_key(sample_func, CachePolicy.INPUTS, (1,), {})
        key2 = compute_cache_key(sample_func, CachePolicy.INPUTS, (2,), {})

        # Different inputs should produce different keys
        assert key1 != key2

    def test_compute_key_with_kwargs(self):
        """Test cache key generation with keyword arguments."""

        def sample_func(x: int, y: int = 0) -> int:
            return x + y

        key1 = compute_cache_key(sample_func, CachePolicy.INPUTS, (), {"x": 1, "y": 2})
        key2 = compute_cache_key(sample_func, CachePolicy.INPUTS, (), {"x": 1, "y": 2})

        # Same kwargs should produce same key
        assert key1 == key2

    def test_compute_key_kwargs_order_independence(self):
        """Test that kwargs order doesn't affect cache key."""

        def sample_func(x: int, y: int) -> int:
            return x + y

        # Different order but same values
        key1 = compute_cache_key(
            sample_func, CachePolicy.INPUTS, (), {"x": 1, "y": 2}
        )
        key2 = compute_cache_key(
            sample_func, CachePolicy.INPUTS, (), {"y": 2, "x": 1}
        )

        # Should produce same key (sorted internally)
        assert key1 == key2

    def test_compute_key_with_task_source_policy(self):
        """Test cache key generation with TASK_SOURCE policy."""

        def sample_func_v1(x: int) -> int:
            return x * 2

        def sample_func_v2(x: int) -> int:
            return x * 3  # Different implementation

        key1 = compute_cache_key(sample_func_v1, CachePolicy.TASK_SOURCE, (1,), {})
        key2 = compute_cache_key(sample_func_v2, CachePolicy.TASK_SOURCE, (1,), {})

        # Different source code should produce different keys
        assert key1 != key2

    def test_compute_key_same_source_same_key(self):
        """Test that same source produces same key with TASK_SOURCE policy."""

        def sample_func(x: int) -> int:
            return x * 2

        key1 = compute_cache_key(sample_func, CachePolicy.TASK_SOURCE, (1,), {})
        key2 = compute_cache_key(sample_func, CachePolicy.TASK_SOURCE, (1,), {})

        # Same source should produce same key
        assert key1 == key2

    def test_compute_key_no_cache_policy_raises(self):
        """Test that NO_CACHE policy raises ValueError."""

        def sample_func(x: int) -> int:
            return x

        with pytest.raises(ValueError, match="Cannot compute cache key for NO_CACHE"):
            compute_cache_key(sample_func, CachePolicy.NO_CACHE, (1,), {})

    def test_compute_key_complex_inputs(self):
        """Test cache key with complex nested data structures."""

        def sample_func(data: dict) -> dict:
            return data

        complex_data = {"nested": {"list": [1, 2, 3], "value": "test"}}

        key1 = compute_cache_key(
            sample_func, CachePolicy.INPUTS, (complex_data,), {}
        )
        key2 = compute_cache_key(
            sample_func, CachePolicy.INPUTS, (complex_data,), {}
        )

        # Same complex data should produce same key
        assert key1 == key2

    def test_compute_key_deterministic(self):
        """Test that cache key generation is deterministic."""

        def sample_func(x: int, y: str, z: bool) -> str:
            return f"{x}_{y}_{z}"

        # Generate same key multiple times
        keys = [
            compute_cache_key(
                sample_func, CachePolicy.INPUTS, (42, "test", True), {}
            )
            for _ in range(10)
        ]

        # All keys should be identical
        assert len(set(keys)) == 1

    def test_compute_key_function_name_in_key(self):
        """Test that function name is included in cache key."""

        def func_a(x: int) -> int:
            return x

        def func_b(x: int) -> int:
            return x

        key_a = compute_cache_key(func_a, CachePolicy.INPUTS, (1,), {})
        key_b = compute_cache_key(func_b, CachePolicy.INPUTS, (1,), {})

        # Different functions should produce different keys
        assert key_a != key_b
        assert "func_a" in key_a
        assert "func_b" in key_b


@pytest.mark.unit
class TestSerializeResult:
    """Test result serialization."""

    def test_serialize_simple_types(self):
        """Test serialization of simple types."""
        assert serialize_result(123) == 123
        assert serialize_result("test") == "test"
        assert serialize_result(True) is True
        assert serialize_result(None) is None

    def test_serialize_collections(self):
        """Test serialization of collections."""
        assert serialize_result([1, 2, 3]) == [1, 2, 3]
        assert serialize_result({"key": "value"}) == {"key": "value"}
        assert serialize_result((1, 2, 3)) == (1, 2, 3)

    def test_serialize_nested_structures(self):
        """Test serialization of nested data structures."""
        data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "metadata": {"count": 2, "active": True},
        }
        assert serialize_result(data) == data

    def test_serialize_non_serializable_raises(self):
        """Test that non-serializable objects raise ValueError."""

        class CustomClass:
            pass

        with pytest.raises(ValueError, match="must be JSON serializable"):
            serialize_result(CustomClass())

    def test_serialize_with_custom_objects_raises(self):
        """Test that objects with custom __dict__ raise ValueError."""

        class Person:
            def __init__(self, name: str):
                self.name = name

        with pytest.raises(ValueError, match="must be JSON serializable"):
            serialize_result(Person("Alice"))


@pytest.mark.unit
class TestDeserializeResult:
    """Test result deserialization."""

    def test_deserialize_simple_types(self):
        """Test deserialization of simple types."""
        assert deserialize_result(123) == 123
        assert deserialize_result("test") == "test"
        assert deserialize_result(True) is True
        assert deserialize_result(None) is None

    def test_deserialize_collections(self):
        """Test deserialization of collections."""
        assert deserialize_result([1, 2, 3]) == [1, 2, 3]
        assert deserialize_result({"key": "value"}) == {"key": "value"}

    def test_deserialize_nested_structures(self):
        """Test deserialization of nested data structures."""
        data = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "metadata": {"count": 2, "active": True},
        }
        assert deserialize_result(data) == data

    def test_serialize_deserialize_roundtrip(self):
        """Test that serialize -> deserialize produces same result."""
        original = {
            "id": 123,
            "name": "Test User",
            "tags": ["python", "temporal"],
            "active": True,
            "score": 95.5,
        }

        serialized = serialize_result(original)
        deserialized = deserialize_result(serialized)

        assert deserialized == original

    @pytest.mark.parametrize(
        "value,expected",
        [
            (123, 123),
            ("test", "test"),
            (True, True),
            (None, None),
            ([1, 2, 3], [1, 2, 3]),
            ({"key": "value"}, {"key": "value"}),
            (3.14159, 3.14159),
            (0, 0),
            ("", ""),
            ([], []),
            ({}, {}),
        ],
    )
    def test_serialize_deserialize_various_types(self, value, expected):
        """Test serialization/deserialization of various data types."""
        serialized = serialize_result(value)
        deserialized = deserialize_result(serialized)
        assert deserialized == expected


@pytest.mark.unit
class TestCacheKeyEdgeCases:
    """Test edge cases in cache key generation."""

    @pytest.mark.parametrize(
        "args1,kwargs1,args2,kwargs2,should_match",
        [
            # Same args should match
            ((1, 2), {}, (1, 2), {}, True),
            # Different args should not match
            ((1, 2), {}, (2, 1), {}, False),
            # Args vs kwargs (same values) should not match
            ((1,), {"x": 2}, (1, 2), {}, False),
            # Same kwargs different order should match
            ((), {"x": 1, "y": 2}, (), {"y": 2, "x": 1}, True),
            # Different kwargs should not match
            ((), {"x": 1}, (), {"x": 2}, False),
            # Empty args/kwargs should match
            ((), {}, (), {}, True),
        ],
    )
    def test_cache_key_consistency(
        self, args1, kwargs1, args2, kwargs2, should_match
    ):
        """Test that cache keys are consistent for equivalent inputs."""

        def test_func():
            pass

        key1 = compute_cache_key(test_func, CachePolicy.INPUTS, args1, kwargs1)
        key2 = compute_cache_key(test_func, CachePolicy.INPUTS, args2, kwargs2)

        if should_match:
            assert key1 == key2
        else:
            assert key1 != key2

    def test_cache_key_collision_resistance(self):
        """Test that different inputs produce different cache keys."""

        def test_func():
            pass

        # Generate many keys and check for collisions
        keys = set()
        for i in range(1000):
            key = compute_cache_key(test_func, CachePolicy.INPUTS, (i,), {})
            keys.add(key)

        # Should have 1000 unique keys
        assert len(keys) == 1000

    def test_cache_key_with_unicode(self):
        """Test cache key generation with unicode characters."""

        def test_func(text: str):
            return text

        key1 = compute_cache_key(test_func, CachePolicy.INPUTS, ("hello",), {})
        key2 = compute_cache_key(test_func, CachePolicy.INPUTS, ("世界",), {})
        key3 = compute_cache_key(test_func, CachePolicy.INPUTS, ("🚀",), {})

        # All should be different
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3

        # But same unicode should produce same key
        key4 = compute_cache_key(test_func, CachePolicy.INPUTS, ("世界",), {})
        assert key2 == key4

    def test_cache_key_with_nested_structures(self):
        """Test cache key with deeply nested structures."""

        def test_func(data):
            return data

        nested1 = {"a": {"b": {"c": {"d": [1, 2, 3]}}}}
        nested2 = {"a": {"b": {"c": {"d": [1, 2, 3]}}}}
        nested3 = {"a": {"b": {"c": {"d": [1, 2, 4]}}}}  # Different

        key1 = compute_cache_key(test_func, CachePolicy.INPUTS, (nested1,), {})
        key2 = compute_cache_key(test_func, CachePolicy.INPUTS, (nested2,), {})
        key3 = compute_cache_key(test_func, CachePolicy.INPUTS, (nested3,), {})

        # Same nested structure should produce same key
        assert key1 == key2

        # Different nested structure should produce different key
        assert key1 != key3

    def test_cache_key_with_large_inputs(self):
        """Test cache key generation with large inputs."""

        def test_func(data):
            return data

        large_list = list(range(10000))

        # Should not raise an error
        key = compute_cache_key(test_func, CachePolicy.INPUTS, (large_list,), {})

        # Should be consistent
        key2 = compute_cache_key(test_func, CachePolicy.INPUTS, (large_list,), {})
        assert key == key2

    def test_cache_key_special_numeric_values(self):
        """Test cache key with special numeric values."""

        def test_func(val):
            return val

        # Test different numeric edge cases
        key_zero = compute_cache_key(test_func, CachePolicy.INPUTS, (0,), {})
        key_neg_zero = compute_cache_key(test_func, CachePolicy.INPUTS, (-0,), {})
        key_float_zero = compute_cache_key(test_func, CachePolicy.INPUTS, (0.0,), {})

        # These should actually be equal in Python
        # 0 == -0
        # but 0 and 0.0 are different types
        assert key_zero == key_neg_zero
        assert key_zero != key_float_zero
