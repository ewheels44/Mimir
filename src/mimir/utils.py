"""Shared utility functions for Mimir modules.

Consolidates common patterns that were previously duplicated across:
- mcp_server_llamaindex.py
- indexing.py
- knowledge_graph.py
- metrics.py
- sdk_cache.py
"""

from pathlib import Path
from typing import Optional


# Project root detection markers (ordered by reliability)
PROJECT_MARKERS = [
    ".opencode",
    "opencode.json",
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
]


def detect_project_root(
    cwd: Optional[Path] = None,
    env_vars: Optional[list[str]] = None,
) -> Path:
    """Detect project root by walking up from cwd looking for marker files.

    Args:
        cwd: Starting directory. Defaults to Path.cwd().
        env_vars: Environment variables to check first (e.g. ["PROJECT_ROOT", "WORKSPACE_FOLDER"]).
                  Defaults to ["PROJECT_ROOT", "WORKSPACE_FOLDER", "VSCODE_CWD"].

    Returns:
        Path to project root, or cwd if no markers found.
    """
    import os

    if env_vars is None:
        env_vars = ["PROJECT_ROOT", "WORKSPACE_FOLDER", "VSCODE_CWD"]

    # Check env vars first
    for var in env_vars:
        if path := os.environ.get(var):
            resolved = Path(path).resolve()
            if resolved.exists():
                return resolved

    # Walk up from cwd
    start = (cwd or Path.cwd()).resolve()
    current = start
    while current != current.parent:
        for marker in PROJECT_MARKERS:
            if (current / marker).exists():
                return current
        current = current.parent

    return start


# File exclusion patterns for indexing
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".github",
    ".gitignore",
    "node_modules",
    "target",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "out",
    ".venv",
    "venv",
    ".env",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp4",
    "*.webm",
    "*.mov",
    "*.mp3",
    "*.wav",
    "*.ogg",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.rar",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.tflite",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "uv.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    ".DS_Store",
    "Thumbs.db",
    "test-results",
    "playwright-report",
    "blob-report",
]


def should_exclude(
    file_path: Path, custom_patterns: Optional[list[str]] = None
) -> bool:
    """Check if a file path should be excluded from indexing.

    Checks both directory components and filename patterns.
    Merges default EXCLUDE_PATTERNS with custom patterns.

    Args:
        file_path: Path to check
        custom_patterns: Additional patterns to exclude (optional)

    Returns:
        True if file should be excluded, False otherwise
    """
    import fnmatch

    # Merge default and custom patterns
    all_patterns = EXCLUDE_PATTERNS[:]
    if custom_patterns:
        all_patterns.extend(custom_patterns)

    path_str = str(file_path)
    name = file_path.name

    for pattern in all_patterns:
        # Check if pattern appears in path (for directory patterns)
        if "*" not in pattern and pattern in path_str:
            return True
        # Check glob pattern against filename
        if "*" in pattern and fnmatch.fnmatch(name, pattern):
            return True

    return False


def resolve_api_key() -> tuple[str, Optional[str]]:
    """Resolve API key and base URL from environment or auth file.

    Checks in order:
    1. OPENROUTER_API_KEY env var
    2. OPENAI_API_KEY env var
    3. opencode auth file at ~/.local/share/opencode/auth.json

    Returns:
        Tuple of (api_key, api_base_url). Empty string if no key found.
    """
    import os
    import json

    # Check env vars first
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "OPENAI_API_KEY", ""
    )
    if api_key:
        return api_key, os.environ.get(
            "OPENAI_BASE_URL", "https://openrouter.ai/api/v1"
        )

    # Fall back to opencode auth file
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if auth_path.exists():
        try:
            auth_data = json.loads(auth_path.read_text())
            if openrouter := auth_data.get("openrouter"):
                key = openrouter.get("key", "")
                if key:
                    return key, "https://openrouter.ai/api/v1"
        except (json.JSONDecodeError, KeyError):
            pass

    return "", None
