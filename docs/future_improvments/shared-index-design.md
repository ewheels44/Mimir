# Shared Index Composition — Design Document

**Status:** Future Implementation (Tabled)
**Date:** 2026-04-06
**Author:** Design conversation with OpenAgent
**Priority:** High for FDE workflow scalability

---

## Problem Statement

Mimir currently indexes one project at a time. Each project gets its own `.knowledge/llamaindex/` vector index. When an FDE (Forward Deployed Engineer) needs to integrate a large SDK (e.g., LiveKit) into a customer's codebase, they face two problems:

1. **Redundant indexing** — LiveKit's SDK is massive. Re-indexing it for every customer engagement wastes time and embedding API costs.
2. **No cross-codebase search** — The FDE can't query "how does LiveKit's auth work?" and "where is the customer's auth code?" in a single search. They must manually switch between knowledge bases.

### The FDE Use Case

An FDE working for LiveKit needs to:
- Reference LiveKit's SDK patterns (indexed once, reused across engagements)
- Understand a customer's existing codebase (indexed per engagement)
- Bridge the two: "How do I integrate LiveKit's voice pipeline into this customer's Express.js app?"

Today this requires:
```bash
# Customer project
cd ~/customer-project
python .opencode/mimir-index.py

# Then manually look up LiveKit docs separately
sdk_cache_get(library="livekit", topic="agents")
# Or worse: --add the entire LiveKit SDK into the customer's index every time
```

The `--add` approach doesn't scale. LiveKit's SDK is huge, and re-indexing it for every customer is wasteful.

---

## Proposed Solution: Option C — Shared Index Composition

### Architecture

```
~/.mimir/shared-indexes/                    ← Global shared store (indexed ONCE)
├── livekit-sdk@1.2/
│   └── llamaindex/
├── livekit-sdk@2.0/
│   └── llamaindex/
└── openai-sdk/
    └── llamaindex/

~/customer-a/
├── .mimir/config.json
│   └── shared_indexes: { "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk@1.2/llamaindex" }
└── .knowledge/llamaindex/                  ← Customer code only

~/customer-b/
├── .mimir/config.json
│   └── shared_indexes: { "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk@2.0/llamaindex" }
└── .knowledge/llamaindex/                  ← Customer code only
```

### How It Works

1. **Index shared SDK once** — stored globally in `~/.mimir/shared-indexes/`
2. **Reference from project config** — each project declares which shared indices it uses
3. **Query all indices simultaneously** — local + shared, merged by score
4. **Source tag every result** — `[YOUR CODE]` vs `[LIVEKIT SDK]` so the LLM never confuses them

### Query Flow

```
Query: "use livekit agents to build a voice AI"
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Parallel Retrieval                                      │
│                                                          │
│  Local index:                                            │
│    [0.82] src/auth/middleware.ts — JWT validation        │
│    [0.71] src/api/voice.ts — existing voice endpoint     │
│                                                          │
│  LiveKit shared index:                                   │
│    [0.91] agents/voice_pipeline.py — STT→LLM→TTS        │
│    [0.88] agents/room.py — WebRTC room management       │
│    [0.79] agents/token.py — AccessToken permissions     │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Merge by Score + Source Tag                             │
│                                                          │
│  [0.91] [LIVEKIT SDK] agents/voice_pipeline.py          │
│  [0.88] [LIVEKIT SDK] agents/room.py                    │
│  [0.82] [YOUR CODE] src/auth/middleware.ts               │
│  [0.79] [LIVEKIT SDK] agents/token.py                   │
│  [0.71] [YOUR CODE] src/api/voice.ts                    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
  LLM synthesizes answer with clear distinction between
  "what LiveKit provides" and "what the customer has"
```

---

## Implementation Details

### New File: `src/mimir/shared_index.py`

```python
class SharedIndexRegistry:
    """Lazy-loading registry for shared indices."""
    
    def __init__(self, shared_configs: dict[str, Path], embedding_model: str):
        self._configs = shared_configs
        self._embedding_model = embedding_model
        self._indices: dict[str, VectorStoreIndex] = {}
        self._loaded: set[str] = set()
    
    def get(self, name: str) -> Optional[VectorStoreIndex]:
        """Load and cache a shared index by name."""
        if name in self._loaded:
            return self._indices.get(name)
        
        path = self._configs.get(name)
        if not path or not (path / "index_store.json").exists():
            print(f"⚠️  Shared index '{name}' not found at {path}, skipping")
            return None
        
        # Validate embedding model match
        manifest = self._load_manifest(path)
        if manifest.get("embedding_model") != self._embedding_model:
            raise ValueError(
                f"Shared index '{name}' uses {manifest['embedding_model']} "
                f"but project uses {self._embedding_model}. "
                f"Re-index one to match."
            )
        
        self._indices[name] = load_index_from_storage(
            StorageContext.from_defaults(persist_dir=str(path))
        )
        self._loaded.add(name)
        return self._indices[name]
    
    def get_all(self) -> dict[str, VectorStoreIndex]:
        """Load all configured shared indices."""
        for name in self._configs:
            self.get(name)
        return dict(self._indices)
    
    def available(self) -> list[str]:
        """List names of configured shared indices."""
        return list(self._configs.keys())


def merge_results(nodes_by_index: dict[str, list], top_k: int) -> list:
    """Merge results from multiple indices by score.
    
    Assumes same embedding model across all indices (scores comparable).
    Tags each node with _source metadata.
    """
    all_nodes = []
    for source, nodes in nodes_by_index.items():
        for node in nodes:
            node.metadata["_source"] = source
            all_nodes.append(node)
    
    all_nodes.sort(key=lambda n: n.score or 0, reverse=True)
    return all_nodes[:top_k]


def format_tagged_results(nodes) -> str:
    """Format results with source tags for LLM consumption."""
    formatted = []
    for i, node in enumerate(nodes, 1):
        source = node.metadata.get("_source", "unknown")
        if source == "local":
            tag = "[YOUR CODE]"
        elif source.startswith("shared:"):
            tag = f"[{source.replace('shared:', '').upper()} SDK]"
        else:
            tag = f"[{source.upper()}]"
        
        file_name = node.metadata.get("file_name", "unknown")
        score = node.score if hasattr(node, "score") else 0.0
        text = node.text[:500] + "..." if len(node.text) > 500 else node.text
        formatted.append(f"[{i}] {tag} {file_name} (score: {score:.3f})\n{text}")
    
    return "\n\n".join(formatted)


def validate_scope(scope: str, available: list[str]) -> tuple[bool, str]:
    """Validate scope parameter against available indices.
    
    Returns (is_valid, error_message).
    """
    if scope == "all":
        return True, ""
    if scope == "local":
        return True, ""
    if scope.startswith("shared:"):
        name = scope.replace("shared:", "")
        if name in available:
            return True, ""
        return False, f"Unknown shared index '{name}'. Available: {', '.join(available)}"
    return False, f"Invalid scope '{scope}'. Use 'all', 'local', or 'shared:{{name}}'"
```

### Modifications to `mcp_server_llamaindex.py`

#### `ServerConfig` — Add shared indexes

```python
@dataclass(frozen=True)
class ServerConfig:
    project_root: Path
    knowledge_dir: Path
    docs_dir: Path
    code_dirs: list[Path]
    embedding_model: str
    api_key: str
    api_base: Optional[str]
    shared_indexes: dict[str, Path]  # NEW

    @classmethod
    def from_env(cls) -> "ServerConfig":
        # ... existing code ...
        
        # Parse shared_indexes from config
        shared_indexes = {}
        raw_shared = project_config.get("shared_indexes", {})
        for name, path_str in raw_shared.items():
            path = Path(path_str).expanduser()
            shared_indexes[name] = path
        
        return cls(
            # ... existing fields ...
            shared_indexes=shared_indexes,
        )
```

#### `KnowledgeServer` — Multi-index support

```python
class KnowledgeServer:
    def __init__(self, config: ServerConfig):
        # ... existing init ...
        self._shared_registry = SharedIndexRegistry(
            config.shared_indexes,
            config.embedding_model,
        )
    
    def search(self, query: str, top_k: int = 5, scope: str = "all") -> str:
        start_time = time.time()
        
        # Validate scope
        available = self._shared_registry.available()
        is_valid, error = validate_scope(scope, available)
        if not is_valid:
            return error
        
        # Collect results from requested indices
        nodes_by_index = {}
        
        if scope in ("all", "local"):
            index = self.get_index()
            if index:
                nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
                nodes_by_index["local"] = nodes
        
        if scope == "all" or scope.startswith("shared:"):
            for name, index in self._shared_registry.get_all().items():
                if scope == "all" or scope == f"shared:{name}":
                    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
                    nodes_by_index[f"shared:{name}"] = nodes
        
        if not nodes_by_index:
            return "No knowledge base found."
        
        # Merge and format
        merged = merge_results(nodes_by_index, top_k)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Track metrics
        tracker = get_tracker(self.config.project_root)
        tracker.record_query(
            query_type="search",
            query_text=query,
            docs_retrieved=len(merged),
            duration_ms=duration_ms,
        )
        
        return format_tagged_results(merged)
    
    def get_stats(self) -> dict:
        stats = {
            # ... existing fields ...
            "shared_indexes": {},
        }
        
        for name in self._shared_registry.available():
            path = self._config.shared_indexes[name]
            exists = (path / "index_store.json").exists()
            stats["shared_indexes"][name] = {
                "path": str(path),
                "exists": exists,
            }
        
        return stats
```

#### MCP Tools — Add scope parameter

```python
@mcp.tool()
async def search(query: str, top_k: int = 5, scope: str = "all") -> str:
    """Search the project knowledge base using semantic similarity.
    
    Args:
        query: Search query string
        top_k: Number of results to return (default: 5)
        scope: Search scope - "all" (default), "local", or "shared:{name}"
    """
    return server.search(query, top_k, scope)

@mcp.tool()
async def enrich_task(task: str, top_k: int = 5, scope: str = "all") -> str:
    """Search Mimir for project context relevant to an OpenSpace task.
    
    Args:
        task: Task description in natural language
        top_k: Number of context chunks to retrieve (default: 5)
        scope: Search scope - "all" (default), "local", or "shared:{name}"
    """
    # ... existing logic with scope passed through ...
```

#### CLI — Shared index management

```python
parser.add_argument(
    "--shared-index", metavar="DIR",
    help="Index a directory as a shared reference index"
)
parser.add_argument(
    "--shared-name", metavar="NAME",
    help="Name for the shared index (used with --shared-index)"
)
parser.add_argument(
    "--shared-list", action="store_true",
    help="List available shared indices"
)

# In main():
if args.shared_index:
    name = args.shared_name or Path(args.shared_index).name
    shared_dir = Path.home() / ".mimir" / "shared-indexes" / name / "llamaindex"
    shared_dir.mkdir(parents=True, exist_ok=True)
    
    source_dir = Path(args.shared_index)
    print(f"Indexing {source_dir} as shared index '{name}'...")
    # Use index_with_progress with shared_dir as knowledge_dir
    # Store embedding_model in manifest for validation
    ...
    return

if args.shared_list:
    shared_base = Path.home() / ".mimir" / "shared-indexes"
    if not shared_base.exists():
        print("No shared indices found.")
        return
    
    for d in sorted(shared_base.iterdir()):
        if (d / "llamaindex" / "index_store.json").exists():
            print(f"  ✓ {d.name}")
        else:
            print(f"  ✗ {d.name} (incomplete)")
    return
```

---

## Config Schema

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small",
  "shared_indexes": {
    "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex",
    "openai-sdk": "~/.mimir/shared-indexes/openai-sdk/llamaindex"
  }
}
```

---

## CLI Usage

```bash
# Index a shared SDK (once, globally)
python mcp_server_llamaindex.py --shared-index ~/LiveKit_test/sdk/ --name livekit-sdk

# List available shared indices
python mcp_server_llamaindex.py --shared-list

# In a project, add to .mimir/config.json:
# "shared_indexes": { "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex" }

# Then search with scope
# (via MCP tool)
search(query="voice pipeline", scope="all")           # default
search(query="voice pipeline", scope="local")          # customer code only
search(query="voice pipeline", scope="shared:livekit-sdk")  # LiveKit only
```

---

## Safeguards (Must-Have for v1)

### 1. Embedding Model Validation

At load time, compare shared index embedding model to local project's model. Error if mismatch.

```python
# In SharedIndexRegistry.get()
manifest = self._load_manifest(path)
if manifest.get("embedding_model") != self._embedding_model:
    raise ValueError(
        f"Shared index '{name}' uses {manifest['embedding_model']} "
        f"but project uses {self._embedding_model}. Re-index one to match."
    )
```

**Why:** Different embedding models produce incompatible vector spaces. Merging scores from different models produces meaningless rankings.

### 2. Graceful Missing Index

If a shared index path doesn't exist, warn and skip. Don't crash.

```python
if not path or not (path / "index_store.json").exists():
    print(f"⚠️  Shared index '{name}' not found at {path}, skipping")
    return None
```

**Why:** User might have config referencing a shared index they haven't created yet, or path changed.

### 3. Scope Validation

If scope param doesn't match any known index, return helpful error with available options.

```python
is_valid, error = validate_scope(scope, available)
if not is_valid:
    return error  # "Unknown shared index 'livikit'. Available: livekit-sdk, openai-sdk"
```

**Why:** Typos in scope names would silently return empty results. Better to fail loud.

---

## Known Problems and Future Considerations

### Versioned Shared Indices

Different customers may use different SDK versions. Design supports this via directory naming:

```
~/.mimir/shared-indexes/
├── livekit-sdk@1.2/llamaindex/
├── livekit-sdk@2.0/llamaindex/
```

Config references specific version:
```json
{
  "shared_indexes": {
    "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk@1.2/llamaindex"
  }
}
```

### Stale Index Detection

Store a hash of the source directory at index time. On query, optionally check if source has changed since last index. Not critical for v1.

### Memory Pressure

Each shared index loads into memory. For FDE use case (2-3 shared indices), this is fine. For power users with 10+, implement eviction:

```python
def evict(self, name: str):
    if name in self._indices:
        del self._indices[name]
        self._loaded.discard(name)
```

### Overlap Detection

Warn if shared index source path overlaps with local code_dirs. Prevents duplicate results.

### Score Normalization

Assumes same embedding model across all indices (enforced by validation). Scores are comparable via cosine similarity. Document this assumption.

### MCP Schema Backward Compatibility

`scope` parameter is optional with default `"all"`. Existing callers that don't pass `scope` get the old behavior. Fully backward compatible.

---

## Why Not Other Approaches

### Option A: ComposableGraph / RouterQueryEngine

Uses LlamaIndex's built-in multi-index routing. Adds an LLM call to decide which index to query.

**Rejected because:**
- Extra LLM call per query (cost, latency)
- Router might choose wrong index
- Overkill for "search all, merge by score"

### Option B: Merge-at-Index-Time

Copy shared index docs into every project's local index via `--add`.

**Rejected because:**
- Duplicates shared docs in every project
- Large SDKs bloat every project's index
- Version tracking nightmare

### Option C: Shared Index Composition (Chosen)

Query all indices in parallel, merge by score, tag source.

**Chosen because:**
- No duplication — shared indices indexed once
- No extra LLM calls — deterministic merge by score
- Source tagging — LLM can distinguish reference from local
- Scoped search — explicit control over what's queried
- Simple mental model

---

## When to Build This

This feature becomes critical when:
1. FDE engagements become frequent (3+ customers)
2. SDKs being integrated are large (10K+ files)
3. Manual `--add` per engagement becomes a bottleneck
4. Cross-codebase questions become common ("how does X work in SDK vs customer code?")

---

## Related Skills (Post-Implementation)

Once built, create a skill for FDE workflow:

**Skill: `shared-index-setup`**
- Guide for indexing a shared SDK
- Guide for configuring a project to reference it
- Guide for using scoped search in integration tasks
- Examples of cross-codebase queries

---

## Summary

| Aspect | Detail |
|--------|--------|
| **Problem** | Can't efficiently reference large SDKs across multiple customer engagements |
| **Solution** | Shared indices stored globally, referenced per-project, queried together |
| **Key Innovation** | Source tagging + scoped search — LLM always knows what's reference vs local |
| **Effort** | ~300 lines Python, mostly in new `shared_index.py` + modifications to `mcp_server_llamaindex.py` |
| **Dependencies** | LlamaIndex (already used), no new external deps |
| **Risk** | Low — backward compatible, optional feature, graceful degradation |
