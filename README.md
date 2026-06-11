# Mimir — Persistent Knowledge Base for AI Agents

A semantic knowledge base that gives AI agents instant access to your codebase, eliminating repeated discovery and context loss between sessions.

**Now embedded directly in [ecode](https://github.com/ewheels44/ecode) (a fork of [Jcode](https://github.com/1jehuang/jcode)) — no MCP server needed.**

---

## What is Mimir?

**The Problem**: Every session, AI agents re-discover the same codebase patterns. 30% of context is wasted on exploration. Knowledge is lost between sessions.

**The Solution**: Mimir indexes your docs and code once. Agents query it instantly via semantic search.

| Without Mimir | With Mimir |
|---------------|------------|
| Agents grep for files every session | Agents query indexed knowledge instantly |
| 30% of context spent on discovery | 5% on discovery, 95% on implementation |
| No memory between sessions | Persistent semantic index across sessions |
| Keyword searches miss related code | Semantic search finds concepts across files |

---

## Quick Start

### Prerequisites

| Requirement | How to Install | Verify |
|-------------|----------------|--------|
| **Python 3.12+** | `brew install python` or [python.org](https://python.org) | `python3 --version` |
| **uv package manager** | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **OpenRouter API key** | [openrouter.ai](https://openrouter.ai) → Settings → Keys | — |

### Installation

```bash
# 1. Clone Mimir
git clone https://github.com/ewheels44/Mimir.git ~/Mimir
cd ~/Mimir

# 2. Run the install script
bash install.sh

# 3. Set your API key
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
# Or add it to ~/.zshrc / ~/.bashrc for persistence

# 4. (Optional) Build the web UI
cd web
./build.sh  # Requires Rust + Node.js
```

The install script:
- Checks prerequisites (Python 3.12+, uv)
- Sets up a Python virtual environment
- Installs all Python dependencies
- Optionally builds web components (Rust server + React client)

### Install Script Options

```bash
bash install.sh                  # Install with defaults
bash install.sh --skip-web      # Skip building web UI (Rust + React)
bash install.sh --skip-hooks    # Skip git hooks installation
bash install.sh --force         # Force reinstallation
bash install.sh --help          # Show all options
```

---

## How Mimir Works

Mimir is a **5-layer system** with a multi-stage query pipeline that minimizes token usage by checking cheaper sources first:

```
User/Agent Query
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: Entry Points                                        │
│  ┌──────────────────────┐  ┌────────────────────────────┐    │
│  │ mimir_bridge.py      │  │ langgraph/cli.py           │    │
│  │ (JSON stdin/stdout   │  │ (Terminal CLI:             │    │
│  │  for ecode/jcode)    │  │  rag, agent, prep, diff)   │    │
│  └──────────┬───────────┘  └─────────────┬──────────────┘    │
└─────────────┼───────────────────────────┼────────────────────┘
              │                           │
              ▼                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 2: Query Router (query_router.py)                     │
│                                                              │
│  STEP 1: Pre-compiled Artifact Check ── hit ──► Return       │
│       │ (instant, zero token cost)          instant answer   │
│       │ miss                                                │
│       ▼                                                     │
│  STEP 2: Semantic Cache Check  ────────── hit ──► Return    │
│       │ (embedding similarity)              cached result   │
│       │ miss                                                │
│       ▼                                                     │
│  STEP 3: Query Classification (3-tier)                      │
│       │ ┌─────────────────────────────────────────────────┐ │
│       │ │ 1. Keyword confidence check (free, ≥0.75→done) │ │
│       │ │ 2. Neural classifier (numpy 1.1KB, $0.000001)  │ │
│       │ │ 3. Keyword fallback (rule-based, always avails)│ │
│       │ │    LLM fallback: planned, not wired in          │ │
│       │ └─────────────────────────────────────────────────┘ │
│       ▼                                                     │
│  STEP 4: Route based on classification + confidence         │
│                                                              │
│  ┌─ structural (high conf) ──► Graph only (Dijkstra)       │
│  ├─ structural (mid conf)  ──► Hybrid (Graph + Vector)     │
│  └─ semantic / fallback    ──► Vector search (LlamaIndex)  │
│                                                              │
│  Results are cached, metrics recorded, circuit breaker      │
│  protects against repeated failures.                         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 3: Core Components                                    │
│                                                              │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │ LlamaIndex         │  │ Knowledge Graph              │   │
│  │ (Vector store +    │  │ (Python AST + tree-sitter    │   │
│  │  BM25 hybrid       │  │  extraction → Rust server    │   │
│  │  retrieval)        │  │  with Dijkstra path-finding) │   │
│  └────────────────────┘  └──────────────────────────────┘   │
│                                                              │
│  ┌────────────────────┐  ┌──────────────────────────────┐   │
│  │ Pre-compiled       │  │ Semantic Cache               │   │
│  │ Artifacts          │  │ (Embedding similarity,       │   │
│  │ (Dependency-tracked│  │  TTL, circuit breaker)       │   │
│  │  knowledge snippets│  │                              │   │
│  │  with hash-based   │  │                              │   │
│  │  invalidation)     │  │                              │   │
│  └────────────────────┘  └──────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────┘
                           │ stores to / reads from
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 4: Storage & Indexing                                 │
│                                                              │
│  .knowledge/llamaindex/   (LlamaIndex vector store)          │
│  .knowledge/code_relationships.json  (knowledge graph data)  │
│  .knowledge/artifacts/    (pre-compiled artifacts)           │
│  .knowledge/sdk-cache/    (SDK documentation cache)          │
│  .mimir/config.json       (project configuration)            │
│  .mimir/index_state.json  (file hash tracking)              │
│  .knowledge/cost_metrics.jsonl  (per-query cost tracking)    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Layer 5: Background Services                                │
│                                                              │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ File Watcher    │  │ Git Hooks    │  │ Rust Server  │   │
│  │ (watchdog, auto-│  │ (post-commit │  │ (Axum HTTP,  │   │
│  │  reindex on     │  │  auto-index  │  │  Dijkstra,   │   │
│  │  file changes)  │  │  on docs/    │  │  React UI)   │   │
│  │                 │  │  changes)   │  │              │   │
│  └─────────────────┘  └──────────────┘  └──────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Indexing Pipeline (`src/mimir/indexing.py`)

The indexing pipeline takes source files and builds a searchable vector index.

**Change Detection:**
- Stores SHA-256 hashes of all indexed files in `.mimir/index_state.json`
- Quick mtime check first — if no directories changed, skips the expensive full walk
- Returns `{added, modified, deleted}` file lists for incremental updates
- 50MB file size limit for hashing

**Indexing Process:**
1. Reads files from `docs/` and code dirs using LlamaIndex's `SimpleDirectoryReader`
2. Configures OpenAI embeddings (`text-embedding-3-large` default)
3. Builds a `VectorStoreIndex` with vector embeddings + BM25 (hybrid retrieval)
4. Persists to `.knowledge/llamaindex/` (docstore.json, index_store.json, etc.)
5. Writes a manifest.json tracking what was indexed

**Incremental Updates:**
- `add_directory_with_progress()` — adds new files to existing index
- `add_file_to_index()` — adds a single file
- `remove_file_from_index()` — removes a file and its embeddings
- `remove_directory_from_index()` — removes an entire directory
- Backup/restore support via `.knowledge_backups/`

Pro tip: `python src/mimir/mimir-index.py` is the standalone CLI wrapper with flags like `--add`, `--remove-file`, `--list`, `--reindex`.

### 2. Query Router (`src/mimir/query_router.py`)

The decision engine that routes every query through the cheapest available path.

**Decision chain** (in order):

```
1. Pre-compiled artifact check (instant, zero token cost)
   → Matches keywords to artifact IDs, loads pre-built content
   
2. Semantic cache check (embedding similarity)
   → Returns cached result if a similar query was answered recently
   
3. Query classification → determines whether to use graph or vector
   
4. Route to:
   a) Graph only — high confidence structural query (Dijkstra path-finding)
   b) Hybrid — mid confidence structural (graph + vector merged)
   c) Vector only — semantic queries or fallback
```

**Safety features:**
- Circuit breaker — opens after configurable consecutive failures
- Content filtering — detects and redacts sensitive data (keys, tokens, passwords)
- Blocked filenames — skips `.env`, `*.pem`, credential files
- Per-project singleton — separate cache + circuit per project root

### 3. Query Classifier (`src/mimir/query_classifier.py`)

Determines whether a query is "structural" (asking about code relationships, dependencies, imports) or "semantic" (asking about concepts, explanations, usage).

**3-tier classification pipeline:**

```
Query → Keyword confidence check
         │
         ├─ Confidence ≥ 0.75 → Return immediately (free, deterministic)
         │
         └─ Confidence < 0.75 → Neural classifier (SimpleQueryClassifier)
                                  │
                                  ├─ Confidence ≥ 0.6 → Return neural result
                                  │
                                  └─ Confidence < 0.6 → Keyword fallback
```

**SimpleQueryClassifier:**
- 10→8→2 feedforward neural network
- Pure numpy — zero ML dependencies
- 1,107 bytes (1.1KB) model file (`query_classifier_model.pkl`)
- Trained on 30 hand-labeled examples via gradient descent (200 epochs)
- 10 handcrafted features: keyword density, query length, question words, structural phrase position
- Inference cost: ~$0.000001 per query

**Keyword fallback:**
- Deterministic rule-based: counts structural keywords (connect, depend, path, etc.)
- Checks phrase patterns ("connect to", "path from", "depends on", "how does")
- Always available even without a trained model

**Cost tracking:**
- Logs every classification to `classification_tracking.json`
- Tracks neural_calls vs llm_calls vs keyword_calls
- Savings: ~$0.0015 saved per neural call vs. LLM alternative

*Note: The LLM fallback path is defined as `use_llm_fallback=True` but is not wired in — it says "Would call LLM here in production". The actual 3 tiers are keyword → neural → keyword fallback.*

### 4. Knowledge Graph (`src/mimir/knowledge_graph.py` + `web/server/`)

Extracts code relationships (imports, function calls, inheritance) and provides path-finding queries.

**Relationship Extraction:**

The `CombinedExtractor` routes each file type to the best available parser:

| File Type | Extractor | Method |
|-----------|-----------|--------|
| `.py` | `PythonASTExtractor` | Python's built-in `ast` module |
| `.ts/.tsx/.js/.jsx/.rs/.go` | `TreeSitterExtractor` | tree-sitter CST walk (requires `tree-sitter-languages`) |
| `.cpp/.c/.h` | `CppExtractor` | Regex patterns |
| `.astro` | `AstroExtractor` | Regex for imports + components |

**Relationship types extracted:**
- `imports_from` — module/file imports
- `calls` — function/method calls
- `inherits_from` — class inheritance
- `contains` — file contains class/function

Output written to `.knowledge/code_relationships.json`.

**Rust Graph Server** (`web/server/src/graph.rs`):
- Reads `docstore.json` (LlamaIndex) + `code_relationships.json` into an in-memory `GraphCache`
- Provides **weighted Dijkstra shortest path** — edge weights vary by relationship type
- BFS neighbor enumeration with depth and relation filtering
- Module children queries (functions + classes inside a file)
- Pre-computed layout positions for visualization
- API endpoints: `/api/graph`, `/api/graph/path`, `/api/graph/neighbors`, `/api/graph/stats`, `/api/graph/module/{id}/children`
- Cache is invalidated when source file mtimes change
- Serves a React UI via Cytoscape.js

### 5. Pre-compiled Artifacts (`src/mimir/artifacts.py`)

**Inspired by Pinecone Nexus's approach.** Pre-built knowledge snippets that answer common questions instantly with zero token cost.

**How it works:**
- Each artifact has a unique `artifact_id`, content (JSON), and dependency list
- Artifacts track which source files they depend on via SHA-256 hashes
- Staleness checked by: TTL (1 hour default) + source file hash changes
- File watcher invalidates artifacts when dependencies change

**Generated artifacts** (via `scripts/generate_artifacts.py`):
- `rag_architecture` — how RAG retrieval works
- `indexing_architecture` — how indexing works
- `artifact_system` — the artifact system itself
- `code_chunking` — AST-aware chunking strategy
- `knowledge_graph_integration` — graph query patterns
- `query_caching` — cache invalidation rules

When a query matches artifact keywords (via `_find_matching_artifact`), the artifact is returned **before any search or retrieval** — the fastest path in the system.

### 6. Semantic Cache (`src/mimir/query_cache.py`)

Embedding-based cache built into `route_task()`:
- Uses OpenAI embeddings to compare query similarity
- Returns cached result when similarity exceeds threshold (default 0.85)
- TTL-based expiration
- Per-project cache (separate instances)
- Circuit breaker integration

### 7. Code Chunking (`src/mimir/chunking.py`)

Splits code files at logical boundaries — functions, classes, methods — rather than arbitrary token limits.

**Two strategies:**
- `PythonASTChunker` — uses Python's `ast` module. Splits on `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, and individual methods within classes
- `TreeSitterChunker` — uses tree-sitter for `.ts`/`.js`/`.rs`/`.go` files. Falls back to whole-file if parse fails
- `IntelligentChunker` — routes to the appropriate strategy by file extension

Max chunk size: ~1,500 tokens (approximate via 4 chars/token heuristic).

### 8. File Watcher (`src/mimir/watcher.py`)

Background file monitoring using `watchdog`:
- Watches docs/ and code dirs for changes
- 2-second debounce for index changes, 5-second debounce for knowledge graph
- On file change: triggers incremental reindex + artifact invalidation
- Graceful shutdown via signal handling
- Pure polling (`PollingObserver`) for reliable cross-platform detection

### 9. LangGraph Workflows (`langgraph/workflows/`)

Four LangGraph `StateGraph` workflows with `MemorySaver` checkpointing:

**RAG** (`rag.py`):
- 2-step: `retrieve → generate`
- Searches knowledge base via MCP tool, then LLM-synthesizes answer
- Token tracking via `TokenUsageCallbackHandler`
- Records metrics to `cost_metrics.jsonl`

**Knowledge Agent** (`knowledge_agent.py`):
- Multi-step: `check_knowledge → agent → execute_tools → agent` (loop)
- Max 3 tool call rounds with stop conditions
- Tools: `search`, `query`, `read_file`, `stats`
- Built-in safeguards against hallucination (stop calling tools on empty results)

**Call Prep** (`call_prep.py`):
- Generates customer call briefings with relevant KB context
- Searches for related code patterns, known issues, and common patterns

**Session Diff** (`session_diff.py`):
- Compares recent sessions against stored knowledge
- Reports what's been learned and what's changed

**Performance note:** All workflows use `bridge_client.py` which wraps `KnowledgeServer` as a lazy singleton — avoiding ~24 seconds of LlamaIndex re-initialization overhead per tool call that the old subprocess approach had.

### 10. SDK Cache (`src/mimir/sdk_cache.py`)

Caches external library documentation for offline querying:
- Stores SDK docs in `.knowledge/sdk-cache/`
- TTL-based expiration (7 days default)
- List/cache/cleanup operations via bridge actions

### 11. Metrics & Cost Tracking (`src/mimir/metrics.py`)

Every query is logged to `.knowledge/cost_metrics.jsonl` with:
- Query type, tokens in/out, cost, docs retrieved, duration
- Embedding and LLM cost breakdowns
- Comparison against estimated "traditional" cost (no-Mimir baseline)

The **Rust metrics server** (`web/server/src/metrics.rs`) exposes:
- `GET /api/metrics/summary` — total queries, costs, savings percentage
- `GET /api/metrics/daily` — daily breakdowns
- `GET /api/metrics/breakdown` — per query-type costs
- `GET /api/metrics/components` — embedding vs LLM cost split

Savings calculation: compares actual Mimir costs against a traditional baseline of $0.001/1K tokens and 30s/query.

### 12. Handoff Generator (`src/mimir/handoff.py`)

Generates structured FDE-style handoff documents for agent handovers:
- Project overview (tech stack, directories, key files)
- Knowledge base statistics
- What was built
- Integration points
- Known issues
- Next steps

Output as Markdown with table of contents, sectioned by priority.

---

## Using Mimir with ecode

Once Mimir is installed and your project is indexed, ecode agents automatically use `mimir_bridge.py`:

```
User: "How does authentication work?"
Agent: [Calls mimir_bridge.py with action="search"]
       → Finds auth.py, middleware.py, jwt.ts
Agent: "The auth flow uses JWT with refresh tokens..."
```

**No setup needed** — ecode detects Mimir automatically and routes queries through the bridge.

---

## Entry Points

### 1. mimir_bridge.py — For ecode/jcode Integration

The **JSON bridge** is used by ecode/jcode editors automatically:

```bash
# Example: How ecode sends a query to Mimir
echo '{"action":"search","params":{"query":"authentication patterns"}}' | python3 mimir_bridge.py

# Returns JSON on stdout:
# {"status": "ok", "results": [{"source": "auth.py", "score": 0.95, "text": "..."}]}
```

**Available bridge actions:**

| Action | Purpose |
|--------|---------|
| `init` | Bootstrap a new Mimir project |
| `search` | Semantic search (vector + BM25 hybrid) |
| `query` | Natural language Q&A |
| `rag_workflow` | Structured RAG via LangGraph (2-step) |
| `knowledge_agent` | Multi-step agentic research via LangGraph |
| `enrich_task` | Get project context before tasks (uses query router) |
| `reindex` | Rebuild the knowledge base |
| `incremental_reindex` | Incremental update (only changed files) |
| `remove_file` | Remove file from index |
| `add_directory` | Add a directory to index |
| `stats` | Index statistics |
| `task_health` | Check query router health (circuit breaker, cache) |
| `sdk_cache_get` | Get SDK documentation |
| `sdk_cache_list` | List cached SDKs |
| `cache_stats` | Query cache statistics |
| `cache_clear` | Clear query cache |
| `cache_cleanup` | Remove expired cache entries |

### 2. langgraph/cli.py — For Terminal Usage

The **CLI tool** is for developers to test workflows manually:

```bash
# RAG workflow
python langgraph/cli.py rag "How does auth work?"

# Knowledge agent
python langgraph/cli.py agent "Find all API endpoints"

# Call briefing
python langgraph/cli.py prep "video latency issues" --customer acme

# Session diff
python langgraph/cli.py session-diff --days 3

# Test workflows
python langgraph/cli.py test

# View cost metrics
python langgraph/cli.py metrics --days 30
```

**CLI subcommands:**

| Command | Purpose |
|---------|---------|
| `rag "query"` | Run RAG workflow |
| `agent "query"` | Run knowledge agent |
| `prep "topic"` | Generate call briefing |
| `session-diff` | Compare recent sessions |
| `test` | Test all workflows |
| `metrics` | Cost/usage report |

---

## Indexing Your Project

### Initialize a Project

```bash
cd ~/Projects/YourProject
mkdir -p .mimir
cat > .mimir/config.json << EOF
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small",
  "llm_model": "google/gemini-3.1-flash-lite-preview"
}
EOF
```

### Build the Index

```bash
# Full index
python -c "
from src.mimir.indexing import index_with_progress
from src.mimir.config import get_config, reset_config
reset_config()
config = get_config(project_root='$(pwd)')
index_with_progress(
    project_root=config.project_root,
    docs_dir=config.docs_dir,
    code_dirs=config.code_dirs,
    knowledge_dir=config.knowledge_dir,
    force_reindex=True
)
"

# Or use the standalone index CLI
python src/mimir/mimir-index.py
python src/mimir/mimir-index.py --reindex   # Force rebuild
python src/mimir/mimir-index.py --add src   # Add specific directory
python src/mimir/mimir-index.py --list      # Show indexed contents

# Extract knowledge graph (code relationships)
python src/mimir/mimir-index.py --knowledge-graph

# Check index status
echo '{"action":"stats","params":{}}' | python3 mimir_bridge.py
```

### Auto-Indexing

Install git hooks to automatically reindex on commits:

```bash
bash scripts/install-git-hooks.sh
bash scripts/install-git-hooks.sh /path/to/repo  # specific repo
bash scripts/install-git-hooks.sh --all           # all Mimir projects
```

The post-commit hook only triggers when `docs/` files change.

---

## Web UI (Optional)

Visual interface for exploring your knowledge base:

```bash
cd /path/to/Mimir/web
./dev.sh --project /path/to/your/project
```

Features:
- Interactive knowledge graph visualization (Cytoscape.js)
- Dijkstra path-finding — click two nodes to see shortest weighted path
- Semantic search interface
- Cost metrics dashboard (daily, per-type, component breakdown)
- Document relationship exploration
- Module hierarchy (file → functions/classes)

The web stack:
- **Server**: Rust (Axum) — graph queries, metrics, proxy to Python sidecar
- **Client**: React + TypeScript + Vite + Cytoscape.js
- **Sidecar**: Python (LlamaIndex) — search + query via internal port

---

## Configuration

### Project Config: `.mimir/config.json`

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small",
  "llm_model": "google/gemini-3.1-flash-lite-preview",
  "sdk_cache_ttl_days": 7,
  "exclude_patterns": ["node_modules", "__pycache__", "*.pyc"],
  "files": ["README.md"]
}
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENROUTER_API_KEY` | API key for embeddings/LLM | — |
| `OPENAI_API_KEY` | Fallback API key | — |
| `EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `MIMIR_LLM_MODEL` | LLM model | `google/gemini-3.1-flash-lite-preview` |
| `PROJECT_ROOT` | Override project root | Auto-detected |
| `KNOWLEDGE_DIR` | Override knowledge directory | `.knowledge/llamaindex` |

Resolution order: Environment variables > `.mimir/config.json` > hardcoded defaults.

---

## Key Files

```
/path/to/Mimir/
├── mimir_bridge.py                 # JSON bridge (ecode/jcode entry point)
├── install.sh                      # Installation script
│
├── langgraph/
│   ├── cli.py                      # Terminal CLI (rag, agent, prep, diff, metrics)
│   └── workflows/
│       ├── rag.py                  # RAG workflow (retrieve → generate)
│       ├── knowledge_agent.py      # Multi-step agentic research
│       ├── call_prep.py            # Customer call briefing
│       ├── session_diff.py         # Session comparison
│       ├── bridge_client.py        # KnowledgeServer adapter (lazy singleton)
│       └── utils.py                # Shared workflow utilities
│
├── src/mimir/
│   ├── config.py                   # Unified configuration (env → config.json → defaults)
│   ├── indexing.py                 # Document indexing + change detection (SHA-256)
│   ├── query_router.py             # Query routing engine (artifact → cache → classify → route)
│   ├── query_classifier.py         # 3-tier classifier (keyword → neural → keyword fallback)
│   ├── query_classifier_model.pkl  # Trained neural model (1.1KB, numpy-only)
│   ├── knowledge_graph.py          # Code relationship extraction (AST + tree-sitter + regex)
│   ├── chunking.py                 # AST-aware code chunking (Python AST + tree-sitter)
│   ├── artifacts.py                # Pre-compiled artifact system (dependency-tracked)
│   ├── sdk_cache.py                # External library documentation cache
│   ├── cache_query.py              # Embedding-based semantic cache
│   ├── server.py                   # KnowledgeServer (search, query, index, stats API)
│   ├── metrics.py                  # Per-query cost tracking (CSV → cost_metrics.jsonl)
│   ├── handoff.py                  # FDE handoff document generator
│   ├── watcher.py                  # File change watcher (watchdog-based)
│   ├── activation.py               # Gating logic for when to use Mimir
│   ├── token_callback.py           # LangChain token usage callback
│   ├── shared_index.py             # Multi-project shared indexes
│   ├── projects.py                 # Project discovery and management
│   ├── utils.py                    # Shared utilities (project root detection, excludes)
│   ├── openspace_bridge.py         # DEPRECATED — thin wrapper around query_router
│   └── mimir-index.py              # Standalone indexing CLI
│
├── web/
│   ├── server/                     # Rust graph server (Axum, Dijkstra, metrics)
│   │   └── src/
│   │       ├── main.rs             # HTTP server, route handlers
│   │       ├── graph.rs            # Graph builder, Dijkstra path-finding, BFS
│   │       ├── metrics.rs          # Cost metrics API
│   │       ├── models.rs           # Shared types
│   │       ├── proxy.rs            # Sidecar search proxy
│   │       └── sidecar.rs          # Python sidecar lifecycle
│   └── client/                     # React UI (Cytoscape.js, Vite, TypeScript)
│
├── scripts/
│   ├── install-git-hooks.sh        # Auto-indexing hook installer
│   ├── git-hooks/post-commit       # Git hook: auto-reindex on docs/ changes
│   ├── generate_artifacts.py       # Pre-compiled artifact generator
│   └── mimir-projects.py           # Multi-project management
│
└── tests/
    ├── test_config.py              # Configuration tests
    ├── test_indexing.py            # Indexing pipeline tests
    ├── test_metrics.py             # Metrics tracking tests
    ├── test_openspace_bridge.py    # Compatibility tests
    ├── test_query_router_improvements.py  # Router tests
    ├── test_sdk_cache.py           # SDK cache tests
    ├── test_utils.py               # Utility tests
    ├── test_workflows.py           # LangGraph workflow smoke tests
    └── test_phase2_unified_bridge.py  # Bridge integration tests
```

---

## Cost Tracking

Mimir tracks usage and calculates savings:

```bash
python langgraph/cli.py metrics --days 30
```

**What's tracked:**
- Every search, query, RAG, and agent call
- Tokens in/out, cost, duration, docs retrieved
- Embedding vs LLM cost breakdown
- Traditional cost comparison (what it would cost without Mimir)

**Savings methodology:**
Traditional baseline is estimated at $0.001/1K tokens and ~30s per manual query.
Mimir costs include actual embedding + LLM token usage.
Savings = (traditional_cost - actual_cost) / traditional_cost.

---

## Development

### Running Tests

```bash
cd ~/Mimir
source .venv/bin/activate
pytest tests/
```

### Testing Workflows

```bash
# Test all workflows
python langgraph/cli.py test

# Test specific workflow
python langgraph/cli.py rag "What is Mimir?"
```

### Building Web UI

```bash
cd ~/Mimir/web
./build.sh          # Production build (Rust + React)
./dev.sh --project /path/to/project   # Development mode
```

---

## Changelog

| Change | Impact |
|--------|--------|
| **Embedded in ecode** | Mimir is now embedded directly in ecode (jcode fork) — no MCP server needed |
| **JSON bridge** | `mimir_bridge.py` provides stdin/stdout JSON communication for ecode/jcode |
| **Terminal CLI** | `langgraph/cli.py` for testing workflows, generating call briefings, and viewing metrics |
| **Removed MCP dependencies** | Dropped `langchain-mcp-adapters` and MCP server code |
| **Simplified architecture** | Better performance, less overhead, tighter integration |
| **LangGraph token tracking** | `TokenUsageCallbackHandler` captures actual token usage from API calls |
| **3-tier query classifier** | Keyword → neural (numpy 1.1KB) → keyword fallback routing |
| **Rust graph server** | Weighted Dijkstra path-finding, BFS neighbors, React visualization |
| **Pre-compiled artifacts** | Zero-token-cost instant answers with dependency tracking |
| **AST-aware chunking** | Code split at function/class boundaries (Python AST + tree-sitter) |
| **Semantic cache** | Embedding similarity cache with TTL and circuit breaker |
| **File watcher** | Background auto-reindexing on file changes via watchdog |
| **Handoff generator** | Structured FDE handoff documents for agent handovers |

---

## License

MIT