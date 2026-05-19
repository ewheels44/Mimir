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
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.mimir.config import MimirConfig

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
    """Bridge configuration. Now delegates to MimirConfig for defaults."""

    enabled: bool = True
    cache_maxsize: int = 128
    cache_ttl_seconds: int = 600
    circuit_breaker_threshold: int = 3
    circuit_breaker_reset_seconds: int = 60
    search_timeout_seconds: float = 30.0
    max_context_tokens: int = 2500
    top_k: int = 5
    freshness_decay_hours: float = 168.0
    classification_model: str = "gpt-3.5-turbo"  # Fast model for query classification
    classification_enabled: bool = True

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Load from MimirConfig (which handles env vars, config file, defaults)."""
        from src.mimir.config import get_config

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
    status: str = (
        "ok"  # "ok", "no_results", "no_index", "error", "disabled", "circuit_open"
    )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "context": self.context,
            "result_count": len(self.results),
            "cache_hit": self.cache_hit,
            "circuit_open": self.circuit_open,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "status": self.status,
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
            status=result.status,
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
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


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


# ─── API Key Resolution ───────────────────────────────────────────────────────


def _resolve_api_key_from_env() -> tuple[str, Optional[str]]:
    """Resolve API key and base URL from environment or auth file.

    Returns (api_key, api_base) tuple. Empty string if no key found.

    NOTE: Now delegates to MimirConfig for consistency.
    """
    from src.mimir.config import get_config

    cfg = get_config()
    return cfg.api_key, cfg.api_base


# ─── Query Classification ─────────────────────────────────────────────────

# Classification prompt template
_CLASSIFICATION_PROMPT = """Classify this query as exactly one of:
- "structural": Questions about relationships, connections, dependencies, paths between components
- "semantic": Questions about meaning, usage, concepts, how things work

Key indicators for STRUCTURAL:
- Mentions connections, relationships, dependencies
- Asks "how does X connect to Y" or "path from A to B"
- References multiple components and their relationship
- Uses words: connect, link, depend, call, import, path, relationship

Key indicators for SEMANTIC:
- Asks how something works conceptually
- Requests examples or usage patterns
- Asks about meaning or purpose
- Uses words: how does it work, what is, explain, example

Query: {query}

Answer with exactly one word (structural or semantic):"""

# Structural query indicators for quick pre-check
_STRUCTURAL_KEYWORDS = [
    "connect", "connection", "link", "linked", "relate", "relationship",
    "depend", "depends", "dependency", "path", "between", "from", "to",
    "import", "call", "invoke", "structure of", "graph",
    "how does", "how do",
]


def _quick_structural_check(query: str) -> Optional[str]:
    """Fast keyword-based pre-classification. Returns None if uncertain."""
    query_lower = query.lower()
    keyword_hits = sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in query_lower)
    
    # Strong structural signal: 2+ keywords OR specific structural phrases
    # BUT exclude "how do I..." (semantic question)
    has_structural_phrase = any(
        phrase in query_lower 
        for phrase in ["connect to", "path from", "depends on", "how does"]
    )
    
    # "how do" is structural only if followed by structural keywords
    is_how_do_structural = "how do" in query_lower and any(
        kw in query_lower for kw in ["connect", "link", "relate", "depend", "call"]
    )
    
    if keyword_hits >= 2 or has_structural_phrase or is_how_do_structural:
        return "structural"
    if keyword_hits == 0:
        return "semantic"
    return None  # Uncertain, let LLM decide


# ─── Graph Search Helper ─────────────────────────────────────────────────

def _parse_graph_response(response_text: str) -> Optional[dict]:
    """Parse graph tool JSON response."""
    try:
        # Graph tools return JSON directly
        return json.loads(response_text)
    except (json.JSONDecodeError, TypeError):
        return None


def _format_graph_result(graph_data: dict) -> str:
    """Format graph query result into context string."""
    if not graph_data:
        return ""
    
    # Handle graph_query response (path finding)
    if "steps" in graph_data:
        steps = graph_data.get("steps", [])
        if not steps:
            return "No path found between the specified components."
        
        lines = ["[Graph Path]"]
        for i, step in enumerate(steps, 1):
            source = step.get("source", "?")
            target = step.get("target", "?")
            edge = step.get("edge_type", "related")
            lines.append(f"  {i}. {source} --{edge}--> {target}")
        return "\n".join(lines)
    
    # Handle graph_neighbors response
    if "neighbors" in graph_data:
        neighbors = graph_data.get("neighbors", [])
        center = graph_data.get("center", "?")
        lines = [f"[Graph Neighbors of {center}]"]
        for nb in neighbors[:10]:  # Limit output
            label = nb.get("label", "?")
            edge = nb.get("edge_type", "related")
            direction = nb.get("direction", "")
            lines.append(f"  - {label} ({edge}, {direction})")
        return "\n".join(lines)
    
    return str(graph_data)


# ─── Main Bridge ─────────────────────────────────────────────────────────────


class MimirOpenSpaceBridge:
    """Adapter between Mimir's knowledge base and OpenSpace's skill engine.

    All integration guardrails live here. Both systems remain independent.
    If the bridge breaks, both systems still work standalone.

    Args:
        project_root: Path to the project root (where .mimir/config.json lives).
        config: Bridge configuration. Defaults to env vars.
    """

    def __init__(
        self,
        project_root: Path,
        config: Optional[BridgeConfig] = None,
        mimir_config: Optional[MimirConfig] = None,
    ):
        self._project_root = project_root.resolve()
        if mimir_config is not None:
            self._config = BridgeConfig(
                enabled=mimir_config.bridge_enabled,
                cache_maxsize=mimir_config.bridge_cache_maxsize,
                cache_ttl_seconds=mimir_config.bridge_cache_ttl_seconds,
                circuit_breaker_threshold=mimir_config.bridge_circuit_breaker_threshold,
                circuit_breaker_reset_seconds=mimir_config.bridge_circuit_breaker_reset_seconds,
                search_timeout_seconds=mimir_config.bridge_search_timeout_seconds,
                max_context_tokens=mimir_config.bridge_max_context_tokens,
                top_k=mimir_config.bridge_top_k,
                freshness_decay_hours=mimir_config.bridge_freshness_decay_hours,
            )
        else:
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
        return not self._circuit.check(self._config.circuit_breaker_reset_seconds)

    def _resolve_api_key(self) -> tuple[str, Optional[str]]:
        """Resolve API key — uses MimirConfig as single source of truth."""
        with _timed("_resolve_api_key"):
            from src.mimir.config import get_config

            cfg = get_config()
            return cfg.api_key, cfg.api_base

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
                with _timed("_get_index.resolve_config"):
                    from src.mimir.config import get_config

                    cfg = get_config()
                    api_key = cfg.api_key
                    api_base = cfg.api_base
                    model_name = cfg.embedding_model

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
                # Add safety margin: 1 token = ~4 chars
                max_chars = self._config.max_context_tokens * 4 // max(top_k, 1) // 2
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

    def _classify_query(self, query: str) -> str:
        """Classify query as 'structural' or 'semantic'.
        
        Uses neural classifier (Phase 1) for fast, cheap classification.
        Falls back to LLM if classifier is uncertain or unavailable.
        Final fallback to keyword-based classification.
        """
        if not self._config.classification_enabled:
            return "semantic"  # Default to semantic
        
        # Quick pre-check to avoid unnecessary calls
        quick_result = _quick_structural_check(query)
        if quick_result:
            logger.debug("[CLASSIFY] Quick classification: %s", quick_result)
            return quick_result
        
        # Try neural classifier first (fast, cheap ~$0.000001 per query)
        try:
            from src.mimir.query_classifier import load_model, track_classification
            
            classifier = load_model()
            if classifier is not None:
                label, confidence = classifier.predict_with_confidence(query)
                
                # If confident, return neural classification
                if confidence >= 0.6:
                    logger.info("[CLASSIFY] Neural classified as: %s (confidence: %.2f)", label, confidence)
                    track_classification("neural", query, confidence)
                    return label
                else:
                    logger.debug("[CLASSIFY] Neural uncertain (%.2f), trying LLM", confidence)
        except Exception as e:
            logger.debug("[CLASSIFY] Neural classifier unavailable: %s", e)
        
        # Fallback to LLM for ambiguous cases (~$0.0015 per query)
        try:
            from llama_index.llms.openai import OpenAI as OpenAILike
            
            api_key, api_base = self._resolve_api_key()
            llm_kwargs = {"model": self._config.classification_model}
            if api_key:
                llm_kwargs["api_key"] = api_key
                if api_base:
                    llm_kwargs["api_base"] = api_base
            
            llm = OpenAILike(**llm_kwargs)
            prompt = _CLASSIFICATION_PROMPT.format(query=query)
            
            with _timed("_classify_query.llm_call"):
                response = llm.complete(prompt).text.strip().lower()
            
            # Parse response
            if "structural" in response:
                logger.info("[CLASSIFY] LLM classified as: structural")
                from src.mimir.query_classifier import track_classification
                track_classification("llm", query, confidence=None)
                return "structural"
            elif "semantic" in response:
                logger.info("[CLASSIFY] LLM classified as: semantic")
                from src.mimir.query_classifier import track_classification
                track_classification("llm", query, confidence=None)
                return "semantic"
            else:
                logger.warning("[CLASSIFY] LLM returned unclear response: %s", response)
                return "semantic"  # Safe default
                
        except Exception as e:
            logger.warning("[CLASSIFY] LLM classification failed: %s. Using keyword fallback.", e)
            # Final fallback to keyword check
            from src.mimir.query_classifier import track_classification
            result = _quick_structural_check(query) or "semantic"
            track_classification("keyword", query, confidence=None)
            return result


    def _search_graph(self, query: str) -> Optional[str]:
        """Search using graph tools for structural queries.
        
        Attempts to extract source/target nodes from query and use graph_query.
        Falls back to graph_neighbors if path query fails.
        """
        # Simple extraction - look for "between X and Y" or "X to Y" patterns
        import re
        
        # Pattern: "between X and Y" or "from X to Y"
        patterns = [
            r"between\s+(\S+)\s+and\s+(\S+)",
            r"from\s+(\S+)\s+to\s+(\S+)",
            r"(\S+)\s+to\s+(\S+)",
            r"(\S+)\s+and\s+(\S+)",
        ]
        
        source = target = None
        for pattern in patterns:
            match = re.search(pattern, query.lower())
            if match:
                source, target = match.group(1), match.group(2)
                break
        
        if source and target:
            # Try graph_query for path
            try:
                from urllib.request import urlopen
                from urllib.parse import urlencode
                
                # Call graph API via localhost (assuming web server is running)
                port = os.environ.get("MIMIR_WEB_PORT", "8000")
                params = urlencode({"source": source, "target": target})
                url = f"http://localhost:{port}/api/graph/path?{params}"
                
                with _timed("_search_graph.query"):
                    with urlopen(url, timeout=10) as resp:
                        result = json.loads(resp.read().decode())
                
                if result.get("found"):
                    logger.info("[GRAPH] Found path from %s to %s", source, target)
                    return _format_graph_result(result)
            except Exception as e:
                logger.warning("[GRAPH] graph_query failed: %s", e)
        
        # Fallback: try to extract a single node and use graph_neighbors
        node_match = re.search(r"(?:of|for|about)\s+(\S+)", query.lower())
        if node_match:
            node = node_match.group(1)
            try:
                port = os.environ.get("MIMIR_WEB_PORT", "8000")
                params = urlencode({"node_id": node, "depth": "2"})
                url = f"http://localhost:{port}/api/graph/neighbors?{params}"
                
                with _timed("_search_graph.neighbors"):
                    with urlopen(url, timeout=10) as resp:
                        result = json.loads(resp.read().decode())
                
                logger.info("[GRAPH] Found neighbors for %s", node)
                return _format_graph_result(result)
            except Exception as e:
                logger.warning("[GRAPH] graph_neighbors failed: %s", e)
        
        return None

    def enrich_task(self, task: str, top_k: Optional[int] = None) -> EnrichmentResult:
        """Enrich an OpenSpace task description with Mimir context.
        
        This is the main entry point. OpenSpace calls this before skill
        selection to get project-specific context.
        
        Now with LLM-based query classification:
        - Structural queries → graph tools
        - Semantic queries → vector search
        
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
                    status="disabled",
                )

            # Circuit breaker
            if self._circuit.check(self._config.circuit_breaker_reset_seconds):
                logger.info("[BRIDGE] enrich_task - CIRCUIT OPEN")
                return EnrichmentResult(
                    success=False,
                    circuit_open=True,
                    error="Circuit breaker open — Mimir unavailable",
                    elapsed_ms=0,
                    status="circuit_open",
                )

            # Cache check
            with _timed("enrich_task.cache_check"):
                cached = self._cache.get(task, k)
            if cached is not None:
                logger.info("[BRIDGE] enrich_task - CACHE HIT")
                return cached

            # Classify query and route appropriately
            query_type = self._classify_query(task)
            logger.info("[BRIDGE] enrich_task - Query classified as: %s", query_type)
            
            if query_type == "structural":
                # Try graph search first
                graph_context = self._search_graph(task)
                if graph_context:
                    elapsed = int((time.time() - start) * 1000)
                    result = EnrichmentResult(
                        success=True,
                        context=graph_context,
                        results=(),
                        elapsed_ms=elapsed,
                        status="ok",
                    )
                    self._circuit.record_success()
                    self._cache.put(task, k, result)
                    logger.info("[BRIDGE] enrich_task - GRAPH SUCCESS (%dms)", elapsed)
                    return result
                else:
                    logger.info("[BRIDGE] enrich_task - Graph search failed, falling back to vector")

            # Execute vector search (for semantic queries or graph fallback)
            try:
                with _timed("enrich_task.search_raw"):
                    results = self._search_raw(task, k)
                elapsed = int((time.time() - start) * 1000)

                if not results:
                    # Distinguish "no matches" from "no index"
                    knowledge_dir = self._project_root / ".knowledge" / "llamaindex"
                    has_index = (knowledge_dir / "index_store.json").exists()

                    if not has_index:
                        result = EnrichmentResult(
                            success=False,
                            context="",
                            results=(),
                            error="No knowledge base index found. Run indexing first.",
                            elapsed_ms=elapsed,
                            status="no_index",
                        )
                    else:
                        result = EnrichmentResult(
                            success=True,
                            context="",
                            results=(),
                            elapsed_ms=elapsed,
                            status="no_results",
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
                        status="ok",
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
                if self._circuit.failure_count >= self._config.circuit_breaker_threshold:
                    logger.warning(
                        "Circuit breaker tripped after %d failures (%d threshold)",
                        self._circuit.failure_count,
                        self._config.circuit_breaker_threshold,
                    )
                logger.error("Mimir search failed: %s", e)
                return EnrichmentResult(
                    success=False,
                    error=str(e),
                    elapsed_ms=elapsed,
                    status="error",
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
