#!/usr/bin/env python3
"""Tests for the shared utils module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))

from src.mimir.utils import (
    EXCLUDE_PATTERNS,
    PROJECT_MARKERS,
    detect_project_root,
    resolve_api_key,
    should_exclude,
)


# ─── Constants Tests ─────────────────────────────────────────────────────────


class TestConstants:
    """Test that module constants are properly defined."""

    def test_exclude_patterns_is_non_empty_list(self):
        """EXCLUDE_PATTERNS should be a non-empty list."""
        assert isinstance(EXCLUDE_PATTERNS, list)
        assert len(EXCLUDE_PATTERNS) > 0

    def test_exclude_patterns_contains_common_entries(self):
        """EXCLUDE_PATTERNS should contain common exclusions."""
        assert ".git" in EXCLUDE_PATTERNS
        assert "node_modules" in EXCLUDE_PATTERNS
        assert "__pycache__" in EXCLUDE_PATTERNS

    def test_project_markers_is_non_empty_list(self):
        """PROJECT_MARKERS should be a non-empty list."""
        assert isinstance(PROJECT_MARKERS, list)
        assert len(PROJECT_MARKERS) > 0

    def test_project_markers_contains_common_markers(self):
        """PROJECT_MARKERS should contain common project markers."""
        assert ".git" in PROJECT_MARKERS
        assert "pyproject.toml" in PROJECT_MARKERS


# ─── detect_project_root Tests ───────────────────────────────────────────────


class TestDetectProjectRoot:
    """Tests for detect_project_root function."""

    def test_detects_root_from_marker_file(self, tmp_path: Path):
        """Should find project root when marker file exists."""
        # Arrange
        project_root = tmp_path / "myproject"
        project_root.mkdir()
        (project_root / ".git").mkdir()
        sub_dir = project_root / "src" / "module"
        sub_dir.mkdir(parents=True)

        # Act
        result = detect_project_root(cwd=sub_dir)

        # Assert
        assert result.resolve() == project_root.resolve()

    def test_respects_env_var_override(self, tmp_path: Path, monkeypatch):
        """Should use PROJECT_ROOT env var when set and path exists."""
        # Arrange
        env_root = tmp_path / "env_project"
        env_root.mkdir()
        monkeypatch.setenv("PROJECT_ROOT", str(env_root))

        other_dir = tmp_path / "other_project"
        other_dir.mkdir()
        (other_dir / ".git").mkdir()

        # Act
        result = detect_project_root(cwd=other_dir)

        # Assert
        assert result.resolve() == env_root.resolve()

    def test_ignores_nonexistent_env_var_path(self, tmp_path: Path, monkeypatch):
        """Should fall back to marker detection if env var path doesn't exist."""
        # Arrange
        project_root = tmp_path / "real_project"
        project_root.mkdir()
        (project_root / "pyproject.toml").write_text("# project")
        sub_dir = project_root / "src"
        sub_dir.mkdir()

        monkeypatch.setenv("PROJECT_ROOT", "/nonexistent/path")

        # Act
        result = detect_project_root(cwd=sub_dir)

        # Assert
        assert result.resolve() == project_root.resolve()

    def test_fallback_to_cwd_when_no_markers(self, tmp_path: Path):
        """Should return cwd when no markers found."""
        # Arrange
        isolated_dir = tmp_path / "isolated"
        isolated_dir.mkdir()

        # Act
        result = detect_project_root(cwd=isolated_dir)

        # Assert
        assert result.resolve() == isolated_dir.resolve()

    def test_walks_up_to_find_marker(self, tmp_path: Path):
        """Should walk up directory tree to find marker."""
        # Arrange
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "opencode.json").write_text("{}")
        deep_dir = project_root / "a" / "b" / "c" / "d"
        deep_dir.mkdir(parents=True)

        # Act
        result = detect_project_root(cwd=deep_dir)

        # Assert
        assert result.resolve() == project_root.resolve()

    def test_custom_env_vars_parameter(self, tmp_path: Path, monkeypatch):
        """Should respect custom env_vars list."""
        # Arrange
        custom_root = tmp_path / "custom_root"
        custom_root.mkdir()
        monkeypatch.setenv("CUSTOM_VAR", str(custom_root))

        # Act
        result = detect_project_root(cwd=tmp_path, env_vars=["CUSTOM_VAR"])

        # Assert
        assert result.resolve() == custom_root.resolve()

    def test_default_cwd_is_current_directory(self):
        """Should use Path.cwd() when cwd is None."""
        # Act
        result = detect_project_root(cwd=None)

        # Assert - should return a valid Path
        assert isinstance(result, Path)


# ─── should_exclude Tests ─────────────────────────────────────────────────────


class TestShouldExclude:
    """Tests for should_exclude function."""

    def test_excludes_git_directory(self, tmp_path: Path):
        """Should exclude files in .git directory."""
        # Arrange
        git_file = tmp_path / ".git" / "objects" / "abc123"

        # Act
        result = should_exclude(git_file)

        # Assert
        assert result is True

    def test_excludes_node_modules_directory(self, tmp_path: Path):
        """Should exclude files in node_modules directory."""
        # Arrange
        node_file = tmp_path / "node_modules" / "package" / "index.js"

        # Act
        result = should_exclude(node_file)

        # Assert
        assert result is True

    def test_excludes_pyc_files(self, tmp_path: Path):
        """Should exclude .pyc files."""
        # Arrange
        pyc_file = tmp_path / "module" / "__pycache__" / "module.cpython-311.pyc"

        # Act
        result = should_exclude(pyc_file)

        # Assert
        assert result is True

    def test_excludes_png_files(self, tmp_path: Path):
        """Should exclude .png files."""
        # Arrange
        png_file = tmp_path / "assets" / "logo.png"

        # Act
        result = should_exclude(png_file)

        # Assert
        assert result is True

    def test_excludes_jpg_files(self, tmp_path: Path):
        """Should exclude .jpg files."""
        # Arrange
        jpg_file = tmp_path / "images" / "photo.jpg"

        # Act
        result = should_exclude(jpg_file)

        # Assert
        assert result is True

    def test_excludes_pdf_files(self, tmp_path: Path):
        """Should exclude .pdf files."""
        # Arrange
        pdf_file = tmp_path / "docs" / "manual.pdf"

        # Act
        result = should_exclude(pdf_file)

        # Assert
        assert result is True

    def test_allows_python_files(self, tmp_path: Path):
        """Should not exclude .py files."""
        # Arrange
        py_file = tmp_path / "src" / "module.py"

        # Act
        result = should_exclude(py_file)

        # Assert
        assert result is False

    def test_allows_markdown_files(self, tmp_path: Path):
        """Should not exclude .md files."""
        # Arrange
        md_file = tmp_path / "docs" / "README.md"

        # Act
        result = should_exclude(md_file)

        # Assert
        assert result is False

    def test_allows_json_files(self, tmp_path: Path):
        """Should not exclude .json files (except package-lock.json)."""
        # Arrange
        json_file = tmp_path / "config" / "settings.json"

        # Act
        result = should_exclude(json_file)

        # Assert
        assert result is False

    def test_excludes_package_lock_json(self, tmp_path: Path):
        """Should exclude package-lock.json files."""
        # Arrange
        lock_file = tmp_path / "package-lock.json"

        # Act
        result = should_exclude(lock_file)

        # Assert
        assert result is True

    def test_excludes_uv_lock(self, tmp_path: Path):
        """Should exclude uv.lock files."""
        # Arrange
        lock_file = tmp_path / "uv.lock"

        # Act
        result = should_exclude(lock_file)

        # Assert
        assert result is True

    def test_excludes_minified_js(self, tmp_path: Path):
        """Should exclude .min.js files."""
        # Arrange
        min_file = tmp_path / "dist" / "bundle.min.js"

        # Act
        result = should_exclude(min_file)

        # Assert
        assert result is True

    def test_excludes_ds_store(self, tmp_path: Path):
        """Should exclude .DS_Store files."""
        # Arrange
        ds_file = tmp_path / ".DS_Store"

        # Act
        result = should_exclude(ds_file)

        # Assert
        assert result is True


# ─── resolve_api_key Tests ───────────────────────────────────────────────────


class TestResolveApiKey:
    """Tests for resolve_api_key function."""

    def test_returns_openrouter_key_from_env(self, monkeypatch):
        """Should return OPENROUTER_API_KEY when set."""
        # Arrange
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test123")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Act
        key, base = resolve_api_key()

        # Assert
        assert key == "sk-or-test123"
        assert base == "https://openrouter.ai/api/v1"

    def test_returns_openai_key_from_env(self, monkeypatch):
        """Should return OPENAI_API_KEY when OPENROUTER_API_KEY not set."""
        # Arrange
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test456")

        # Act
        key, base = resolve_api_key()

        # Assert
        assert key == "sk-oai-test456"

    def test_openrouter_takes_precedence(self, monkeypatch):
        """OPENROUTER_API_KEY should take precedence over OPENAI_API_KEY."""
        # Arrange
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-first")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-second")

        # Act
        key, _ = resolve_api_key()

        # Assert
        assert key == "sk-or-first"

    def test_custom_base_url_from_env(self, monkeypatch):
        """Should use OPENAI_BASE_URL when set."""
        # Arrange
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api/v1")

        # Act
        key, base = resolve_api_key()

        # Assert
        assert base == "https://custom.api/v1"

    def test_returns_empty_string_when_no_key(self, monkeypatch, tmp_path: Path):
        """Should return empty string when no key found."""
        # Arrange
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock the auth file path to a non-existent location
        with patch("src.mimir.utils.Path.home", return_value=tmp_path):
            # Act
            key, base = resolve_api_key()

        # Assert
        assert key == ""
        assert base is None

    def test_reads_from_auth_file(self, monkeypatch, tmp_path: Path):
        """Should read key from opencode auth file."""
        # Arrange
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Create mock auth file
        auth_dir = tmp_path / ".local" / "share" / "opencode"
        auth_dir.mkdir(parents=True)
        auth_file = auth_dir / "auth.json"
        auth_file.write_text('{"openrouter": {"key": "sk-file-key"}}')

        with patch("src.mimir.utils.Path.home", return_value=tmp_path):
            # Act
            key, base = resolve_api_key()

        # Assert
        assert key == "sk-file-key"
        assert base == "https://openrouter.ai/api/v1"

    def test_handles_malformed_auth_file(self, monkeypatch, tmp_path: Path):
        """Should handle malformed auth file gracefully."""
        # Arrange
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Create malformed auth file
        auth_dir = tmp_path / ".local" / "share" / "opencode"
        auth_dir.mkdir(parents=True)
        auth_file = auth_dir / "auth.json"
        auth_file.write_text("{ invalid json }")

        with patch("src.mimir.utils.Path.home", return_value=tmp_path):
            # Act
            key, base = resolve_api_key()

        # Assert
        assert key == ""
        assert base is None

    def test_handles_missing_auth_file(self, monkeypatch, tmp_path: Path):
        """Should handle missing auth file gracefully."""
        # Arrange
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # No auth file created
        with patch("src.mimir.utils.Path.home", return_value=tmp_path):
            # Act
            key, base = resolve_api_key()

        # Assert
        assert key == ""
        assert base is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
