"""In-Memory TTL & LRU Caching Module for Step 24.

Provides asynchronous, thread-safe, bounded, in-memory caching with configurable
Time-To-Live (TTL), LRU eviction, stable key generation, and feature flag bypass.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float
    created_at: float


class AsyncTTLCache:
    """Thread-safe and coroutine-safe in-memory cache with TTL and LRU eviction."""

    def __init__(
        self,
        ttl_seconds: Optional[int] = None,
        max_size: Optional[int] = None,
        enabled: Optional[bool] = None,
    ):
        self._ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else settings.CACHE_TTL_SECONDS
        )
        self._max_size = max_size if max_size is not None else settings.CACHE_MAX_SIZE
        self._enabled = enabled if enabled is not None else settings.CACHE_ENABLED
        self._store: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_ttl(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds

    def set_max_size(self, max_size: int) -> None:
        self._max_size = max_size

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value if exists and not expired.

        Args:
            key: Cache lookup key.

        Returns:
            Cached value if found and valid; None otherwise.
        """
        if not self._enabled:
            return None

        async with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            entry = self._store[key]
            now = time.time()

            if now > entry.expires_at:
                # Expired - remove from store
                del self._store[key]
                self._misses += 1
                return None

            # Refresh LRU access position
            self._store.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in cache with TTL and enforce bounded size limit.

        Args:
            key: Cache key.
            value: Data to store (must not be None or an error placeholder).
            ttl: Optional TTL override in seconds.
        """
        if not self._enabled or value is None:
            return

        effective_ttl = ttl if ttl is not None else self._ttl_seconds
        expires_at = time.time() + effective_ttl

        async with self._lock:
            # If key exists, update and move to end
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = _CacheEntry(
                    value=value, expires_at=expires_at, created_at=time.time()
                )
                return

            # Check capacity and evict oldest item if needed
            while len(self._store) >= self._max_size and self._store:
                self._store.popitem(last=False)

            self._store[key] = _CacheEntry(
                value=value, expires_at=expires_at, created_at=time.time()
            )

    async def delete(self, key: str) -> bool:
        """Explicitly remove a single key from cache."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries from cache and reset counters."""
        async with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    async def size(self) -> int:
        """Return current number of items in cache (including unpruned expired ones)."""
        async with self._lock:
            return len(self._store)

    async def prune_expired(self) -> int:
        """Explicitly prune all expired entries and return the count removed."""
        now = time.time()
        pruned_count = 0
        async with self._lock:
            keys_to_remove = [k for k, v in self._store.items() if now > v.expires_at]
            for k in keys_to_remove:
                del self._store[k]
                pruned_count += 1
        return pruned_count

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics and capacity metrics."""
        total = self._hits + self._misses
        hit_ratio = (self._hits / total) if total > 0 else 0.0
        return {
            "enabled": self._enabled,
            "ttl_seconds": self._ttl_seconds,
            "max_size": self._max_size,
            "current_size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": round(hit_ratio, 4),
        }


def generate_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a stable, deterministic cache key from prefix and arguments.

    Args:
        prefix: Namespace prefix (e.g. 'crawler', 'ai_verify', 'ai_analyze').
        *args: Positional argument values to hash.
        **kwargs: Keyword argument values to hash.

    Returns:
        Structured string like 'prefix:sha256_hash'.
    """
    key_dict = {
        "args": [str(a) for a in args],
        "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
    }
    serialized = json.dumps(key_dict, sort_keys=True, default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


# Global default cache instance
app_cache = AsyncTTLCache()
