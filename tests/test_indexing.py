#!/usr/bin/env python3
"""Tests for the indexing utilities module."""

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))

from src.mimir.indexing import (
    MAX_FILE_SIZE_FOR_HASHING,
    add_to_manifest,
    clear_manifest,
    compute_file_hash,
    detect_changed_files,
    get_manifest_path,
    get_progress_bar,
    list_indexed_files,
    load_hash_state,
    load_manifest,
    remove_from_manifest,
    save_hash_state,
    save_manifest,
)
from src.mimir.utils import EXCLUDE_PATTERNS


# ─── Constants Tests ─────────────────────────────────────────────────────────


class TestConstants:
    """Tests for module constants."""

    def test_max_file_size_is_reasonable(self):
        """MAX_FILE_SIZE_FOR_HASHING should be 50MB."""
        assert MAX_FILE_SIZE_FOR_HASHING == 50 * 1024 * 1024

    def test_exclude_patterns_imported(self):
        """EXCLUDE_PATTERNS should be imported from utils."""
        assert EXCLUDE_PATTERNS is not None
        assert len(EXCLUDE_PATTERNS) > 0


# ─── Progress Bar Tests ──────────────────────────────────────────────────────


class TestProgressBar:
    """Tests for progress bar functionality."""

    def test_get_progress_bar_returns_context_manager(self):
        """Should return a context manager."""
        bar = get_progress_bar(total=10, desc="test")
        assert hasattr(bar, "__enter__")
        assert hasattr(bar, "__exit__")

    def test_progress_bar_iterates(self):
        """Should iterate over items."""
        items = [1, 2, 3]
        bar = get_progress_bar(iterable=items, desc="test")
        result = list(bar)
        assert result == items


# ─── Manifest Path Tests ─────────────────────────────────────────────────────


class TestManifestPath:
    """Tests for manifest path functions."""

    def test_get_manifest_path_returns_correct_path(self, tmp_path: Path):
        """Should return path to manifest.json."""
        knowledge_dir = tmp_path / ".knowledge"
        manifest_path = get_manifest_path(knowledge_dir)
        assert manifest_path.name == "manifest.json"
        assert manifest_path.parent == knowledge_dir


# ─── Manifest Load/Save Tests ────────────────────────────────────────────────


class TestManifestLoadSave:
    """Tests for manifest load/save functions."""

    def test_load_manifest_missing_file(self, tmp_path: Path):
        """Should return default manifest for missing file."""
        knowledge_dir = tmp_path / ".knowledge"
        manifest = load_manifest(knowledge_dir)
        assert manifest["version"] == "1.0"
        assert manifest["indexed_directories"] == {}
        assert manifest["total_documents"] == 0

    def test_load_manifest_valid_file(self, tmp_path: Path):
        """Should load valid manifest file."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        manifest_data = {
            "version": "1.0",
            "indexed_directories": {"test": {"files": ["a.py"]}},
            "total_documents": 5,
            "last_updated": "2024-01-01T00:00:00",
        }
        (knowledge_dir / "manifest.json").write_text(json.dumps(manifest_data))

        manifest = load_manifest(knowledge_dir)
        assert manifest["total_documents"] == 5

    def test_load_manifest_malformed_json(self, tmp_path: Path):
        """Should return default manifest for malformed JSON."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "manifest.json").write_text("{ invalid json }")

        manifest = load_manifest(knowledge_dir)
        assert manifest["version"] == "1.0"

    def test_save_manifest_creates_file(self, tmp_path: Path):
        """Should create manifest file."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        manifest = {
            "version": "1.0",
            "indexed_directories": {},
            "total_documents": 0,
        }

        save_manifest(knowledge_dir, manifest)

        manifest_path = knowledge_dir / "manifest.json"
        assert manifest_path.exists()

    def test_save_manifest_adds_timestamp(self, tmp_path: Path):
        """Should add last_updated timestamp."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        manifest = {
            "version": "1.0",
            "indexed_directories": {},
            "total_documents": 0,
        }

        save_manifest(knowledge_dir, manifest)

        loaded = json.loads((knowledge_dir / "manifest.json").read_text())
        assert "last_updated" in loaded

    def test_save_load_roundtrip(self, tmp_path: Path):
        """Should preserve data through save/load cycle."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        original = {
            "version": "1.0",
            "indexed_directories": {
                "/path/to/docs": {
                    "files": ["a.md", "b.md"],
                    "file_count": 2,
                    "document_count": 10,
                }
            },
            "total_documents": 10,
        }

        save_manifest(knowledge_dir, original)
        loaded = load_manifest(knowledge_dir)

        assert loaded["total_documents"] == 10
        assert loaded["indexed_directories"]["/path/to/docs"]["file_count"] == 2


# ─── Add to Manifest Tests ──────────────────────────────────────────────────


class TestAddToManifest:
    """Tests for add_to_manifest function."""

    def test_add_new_directory(self, tmp_path: Path):
        """Should add new directory to manifest."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        add_to_manifest(knowledge_dir, docs_dir, ["a.md", "b.md"], 5)

        manifest = load_manifest(knowledge_dir)
        dir_key = str(docs_dir.resolve())
        assert dir_key in manifest["indexed_directories"]
        assert manifest["total_documents"] == 5

    def test_add_incremental_update(self, tmp_path: Path):
        """Should merge files for incremental update."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        # First add
        add_to_manifest(knowledge_dir, docs_dir, ["a.md"], 3, is_incremental=False)

        # Incremental add
        add_to_manifest(knowledge_dir, docs_dir, ["b.md"], 2, is_incremental=True)

        manifest = load_manifest(knowledge_dir)
        dir_key = str(docs_dir.resolve())
        files = manifest["indexed_directories"][dir_key]["files"]
        assert "a.md" in files
        assert "b.md" in files
        assert manifest["total_documents"] == 5

    def test_add_with_file_hashes(self, tmp_path: Path):
        """Should store file hashes when provided."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        hashes = {"/path/a.md": "abc123"}
        add_to_manifest(knowledge_dir, docs_dir, ["a.md"], 1, file_hashes=hashes)

        manifest = load_manifest(knowledge_dir)
        dir_key = str(docs_dir.resolve())
        assert "file_hashes" in manifest["indexed_directories"][dir_key]


# ─── Remove from Manifest Tests ──────────────────────────────────────────────


class TestRemoveFromManifest:
    """Tests for remove_from_manifest function."""

    def test_remove_existing_file(self, tmp_path: Path):
        """Should remove file from manifest."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        # Add files first
        file_path = docs_dir / "a.md"
        add_to_manifest(knowledge_dir, docs_dir, [str(file_path)], 1)

        # Remove file
        result = remove_from_manifest(knowledge_dir, file_path)

        assert result is True
        manifest = load_manifest(knowledge_dir)
        dir_key = str(docs_dir.resolve())
        # Check that the file is no longer in the files list
        if dir_key in manifest["indexed_directories"]:
            assert str(file_path.resolve()) not in manifest["indexed_directories"][
                dir_key
            ].get("files", [])

    def test_remove_nonexistent_file(self, tmp_path: Path):
        """Should return False for nonexistent file."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()

        result = remove_from_manifest(knowledge_dir, Path("/nonexistent/file.md"))
        assert result is False

    def test_remove_last_file_removes_directory_entry(self, tmp_path: Path):
        """Should remove directory entry when no files left."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        file_path = docs_dir / "only.md"
        add_to_manifest(knowledge_dir, docs_dir, [str(file_path)], 1)

        remove_from_manifest(knowledge_dir, file_path)

        manifest = load_manifest(knowledge_dir)
        dir_key = str(docs_dir.resolve())
        assert dir_key not in manifest["indexed_directories"]


# ─── Clear Manifest Tests ───────────────────────────────────────────────────


class TestClearManifest:
    """Tests for clear_manifest function."""

    def test_clear_resets_manifest(self, tmp_path: Path):
        """Should reset manifest to empty state."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        # Add some data
        add_to_manifest(knowledge_dir, docs_dir, ["a.md"], 5)

        # Clear
        clear_manifest(knowledge_dir)

        manifest = load_manifest(knowledge_dir)
        assert manifest["indexed_directories"] == {}
        assert manifest["total_documents"] == 0


# ─── List Indexed Files Tests ────────────────────────────────────────────────


class TestListIndexedFiles:
    """Tests for list_indexed_files function."""

    def test_list_returns_manifest(self, tmp_path: Path):
        """Should return the manifest dict."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"

        add_to_manifest(knowledge_dir, docs_dir, ["a.md"], 3)

        result = list_indexed_files(knowledge_dir)
        assert isinstance(result, dict)
        assert "indexed_directories" in result


# ─── File Hash Tests ─────────────────────────────────────────────────────────


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256_hash(self, tmp_path: Path):
        """Should compute correct SHA-256 hash."""
        file_path = tmp_path / "test.txt"
        content = "Hello, World!"
        file_path.write_text(content)

        result = compute_file_hash(file_path)

        # Verify against known hash
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert result == expected

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path):
        """Should return None for nonexistent file."""
        result = compute_file_hash(tmp_path / "nonexistent.txt")
        assert result is None

    def test_returns_none_for_large_file(self, tmp_path: Path):
        """Should return None for files exceeding size limit."""
        file_path = tmp_path / "large.bin"
        # Create a small file but test the logic by using a small threshold
        file_path.write_bytes(b"x" * 100)

        # Test by temporarily modifying the constant
        import src.mimir.indexing as indexing_module

        original_max = indexing_module.MAX_FILE_SIZE_FOR_HASHING
        try:
            indexing_module.MAX_FILE_SIZE_FOR_HASHING = 50  # Set below file size
            result = compute_file_hash(file_path)
            assert result is None
        finally:
            indexing_module.MAX_FILE_SIZE_FOR_HASHING = original_max

    def test_handles_binary_files(self, tmp_path: Path):
        """Should handle binary files correctly."""
        file_path = tmp_path / "binary.bin"
        content = b"\x00\x01\x02\x03\xff\xfe\xfd"
        file_path.write_bytes(content)

        result = compute_file_hash(file_path)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_handles_empty_file(self, tmp_path: Path):
        """Should handle empty files."""
        file_path = tmp_path / "empty.txt"
        file_path.write_text("")

        result = compute_file_hash(file_path)

        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected


# ─── Hash State Tests ────────────────────────────────────────────────────────


class TestHashState:
    """Tests for hash state load/save functions."""

    def test_load_hash_state_missing_file(self, tmp_path: Path):
        """Should return empty state for missing file."""
        state = load_hash_state(tmp_path)
        assert state == {"file_hashes": {}}

    def test_load_hash_state_valid_file(self, tmp_path: Path):
        """Should load valid hash state."""
        state_dir = tmp_path / ".mimir"
        state_dir.mkdir()
        state_file = state_dir / "index_state.json"
        state_data = {"file_hashes": {"/path/a.py": "hash123"}}
        state_file.write_text(json.dumps(state_data))

        state = load_hash_state(tmp_path)
        assert state["file_hashes"]["/path/a.py"] == "hash123"

    def test_save_hash_state_creates_file(self, tmp_path: Path):
        """Should create hash state file."""
        state = {"file_hashes": {"/path/a.py": "hash123"}}

        save_hash_state(tmp_path, state)

        state_file = tmp_path / ".mimir" / "index_state.json"
        assert state_file.exists()

    def test_save_hash_state_adds_timestamp(self, tmp_path: Path):
        """Should add last_updated timestamp."""
        state = {"file_hashes": {}}

        save_hash_state(tmp_path, state)

        loaded = json.loads((tmp_path / ".mimir" / "index_state.json").read_text())
        assert "last_updated" in loaded

    def test_hash_state_roundtrip(self, tmp_path: Path):
        """Should preserve data through save/load cycle."""
        original = {
            "file_hashes": {
                "/path/a.py": "hash1",
                "/path/b.py": "hash2",
            }
        }

        save_hash_state(tmp_path, original)
        loaded = load_hash_state(tmp_path)

        assert loaded["file_hashes"] == original["file_hashes"]


# ─── Detect Changed Files Tests ──────────────────────────────────────────────


class TestDetectChangedFiles:
    """Tests for detect_changed_files function."""

    def test_detects_added_files(self, tmp_path: Path):
        """Should detect newly added files."""
        watched_dir = tmp_path / "docs"
        watched_dir.mkdir()

        # Create a new file
        new_file = watched_dir / "new.md"
        new_file.write_text("# New Doc")

        changes = detect_changed_files(tmp_path, [watched_dir], update_state=False)

        assert len(changes["added"]) == 1
        assert new_file.resolve() in [f.resolve() for f in changes["added"]]
        assert len(changes["modified"]) == 0
        assert len(changes["deleted"]) == 0

    def test_detects_deleted_files(self, tmp_path: Path):
        """Should detect deleted files."""
        watched_dir = tmp_path / "docs"
        watched_dir.mkdir()

        # Create initial state
        old_file = watched_dir / "old.md"
        old_file.write_text("# Old Doc")

        # Save initial state
        detect_changed_files(tmp_path, [watched_dir], update_state=True)

        # Delete the file
        old_file.unlink()

        # Detect changes
        changes = detect_changed_files(tmp_path, [watched_dir], update_state=False)

        assert len(changes["deleted"]) == 1

    def test_detects_modified_files(self, tmp_path: Path):
        """Should detect modified files."""
        watched_dir = tmp_path / "docs"
        watched_dir.mkdir()

        # Create initial file
        mod_file = watched_dir / "mod.md"
        mod_file.write_text("Original content")

        # Save initial state
        detect_changed_files(tmp_path, [watched_dir], update_state=True)

        # Modify the file
        time.sleep(0.1)  # Ensure different timestamp
        mod_file.write_text("Modified content")

        # Detect changes
        changes = detect_changed_files(tmp_path, [watched_dir], update_state=False)

        assert len(changes["modified"]) == 1

    def test_excludes_patterns(self, tmp_path: Path):
        """Should exclude files matching EXCLUDE_PATTERNS."""
        watched_dir = tmp_path / "project"
        watched_dir.mkdir()

        # Create files that should be excluded
        (watched_dir / ".git").mkdir()
        (watched_dir / ".git" / "config").write_text("git config")
        (watched_dir / "node_modules").mkdir()
        (watched_dir / "node_modules" / "package.json").write_text("{}")
        (watched_dir / "image.png").write_bytes(b"fake image")

        # Create a file that should be included
        (watched_dir / "readme.md").write_text("# README")

        changes = detect_changed_files(tmp_path, [watched_dir], update_state=False)

        added_names = [f.name for f in changes["added"]]
        assert "readme.md" in added_names
        assert "config" not in added_names
        assert "package.json" not in added_names
        assert "image.png" not in added_names

    def test_handles_nonexistent_directory(self, tmp_path: Path):
        """Should handle nonexistent watched directories."""
        nonexistent = tmp_path / "nonexistent"

        changes = detect_changed_files(tmp_path, [nonexistent], update_state=False)

        assert changes["added"] == []
        assert changes["modified"] == []
        assert changes["deleted"] == []

    def test_update_state_parameter(self, tmp_path: Path):
        """Should update state when update_state=True."""
        watched_dir = tmp_path / "docs"
        watched_dir.mkdir()
        (watched_dir / "doc.md").write_text("content")

        # First call with update_state=True
        detect_changed_files(tmp_path, [watched_dir], update_state=True)

        # Second call should show no changes
        changes = detect_changed_files(tmp_path, [watched_dir], update_state=False)

        assert len(changes["added"]) == 0


# ─── Integration Tests ──────────────────────────────────────────────────────


class TestIndexingIntegration:
    """Integration tests for indexing workflow."""

    def test_full_workflow(self, tmp_path: Path):
        """Test complete indexing workflow."""
        knowledge_dir = tmp_path / ".knowledge"
        knowledge_dir.mkdir()
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create some files
        (docs_dir / "a.md").write_text("# Doc A")
        (docs_dir / "b.md").write_text("# Doc B")

        # Add to manifest
        add_to_manifest(
            knowledge_dir,
            docs_dir,
            [str(docs_dir / "a.md"), str(docs_dir / "b.md")],
            2,
        )

        # Verify manifest
        manifest = load_manifest(knowledge_dir)
        assert manifest["total_documents"] == 2

        # Add another file incrementally
        (docs_dir / "c.md").write_text("# Doc C")
        add_to_manifest(
            knowledge_dir,
            docs_dir,
            [str(docs_dir / "c.md")],
            1,
            is_incremental=True,
        )

        manifest = load_manifest(knowledge_dir)
        assert manifest["total_documents"] == 3

        # Remove a file
        remove_from_manifest(knowledge_dir, docs_dir / "a.md")

        manifest = load_manifest(knowledge_dir)
        assert manifest["total_documents"] == 2

        # Clear manifest
        clear_manifest(knowledge_dir)

        manifest = load_manifest(knowledge_dir)
        assert manifest["total_documents"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
