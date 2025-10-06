"""Tests for cache policy enums."""

import pytest

from temporal_activity_cache.enums import CachePolicy


@pytest.mark.unit
class TestCachePolicy:
    """Test CachePolicy enum."""

    def test_cache_policy_values(self):
        """Test that CachePolicy has expected values."""
        assert CachePolicy.INPUTS.value == "inputs"
        assert CachePolicy.TASK_SOURCE.value == "task_source"
        assert CachePolicy.NO_CACHE.value == "no_cache"

    def test_cache_policy_members(self):
        """Test that all expected members exist."""
        policies = list(CachePolicy)
        assert len(policies) == 3
        assert CachePolicy.INPUTS in policies
        assert CachePolicy.TASK_SOURCE in policies
        assert CachePolicy.NO_CACHE in policies

    def test_cache_policy_string_representation(self):
        """Test string representation of cache policies."""
        assert str(CachePolicy.INPUTS) == "CachePolicy.INPUTS"
        assert str(CachePolicy.TASK_SOURCE) == "CachePolicy.TASK_SOURCE"
        assert str(CachePolicy.NO_CACHE) == "CachePolicy.NO_CACHE"

    def test_cache_policy_equality(self):
        """Test equality comparison of cache policies."""
        assert CachePolicy.INPUTS == CachePolicy.INPUTS
        assert CachePolicy.INPUTS != CachePolicy.TASK_SOURCE
        assert CachePolicy.INPUTS == "inputs"
        assert CachePolicy.TASK_SOURCE == "task_source"

    def test_cache_policy_is_enum(self):
        """Test that CachePolicy is a string enum."""
        # Should be comparable to strings
        assert CachePolicy.INPUTS == "inputs"
        # Should still be an enum
        assert isinstance(CachePolicy.INPUTS, CachePolicy)
