# Mimir Module API Reference

This document provides the authoritative API reference for all Mimir modules.
All documentation here matches the actual codebase implementation.

## Module Overview

| Module | Type | Key Exports | Purpose |
|--------|------|--------------|---------|
| `config.py` | Class-based | `MimirConfig`, `get_config()`, `reset_config()` | Unified configuration |
| `indexing.py` | Function-based | `compute_file_hash()`, `add_to_manifest()`, `incremental_reindex()` | Document indexing |
| `artifacts.py` | Function-based | `create_artifact()`, `get_artifact()`, `load_manifest()` | Pre-compiled artifacts |
| `knowledge_graph.py` | Class + functions | `CombinedExtractor`, `extract_code_relationships()`, `incremental_graph_update()` | Code relationships |
| `metrics.py` | Class-based | `TokenTracker`, `MetricsTracker`, `QueryMetrics`, `TokenUsage` | Cost/token tracking |
| `sdk_cache.py` | Class-based | `SDKCache` | SDK documentation cache |
| `shared_index.py` | Class + functions | `SharedIndexRegistry`, `merge_results()`, `format_tagged_results()` | Cross-codebase search |
| `watcher.py` | Class + functions | `MimirFileWatcher`, `detect_changed_files()`, `incremental_reindex()` | File watcher |
| `openspace_bridge.py` | Class + functions | `MimirOpenSpaceBridge`, `enrich_task_for_openspace()` | OpenSpace integration (deprecated - uses query_router) |
| `query_classifier.py` | Class + functions | `SimpleQueryClassifier`, `classify_query()`, `extract_features()` | Neural query classification |
| `query_router.py` | Class + functions | `RouterConfig`, `RoutingResult`, `enrich_task_for_openspace()` | Query routing |

---

## Detailed Module APIs

### `config.py` - Unified Configuration

**Classes:**
- `MimirConfig` - Immutable configuration dataclass

**Functions:**
- `get_config(**kwargs) -> MimirConfig` - Get or create singleton config
- `reset_config() -> None` - Reset singleton (useful for testing)

**Usage:**
```python
from mimir.config import MimirConfig, get_config

# Load config (auto-detects project root, API key, etc.)
config = MimirConfig.load()

# Or use singleton
config = get_config()

# Access settings
config.api_key
config.embedding_model
config.llm_model
config.docs_dir
config.knowledge_dir
config.code_dirs
```

**Configuration Resolution Order:**
1. Environment variables
2. `.mimir/config.json` (project-level)
3. Defaults

---

### `indexing.py` - Document Indexing

**Functions:**
- `compute_file_hash(file_path: Path) -> str` - SHA-256 hash of file
- `add_to_manifest(...)` - Track indexed files
- `add_file_to_index(...)` - Index single file
- `add_directory_with_progress(...)` - Index directory with progress bar
- `incremental_reindex(...)` - Reindex only changed files
- `backup_index(...)` - Backup existing index

**Note:** This module is function-based, not class-based.

---

### `artifacts.py` - Pre-compiled Artifacts

**Functions:**
- `create_artifact(name, content, depends_on, ...)` - Create new artifact
- `get_artifact(name) -> dict` - Load artifact from disk
- `delete_artifact(name)` - Remove artifact
- `list_artifacts() -> list` - List all artifacts
- `load_manifest() -> dict` - Load artifact manifest
- `save_manifest(manifest)` - Save artifact manifest
- `compute_file_hash(path) -> str` - Hash for dependency tracking
- `compute_source_hashes(files) -> dict` - Batch hash computation
- `invalidate_artifact(name)` - Mark artifact as stale
- `invalidate_artifacts_for_file(file_path)` - Invalidate all artifacts depending on a file
- `rebuild_artifact(name)` - Rebuild stale artifact

**Manifest Structure:**
```json
{
  "artifacts": {
    "artifact_name": {
      "path": "/path/to/artifact.json",
      "version": "1.0.0",
      "depends_on": ["/path/to/source1.py", ...],
      "source_hashes": {"/path/to/source1.py": "abc123..."},
      "last_built": "2026-05-21T14:00:00.000000",
      "stale": false,
      "invalidated_at": null,
      "ttl_seconds": 3600,
      "eager_rebuild": false
    }
  },
  "schema_version": "1.0",
  "last_updated": "2026-05-21T14:00:00.000000"
}
```

**Note:** This module is function-based. There is no `ArtifactManager` class.

---

### `knowledge_graph.py` - Code Relationship Extraction

**Classes:**
- `Relationship` - Represents a code relationship (source, target, relation_type)
- `CodeEntity` - Represents a code entity (file, type, name)
- `PythonASTExtractor` - AST-based relationship extractor
- `TreeSitterExtractor` - Tree-sitter based extractor (multi-language)
- `CombinedExtractor` - Combines AST + tree-sitter extractors

**Functions:**
- `extract_code_relationships(output_dir, ...)` - Main extraction function
- `incremental_graph_update(output_dir, changed_files, ...)` - Update graph incrementally
- `save_to_file(extractor, output_path)` - Save relationships to JSON

**Output Structure (`code_relationships.json`):**
```json
{
  "relationships": [
    {
      "source": "file1.py",
      "target": "file2.py",
      "relation_type": "imports_module",
      "metadata": {"line": 10, "asname": null}
    }
  ],
  "entities": [
    {
      "file": "file1.py",
      "type": "module",
      "name": "file1"
    }
  ]
}
```

**Note:** Uses `entities` and `relationships`, NOT `nodes` and `edges`.

---

### `metrics.py` - Cost/Token Tracking

**Classes:**
- `TokenUsage` - Token count dataclass (prompt, completion, total)
- `TokenTracker` - Tracks token usage per component
- `QueryMetrics` - Metrics for a single query
- `MetricsTracker` - Aggregates metrics across queries

**Functions:**
- `format_report(metrics) -> str` - Format metrics as human-readable string
- `get_summary() -> dict` - Get summary of all tracked metrics

**Usage:**
```python
from mimir.metrics import TokenTracker, QueryMetrics

tracker = TokenTracker()
metrics = QueryMetrics(query="...", tokens_used=100, cost_usd=0.001)
tracker.record_query(metrics)
```

---

### `sdk_cache.py` - SDK Documentation Cache

**Classes:**
- `SDKCache` - Main cache class

**Functions:**
- `main()` - CLI entry point

**Usage:**
```python
from mimir.sdk_cache import SDKCache

cache = SDKCache()
docs = cache.get("stripe", topic="checkout sessions")
cache.list_cached()
```

---

### `shared_index.py` - Cross-Codebase Search

**Classes:**
- `TaggedNode` - Node with source tag (local vs shared)
- `SharedIndexRegistry` - Manages shared index references

**Functions:**
- `merge_results(local_results, shared_results) -> list` - Merge search results with source tags
- `format_tagged_results(results) -> str` - Format results with source labels
- `validate_scope(scope) -> bool` - Validate search scope string

**Usage:**
```python
from mimir.shared_index import SharedIndexRegistry, merge_results

registry = SharedIndexRegistry()
registry.add("acme-sdk", "/path/to/shared/index")
results = registry.search("voice pipeline", scope="all")
```

---

### `watcher.py` - File Watcher

**Classes:**
- `MimirFileWatcher` - Watchdog-based file watcher

**Functions:**
- `detect_changed_files(last_index_time, ...)` - Detect files changed since last index
- `incremental_reindex(...)` - Reindex changed files
- `invalidate_artifacts_for_file(file_path)` - Invalidate affected artifacts

**Usage:**
```python
from mimir.watcher import MimirFileWatcher, detect_changed_files

watcher = MimirFileWatcher(project_root, callback=...)
watcher.start()

# Or use functional API
changed = detect_changed_files(last_index_time, code_dirs)
```

---

### `openspace_bridge.py` - OpenSpace Integration (Deprecated)

**Classes:**
- `BridgeConfig` - Bridge configuration
- `EnrichmentResult` - Result from enrichment
- `MimirOpenSpaceBridge` - Main bridge class

**Functions:**
- `enrich_task_for_openspace(task_description) -> dict` - Main entry point
- `get_bridge() -> MimirOpenSpaceBridge` - Get singleton bridge instance

**Note:** This module is deprecated. The Query Router (`query_router.py`) is the new standalone implementation.

---

### `query_classifier.py` - Neural Query Classifier

**Classes:**
- `SimpleQueryClassifier` - 10→8→2 neural network for query classification

**Functions:**
- `classify_query(query) -> tuple[str, float]` - Classify a query (type, confidence)
- `extract_features(query) -> list[float]` - Extract features for classification
- `get_savings_report() -> dict` - Get cost savings statistics

**Usage:**
```python
from mimir.query_classifier import SimpleQueryClassifier, classify_query

classifier = SimpleQueryClassifier()
query_type, confidence = classify_query("How does auth work?")
# Returns: ("semantic", 0.95)
```

**Model:** Stored in `query_classifier_model.pkl` (1.1KB)

---

### `query_router.py` - Query Router

**Classes:**
- `RouterConfig` - Router configuration
- `RoutingResult` - Result from routing decision
- `SearchResult` - Search result with metadata

**Functions:**
- `enrich_task_for_openspace(task_description) -> dict` - Main entry point (replaces OpenSpace bridge)
- `get_config() -> RouterConfig` - Get router config
- `get_bridge() -> QueryRouter` - Get router instance (internal)

**Usage:**
```python
from mimir.query_router import enrich_task_for_openspace

result = enrich_task_for_openspace("Implement JWT auth")
# Returns: {"status": "routed", "query_type": "semantic", ...}
```

**Decision Chain:**
1. Keyword pre-check (free) - 2+ structural keywords → instant routing
2. Neural classifier (~$0.000001) - handles uncertain cases
3. Keyword fallback (free) - final deterministic check

**Guardrails:**
- Circuit breaker: 3 failures → 60s cooldown
- LRU cache: 128 entries, 10min TTL
- Content filter: blocks sensitive data
- Freshness scoring: exponential decay over 168h

---

## API Pattern Summary

Mimir uses mixed API patterns:

**Class-based modules** (instantiate a class):
- `config.py` - `MimirConfig`
- `metrics.py` - `TokenTracker`, `MetricsTracker`
- `sdk_cache.py` - `SDKCache`
- `watcher.py` - `MimirFileWatcher`
- `knowledge_graph.py` - `CombinedExtractor`

**Function-based modules** (call functions directly):
- `indexing.py` - `compute_file_hash()`, etc.
- `artifacts.py` - `create_artifact()`, etc.
- `shared_index.py` - `merge_results()`, etc.

**Hybrid modules** (both classes and functions):
- `knowledge_graph.py` - `CombinedExtractor` class + `extract_code_relationships()` function
- `watcher.py` - `MimirFileWatcher` class + `detect_changed_files()` function
- `openspace_bridge.py` - `MimirOpenSpaceBridge` class + `enrich_task_for_openspace()` function
- `query_router.py` - `RouterConfig` class + `enrich_task_for_openspace()` function

---

## Import Path Notes

When importing from project root, add `src/` to Python path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mimir.config import MimirConfig
from mimir.artifacts import get_artifact
```

Or use `pip install -e .` with proper `pyproject.toml` configuration.
