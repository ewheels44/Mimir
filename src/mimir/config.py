"""Unified configuration for Mimir.

Single source of truth for ALL settings. Every entry point (MCP server,
LangGraph CLI, init script, OpenSpace bridge) should use this instead of
rolling its own config detection.

Resolution order (highest priority first):
    1. Environment variables
    2. .mimir/config.json (project-level)
    3. Defaults

Usage:
    from src.mimir.config import MimirConfig

    # Auto-detect everything
    config = MimirConfig.load()

    # Override specific values
    config = MimirConfig.load(project_root=Path("/my/project"))

    # Access settings
    config.api_key          # resolved from env or auth file
    config.embedding_model  # from config.json or default
    config.llm_model        # from config.json or default
    config.docs_dir         # from config.json or default
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Defaults ────────────────────────────────────────────────────────────────

DEFAULTS = {
    # Models
    "embedding_model": "text-embedding-3-small",
    "llm_model": "google/gemini-3.1-flash-lite-preview",
    # Directories (relative to project_root)
    "docs_dir": "docs",
    "knowledge_dir": ".knowledge/llamaindex",
    # SDK cache
    "sdk_cache_ttl_days": 7,
    # Bridge
    "bridge_enabled": True,
    "bridge_cache_maxsize": 128,
    "bridge_cache_ttl_seconds": 600,
    "bridge_circuit_breaker_threshold": 3,
    "bridge_circuit_breaker_reset_seconds": 60,
    "bridge_search_timeout_seconds": 30.0,
    "bridge_max_context_tokens": 2500,
    "bridge_top_k": 5,
    "bridge_freshness_decay_hours": 168.0,
    # API
    "api_base_url": "https://openrouter.ai/api/v1",
}

# Project root detection markers (ordered by reliability)
_PROJECT_MARKERS = [
    "opencode.json",
    ".opencode",
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
]

# Auth file locations to check (in order)
_AUTH_FILE_PATHS = [
    Path.home() / ".local" / "share" / "opencode" / "auth.json",
    Path.home() / ".config" / "opencode" / "auth.json",
]


# ─── Config class ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MimirConfig:
    """Immutable Mimir configuration. All settings in one place.

    Create via MimirConfig.load() — don't construct directly unless
    you know what you're doing.
    """

    # Core
    project_root: Path
    mimir_root: Path  # Where Mimir itself is installed

    # API
    api_key: str
    api_base: str

    # Models
    embedding_model: str
    llm_model: str

    # Directories (absolute paths)
    docs_dir: Path
    knowledge_dir: Path
    code_dirs: tuple[Path, ...] = ()
    shared_indexes: dict[str, Path] = field(default_factory=dict)

    # SDK cache
    sdk_cache_ttl_days: int = 7

    # Bridge settings
    bridge_enabled: bool = True
    bridge_cache_maxsize: int = 128
    bridge_cache_ttl_seconds: int = 600
    bridge_circuit_breaker_threshold: int = 3
    bridge_circuit_breaker_reset_seconds: int = 60
    bridge_search_timeout_seconds: float = 30.0
    bridge_max_context_tokens: int = 2500
    bridge_top_k: int = 5
    bridge_freshness_decay_hours: float = 168.0

    # Metadata
    _config_source: str = ""  # For debugging: where did config come from?

    @classmethod
    def load(
        cls,
        project_root: Optional[Path] = None,
        mimir_root: Optional[Path] = None,
    ) -> MimirConfig:
        """Load configuration from all sources with proper precedence.

        Args:
            project_root: Project root directory. Auto-detected if None.
            mimir_root: Where Mimir is installed. Auto-detected if None.
        """
        # Detect roots
        actual_project_root = project_root or _detect_project_root()
        actual_mimir_root = mimir_root or _detect_mimir_root()

        # Load project config file
        file_config = _load_config_file(actual_project_root)

        # Resolve API key
        api_key, api_base = _resolve_api_key()
        if api_key and not api_base:
            api_base = _env_or_default("OPENAI_BASE_URL", "api_base_url")

        # Resolve directories
        docs_dir = _resolve_dir(
            actual_project_root,
            env_var="DOCS_DIR",
            config_key="docs_dir",
            default_rel=DEFAULTS["docs_dir"],
            file_config=file_config,
        )
        knowledge_dir = _resolve_dir(
            actual_project_root,
            env_var="KNOWLEDGE_DIR",
            config_key="knowledge_dir",
            default_rel=DEFAULTS["knowledge_dir"],
            file_config=file_config,
        )

        # Code dirs
        code_dirs = _resolve_code_dirs(actual_project_root, file_config)

        # Shared indexes
        raw_shared = file_config.get("shared_indexes", {})
        shared_indexes = {}
        for name, path_str in raw_shared.items():
            path = Path(path_str).expanduser()
            shared_indexes[name] = path

        # Models
        embedding_model = (
            file_config.get("embedding_model")
            or os.environ.get("EMBEDDING_MODEL")
            or DEFAULTS["embedding_model"]
        )
        llm_model = (
            file_config.get("llm_model")
            or os.environ.get("MIMIR_LLM_MODEL")
            or DEFAULTS["llm_model"]
        )

        # SDK cache
        sdk_cache_ttl = int(
            os.environ.get("MIMIR_SDK_CACHE_TTL")
            or file_config.get("sdk_cache_ttl_days", DEFAULTS["sdk_cache_ttl_days"])
        )

        # Bridge settings
        bridge = file_config.get("bridge", {})

        return cls(
            project_root=actual_project_root,
            mimir_root=actual_mimir_root,
            api_key=api_key,
            api_base=api_base or DEFAULTS["api_base_url"],
            embedding_model=embedding_model,
            llm_model=llm_model,
            docs_dir=docs_dir,
            knowledge_dir=knowledge_dir,
            code_dirs=tuple(code_dirs),
            shared_indexes=shared_indexes,
            sdk_cache_ttl_days=sdk_cache_ttl,
            bridge_enabled=_env_bool(
                "MIMIR_OPENSPACE_ENABLED", bridge.get("enabled", True)
            ),
            bridge_cache_maxsize=int(
                os.environ.get("MIMIR_BRIDGE_CACHE_SIZE")
                or bridge.get("cache_maxsize", DEFAULTS["bridge_cache_maxsize"])
            ),
            bridge_cache_ttl_seconds=int(
                os.environ.get("MIMIR_BRIDGE_CACHE_TTL")
                or bridge.get("cache_ttl_seconds", DEFAULTS["bridge_cache_ttl_seconds"])
            ),
            bridge_circuit_breaker_threshold=int(
                os.environ.get("MIMIR_BRIDGE_CB_THRESHOLD")
                or bridge.get(
                    "circuit_breaker_threshold",
                    DEFAULTS["bridge_circuit_breaker_threshold"],
                )
            ),
            bridge_circuit_breaker_reset_seconds=int(
                os.environ.get("MIMIR_BRIDGE_CB_RESET")
                or bridge.get(
                    "circuit_breaker_reset_seconds",
                    DEFAULTS["bridge_circuit_breaker_reset_seconds"],
                )
            ),
            bridge_search_timeout_seconds=float(
                os.environ.get("MIMIR_BRIDGE_TIMEOUT")
                or bridge.get(
                    "search_timeout_seconds",
                    DEFAULTS["bridge_search_timeout_seconds"],
                )
            ),
            bridge_max_context_tokens=int(
                os.environ.get("MIMIR_BRIDGE_MAX_TOKENS")
                or bridge.get(
                    "max_context_tokens", DEFAULTS["bridge_max_context_tokens"]
                )
            ),
            bridge_top_k=int(
                os.environ.get("MIMIR_BRIDGE_TOP_K")
                or bridge.get("top_k", DEFAULTS["bridge_top_k"])
            ),
            bridge_freshness_decay_hours=float(
                bridge.get(
                    "freshness_decay_hours", DEFAULTS["bridge_freshness_decay_hours"]
                )
            ),
            _config_source=_describe_sources(file_config),
        )

    def to_dict(self) -> dict:
        """Serialize config for logging/debugging (excludes secrets)."""
        return {
            "project_root": str(self.project_root),
            "mimir_root": str(self.mimir_root),
            "api_key": f"***{self.api_key[-4:]}" if self.api_key else "(none)",
            "api_base": self.api_base,
            "embedding_model": self.embedding_model,
            "llm_model": self.llm_model,
            "docs_dir": str(self.docs_dir),
            "knowledge_dir": str(self.knowledge_dir),
            "code_dirs": [str(d) for d in self.code_dirs],
            "shared_indexes": {k: str(v) for k, v in self.shared_indexes.items()},
            "sdk_cache_ttl_days": self.sdk_cache_ttl_days,
            "bridge_enabled": self.bridge_enabled,
            "bridge_top_k": self.bridge_top_k,
            "_config_source": self._config_source,
        }

    def validate(self) -> list[str]:
        """Check for common configuration problems.

        Returns list of warning messages (empty = all good).
        """
        warnings = []

        if not self.api_key:
            warnings.append(
                "No API key found. Set OPENROUTER_API_KEY or run: opencode auth openrouter"
            )

        if not self.project_root.exists():
            warnings.append(f"Project root does not exist: {self.project_root}")

        if not self.docs_dir.exists():
            warnings.append(f"Docs directory does not exist: {self.docs_dir}")

        if not self.knowledge_dir.exists():
            warnings.append(
                f"Knowledge directory does not exist: {self.knowledge_dir}. "
                "Run indexing first: python mimir-index.py"
            )

        if not (self.knowledge_dir / "index_store.json").exists():
            warnings.append(
                "No index found in knowledge directory. "
                "Run indexing first: python mimir-index.py"
            )

        return warnings


# ─── Private helpers ─────────────────────────────────────────────────────────


def _detect_project_root(
    cwd: Optional[Path] = None,
    env_vars: Optional[list[str]] = None,
) -> Path:
    """Detect project root by walking up from cwd looking for marker files."""
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
        for marker in _PROJECT_MARKERS:
            if (current / marker).exists():
                return current
        current = current.parent

    return start


def _detect_mimir_root() -> Path:
    """Detect where Mimir itself is installed.

    Checks:
    1. MIMIR_ROOT env var
    2. Location of this file (src/mimir/config.py → project root)
    3. ~/Documents/Mimir (legacy fallback)
    """
    if env := os.environ.get("MIMIR_ROOT"):
        p = Path(env).resolve()
        if p.exists():
            return p

    # This file is at {mimir_root}/src/mimir/config.py
    this_file = Path(__file__).resolve()
    candidate = this_file.parent.parent.parent
    if (candidate / "mcp_server_llamaindex.py").exists():
        return candidate

    # Legacy fallback
    legacy = Path.home() / "Documents" / "Mimir"
    if legacy.exists():
        return legacy

    return candidate


def _load_config_file(project_root: Path) -> dict:
    """Load .mimir/config.json if it exists."""
    config_path = project_root / ".mimir" / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load config file %s: %s", config_path, e)
    return {}


def _resolve_api_key() -> tuple[str, Optional[str]]:
    """Resolve API key from env vars or auth file.

    Returns (api_key, api_base) tuple.
    """
    # Check env vars first
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "OPENAI_API_KEY", ""
    )
    if api_key:
        return api_key, os.environ.get("OPENAI_BASE_URL")

    # Try auth files
    for auth_path in _AUTH_FILE_PATHS:
        if auth_path.exists():
            try:
                auth_data = json.loads(auth_path.read_text())
                if openrouter := auth_data.get("openrouter"):
                    key = openrouter.get("key", "")
                    if key:
                        return key, "https://openrouter.ai/api/v1"
            except (json.JSONDecodeError, KeyError):
                continue

    return "", None


def _resolve_dir(
    project_root: Path,
    env_var: str,
    config_key: str,
    default_rel: str,
    file_config: dict,
) -> Path:
    """Resolve a directory path from config sources.

    Checks: env var → config file → default (relative to project_root).
    """
    raw = os.environ.get(env_var) or file_config.get(config_key) or default_rel
    path = Path(raw)
    if not path.is_absolute():
        path = project_root / path
    return path


def _resolve_code_dirs(project_root: Path, file_config: dict) -> list[Path]:
    """Resolve code directories from config sources."""
    # Config file takes precedence
    if "code_dirs" in file_config:
        return [Path(d) for d in file_config["code_dirs"]]

    # Env var (comma-separated)
    if env := os.environ.get("CODE_DIRS", ""):
        return [Path(d.strip()) for d in env.split(",") if d.strip()]

    return []


def _env_or_default(env_var: str, default_key: str) -> str:
    """Get value from env var or fall back to DEFAULTS."""
    return os.environ.get(env_var) or DEFAULTS.get(default_key, "")


def _env_bool(env_var: str, default: bool) -> bool:
    """Parse a boolean from env var with fallback."""
    val = os.environ.get(env_var)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


def _describe_sources(file_config: dict) -> str:
    """Describe where config values came from (for debugging)."""
    sources = []
    if file_config:
        sources.append(".mimir/config.json")
    env_vars = [
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "EMBEDDING_MODEL",
        "MIMIR_LLM_MODEL",
        "PROJECT_ROOT",
        "MIMIR_ROOT",
    ]
    active_env = [v for v in env_vars if os.environ.get(v)]
    if active_env:
        sources.append(f"env({', '.join(active_env)})")
    sources.append("defaults")
    return " → ".join(sources)


# ─── Convenience ─────────────────────────────────────────────────────────────

# Module-level singleton for simple use cases
_config_instance: Optional[MimirConfig] = None


def get_config(**kwargs) -> MimirConfig:
    """Get or create the singleton config instance.

    First call loads config. Subsequent calls return cached instance.
    Pass kwargs to override on first call.
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = MimirConfig.load(**kwargs)
    return _config_instance


def reset_config() -> None:
    """Reset the singleton (useful for testing)."""
    global _config_instance
    _config_instance = None
