# Knowledge Graph Impact Analysis — Design Discussion

> **Status**: Tabled for future implementation
> **Date**: 2026-04-06
> **Context**: Exploration of whether Mimir's current knowledge graph understands node relationships and can track the impact of changes across files and systems.

---

## Current State of Mimir's Graph

Mimir has **two separate systems** that each understand some relationships, but neither provides true dependency-aware impact analysis.

### 1. LlamaIndex Vector Store

**Location**: `.knowledge/llamaindex/`
**Documents indexed**: 213 (docs + code across 10,429 source files)

- Pure **semantic similarity** — finds chunks that look related by embedding distance
- No structural understanding of imports, dependencies, or call chains
- `search("auth patterns")` returns textually similar chunks — it doesn't know that `auth/middleware.py` imports from `auth/service.py`
- Updated incrementally by the file watcher via SHA-256 hash comparison

### 2. Code Relationships Extractor

**Location**: `src/mimir/knowledge_graph.py`
**Output**: `.knowledge/code_relationships.json`

Extracts structural relationships from source code using AST parsing (Python) and tree-sitter (TS/JS/Rust/Go):

| Relationship Type | What It Tracks |
|---|---|
| `imports_module` | `import foo` / `use foo::bar` |
| `imports_from` | `from foo import bar` |
| `inherits_from` | Class inheritance / trait implementations |
| `calls` | Function/method call expressions |
| `has_method` | Class → method containment |

Also tracks **entities** (classes, methods, functions, structs, interfaces) with file paths and line numbers.

### 3. File Watcher

**Location**: `src/mimir/watcher.py`

- Uses `watchdog` to detect file changes (create, modify, delete, move)
- Debounced at 2s for vector reindex, 5s for graph update
- Triggers both `incremental_reindex` (vector store) and `incremental_graph_update` (code relationships)
- Changes detected via SHA-256 hashing in `.mimir/index_state.json`

### 4. Rust Web Server Graph

**Location**: `web/server/src/graph.rs`

- Reads `docstore.json` and builds a graph for the web UI
- Annotates code nodes with child counts (functions, classes)
- Uses mtime-based cache key for auto-detection of changes

---

## The Gap: What's Missing

The building blocks exist, but there's no layer that answers: **"If I change X, what's affected?"**

Specifically:

1. **No reverse dependency tracking** — The graph knows `A imports B`, but there's no query for "what depends on B?"
2. **No cross-system linking** — The vector store and code relationships graph are updated independently. No mapping between doc chunks and code entities.
3. **No impact analysis tool** — No command to take a file/function and walk the graph to find downstream consumers.
4. **No semantic change detection** — The watcher detects file modifications but doesn't analyze what changed (renamed API vs. typo fix).

---

## Proposed Implementation

### What Would Be Built

1. **Reverse dependency index** — Invert the existing relationship edges to enable "who imports me?" queries
2. **Transitive dependency walker** — Recursively follow the graph to find all downstream effects
3. **Stale doc detection** — Flag documentation chunks when their source files change (metadata lookup, no graph walking)
4. **Impact query interface** — Something like `mimir_impact(file="src/auth/service.py", symbol="login")`

### Existing Data That Enables This

The `code_relationships.json` already contains the raw edges. The `incremental_graph_update` function already handles add/modify/delete operations on the graph. The watcher already detects changes. The missing piece is the query/analysis layer on top.

---

## Problems and Drawbacks

### 1. False Positives Will Erode Trust

Static analysis is inherently noisy:

- **Shallow call resolution** — The extractor records that file A calls `process()`, but doesn't resolve which `process()`. If five modules export that name, the graph says A depends on all of them.
- **Dynamic imports are invisible** — `importlib.import_module(f"plugins.{name}")`, `__getattr__`, lazy loading, plugin systems — none of these appear in the graph.
- **Re-exports and barrel files** — `from auth import login` might come from `auth/__init__.py` re-exporting `auth/service.py`. The graph sees the surface import, not the transitive chain.

**Risk**: "This change affects 12 files!" → 9 are false alarms → users stop trusting the tool.

### 2. Graph Staleness Between Watcher Runs

- **Branch switching** — `git checkout feature-x` changes dozens of files. The incremental update processes files one-by-one. A crash mid-update leaves the graph half-old, half-new. Silent corruption.
- **Merge conflicts** — Post-merge, the graph reflects the result, but logical dependencies may have changed in ways the extractor doesn't detect.
- **External dependencies** — The graph tracks `import stripe` but has no concept of Stripe API versions or breaking changes.

### 3. Performance at Scale

Current scale is fine (213 docs, ~10K files). Concerns emerge with:

- **Reverse index maintenance** — Inverting edges on every query, or maintaining a second index that doubles storage and update complexity.
- **Transitive closure explosion** — Walking the graph recursively for a utility module touched by everything could return the entire codebase.
- **Vector store re-embedding** — Enriching document metadata with graph relationships means re-indexing when the graph changes.

### 4. Uneven Language Coverage

| Language | Method | Reliability |
|----------|--------|-------------|
| Python | `ast` module | **High** — built-in, accurate |
| TypeScript/JS | tree-sitter | **Medium** — misses dynamic requires, no `node_modules` resolution |
| Rust | tree-sitter | **Medium** — handles `use`/`impl`, macro-generated code invisible |
| Go | tree-sitter | **Low-Medium** — interface satisfaction not tracked |

Mixed-language projects get an unevenly reliable graph. Users won't know which edges to trust.

### 5. The "So What?" Problem

Even with a perfect graph, structural dependencies ≠ broken code:

- **Signature change** → 8 files call it → 7 pass the same args → only 1 breaks
- **Return type change** → graph can't tell if callers care about the shape
- **Behavior change, same interface** → graph sees zero impact, runtime behavior changes everywhere

Static analysis tells you **structural** dependencies, not **semantic** ones. The gap between "these files are connected" and "these files will break" is where most of the value lives, and it's the hardest part to solve.

### 6. Maintenance Burden

- **tree-sitter grammar updates** — Node types change between versions. The extractor hardcodes types like `"import_statement"`. A grammar update can silently break extraction with no errors — just missing relationships.
- **New language patterns** — Python 3.12 type parameter syntax, newer TS features — edge cases accumulate over time.
- **Two systems to keep in sync** — Vector store and code graph are updated independently by the watcher. If one fails and the other succeeds, you have inconsistent state with no error signal.

---

## Recommended Approach (When Resuming)

Start narrow, earn trust, then expand:

### Phase 1: Simple Reverse Lookup
- Build "who imports me?" by reversing `imports_module` / `imports_from` edges
- Python only (most reliable extractor)
- Fast, low-risk, high signal

### Phase 2: Stale Doc Detection
- When a file changes, flag documentation chunks whose `file_path` metadata matches
- No graph walking needed — just a metadata lookup
- Immediate value for documentation maintenance

### Phase 3: Explicit Dependency Traces
- Let users ask "trace dependencies for `src/auth/service.py`"
- Show the chain with confidence scores per edge
- Don't try to answer "what breaks?" automatically — show the data and let humans decide

### Phase 4: Impact Analysis (If Phase 1-3 Earn Trust)
- Transitive closure with depth limits
- Heuristic filtering (ignore test files, ignore type-only imports)
- Integration with git diff to show "what changed" alongside "what's connected"

---

## Key Files for Reference

| File | Purpose |
|------|---------|
| `src/mimir/knowledge_graph.py` | Relationship extraction (Python AST + tree-sitter) |
| `src/mimir/indexing.py` | Vector store indexing with incremental updates |
| `src/mimir/watcher.py` | File system watcher triggering reindex + graph updates |
| `web/server/src/graph.rs` | Rust web server graph loading and caching |
| `.knowledge/code_relationships.json` | Extracted relationship data |
| `.knowledge/llamaindex/manifest.json` | Index manifest with file listings |
| `.mimir/index_state.json` | SHA-256 hashes for change detection |

---

## Summary

Mimir has the **raw data** (code relationships, vector embeddings, file change detection) but lacks the **analysis layer** to answer impact questions. The main risks are false positives from shallow static analysis, graph staleness during branch operations, uneven language coverage, and the fundamental gap between structural dependencies and actual breakage. A phased approach starting with simple reverse lookups and stale doc detection is recommended over building a full impact analysis system upfront.
