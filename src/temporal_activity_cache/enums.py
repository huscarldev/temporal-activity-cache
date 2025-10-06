"""Cache policy enums for activity caching."""

from enum import Enum


class CachePolicy(str, Enum):
    """Cache policy determining how cache keys are generated.

    Similar to Prefect's cache policies:
    - INPUTS: Cache based on function inputs only
    - TASK_SOURCE: Cache based on function source code + inputs
    - NO_CACHE: Disable caching for this activity
    """

    INPUTS = "inputs"
    """Cache based on activity inputs (arguments) only."""

    TASK_SOURCE = "task_source"
    """Cache based on activity source code and inputs."""

    NO_CACHE = "no_cache"
    """Disable caching entirely."""
