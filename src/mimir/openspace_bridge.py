#!/usr/bin/env python3
"""
Mimir ↔ OpenSpace Bridge Adapter (DEPRECATED)

This module exists ONLY for backward compatibility. All logic has been
moved to src.mimir.query_router — a standalone module with zero OpenSpace
dependency.

The MimirOpenSpaceBridge class is preserved as a thin wrapper so existing
callers (tests, skills, etc.) don't break, but new code should use
query_router.route_task() directly.

Migration path:
  - Old: bridge = MimirOpenSpaceBridge(root); bridge.enrich_task(q)
  - New: from mimir.query_router import route_task; route_task(q)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mimir.query_router import (
    RoutingResult,
    SearchResult,
    _CircuitBreakerState,
    _TimedCache,
    _compute_freshness,
    _filter_sensitive,
    _is_blocked_filename,
    _is_sensitive,
    _quick_structural_check,
    enrich_task_for_openspace,
    get_bridge,
    route_task,
)


# ─── Bridge Config (thin alias for backward compat) ──────────────────────────


@dataclass(frozen=True)
class BridgeConfig:
    """Deprecated — use RouterConfig from query_router instead.

    Kept here so existing code that references BridgeConfig doesn't break.
    All fields map directly to RouterConfig equivalents.
    """

    enabled: bool = True
    cache_maxsize: int = 128
    cache_ttl_seconds: int = 600
    circuit_breaker_threshold: int = 3
    circuit_breaker_reset_seconds: int = 60
    search_timeout_seconds: float = 30.0
    max_context_tokens: int = 2500
    top_k: int = 5
    freshness_decay_hours: float = 168.0
    classification_model: str = "gpt-3.5-turbo"
    classification_enabled: bool = True

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Load from env — delegates to MimirConfig (same as before)."""
        from mimir.config import get_config

        config = get_config()
        return cls(
            enabled=config.bridge_enabled,
            cache_maxsize=config.bridge_cache_maxsize,
            cache_ttl_seconds=config.bridge_cache_ttl_seconds,
            circuit_breaker_threshold=config.bridge_circuit_breaker_threshold,
            circuit_breaker_reset_seconds=config.bridge_circuit_breaker_reset_seconds,
            search_timeout_seconds=config.bridge_search_timeout_seconds,
            max_context_tokens=config.bridge_max_context_tokens,
            top_k=config.bridge_top_k,
            freshness_decay_hours=config.bridge_freshness_decay_hours,
            classification_model=config.bridge_classification_model,
            classification_enabled=config.bridge_classification_enabled,
        )


# ─── EnrichmentResult (thin alias) ───────────────────────────────────────────


class EnrichmentResult(RoutingResult):
    """Deprecated alias for RoutingResult.

    Keeps the same interface so existing MimirOpenSpaceBridge callers work.
    """

    pass


# ─── MimirOpenSpaceBridge (deprecated thin wrapper) ─────────────────────────


class MimirOpenSpaceBridge:
    """DEPRECATED — thin wrapper around query_router.route_task().

    All guardrails (circuit breaker, cache, content filtering, classification)
    are now handled by query_router directly. This class exists only to avoid
    breaking existing callers.

    Migration:
        # Old (OpenSpace-coupled):
        bridge = MimirOpenSpaceBridge(project_root=Path("."))
        result = bridge.enrich_task("Build auth middleware")

        # New (standalone):
        from mimir.query_router import route_task
        result = route_task("Build auth middleware")
    """

    def __init__(
        self,
        project_root: Path,
        config: Optional[BridgeConfig] = None,
        mimir_config: Optional[object] = None,
    ):
        # Accept config params for compat but route everything through query_router
        self._project_root = project_root.resolve()
        self._config = config or BridgeConfig.from_env()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    @property
    def _circuit(self) -> _CircuitBreakerState:
        """Expose circuit breaker for test compatibility."""
        from mimir.query_router import route_task

        if not hasattr(route_task, "_circuit"):
            route_task._circuit = _CircuitBreakerState()
        return route_task._circuit

    def _resolve_api_key(self) -> tuple[str, Optional[str]]:
        from mimir.config import get_config

        cfg = get_config()
        return cfg.api_key, cfg.api_base

    def enrich_task(self, task: str, top_k: Optional[int] = None) -> EnrichmentResult:
        """Enrich a task — delegates to query_router.route_task()."""
        result = route_task(task, project_root=self._project_root, top_k=top_k)
        return EnrichmentResult(
            success=result.success,
            context=result.context,
            results=result.results,
            cache_hit=result.cache_hit,
            circuit_open=result.circuit_open,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            status=result.status,
        )

    def health_check(self) -> dict:
        """Health check — delegates to query_router."""
        from mimir.query_router import RouterConfig
        from mimir.config import get_config

        cfg = get_config()
        rc = RouterConfig.from_mimir_config(cfg)
        knowledge_dir = self._project_root / ".knowledge" / "llamaindex"
        has_index = (knowledge_dir / "index_store.json").exists()

        return {
            "enabled": rc.enabled,
            "circuit_open": rc.enabled and self._circuit.is_open,
            "circuit_failures": self._circuit.failure_count,
            "has_index": has_index,
            "index_timestamp": None,
            "cache_size": 0,  # Cache is on route_task function object
            "project_root": str(self._project_root),
        }

    def get_stats(self) -> dict:
        """Get stats — delegates to health_check."""
        health = self.health_check()
        return health