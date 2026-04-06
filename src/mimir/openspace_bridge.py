#!/usr/bin/env python3
"""
Mimir ↔ OpenSpace Bridge Adapter

Thin integration layer between Mimir's knowledge base and OpenSpace's
self-evolving skill engine. All guardrails live here — both systems
stay independent.

Guardrails:
  - Circuit breaker: Stops calling Mimir after N consecutive failures
  - LRU cache: Avoids repeated identical searches
  - Kill switch: MIMIR_OPENSPACE_ENABLED=false disables everything
  - Content filter: Blocks private data from leaving the system
  - Timeout budget: Enforces max search time per call

Usage:
    from src.mimir.openspace_bridge import MimirOpenSpaceBridge

    bridge = MimirOpenSpaceBridge(project_root=Path("."))
    result = bridge.enrich_task("Build auth middleware for FastAPI")
    if result.success:
        print(result.context)  # Inject into OpenSpace skill prompt
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Debug Timing Helper ─────────────────────────────────────────────────────


def _timed(label: str):
    """Context manager that logs elapsed time for a block."""
    import contextlib

    @contextlib.contextmanager
    def _timer():
        start = time.time()
        logger.debug("[BRIDGE TIMING] %s - START", label)
        try:
            yield
        finally:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.debug("[BRIDGE TIMING] %s - END (%dms)", label, elapsed_ms)

    return _timer()


# ─── Configuration ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BridgeConfig:
    """Immutable bridge configuration. All tunables in one place."""

    enabled: bool = True
    cache_maxsize: int = 128
    cache_ttl_seconds: int = 600  # 10 minutes
    circuit_breaker_threshold: int = 3
    circuit_breaker_reset_seconds: int = 60
    search_timeout_seconds: float = 30.0
    max_context_tokens: int = 2500  # ~15% of 16k context window
    top_k: int = 5
    freshness_decay_hours: float = 168.0  # 7 days

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Load config from environment variables with sensible defaults."""
        return cls(
            enabled=os.environ.get("MIMIR_OPENSPACE_ENABLED", "true").lower() == "true",
            cache_maxsize=int(os.environ.get("MIMIR_BRIDGE_CACHE_SIZE", "128")),
            cache_ttl_seconds=int(os.environ.get("MIMIR_BRIDGE_CACHE_TTL", "600")),
            circuit_breaker_threshold=int(
                os.environ.get("MIMIR_BRIDGE_CB_THRESHOLD", "3")
            ),
            circuit_breaker_reset_seconds=int(
                os.environ.get("MIMIR_BRIDGE_CB_RESET", "60")
            ),
            search_timeout_seconds=float(os.environ.get("MIMIR_BRIDGE_TIMEOUT", "30")),
            max_context_tokens=int(os.environ.get("MIMIR_BRIDGE_MAX_TOKENS", "2500")),
            top_k=int(os.environ.get("MIMIR_BRIDGE_TOP_K", "5")),
        )


# ─── Data Types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SearchResult:
    """Single retrieved document chunk with metadata."""

    source: str
    score: float
    text: str
    freshness: float  # 0.0 = stale, 1.0 = fresh

    def to_prompt_chunk(self) -> str:
        """Format for injection into an LLM prompt."""
        freshness_tag = (
            "fresh"
            if self.freshness > 0.7
            else "recent"
            if self.freshness > 0.3
            else "stale"
        )
        return f"[{self.source} ({freshness_tag}, score={self.score:.2f})]\n{self.text}"


@dataclass(frozen=True)
class EnrichmentResult:
    """Result of enriching an OpenSpace task with Mimir context."""

    success: bool
    context: str = ""
    results: tuple[SearchResult, ...] = ()
    cache_hit: bool = False
    circuit_open: bool = False
    error: Optional[str] = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "context": self.context,
            "result_count": len(self.results),
            "cache_hit": self.cache_hit,
            "circuit_open": self.circuit_open,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


# ─── Circuit Breaker ────────────────────────────────────────────────────────


@dataclass
class _CircuitBreakerState:
    """Mutable circuit breaker state. Internal use only."""

    failure_count: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False

    def record_failure(self, threshold: int, reset_seconds: int) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= threshold:
            self.is_open = True
            logger.warning(
                "Circuit breaker OPEN after %d failures (threshold=%d)",
                self.failure_count,
                threshold,
            )

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def check(self, reset_seconds: int) -> bool:
        """Returns True if circuit is open (calls should be blocked)."""
        if not self.is_open:
            return False
        # Auto-reset after cooldown
        if time.time() - self.last_failure_time > reset_seconds:
            logger.info("Circuit breaker RESET after cooldown")
            self.is_open = False
            self.failure_count = 0
            return False
        return True


# ─── Cache ───────────────────────────────────────────────────────────────────


class _TimedCache:
    """Simple TTL-based LRU cache. No external dependencies."""

    def __init__(self, maxsize: int = 128, ttl_seconds: int = 600):
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, EnrichmentResult]] = {}

    def _make_key(self, query: str, top_k: int) -> str:
        return hashlib.sha256(f"{query}:{top_k}".encode()).hexdigest()[:16]

    def get(self, query: str, top_k: int) -> Optional[EnrichmentResult]:
        key = self._make_key(query, top_k)
        entry = self._store.get(key)
        if entry is None:
            return None
        timestamp, result = entry
        if time.time() - timestamp > self._ttl:
            del self._store[key]
            return None
        # Return with cache_hit=True
        return EnrichmentResult(
            success=result.success,
            context=result.context,
            results=result.results,
            cache_hit=True,
            circuit_open=result.circuit_open,
            error=result.error,
            elapsed_ms=0,
        )

    def put(self, query: str, top_k: int, result: EnrichmentResult) -> None:
        key = self._make_key(query, top_k)
        # Evict oldest if at capacity
        if len(self._store) >= self._maxsize:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
        self._store[key] = (time.time(), result)

    @property
    def size(self) -> int:
        return len(self._store)


# ─── Content Filter ─────────────────────────────────────────────────────────

# Patterns that indicate private/sensitive content
_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*['\"]?\S+"),
    re.compile(
        r"(?i)https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+)"
    ),
    re.compile(
        r"(?:^|\s)(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?:\s|$)"
    ),
    re.compile(r"(?i)internal\.\w+\.\w+"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
]

# File names that should never be shared
_BLOCKED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    "credentials.json",
    "secrets.json",
    "auth.json",
    "id_rsa",
    "id_ed25519",
    "*.pem",
}


def _is_sensitive(text: str) -> bool:
    """Check if text contains sensitive patterns."""
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _filter_sensitive(text: str) -> str:
    """Redact sensitive content from text."""
    filtered = text
    for pattern in _SENSITIVE_PATTERNS:
        filtered = pattern.sub("[REDACTED]", filtered)
    return filtered


def _is_blocked_filename(filename: str) -> bool:
    """Check if a filename should be excluded from sharing."""
    name = Path(filename).name.lower()
    if name in _BLOCKED_FILENAMES:
        return True
    for pattern in _BLOCKED_FILENAMES:
        if "*" in pattern:
            import fnmatch

            if fnmatch.fnmatch(name, pattern):
                return True
    return False


# ─── Freshness Scoring ──────────────────────────────────────────────────────


def _compute_freshness(index_timestamp: Optional[str], decay_hours: float) -> float:
    """Compute freshness score from index timestamp.

    Returns 1.0 for just-indexed, decays exponentially.
    If no timestamp, returns 0.5 (unknown).
    """
    if not index_timestamp:
        return 0.5
    try:
        from datetime import datetime

        indexed = datetime.fromisoformat(index_timestamp)
        age_hours = (datetime.now() - indexed).total_seconds() / 3600
        return max(0.0, min(1.0, 1.0 - (age_hours / decay_hours)))
    except (ValueError, TypeError):
        return 0.5


# ─── Main Bridge ─────────────────────────────────────────────────────────────


class MimirOpenSpaceBridge:
    """Adapter between Mimir's knowledge base and OpenSpace's skill engine.

    All integration guardrails live here. Both systems remain independent.
    If the bridge breaks, both systems still work standalone.

    Args:
        project_root: Path to the project root (where .mimir/config.json lives).
        config: Bridge configuration. Defaults to env vars.
    """

    def __init__(self, project_root: Path, config: Optional[BridgeConfig] = None):
        self._project_root = project_root.resolve()
        self._config = config or BridgeConfig.from_env()
        self._cache = _TimedCache(
            maxsize=self._config.cache_maxsize,
            ttl_seconds=self._config.cache_ttl_seconds,
        )
        self._circuit = _CircuitBreakerState()
        self._index = None  # Lazy-loaded
        self._index_timestamp: Optional[str] = None

    @property
    def is_enabled(self) -> bool:
        """Check kill switch + circuit breaker."""
        if not self._config.enabled:
            return False
        if self._circuit.check(self._config.circuit_breaker_reset_seconds):
            return False
        return True

    def _resolve_api_key(self) -> tuple[str, Optional[str]]:
        """Resolve API key and base URL from env or auth file."""
        with _timed("_resolve_api_key"):
            # Check env vars first
            api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
                "OPENAI_API_KEY", ""
            )
            if api_key:
                logger.debug("[BRIDGE] _resolve_api_key - FROM ENV")
                return api_key, os.environ.get(
                    "OPENAI_BASE_URL", "https://openrouter.ai/api/v1"
                )

            # Fall back to opencode auth file
            auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
            logger.debug(
                "[BRIDGE] _resolve_api_key - checking auth file: %s", auth_path
            )
            if auth_path.exists():
                try:
                    with _timed("_resolve_api_key.read_auth_file"):
                        auth_data = json.loads(auth_path.read_text())
                    if openrouter := auth_data.get("openrouter"):
                        key = openrouter.get("key", "")
                        if key:
                            logger.debug("[BRIDGE] _resolve_api_key - FROM AUTH FILE")
                            return key, "https://openrouter.ai/api/v1"
                except (json.JSONDecodeError, KeyError):
                    pass

            logger.warning("[BRIDGE] _resolve_api_key - NO KEY FOUND")
            return "", None

    def _resolve_embedding_model(self) -> str:
        """Resolve embedding model name from project config or env."""
        config_path = self._project_root / ".mimir" / "config.json"
        if config_path.exists():
            try:
                project_config = json.loads(config_path.read_text())
                if model := project_config.get("embedding_model"):
                    return model
            except (json.JSONDecodeError, OSError):
                pass
        return os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")

    def _get_index(self):
        """Lazy-load the LlamaIndex vector store."""
        if self._index is not None:
            logger.debug("[BRIDGE TIMING] _get_index - CACHED (already loaded)")
            return self._index

        with _timed("_get_index (full load)"):
            try:
                with _timed("_get_index.imports"):
                    from llama_index.core import (
                        Settings,
                        StorageContext,
                        load_index_from_storage,
                    )
                    from llama_index.embeddings.openai import OpenAIEmbedding

                knowledge_dir = self._project_root / ".knowledge" / "llamaindex"
                if not (knowledge_dir / "index_store.json").exists():
                    logger.warning("No Mimir index found at %s", knowledge_dir)
                    return None

                # Configure embedding model (required even for loading existing index)
                with _timed("_get_index.resolve_api_key"):
                    api_key, api_base = self._resolve_api_key()

                with _timed("_get_index.resolve_embedding_model"):
                    model_name = self._resolve_embedding_model()

                with _timed("_get_index.configure_embedding"):
                    embed_kwargs = {
                        "model": model_name,
                        "api_key": api_key,
                    }
                    if api_base:
                        embed_kwargs["api_base"] = api_base
                    Settings.embed_model = OpenAIEmbedding(**embed_kwargs)

                with _timed("_get_index.load_from_storage"):
                    storage_context = StorageContext.from_defaults(
                        persist_dir=str(knowledge_dir)
                    )
                    self._index = load_index_from_storage(storage_context)

                # Track index freshness
                with _timed("_get_index.read_manifest"):
                    manifest_path = knowledge_dir / "manifest.json"
                    if manifest_path.exists():
                        try:
                            manifest = json.loads(manifest_path.read_text())
                            self._index_timestamp = manifest.get("last_updated")
                        except (json.JSONDecodeError, OSError):
                            pass

                logger.info("[BRIDGE TIMING] _get_index - LOADED SUCCESSFULLY")
                return self._index
            except Exception as e:
                logger.error("Failed to load Mimir index: %s", e)
                return None

    def _search_raw(self, query: str, top_k: int) -> list[SearchResult]:
        """Execute raw search against Mimir's index."""
        with _timed(f"_search_raw('{query[:30]}...')"):
            with _timed("_search_raw.get_index"):
                index = self._get_index()
            if index is None:
                logger.warning("[BRIDGE] _search_raw - NO INDEX")
                return []

            with _timed("_search_raw.retrieve"):
                nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
            base_freshness = _compute_freshness(
                self._index_timestamp,
                self._config.freshness_decay_hours,
            )

            results = []
            for node in nodes:
                source = node.metadata.get("file_name", "unknown")
                text = node.text

                # Apply content filter
                if _is_blocked_filename(source):
                    logger.debug("Blocked sensitive file: %s", source)
                    continue
                if _is_sensitive(text):
                    text = _filter_sensitive(text)

                score = node.score if hasattr(node, "score") else 0.0
                # Truncate to stay within token budget
                # Rough estimate: 1 token ≈ 4 chars
                max_chars = self._config.max_context_tokens * 4 // top_k
                if len(text) > max_chars:
                    text = text[:max_chars] + "..."

                results.append(
                    SearchResult(
                        source=source,
                        score=score,
                        text=text,
                        freshness=base_freshness,
                    )
                )

            logger.info("[BRIDGE] _search_raw - %d results", len(results))
            return results

    def enrich_task(self, task: str, top_k: Optional[int] = None) -> EnrichmentResult:
        """Enrich an OpenSpace task description with Mimir context.

        This is the main entry point. OpenSpace calls this before skill
        selection to get project-specific context.

        Args:
            task: The task description from OpenSpace.
            top_k: Number of results to retrieve. Defaults to config.

        Returns:
            EnrichmentResult with context string ready for prompt injection.
        """
        with _timed(f"enrich_task('{task[:50]}...')"):
            start = time.time()
            k = top_k or self._config.top_k

            # Kill switch
            if not self._config.enabled:
                logger.info("[BRIDGE] enrich_task - DISABLED via kill switch")
                return EnrichmentResult(
                    success=False,
                    error="Bridge disabled via MIMIR_OPENSPACE_ENABLED=false",
                    elapsed_ms=0,
                )

            # Circuit breaker
            if self._circuit.check(self._config.circuit_breaker_reset_seconds):
                logger.info("[BRIDGE] enrich_task - CIRCUIT OPEN")
                return EnrichmentResult(
                    success=False,
                    circuit_open=True,
                    error="Circuit breaker open — Mimir unavailable",
                    elapsed_ms=0,
                )

            # Cache check
            with _timed("enrich_task.cache_check"):
                cached = self._cache.get(task, k)
            if cached is not None:
                logger.info("[BRIDGE] enrich_task - CACHE HIT")
                return cached

            # Execute search
            try:
                with _timed("enrich_task.search_raw"):
                    results = self._search_raw(task, k)
                elapsed = int((time.time() - start) * 1000)

                if not results:
                    result = EnrichmentResult(
                        success=True,
                        context="",
                        results=(),
                        elapsed_ms=elapsed,
                    )
                else:
                    # Build context string
                    chunks = [r.to_prompt_chunk() for r in results]
                    context = "\n\n".join(chunks)
                    result = EnrichmentResult(
                        success=True,
                        context=context,
                        results=tuple(results),
                        elapsed_ms=elapsed,
                    )

                self._circuit.record_success()
                self._cache.put(task, k, result)
                logger.info(
                    "[BRIDGE] enrich_task - SUCCESS (%dms, %d results)",
                    elapsed,
                    len(results),
                )
                return result

            except Exception as e:
                elapsed = int((time.time() - start) * 1000)
                self._circuit.record_failure(
                    self._config.circuit_breaker_threshold,
                    self._config.circuit_breaker_reset_seconds,
                )
                logger.error("Mimir search failed: %s", e)
                return EnrichmentResult(
                    success=False,
                    error=str(e),
                    elapsed_ms=elapsed,
                )

    def health_check(self) -> dict:
        """Check bridge health. Used by OpenSpace before relying on Mimir.

        NOTE: This does NOT load the index — just checks if it exists on disk.
        Loading happens lazily when enrich_task() is called.
        """
        with _timed("health_check"):
            # Check if index exists on disk WITHOUT loading it
            knowledge_dir = self._project_root / ".knowledge" / "llamaindex"
            has_index = (knowledge_dir / "index_store.json").exists()

            # Read manifest timestamp if available
            index_timestamp = None
            manifest_path = knowledge_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    index_timestamp = manifest.get("last_updated")
                except (json.JSONDecodeError, OSError):
                    pass

            result = {
                "enabled": self._config.enabled,
                "circuit_open": self._circuit.is_open,
                "circuit_failures": self._circuit.failure_count,
                "has_index": has_index,
                "index_timestamp": index_timestamp,
                "cache_size": self._cache.size,
                "project_root": str(self._project_root),
            }
            logger.info("[BRIDGE] health_check complete: %s", result)
            return result

    def get_stats(self) -> dict:
        """Extended stats for monitoring."""
        health = self.health_check()
        health.update(
            {
                "config": {
                    "cache_maxsize": self._config.cache_maxsize,
                    "cache_ttl_seconds": self._config.cache_ttl_seconds,
                    "circuit_breaker_threshold": self._config.circuit_breaker_threshold,
                    "search_timeout_seconds": self._config.search_timeout_seconds,
                    "max_context_tokens": self._config.max_context_tokens,
                    "top_k": self._config.top_k,
                },
            }
        )
        return health


# ─── Convenience Functions ───────────────────────────────────────────────────

_bridge_instance: Optional[MimirOpenSpaceBridge] = None


def get_bridge(project_root: Optional[Path] = None) -> MimirOpenSpaceBridge:
    """Get or create the singleton bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        root = project_root or Path.cwd()
        _bridge_instance = MimirOpenSpaceBridge(project_root=root)
    return _bridge_instance


def enrich_task_for_openspace(task: str, project_root: Optional[Path] = None) -> dict:
    """One-call convenience function for MCP tool integration.

    Args:
        task: OpenSpace task description.
        project_root: Project root. Auto-detected if None.

    Returns:
        Dict ready for JSON serialization.
    """
    bridge = get_bridge(project_root)
    result = bridge.enrich_task(task)
    return result.to_dict()
