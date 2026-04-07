#!/usr/bin/env python3
"""
sdk_cache.py — Local cache for SDK documentation fetched via Context7 API.

Eliminates repeated API calls by caching docs locally with TTL-based freshness.

Usage:
    from mimir.sdk_cache import SDKCache

    cache = SDKCache(project_root="/path/to/project")

    # Get docs (fetches + caches if stale)
    docs = cache.get("stripe", "checkout sessions")

    # Check freshness
    cache.is_fresh("stripe")  # True/False

    # List cached libraries
    cache.list_cached()  # ["stripe", "nextjs", "react"]
"""

import json
import logging
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 7
CACHE_DIR_NAME = ".knowledge/sdk-cache"


class SDKCache:
    """Local cache for SDK documentation."""

    def __init__(self, project_root: Path, ttl_days: int = DEFAULT_TTL_DAYS):
        self.project_root = Path(project_root)
        self.cache_dir = self.project_root / CACHE_DIR_NAME
        self.ttl_days = ttl_days
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def _library_dir(self, library: str) -> Path:
        """Get cache directory for a library (sanitized name)."""
        safe_name = library.lower().replace("/", "-").replace(" ", "-")
        return self.cache_dir / safe_name

    def _meta_path(self, library: str) -> Path:
        return self._library_dir(library) / "meta.json"

    def _docs_path(self, library: str, topic: str = "general") -> Path:
        safe_topic = topic.lower().replace(" ", "-")[:50]
        return self._library_dir(library) / f"{safe_topic}.md"

    def is_fresh(self, library: str) -> bool:
        """Check if cached docs are within TTL."""
        meta_path = self._meta_path(library)
        if not meta_path.exists():
            return False

        try:
            meta = json.loads(meta_path.read_text())
            fetched = datetime.fromisoformat(meta["fetched_at"])
            ttl = timedelta(days=meta.get("ttl_days", self.ttl_days))
            return datetime.now() - fetched < ttl
        except (json.JSONDecodeError, KeyError, ValueError):
            return False

    def get_cached(self, library: str, topic: str = "general") -> Optional[str]:
        """Get cached docs if fresh. Returns None if stale or missing."""
        if not self.is_fresh(library):
            return None

        docs_path = self._docs_path(library, topic)
        if docs_path.exists():
            return docs_path.read_text()

        # Try general fallback
        general_path = self._library_dir(library) / "general.md"
        if general_path.exists():
            return general_path.read_text()

        return None

    def get(self, library: str, topic: str = "general") -> Optional[str]:
        """
        Get SDK docs — returns cached if fresh, fetches if stale/missing.

        Returns None if fetch fails and no cache exists.
        """
        # Try cache first
        cached = self.get_cached(library, topic)
        if cached:
            logger.info(f"Cache hit: {library}/{topic}")
            return cached

        # Fetch from Context7
        logger.info(f"Cache miss: {library}/{topic} — fetching from Context7")
        docs = self._fetch_from_context7(library, topic)

        if docs:
            self._write_cache(library, topic, docs)
            return docs

        # Fallback: return stale cache if available
        stale = self._read_stale(library, topic)
        if stale:
            logger.warning(f"Using stale cache for {library}/{topic}")
            return stale

        return None

    def _fetch_from_context7(self, library: str, topic: str) -> Optional[str]:
        """Fetch docs from Context7 API using httpx."""
        try:
            import urllib.parse

            encoded_library = urllib.parse.quote(library)
            encoded_topic = urllib.parse.quote(topic)

            with httpx.Client(timeout=20.0) as client:
                # Step 1: Search for library ID
                search_url = f"https://context7.com/api/v2/libs/search?libraryName={encoded_library}&query={encoded_topic}"
                search_resp = client.get(search_url)
                search_resp.raise_for_status()
                search_data = search_resp.json()

                results = search_data.get("results", [])
                if not results:
                    logger.warning(f"No Context7 results for {library}")
                    return None

                library_id = results[0].get("id", "")
                if not library_id:
                    logger.warning(f"No library ID in Context7 results for {library}")
                    return None

                # Step 2: Fetch documentation
                encoded_id = urllib.parse.quote(library_id)
                fetch_url = f"https://context7.com/api/v2/context?libraryId={encoded_id}&query={encoded_topic}&type=txt"
                fetch_resp = client.get(fetch_url)
                fetch_resp.raise_for_status()

                if not fetch_resp.text.strip():
                    logger.warning(
                        f"Context7 fetch returned empty for {library}/{topic}"
                    )
                    return None

                return fetch_resp.text.strip()

        except httpx.TimeoutException:
            logger.warning(f"Context7 timeout for {library}/{topic}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Context7 HTTP error for {library}/{topic}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Context7 fetch error: {e}")
            return None

    def _write_cache(self, library: str, topic: str, docs: str):
        """Write docs and metadata to cache."""
        with self._write_lock:
            lib_dir = self._library_dir(library)
            lib_dir.mkdir(parents=True, exist_ok=True)

            # Write docs
            docs_path = self._docs_path(library, topic)
            docs_path.write_text(docs)

            # Update metadata
            meta_path = self._meta_path(library)
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except json.JSONDecodeError:
                    pass

            meta["fetched_at"] = datetime.now().isoformat()
            meta["ttl_days"] = self.ttl_days
            meta["library"] = library

            # Track topics
            topics = meta.get("topics", [])
            if topic not in topics:
                topics.append(topic)
            meta["topics"] = topics

            meta_path.write_text(json.dumps(meta, indent=2))
            logger.info(f"Cached: {library}/{topic} ({len(docs)} chars)")

    def _read_stale(self, library: str, topic: str) -> Optional[str]:
        """Read stale cache as fallback."""
        docs_path = self._docs_path(library, topic)
        if docs_path.exists():
            return docs_path.read_text()
        general_path = self._library_dir(library) / "general.md"
        if general_path.exists():
            return general_path.read_text()
        return None

    def list_cached(self) -> list[dict]:
        """List all cached libraries with freshness info."""
        results = []
        if not self.cache_dir.exists():
            return results

        for lib_dir in sorted(self.cache_dir.iterdir()):
            if not lib_dir.is_dir():
                continue

            meta_path = lib_dir / "meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except json.JSONDecodeError:
                    pass

            # Count doc files
            doc_files = list(lib_dir.glob("*.md"))

            results.append(
                {
                    "library": lib_dir.name,
                    "fresh": self.is_fresh(lib_dir.name),
                    "fetched_at": meta.get("fetched_at", "unknown"),
                    "topics": meta.get("topics", []),
                    "doc_count": len(doc_files),
                }
            )

        return results

    def invalidate(self, library: str):
        """Remove cached docs for a library."""
        lib_dir = self._library_dir(library)
        if lib_dir.exists():
            import shutil

            shutil.rmtree(lib_dir)
            logger.info(f"Invalidated cache: {library}")

    def refresh(self, library: str, topic: str = "general") -> Optional[str]:
        """Force refresh — fetch fresh docs regardless of cache."""
        docs = self._fetch_from_context7(library, topic)
        if docs:
            self._write_cache(library, topic, docs)
        return docs


# ── CLI interface ──────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="SDK Documentation Cache")
    parser.add_argument(
        "action",
        choices=["get", "list", "refresh", "invalidate"],
        help="Action to perform",
    )
    parser.add_argument("library", nargs="?", help="Library name")
    parser.add_argument("--topic", default="general", help="Documentation topic")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_DAYS)
    args = parser.parse_args()

    # Detect project root
    if args.project_root:
        project_root = args.project_root
    else:
        cwd = Path.cwd()
        markers = [".mimir", ".git", "opencode.json"]
        project_root = cwd
        for parent in [cwd] + list(cwd.parents):
            if any((parent / m).exists() for m in markers):
                project_root = parent
                break

    cache = SDKCache(project_root, ttl_days=args.ttl)

    if args.action == "list":
        cached = cache.list_cached()
        if not cached:
            print("No cached SDK docs.")
            return

        print(f"\n{'Library':<25} {'Fresh':<8} {'Topics':<30} {'Fetched'}")
        print("-" * 80)
        for entry in cached:
            fresh = "✅" if entry["fresh"] else "⏰"
            topics = ", ".join(entry["topics"][:3])
            fetched = (
                entry["fetched_at"][:10] if entry["fetched_at"] != "unknown" else "?"
            )
            print(f"{entry['library']:<25} {fresh:<8} {topics:<30} {fetched}")
        print()

    elif args.action == "get":
        if not args.library:
            print("Error: library name required for 'get'")
            sys.exit(1)
        docs = cache.get(args.library, args.topic)
        if docs:
            print(docs)
        else:
            print(f"No docs found for {args.library}/{args.topic}")
            sys.exit(1)

    elif args.action == "refresh":
        if not args.library:
            print("Error: library name required for 'refresh'")
            sys.exit(1)
        docs = cache.refresh(args.library, args.topic)
        if docs:
            print(f"Refreshed: {args.library}/{args.topic} ({len(docs)} chars)")
        else:
            print(f"Failed to refresh: {args.library}/{args.topic}")
            sys.exit(1)

    elif args.action == "invalidate":
        if not args.library:
            print("Error: library name required for 'invalidate'")
            sys.exit(1)
        cache.invalidate(args.library)
        print(f"Invalidated: {args.library}")


if __name__ == "__main__":
    main()
