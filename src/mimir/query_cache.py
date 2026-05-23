"""Query result caching for Mimir.

Caches search and query results to avoid redundant LLM calls and API costs.
Uses content hashing to detect unchanged queries and serve cached results.

Features:
  - Content-addressable cache using SHA-256 hashes
  - TTL-based expiration (default 1 hour for search, 24 hours for artifacts)
  - Persistent storage in .knowledge/query_cache/
  - Automatic cleanup of expired entries
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from mimir.config import MimirConfig


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_DIR_NAME = "query_cache"
SEARCH_TTL_SECONDS = 3600  # 1 hour
QUERY_TTL_SECONDS = 7200  # 2 hours
ARTIFACT_TTL_SECONDS = 86400  # 24 hours


# ---------------------------------------------------------------------------
# Query Cache Class
# ---------------------------------------------------------------------------

class QueryCache:
    """Cache for query results to reduce redundant API calls."""

    def __init__(self, project_root: Path, cache_dir: Optional[Path] = None):
        self.project_root = Path(project_root)
        self.cache_dir = cache_dir or (self.project_root / ".knowledge" / CACHE_DIR_NAME)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, query: str, query_type: str, **kwargs) -> str:
        """Generate a cache key from query and parameters."""
        # Normalize query and kwargs for consistent hashing
        normalized = f"{query_type}:{query}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache entry."""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, query: str, query_type: str, ttl_seconds: int = SEARCH_TTL_SECONDS, **kwargs) -> Optional[str]:
        """Get cached result if available and not expired.

        Args:
            query: The search/query string
            query_type: Type of query ("search", "query", "rag_workflow")
            ttl_seconds: Time-to-live for cached results
            **kwargs: Additional parameters (top_k, etc.)

        Returns:
            Cached result string, or None if not found/expired
        """
        cache_key = self._get_cache_key(query, query_type, **kwargs)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r") as f:
                entry = json.load(f)

            # Check TTL
            timestamp = entry.get("timestamp", 0)
            if time.time() - timestamp > ttl_seconds:
                # Expired - delete and return None
                cache_path.unlink(missing_ok=True)
                return None

            return entry.get("result")
        except (json.JSONDecodeError, OSError):
            # Corrupt cache entry - delete it
            cache_path.unlink(missing_ok=True)
            return None

    def set(self, query: str, query_type: str, result: str, **kwargs) -> None:
        """Cache a query result.

        Args:
            query: The search/query string
            query_type: Type of query ("search", "query", "rag_workflow")
            result: The result to cache
            **kwargs: Additional parameters (top_k, etc.)
        """
        cache_key = self._get_cache_key(query, query_type, **kwargs)
        cache_path = self._get_cache_path(cache_key)

        entry = {
            "query": query,
            "query_type": query_type,
            "kwargs": kwargs,
            "result": result,
            "timestamp": time.time(),
        }

        try:
            with open(cache_path, "w") as f:
                json.dump(entry, f)
        except OSError:
            pass  # Fail silently - cache is optional

    def invalidate(self, query_type: Optional[str] = None) -> int:
        """Invalidate cached entries.

        Args:
            query_type: If provided, only invalidate entries of this type

        Returns:
            Number of entries invalidated
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if query_type:
                    with open(cache_file, "r") as f:
                        entry = json.load(f)
                    if entry.get("query_type") != query_type:
                        continue

                cache_file.unlink()
                count += 1
            except Exception:
                # Delete corrupt entries
                cache_file.unlink(missing_ok=True)
                count += 1

        return count

    def cleanup(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    entry = json.load(f)

                timestamp = entry.get("timestamp", 0)
                query_type = entry.get("query_type", "search")

                # Use appropriate TTL
                if query_type == "search":
                    ttl = SEARCH_TTL_SECONDS
                elif query_type == "query":
                    ttl = QUERY_TTL_SECONDS
                else:
                    ttl = ARTIFACT_TTL_SECONDS

                if time.time() - timestamp > ttl:
                    cache_file.unlink()
                    count += 1
            except Exception:
                cache_file.unlink(missing_ok=True)
                count += 1

        return count

    def stats(self) -> dict:
        """Get cache statistics."""
        total = 0
        by_type = {}

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    entry = json.load(f)

                total += 1
                query_type = entry.get("query_type", "unknown")
                by_type[query_type] = by_type.get(query_type, 0) + 1
            except Exception:
                pass

        return {
            "total_entries": total,
            "by_type": by_type,
            "cache_dir": str(self.cache_dir),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_query_cache(project_root: Path) -> QueryCache:
    """Get or create a QueryCache instance for a project."""
    return QueryCache(project_root)


def cached_query(cache: QueryCache, query: str, query_type: str, executor_func, ttl_seconds: Optional[int] = None, **kwargs) -> str:
    """Execute a query with caching.

    Args:
        cache: QueryCache instance
        query: The search/query string
        query_type: Type of query ("search", "query", "rag_workflow")
        executor_func: Function to execute if cache miss
        ttl_seconds: Override default TTL
        **kwargs: Additional parameters for executor_func

    Returns:
        Query result (from cache or fresh)
    """
    # Check cache first
    if ttl_seconds is None:
        if query_type == "search":
            ttl_seconds = SEARCH_TTL_SECONDS
        elif query_type == "query":
            ttl_seconds = QUERY_TTL_SECONDS
        else:
            ttl_seconds = ARTIFACT_TTL_SECONDS

    cached = cache.get(query, query_type, ttl_seconds, **kwargs)
    if cached is not None:
        return cached + "\n[Cache Hit]"

    # Execute query
    result = executor_func(**kwargs)

    # Cache result
    cache.set(query, query_type, result, **kwargs)

    return result
