#!/usr/bin/env python3
"""Tests for the SDK documentation cache module."""

import json
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_mimir_config():
    """Reset MimirConfig singleton before each test to avoid stale cached values."""
    from src.mimir.config import reset_config

    reset_config()
    yield
    reset_config()


from src.mimir.sdk_cache import (
    CACHE_DIR_NAME,
    DEFAULT_TTL_DAYS,
    SDKCache,
)


# ─── SDKCache.__init__ Tests ─────────────────────────────────────────────────


class TestSDKCacheInit:
    """Tests for SDKCache initialization."""

    def test_creates_cache_directory(self, tmp_path: Path):
        """Should create cache directory on init."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root)

        # Assert
        assert cache.cache_dir.exists()
        assert cache.cache_dir.name == CACHE_DIR_NAME.split("/")[-1]

    def test_creates_nested_cache_directory(self, tmp_path: Path):
        """Should create nested cache directory structure."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root)

        # Assert
        assert cache.cache_dir.exists()
        assert cache.cache_dir.parent.name == ".knowledge"

    def test_uses_custom_ttl(self, tmp_path: Path):
        """Should use custom TTL when provided."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root, ttl_days=14)

        # Assert
        assert cache.ttl_days == 14

    def test_default_ttl_is_seven_days(self, tmp_path: Path):
        """Should default TTL to 7 days."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root)

        # Assert
        assert cache.ttl_days == DEFAULT_TTL_DAYS
        assert cache.ttl_days == 7

    def test_has_write_lock(self, tmp_path: Path):
        """Should have a write lock for thread safety."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root)

        # Assert
        assert hasattr(cache, "_write_lock")
        assert isinstance(cache._write_lock, type(threading.Lock()))


# ─── _library_dir Tests ──────────────────────────────────────────────────────


class TestLibraryDir:
    """Tests for _library_dir method."""

    def test_sanitizes_slashes(self, tmp_path: Path):
        """Should replace slashes with dashes."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        lib_dir = cache._library_dir("org/library")

        # Assert
        assert lib_dir.name == "org-library"

    def test_sanitizes_spaces(self, tmp_path: Path):
        """Should replace spaces with dashes."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        lib_dir = cache._library_dir("my library")

        # Assert
        assert lib_dir.name == "my-library"

    def test_lowercases_names(self, tmp_path: Path):
        """Should lowercase library names."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        lib_dir = cache._library_dir("MyLibrary")

        # Assert
        assert lib_dir.name == "mylibrary"

    def test_returns_path_under_cache_dir(self, tmp_path: Path):
        """Should return path under cache directory."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        lib_dir = cache._library_dir("stripe")

        # Assert
        assert (
            cache.cache_dir in lib_dir.parents or lib_dir == cache.cache_dir / "stripe"
        )


# ─── _docs_path Tests ─────────────────────────────────────────────────────────


class TestDocsPath:
    """Tests for _docs_path method."""

    def test_truncates_long_topic_names(self, tmp_path: Path):
        """Should truncate topic names to 50 characters."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)
        long_topic = "a" * 100

        # Act
        docs_path = cache._docs_path("lib", long_topic)

        # Assert
        assert len(docs_path.stem) <= 50

    def test_replaces_spaces_in_topic(self, tmp_path: Path):
        """Should replace spaces with dashes in topic."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        docs_path = cache._docs_path("lib", "checkout sessions")

        # Assert
        assert "checkout-sessions" in docs_path.name

    def test_returns_md_file(self, tmp_path: Path):
        """Should return .md file path."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        docs_path = cache._docs_path("lib", "general")

        # Assert
        assert docs_path.suffix == ".md"


# ─── is_fresh Tests ───────────────────────────────────────────────────────────


class TestIsFresh:
    """Tests for is_fresh method."""

    def test_returns_false_for_missing_cache(self, tmp_path: Path):
        """Should return False when cache doesn't exist."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        result = cache.is_fresh("nonexistent")

        # Assert
        assert result is False

    def test_returns_true_for_fresh_cache(self, tmp_path: Path):
        """Should return True for cache within TTL."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create a fresh cache entry
        lib_dir = cache._library_dir("stripe")
        lib_dir.mkdir(parents=True)
        meta = {
            "fetched_at": datetime.now().isoformat(),
            "ttl_days": 7,
            "library": "stripe",
        }
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("# Stripe Docs")

        # Act
        result = cache.is_fresh("stripe")

        # Assert
        assert result is True

    def test_returns_false_for_expired_cache(self, tmp_path: Path):
        """Should return False for cache past TTL."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create an expired cache entry
        lib_dir = cache._library_dir("oldlib")
        lib_dir.mkdir(parents=True)
        old_time = datetime.now() - timedelta(days=10)
        meta = {
            "fetched_at": old_time.isoformat(),
            "ttl_days": 7,
            "library": "oldlib",
        }
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("# Old Docs")

        # Act
        result = cache.is_fresh("oldlib")

        # Assert
        assert result is False

    def test_handles_malformed_meta_json(self, tmp_path: Path):
        """Should return False for malformed meta.json."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        lib_dir = cache._library_dir("badlib")
        lib_dir.mkdir(parents=True)
        (lib_dir / "meta.json").write_text("{ invalid json }")
        (lib_dir / "general.md").write_text("# Bad Docs")

        # Act
        result = cache.is_fresh("badlib")

        # Assert
        assert result is False

    def test_handles_missing_fetched_at_field(self, tmp_path: Path):
        """Should return False when fetched_at field is missing."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        lib_dir = cache._library_dir("incomplete")
        lib_dir.mkdir(parents=True)
        meta = {"library": "incomplete"}  # Missing fetched_at
        (lib_dir / "meta.json").write_text(json.dumps(meta))

        # Act
        result = cache.is_fresh("incomplete")

        # Assert
        assert result is False


# ─── get_cached Tests ────────────────────────────────────────────────────────


class TestGetCached:
    """Tests for get_cached method."""

    def test_returns_none_when_missing(self, tmp_path: Path):
        """Should return None when cache doesn't exist."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        result = cache.get_cached("nonexistent")

        # Assert
        assert result is None

    def test_returns_none_when_expired(self, tmp_path: Path):
        """Should return None when cache is expired."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create expired cache
        lib_dir = cache._library_dir("expired")
        lib_dir.mkdir(parents=True)
        old_time = datetime.now() - timedelta(days=10)
        meta = {"fetched_at": old_time.isoformat(), "ttl_days": 7}
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("Old content")

        # Act
        result = cache.get_cached("expired")

        # Assert
        assert result is None

    def test_returns_content_when_fresh(self, tmp_path: Path):
        """Should return cached content when fresh."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create fresh cache
        lib_dir = cache._library_dir("fresh")
        lib_dir.mkdir(parents=True)
        meta = {"fetched_at": datetime.now().isoformat(), "ttl_days": 7}
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("# Fresh Docs\n\nContent here.")

        # Act
        result = cache.get_cached("fresh")

        # Assert
        assert result is not None
        assert "Fresh Docs" in result

    def test_falls_back_to_general_topic(self, tmp_path: Path):
        """Should fall back to general.md when specific topic not found."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create cache with only general.md
        lib_dir = cache._library_dir("fallback")
        lib_dir.mkdir(parents=True)
        meta = {"fetched_at": datetime.now().isoformat(), "ttl_days": 7}
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("General content")

        # Act
        result = cache.get_cached("fallback", topic="specific")

        # Assert
        assert result == "General content"


# ─── _write_cache Tests ───────────────────────────────────────────────────────


class TestWriteCache:
    """Tests for _write_cache method."""

    def test_writes_docs_file(self, tmp_path: Path):
        """Should write documentation to .md file."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)
        docs_content = "# Stripe API\n\nDocumentation content."

        # Act
        cache._write_cache("stripe", "general", docs_content)

        # Assert
        docs_path = cache._docs_path("stripe", "general")
        assert docs_path.exists()
        assert docs_path.read_text() == docs_content

    def test_writes_meta_json(self, tmp_path: Path):
        """Should write metadata to meta.json."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        cache._write_cache("react", "hooks", "# React Hooks")

        # Assert
        meta_path = cache._meta_path("react")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert "fetched_at" in meta
        assert meta["library"] == "react"

    def test_tracks_topics_in_meta(self, tmp_path: Path):
        """Should track topics in metadata."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        cache._write_cache("nextjs", "routing", "# Routing")
        cache._write_cache("nextjs", "data-fetching", "# Data Fetching")

        # Assert
        meta_path = cache._meta_path("nextjs")
        meta = json.loads(meta_path.read_text())
        assert "routing" in meta["topics"]
        assert "data-fetching" in meta["topics"]

    def test_preserves_existing_meta_on_update(self, tmp_path: Path):
        """Should preserve existing metadata when updating."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # First write
        cache._write_cache("vue", "general", "# Vue Docs")

        # Get initial timestamp
        meta_path = cache._meta_path("vue")
        initial_meta = json.loads(meta_path.read_text())

        # Act - second write
        time.sleep(0.1)  # Ensure different timestamp
        cache._write_cache("vue", "components", "# Components")

        # Assert
        updated_meta = json.loads(meta_path.read_text())
        assert updated_meta["library"] == initial_meta["library"]
        assert "components" in updated_meta["topics"]


# ─── list_cached Tests ────────────────────────────────────────────────────────


class TestListCached:
    """Tests for list_cached method."""

    def test_returns_empty_list_when_no_cache(self, tmp_path: Path):
        """Should return empty list when no cache exists."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act
        result = cache.list_cached()

        # Assert
        assert result == []

    def test_returns_library_info(self, tmp_path: Path):
        """Should return info for cached libraries."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create cache entries
        cache._write_cache("stripe", "general", "# Stripe")
        cache._write_cache("react", "hooks", "# Hooks")

        # Act
        result = cache.list_cached()

        # Assert
        assert len(result) == 2
        libraries = [r["library"] for r in result]
        assert "stripe" in libraries
        assert "react" in libraries

    def test_includes_freshness_status(self, tmp_path: Path):
        """Should include freshness status."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        cache._write_cache("fresh-lib", "general", "# Fresh")

        # Act
        result = cache.list_cached()

        # Assert
        assert result[0]["fresh"] is True

    def test_includes_doc_count(self, tmp_path: Path):
        """Should include document count."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        cache._write_cache("multi", "general", "# General")
        cache._write_cache("multi", "advanced", "# Advanced")

        # Act
        result = cache.list_cached()

        # Assert
        multi_entry = next(r for r in result if r["library"] == "multi")
        assert multi_entry["doc_count"] == 2


# ─── invalidate Tests ─────────────────────────────────────────────────────────


class TestInvalidate:
    """Tests for invalidate method."""

    def test_removes_cached_directory(self, tmp_path: Path):
        """Should remove the cached library directory."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        cache._write_cache("to-delete", "general", "# Delete Me")

        # Act
        cache.invalidate("to-delete")

        # Assert
        lib_dir = cache._library_dir("to-delete")
        assert not lib_dir.exists()

    def test_handles_nonexistent_library(self, tmp_path: Path):
        """Should not raise error for nonexistent library."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Act & Assert - should not raise
        cache.invalidate("nonexistent")


# ─── get Tests (Integration) ─────────────────────────────────────────────────


class TestGet:
    """Tests for get method (integration with fetch)."""

    def test_returns_cached_when_fresh(self, tmp_path: Path):
        """Should return cached content when fresh."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Pre-populate cache
        cache._write_cache("cached-lib", "general", "# Cached Content")

        # Act
        result = cache.get("cached-lib")

        # Assert
        assert result == "# Cached Content"

    def test_fetches_when_stale(self, tmp_path: Path):
        """Should fetch new content when cache is stale."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create stale cache
        lib_dir = cache._library_dir("stale-lib")
        lib_dir.mkdir(parents=True)
        old_time = datetime.now() - timedelta(days=10)
        meta = {"fetched_at": old_time.isoformat(), "ttl_days": 7}
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("Old content")

        # Mock the fetch method
        with patch.object(
            cache, "_fetch_from_context7", return_value="# Fresh Content"
        ):
            # Act
            result = cache.get("stale-lib")

        # Assert
        assert result == "# Fresh Content"

    def test_returns_stale_on_fetch_failure(self, tmp_path: Path):
        """Should return stale cache when fetch fails."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        # Create stale cache
        lib_dir = cache._library_dir("failed-fetch")
        lib_dir.mkdir(parents=True)
        old_time = datetime.now() - timedelta(days=10)
        meta = {"fetched_at": old_time.isoformat(), "ttl_days": 7}
        (lib_dir / "meta.json").write_text(json.dumps(meta))
        (lib_dir / "general.md").write_text("Stale but usable")

        # Mock fetch to fail
        with patch.object(cache, "_fetch_from_context7", return_value=None):
            # Act
            result = cache.get("failed-fetch")

        # Assert
        assert result == "Stale but usable"

    def test_returns_none_when_no_cache_and_fetch_fails(self, tmp_path: Path):
        """Should return None when no cache and fetch fails."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        with patch.object(cache, "_fetch_from_context7", return_value=None):
            # Act
            result = cache.get("no-cache")

        # Assert
        assert result is None


# ─── Thread Safety Tests ─────────────────────────────────────────────────────


class TestThreadSafety:
    """Tests for thread safety."""

    def test_write_lock_exists(self, tmp_path: Path):
        """Should have a write lock attribute."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Act
        cache = SDKCache(project_root=project_root)

        # Assert
        assert hasattr(cache, "_write_lock")
        assert isinstance(cache._write_lock, type(threading.Lock()))

    def test_concurrent_writes_safe(self, tmp_path: Path):
        """Should handle concurrent writes safely."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        cache = SDKCache(project_root=project_root)

        errors = []

        def write_docs(topic: str):
            try:
                cache._write_cache("concurrent", topic, f"# {topic}")
            except Exception as e:
                errors.append(e)

        # Act - create multiple threads
        threads = [
            threading.Thread(target=write_docs, args=(f"topic-{i}",)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Assert
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
