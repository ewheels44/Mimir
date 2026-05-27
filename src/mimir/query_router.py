#!/usr/bin/env python3
"""
Standalone Query Router — replaces OpenSpace bridge dependency.

Routes user queries to the most appropriate Mimir backend:
  - Structural queries -> Knowledge graph (Dijkstra path-finding)
  - Semantic queries  -> Vector search (LlamaIndex)
  - Hybrid queries    -> Both graph + vector, merged by confidence threshold

Uses embedding-based semantic caching, normalized query matching, and
sentence-transformer classification for routing decisions.
No external framework dependencies beyond numpy + LlamaIndex.

Usage:
    from mimir.query_router import route_task

    result = route_task("How does the auth module work?", project_root=Path("."))
    print(result.context)   # Injected into prompt
    print(result.routed_to) # "graph" | "vector" | "hybrid" | "artifact" | "none"
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import numpy as np

from mimir.config import MimirConfig, get_config

# ─── Query Normalization ────────────────────────────────────────────────────────
# Normalizes natural language queries to improve cache hit rates and
# reduce surface variation. Based on standard IR normalization practices.

_NORMALIZE_FILLER = re.compile(
    r"\b(?:can you|could you|would you|please|kindly|I want to|I need to|"
    r"tell me|show me|help me|explain|what is|what are|how do I|how can I)\b",
    re.IGNORECASE,
)
_NORMALIZE_WHITESPACE = re.compile(r"\s+")
_NORMALIZE_PUNCTUATION = re.compile(r"\s*([.,;:!?])\s*")


def normalize_query(query: str) -> str:
    """Normalize a query string for better cache matching and retrieval.

    Steps:
      1. Lowercase
      2. Strip filler phrases that don't change semantic meaning
      3. Normalize whitespace
      4. Strip trailing/leading punctuation from words
      5. Strip trailing punctuation from the whole string
    """
    q = query.lower().strip()
    q = _NORMALIZE_FILLER.sub(" ", q)
    q = _NORMALIZE_WHITESPACE.sub(" ", q)
    q = _NORMALIZE_PUNCTUATION.sub(r"\1", q)
    # Strip any remaining trailing/leading punctuation on the full string
    q = q.strip(" .,;:!?\"'()[]{}")
    return q


# ─── Artifact Keyword Mapping ────────────────────────────────────────────────
# Maps task keywords to pre-compiled artifact IDs for instant answers.
# Artifacts are checked FIRST before any search/retrieval (zero token cost).

ARTIFACT_KEYWORDS = {
    "rag_architecture": [
        "rag", "retrieval", "hybrid search", "vector search", "bm25", "retriever",
        "rag workflow", "knowledge agent", "langgraph", "llm", "token tracking",
    ],
    "indexing_architecture": [
        "indexing", "index", "reindex", "incremental", "file watcher", "watchdog",
        "document id", "doc_id", "change detection", "hash",
    ],
    "artifact_system": [
        "artifact", "pre-compiled", "stale", "ttl", "dependency tracking",
        "manifest", "invalidation",
    ],
    "code_chunking": [
        "chunking", "chunk", "ast", "tree-sitter", "python chunker",
        "code chunk", "split",
    ],
    "knowledge_graph_integration": [
        "knowledge graph", "graph query", "dijkstra", "relationship",
        "imports_from", "calls", "inherits_from",
    ],
    "query_caching": [
        "cache", "query cache", "ttl", "expiration", "query_caching",
    ],
}


def _find_matching_artifact(task: str, project_root: Optional[Path] = None) -> Optional[str]:
    """Check if task matches any artifact keywords. Returns artifact_id or None.
    
    Checks both the static ARTIFACT_KEYWORDS mapping and dynamic keywords
    stored in each artifact's content.
    
    Args:
        task: The task/query string
        project_root: Project root for resolving artifact paths
    """
    import re
    from mimir.artifacts import load_manifest, get_artifact
    
    task_lower = task.lower()
    
    best_match = None
    best_score = 0
    
    # First check static keyword mapping (fast path, no I/O)
    for artifact_id, keywords in ARTIFACT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > best_score:
            best_score = score
            best_match = artifact_id
    
    # If we got a good match from static mapping, use it
    if best_score > 0:
        logger.info("[ROUTER] Task matches artifact '%s' (score=%d, static)", best_match, best_score)
        return best_match
    
    # Fall back to dynamic keywords from artifact content
    try:
        manifest = load_manifest(project_root)
        for artifact_id in manifest.get("artifacts", {}):
            content = get_artifact(artifact_id, project_root)
            if content:
                keywords = content.get("keywords", [])
                if not keywords:
                    continue
                score = sum(1 for kw in keywords if kw in task_lower)
                if score > best_score:
                    best_score = score
                    best_match = artifact_id
    except Exception as e:
        logger.warning("[ROUTER] Failed to load dynamic artifact keywords: %s", e)
    
    if best_score > 0:
        logger.info("[ROUTER] Task matches artifact '%s' (score=%d, dynamic)", best_match, best_score)
    return best_match


def _try_artifact(artifact_id: str, project_root: Path) -> Optional[RoutingResult]:
    """Try to retrieve and return an artifact. Returns RoutingResult if found and fresh."""
    try:
        from mimir.artifacts import get_artifact
        
        content = get_artifact(artifact_id, project_root)
        if content is None:
            logger.info("[ROUTER] Artifact '%s' not found", artifact_id)
            return None
        
        # Check if stale
        metadata = content.get("_metadata", {})
        if metadata.get("stale"):
            logger.info("[ROUTER] Artifact '%s' is stale, skipping", artifact_id)
            return None
        
        elapsed = 1  # Artifacts are essentially instant
        context = json.dumps(content, indent=2, ensure_ascii=False)
        
        result = RoutingResult(
            success=True,
            context=f"[ARTIFACT: {artifact_id}]\n{context}",
            query_type="artifact",
            routed_to="artifact",
            elapsed_ms=elapsed,
            status="ok",
        )
        logger.info("[ROUTER] Served artifact '%s' (instant, zero tokens)", artifact_id)
        return result
        
    except Exception as e:
        logger.warning("[ROUTER] Artifact '%s' retrieval failed: %s", artifact_id, e)
        return None

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Guardrail Utilities (inlined — no OpenSpace coupling)
# ═══════════════════════════════════════════════════════════════════════════════

def _timed(label: str):
    """Context manager that logs elapsed time for a block."""
    import contextlib

    @contextlib.contextmanager
    def _timer():
        start = time.time()
        logger.debug("[ROUTER TIMING] %s - START", label)
        try:
            yield
        finally:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.debug("[ROUTER TIMING] %s - END (%dms)", label, elapsed_ms)

    return _timer()


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


class _SemanticCache:
    """Semantic cache using embedding similarity instead of exact-match hashing.

    Instead of SHA256(query) exact lookups, this:
      1. Embeds the query using the same model as document indexing
      2. Computes cosine similarity against cached query embeddings
      3. Returns the cached result if similarity > threshold (default 0.92)

    This handles paraphrases, rewording, and natural language variation
    that exact-match SHA256 hashing misses entirely.

    Research basis: GPTCache (2023), semantic caching surveys show
    exact-match cache hit rates near zero for NL queries.
    """

    def __init__(
        self,
        maxsize: int = 128,
        ttl_seconds: int = 600,
        similarity_threshold: float = 0.92,
    ):
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._threshold = similarity_threshold
        # Store: list of (timestamp, query_text, query_embedding, RoutingResult)
        self._store: list[tuple[float, str, Optional[np.ndarray], "RoutingResult"]] = []  # noqa: F821
        self._embed_model = None
        self._embed_kwargs = {}

    def _ensure_embedding_model(self):
        """Lazily initialize the embedding model to match document indexing."""
        if self._embed_model is not None:
            return
        try:
            from llama_index.core import Settings

            cfg: MimirConfig = get_config()
            api_key = cfg.api_key
            api_base = cfg.api_base

            from llama_index.embeddings.openai import OpenAIEmbedding

            embed_kwargs = {"model": cfg.embedding_model, "api_key": api_key}
            if api_base:
                embed_kwargs["api_base"] = api_base
            self._embed_kwargs = embed_kwargs
            Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
            self._embed_model = Settings.embed_model
        except Exception:
            # Fallback: will use keyword-based matching
            self._embed_model = None

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for a text string. Returns None if unavailable."""
        self._ensure_embedding_model()
        if self._embed_model is None:
            return None
        try:
            emb = self._embed_model.get_text_embedding(text)
            return np.array(emb, dtype=np.float32)
        except Exception:
            return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def get(self, query: str, top_k: int) -> Optional["RoutingResult"]:  # noqa: F821
        """Look up a cached result using semantic similarity."""
        # First try exact-match key (fast path for identical queries)
        exact_key = self._exact_key(query, top_k)
        for entry in self._store:
            ts, qtext, qemb, result = entry
            if qtext == query and result is not None:
                if time.time() - ts > self._ttl:
                    self._store.remove(entry)
                    continue
                return self._make_cache_result(result)

        # Semantic lookup
        query_emb = self._embed(query)
        if query_emb is None:
            return None

        best_match = None
        best_sim = 0.0
        for entry in self._store:
            ts, qtext, qemb, result = entry
            if qemb is None:
                continue
            if time.time() - ts > self._ttl:
                self._store.remove(entry)
                continue
            sim = self._cosine_similarity(query_emb, qemb)
            if sim > best_sim and sim >= self._threshold:
                best_sim = sim
                best_match = entry

        if best_match is not None:
            logger.info(
                "[SEMANTIC CACHE] Hit with similarity=%.3f for query: %s",
                best_sim,
                query[:60],
            )
            return self._make_cache_result(best_match[3])
        return None

    def put(self, query: str, top_k: int, result: "RoutingResult") -> None:  # noqa: F821
        """Store a result with its query embedding."""
        # Evict oldest if at capacity
        if len(self._store) >= self._maxsize:
            self._store.pop(0)

        query_emb = self._embed(query)
        self._store.append((time.time(), query, query_emb, result))

    @staticmethod
    def _exact_key(query: str, top_k: int) -> str:
        return hashlib.sha256(f"{query}:{top_k}".encode()).hexdigest()[:16]

    @staticmethod
    def _make_cache_result(result: "RoutingResult") -> "RoutingResult":  # noqa: F821
        """Return a RoutingResult with cache_hit=True and elapsed_ms=0."""
        return RoutingResult(
            success=result.success,
            context=result.context,
            results=result.results,
            cache_hit=True,
            circuit_open=result.circuit_open,
            error=result.error,
            elapsed_ms=0,
            status=result.status,
            routed_to=result.routed_to,
            query_type=result.query_type,
        )

    @property
    def size(self) -> int:
        return len(self._store)


# ─── Content Filter ─────────────────────────────────────────────────────────

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

_BLOCKED_FILENAMES = {
    ".env", ".env.local", ".env.production", ".env.staging",
    "credentials.json", "secrets.json", "auth.json",
    "id_rsa", "id_ed25519", "*.pem",
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


# ─── Query Classification ─────────────────────────────────────────────────

# Strong structural indicators (high confidence alone is enough)
_STRONG_STRUCTURAL = [
    "connect to", "path from", "depends on", "depends on the",
    "how does.*connect", "how does.*depend", "how does.*call",
    "how do.*connect", "how do.*depend", "how do.*call",
]

_STRUCTURAL_KEYWORDS = [
    "connect", "connection", "link", "linked", "relate", "relationship",
    "depend", "depends", "dependency", "dependen", "path", "between", "from", "to",
    "import", "call", "invoke", "structure of", "graph",
    "how does", "how do",
]


def _quick_structural_check(query: str) -> Optional[str]:
    """Fast keyword-based pre-classification. Returns None if uncertain."""
    query_lower = query.lower()
    keyword_hits = sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in query_lower)

    has_strong_phrase = any(
        phrase in query_lower for phrase in _STRONG_STRUCTURAL
    )
    has_structural_phrase = any(
        phrase in query_lower
        for phrase in ["connect to", "path from", "depends on", "how does"]
    )

    is_how_do_structural = "how do" in query_lower and any(
        kw in query_lower for kw in ["connect", "link", "relate", "depend", "call"]
    )

    if has_strong_phrase or keyword_hits >= 2 or has_structural_phrase or is_how_do_structural:
        return "structural"
    if keyword_hits == 0:
        return "semantic"
    return None  # Uncertain, let LLM decide


# ─── Standalone Graph Search ─────────────────────────────────────────────────


def _format_graph_result(graph_data: dict) -> str:
    """Format graph query result into a readable context string."""
    if not graph_data:
        return ""

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

    if "neighbors" in graph_data:
        neighbors = graph_data.get("neighbors", [])
        center = graph_data.get("center", "?")
        lines = [f"[Graph Neighbors of {center}]"]
        for nb in neighbors[:10]:
            label = nb.get("label", "?")
            edge = nb.get("edge_type", "related")
            direction = nb.get("direction", "")
            lines.append(f"  - {label} ({edge}, {direction})")
        return "\n".join(lines)

    return str(graph_data)


def _search_graph(query: str, project_root: Path) -> Optional[str]:
    """Search the code knowledge graph for structural relationships.

    Extracts source/target nodes from query text and calls the graph
    REST endpoints (via localhost HTTP to the Rust web server).

    Note: This hits the same /api/graph/path and /api/graph/neighbors
    endpoints that the old openspace_bridge used, but does so directly
    without importing anything from that class.

    Args:
        query: Natural language query about code structure
        project_root: Project root directory

    Returns:
        Formatted graph context string, or None if no match
    """
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
        try:
            from urllib.request import urlopen

            port = os.environ.get("MIMIR_WEB_PORT", "8000")
            params = urlencode({"source": source, "target": target})
            url = f"http://localhost:{port}/api/graph/path?{params}"

            with urlopen(url, timeout=10) as resp:
                result = json.loads(resp.read().decode())

            if result.get("found"):
                return _format_graph_result(result)
        except Exception as e:
            logger.warning("[GRAPH] graph_query failed: %s", e)

    node_match = re.search(r"(?:of|for|about)\s+(\S+)", query.lower())
    if node_match:
        node = node_match.group(1)
        try:
            from urllib.request import urlopen

            port = os.environ.get("MIMIR_WEB_PORT", "8000")
            params = urlencode({"node_id": node, "depth": "2"})
            url = f"http://localhost:{port}/api/graph/neighbors?{params}"

            with urlopen(url, timeout=10) as resp:
                result = json.loads(resp.read().decode())

            return _format_graph_result(result)
        except Exception as e:
            logger.warning("[GRAPH] graph_neighbors failed: %s", e)

    return None


# ─── Standalone Raw Vector Search ────────────────────────────────────────────


@dataclass(frozen=True)
class SearchResult:
    """Single retrieved document chunk with metadata."""

    source: str
    score: float
    text: str
    freshness: float

    def to_prompt_chunk(self) -> str:
        freshness_tag = (
            "fresh" if self.freshness > 0.7
            else "recent" if self.freshness > 0.3
            else "stale"
        )
        return f"[{self.source} ({freshness_tag}, score={self.score:.2f})]\n{self.text}"


def _search_raw(query: str, project_root: Path, top_k: int = 5) -> list[SearchResult]:
    """Execute raw vector search against Mimir's LlamaIndex.

    This is the same retrieval path used by KnowledgeServer.search(),
    but without the BM25 hybrid layer for simplicity.

    Args:
        query: Search query string
        project_root: Project root directory
        top_k: Number of results to return

    Returns:
        List of SearchResult objects (may be empty)
    """
    from llama_index.core import Settings, StorageContext, load_index_from_storage
    from llama_index.embeddings.openai import OpenAIEmbedding

    cfg: MimirConfig = get_config()
    api_key = cfg.api_key
    api_base = cfg.api_base

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    if not (knowledge_dir / "index_store.json").exists():
        return []

    embed_kwargs = {"model": cfg.embedding_model, "api_key": api_key}
    if api_base:
        embed_kwargs["api_base"] = api_base

    Settings.embed_model = OpenAIEmbedding(**embed_kwargs)

    storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
    index = load_index_from_storage(storage_context)

    freshness = _compute_freshness(None, 168.0)

    results: list[SearchResult] = []
    for node in index.as_retriever(similarity_top_k=top_k * 2).retrieve(query):
        source = node.metadata.get("file_name", "unknown")
        score = node.score if hasattr(node, "score") else 0.0
        text = node.text[:500] + "..." if len(node.text) > 500 else node.text
        results.append(SearchResult(source=source, score=score, text=text, freshness=freshness))

    return results


# ─── Classification ──────────────────────────────────────────────────────────


def _keyword_fallback(query: str) -> str:
    """Simple keyword-based classification."""
    result = _quick_structural_check(query)
    return result if result else "semantic"


def _keyword_confidence(query: str) -> tuple[str, float]:
    """Keyword-based classification with confidence score.

    Returns (label, confidence) where confidence is 0.0-1.0.
    Strong phrases get high confidence; weak signals get lower.
    """
    query_lower = query.lower()
    keyword_hits = sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in query_lower)

    has_strong_phrase = any(
        phrase in query_lower for phrase in _STRONG_STRUCTURAL
    )
    has_structural_phrase = any(
        phrase in query_lower
        for phrase in ["connect to", "path from", "depends on", "how does"]
    )
    is_how_do_structural = "how do" in query_lower and any(
        kw in query_lower for kw in ["connect", "link", "relate", "depend", "call"]
    )

    # Compute structural score (0 to 1)
    structural_score = 0.0
    if has_strong_phrase:
        structural_score = 0.95
    elif keyword_hits >= 3:
        structural_score = 0.85
    elif has_structural_phrase:
        structural_score = 0.80
    elif is_how_do_structural:
        structural_score = 0.75
    elif keyword_hits == 2:
        structural_score = 0.65
    elif keyword_hits == 1:
        structural_score = 0.40
    else:
        structural_score = 0.10

    # Semantic score is inverse
    semantic_score = 1.0 - structural_score

    if structural_score >= 0.60:
        return "structural", structural_score
    if structural_score <= 0.20:
        return "semantic", semantic_score
    # Uncertain zone: return semantic with low confidence
    return "semantic", semantic_score


def _classify_query(query: str) -> tuple[str, float]:
    """Classify a query as 'structural' or 'semantic' with confidence.

    Decision chain:
      1. Fast keyword pre-check with confidence (free, handles clear patterns)
      2. Neural classifier (~$0.000001 via query_classifier module)
      3. Keyword fallback for uncertain/edge cases

    Returns:
        (label, confidence) tuple where label is 'structural' or 'semantic'
        and confidence is 0.0-1.0.
    """
    # Normalize query for better classification
    norm_query = normalize_query(query)

    # 1. Quick keyword check with confidence
    label, confidence = _keyword_confidence(norm_query)

    # If high confidence from keywords alone, return early
    if confidence >= 0.75:
        logger.debug("[ROUTER] Keyword classification: %s (confidence=%.2f)", label, confidence)
        return label, confidence

    # 2. Try neural classifier for uncertain cases
    if confidence < 0.75:
        try:
            from mimir.query_classifier import (
                classify_query as _nn_classify,
            )

            nn_label = _nn_classify(norm_query, use_llm_fallback=False)
            # Neural classifier returns label; we assign moderate confidence
            nn_confidence = 0.70 if nn_label == label else 0.60
            logger.info("[ROUTER] Neural classified as: %s", nn_label)
            # If neural agrees with keyword, boost confidence
            if nn_label == label:
                confidence = max(confidence, nn_confidence)
            else:
                # Neural disagrees — trust neural slightly more
                label = nn_label
                confidence = nn_confidence
            return label, confidence
        except Exception:
            logger.debug("[ROUTER] Neural classifier unavailable, using keyword confidence")

    return label, confidence


# ─── Configuration ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RouterConfig:
    """Configuration for the query router — sourced from MimirConfig."""

    enabled: bool = True
    cache_maxsize: int = 128
    cache_ttl_seconds: int = 600
    cache_similarity_threshold: float = 0.92
    circuit_breaker_threshold: int = 3
    circuit_breaker_reset_seconds: int = 60
    search_timeout_seconds: float = 30.0
    max_context_tokens: int = 2500
    top_k: int = 5
    freshness_decay_hours: float = 168.0
    neural_classifier_enabled: bool = True
    classification_model: str = "gpt-3.5-turbo"
    query_normalization_enabled: bool = True
    # Hybrid routing: confidence thresholds for blending graph + vector
    hybrid_confidence_min: float = 0.50   # Below this → vector only
    hybrid_confidence_max: float = 0.85   # Above this → graph only (if hit)

    @classmethod
    def from_mimir_config(cls, config: Optional[MimirConfig] = None) -> RouterConfig:
        """Build RouterConfig from existing MimirConfig using safe getattr."""
        if config is None:
            config = get_config()

        def _get_float(key, default):
            val = getattr(config, key, None)
            return float(val) if val is not None else default

        def _get_bool(key, default):
            val = getattr(config, key, None)
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return default

        return cls(
            enabled=getattr(config, "bridge_enabled", True),
            cache_maxsize=getattr(config, "bridge_cache_maxsize", 128),
            cache_ttl_seconds=getattr(config, "bridge_cache_ttl_seconds", 600),
            cache_similarity_threshold=_get_float(
                "bridge_cache_similarity_threshold", 0.92
            ),
            circuit_breaker_threshold=getattr(
                config, "bridge_circuit_breaker_threshold", 3
            ),
            circuit_breaker_reset_seconds=getattr(
                config, "bridge_circuit_breaker_reset_seconds", 60
            ),
            search_timeout_seconds=getattr(
                config, "bridge_search_timeout_seconds", 30.0
            ),
            max_context_tokens=getattr(config, "bridge_max_context_tokens", 2500),
            top_k=getattr(config, "bridge_top_k", 5),
            freshness_decay_hours=_get_float(
                "bridge_freshness_decay_hours", 168.0
            ),
            neural_classifier_enabled=_get_bool(
                "bridge_classification_enabled", True
            ),
            classification_model=getattr(
                config, "bridge_classification_model", "gpt-3.5-turbo"
            ),
            query_normalization_enabled=_get_bool(
                "bridge_query_normalization_enabled", True
            ),
            hybrid_confidence_min=_get_float(
                "bridge_hybrid_confidence_min", 0.50
            ),
            hybrid_confidence_max=_get_float(
                "bridge_hybrid_confidence_max", 0.85
            ),
        )


# ─── Data Types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutingResult:
    """Result of a routed query."""

    success: bool
    context: str = ""
    results: tuple[SearchResult, ...] = ()
    cache_hit: bool = False
    circuit_open: bool = False
    error: Optional[str] = None
    elapsed_ms: int = 0
    status: str = "ok"
    routed_to: str = ""
    query_type: str = ""
    confidence: float = 0.0  # Classification confidence (0.0-1.0)

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
            "routed_to": self.routed_to,
            "query_type": self.query_type,
            "confidence": round(self.confidence, 3),
        }


# ─── Project Root Detection ──────────────────────────────────────────────────


def _detect_project_root(cwd=None, env_vars=None) -> Path:
    """Detect project root — no dependency on openspace_bridge."""
    import os

    if env_vars is None:
        env_vars = ["PROJECT_ROOT", "WORKSPACE_FOLDER", "VSCODE_CWD"]

    for var in env_vars:
        if path := os.environ.get(var):
            resolved = Path(path).resolve()
            if resolved.exists():
                return resolved

    start = (cwd or Path.cwd()).resolve()
    markers = [".opencode", "opencode.json", ".git", "pyproject.toml", "package.json", "Cargo.toml"]
    current = start
    while current != current.parent:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    return start


# ─── Main Entry Point ─────────────────────────────────────────────────────────


def route_task(
    task: str,
    project_root: Optional[Path] = None,
    top_k: Optional[int] = None,
) -> RoutingResult:
    """Route a task to the most appropriate Mimir backend and return context.

    Flow:
      1. Check for matching pre-compiled artifact (instant, zero token cost)
      2. Check semantic cache (handles paraphrases via embedding similarity)
      3. Classify query with confidence (structural vs semantic)
      4. Route to:
         - graph (structural, high confidence)
         - vector (semantic, or structural with no graph hit)
         - hybrid (both graph + vector, mid-confidence structural)

    Replacement for enrich_task_for_openspace() — no OpenSpace dependency.

    Args:
        task: Task/query description
        project_root: Override project root (auto-detected if None)
        top_k: Number of results (uses config default if None)

    Returns:
        RoutingResult with context ready for prompt injection
    """
    from mimir.config import reset_config

    reset_config()
    config = get_config()
    rc = RouterConfig.from_mimir_config(config)

    if not rc.enabled:
        return RoutingResult(success=False, error="Router disabled", status="disabled")

    project_root = project_root or _detect_project_root()
    k = top_k or rc.top_k

    # Apply query normalization (improves downstream cache + retrieval)
    if rc.query_normalization_enabled:
        task_normalized = normalize_query(task)
    else:
        task_normalized = task

    # Per-project singleton circuit breaker + cache (stored on function object)
    if (
        not hasattr(route_task, "_circuit")
        or getattr(route_task, "_cache_root", None) != project_root
    ):
        route_task._circuit = _CircuitBreakerState()  # type: ignore
        route_task._cache = _SemanticCache(  # type: ignore
            maxsize=rc.cache_maxsize,
            ttl_seconds=rc.cache_ttl_seconds,
            similarity_threshold=rc.cache_similarity_threshold,
        )
        route_task._cache_root = project_root  # type: ignore

    circuit = route_task._circuit  # type: ignore
    cache = route_task._cache  # type: ignore

    if circuit.check(rc.circuit_breaker_reset_seconds):
        return RoutingResult(
            success=False, circuit_open=True,
            error="Circuit breaker open", status="circuit_open"
        )

    # ─── STEP 1: Try pre-compiled artifact first (instant, zero token cost) ───
    artifact_id = _find_matching_artifact(task, project_root)
    if artifact_id:
        artifact_result = _try_artifact(artifact_id, project_root)
        if artifact_result:
            cache.put(task_normalized, k, _to_shim(artifact_result))
            return artifact_result

    # ─── STEP 2: Semantic cache check ───
    cached = cache.get(task_normalized, k)
    if cached is not None and hasattr(cached, "success"):
        logger.info("[ROUTER] Semantic cache hit: %s", task[:50])
        return RoutingResult(
            success=cached.success,
            context=cached.context,
            results=cached.results if hasattr(cached, "results") else (),
            cache_hit=True,
            circuit_open=cached.circuit_open,
            error=cached.error,
            elapsed_ms=0,
            status=cached.status,
            routed_to=cached.routed_to,
        )

    # ─── STEP 3: Classify with confidence ───
    start = time.time()
    query_type, confidence = _classify_query(task) if rc.neural_classifier_enabled else ("semantic", 0.5)
    logger.info(
        "[ROUTER] Query classified as: %s (confidence=%.2f)", query_type, confidence
    )

    routed_to = "none"

    # ─── STEP 4: Route based on classification + confidence ───
    # Hybrid routing: if confidence is in the mid-range, try BOTH graph and vector
    if query_type == "structural" and confidence >= rc.hybrid_confidence_max:
        # High confidence structural → try graph only
        graph_context = _search_graph(task, project_root)
        if graph_context:
            elapsed = int((time.time() - start) * 1000)
            result = RoutingResult(
                success=True,
                context=graph_context,
                query_type="structural",
                routed_to="graph",
                confidence=confidence,
                elapsed_ms=elapsed,
                status="ok",
            )
            circuit.record_success()
            cache.put(task_normalized, k, _to_shim(result))
            logger.info("[ROUTER] Graph path found (%dms)", elapsed)
            return result
        logger.info("[ROUTER] Graph search empty, falling to vector")

    elif query_type == "structural" and rc.hybrid_confidence_min <= confidence < rc.hybrid_confidence_max:
        # Mid-confidence structural → try BOTH graph and vector (hybrid)
        logger.info("[ROUTER] Hybrid routing: mid-confidence structural query")
        graph_context = _search_graph(task, project_root)
        vector_results = _search_raw(task, project_root, k)

        if graph_context and vector_results:
            # Merge: graph context first, then vector results for additional context
            max_chars = rc.max_context_tokens * 4 // max(k, 1) // 2
            chunks = [f"[Graph Context]\n{graph_context}"]

            for r in vector_results:
                src = r.source
                if _is_sensitive(r.text):
                    text = _filter_sensitive(r.text)
                else:
                    text = r.text
                if len(text) > max_chars:
                    text = text[:max_chars] + "..."
                chunks.append(f"[{src}]\n{text}")

            context = "\n\n".join(chunks)
            elapsed = int((time.time() - start) * 1000)
            result = RoutingResult(
                success=True,
                context=context,
                results=tuple(vector_results),
                query_type="hybrid",
                routed_to="hybrid",
                confidence=confidence,
                elapsed_ms=elapsed,
                status="ok",
            )
            circuit.record_success()
            cache.put(task_normalized, k, _to_shim(result))
            logger.info("[ROUTER] Hybrid result (%dms)", elapsed)
            return result

        elif graph_context:
            # Graph only (vector returned nothing)
            elapsed = int((time.time() - start) * 1000)
            result = RoutingResult(
                success=True,
                context=graph_context,
                query_type="structural",
                routed_to="graph",
                confidence=confidence,
                elapsed_ms=elapsed,
                status="ok",
            )
            circuit.record_success()
            cache.put(task_normalized, k, _to_shim(result))
            return result

        # Graph failed, fall through to vector search below
        logger.info("[ROUTER] Graph search empty in hybrid, using vector")

    # Vector search (also covers semantic queries and structural fallback)
    try:
        results = _search_raw(task, project_root, k)
        elapsed = int((time.time() - start) * 1000)

        if not results:
            knowledge_dir = project_root / ".knowledge" / "llamaindex"
            has_index = (knowledge_dir / "index_store.json").exists()
            result = RoutingResult(
                success=has_index,
                query_type=query_type,
                routed_to="vector",
                confidence=confidence,
                elapsed_ms=elapsed,
                status="no_index" if not has_index else "no_results",
                error="No knowledge base index found." if not has_index else None,
            )
        else:
            max_chars = rc.max_context_tokens * 4 // max(k, 1) // 2
            chunks = []
            for r in results:
                src = r.source
                if _is_sensitive(r.text):
                    text = _filter_sensitive(r.text)
                else:
                    text = r.text
                if len(text) > max_chars:
                    text = text[:max_chars] + "..."
                chunks.append(f"[{src}]\n{text}")
            context = "\n\n".join(chunks)

            result = RoutingResult(
                success=True,
                context=context,
                results=tuple(results),
                query_type=query_type,
                routed_to="vector",
                confidence=confidence,
                elapsed_ms=elapsed,
                status="ok",
            )

        circuit.record_success()
        cache.put(task_normalized, k, _to_shim(result))
        return result

    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        circuit.record_failure(rc.circuit_breaker_threshold, rc.circuit_breaker_reset_seconds)
        logger.error("[ROUTER] Search failed: %s", e)
        return RoutingResult(
            success=False, error=str(e), elapsed_ms=elapsed, status="error"
        )


# ─── Cache Compatibility Shim ─────────────────────────────────────────────────


class _EnrichmentShim:
    """Wraps RoutingResult to match old EnrichmentResult interface for cache storage."""

    def __init__(self, result: RoutingResult):
        self.success = result.success
        self.context = result.context
        self.results = result.results
        self.cache_hit = result.cache_hit
        self.circuit_open = result.circuit_open
        self.error = result.error
        self.elapsed_ms = result.elapsed_ms
        self.status = result.status
        self.routed_to = result.routed_to
        self.query_type = result.query_type
        self.confidence = getattr(result, "confidence", 0.0)


def _to_shim(result: RoutingResult) -> _EnrichmentShim:
    """Wrap RoutingResult for cache compatibility."""
    return _EnrichmentShim(result)


# ─── Backward Compatibility ───────────────────────────────────────────────────


def enrich_task_for_openspace(task: str, project_root: Optional[Path] = None) -> dict:
    """Drop-in replacement: same function name, same return shape, no OpenSpace."""
    result = route_task(task, project_root=project_root)
    return result.to_dict()


def get_bridge(project_root: Optional[Path] = None):
    """Stub for compatibility — returns None since bridge no longer wraps state."""
    return None