# Mimir — Agent Reference

> Rules are in RULES.md (5 rules). This file is reference material — read when needed.

## What Mimir Is

A per-project knowledge base that gives AI agents memory. Three layers:

```
LlamaIndex (vector search) ← MCP (tool bridge) ← LangGraph (workflows)
```

Each project gets its own index at `.knowledge/llamaindex/`. The MCP server auto-detects which project you're in.

### Pre-compiled Artifacts (Pinecone Nexus-Inspired)

Mimir can serve pre-compiled knowledge artifacts instead of running retrieval every time:

```
.artifacts/rag_architecture.json      # RAG system architecture
.artifacts/indexing_architecture.json  # Indexing system architecture
.artifacts/code_chunking.json          # Code chunking strategy
.artifacts/artifact_system.json        # Artifact dependency tracking
.artifacts/knowledge_graph_integration.json # KG + search integration
.artifacts/query_caching.json          # Query caching mechanisms
.artifacts/manifest.json               # Artifact dependency tracking
```

Artifacts track which source files they depend on, and auto-invalidate when those files change (via the file watcher).

### Knowledge Graph Structure

The knowledge graph is stored at `.knowledge/code_relationships.json` with this structure:

```json
{
  "relationships": [...],  // Edges: {source, target, relation_type, metadata}
  "entities": [...]        // Nodes: {file, type, name, ...}
}
```

Not the typical `nodes`/`edges` format — Mimir uses `entities` and `relationships`.

## MCP Tools

| Tool | What it does | When to use |
|------|-------------|-------------|
| `mimir-knowledge_enrich_task` | Search project context for a task | Before any task (Rule 1) |
| `mimir-knowledge_search` | Semantic similarity search | Finding code/docs by meaning |
| `mimir-knowledge_query` | Ask a question, get synthesized answer | Understanding patterns |
| `mimir-knowledge_sdk_cache_get` | Get library docs (cached, 7-day TTL) | External library questions |
| `mimir-knowledge_sdk_cache_list` | List cached SDK docs | Check what's available |
| `mimir-knowledge_rag_workflow` | Structured retrieve → generate | Complex analysis |
| `mimir-knowledge_knowledge_agent` | Multi-step agentic research | Deep exploration |
| `mimir-knowledge_get_artifact` | Get pre-compiled artifact | Quick answers from cached knowledge |
| `mimir-knowledge_list_artifacts` | List available artifacts | Check what artifacts exist |
| `mimir-knowledge_reindex` | Rebuild the full index | After major changes |
| `mimir-knowledge_health_check` | Check server status | Debugging |
| `mimir-knowledge_stats` | Index statistics | Check what's indexed |
| `mimir-knowledge_graph_query` | Query code relationships (edges between files) | "How does X connect to Y?" |
| `mimir-knowledge_graph_neighbors` | Get related files for a path | "What depends on this?" |
| `mimir-knowledge_graph_stats` | Graph overview (entities, relationships) | "What's the most connected module?" |
| `openspace_search_skills` | Find evolved skills | Before executing |
| `openspace_execute_task` | Run a task with skill guidance | Skill-guided execution |

## Tool Priority

```
1. enrich_task     → project memory (always first)
2. get_artifact    → pre-compiled knowledge (fast, no retrieval)
3. sdk_cache_get   → library docs (before guessing)
4. graph_query     → structural paths ("how does X reach Y?")
5. graph_neighbors → dependency exploration ("what calls this?")
6. search          → semantic similarity
7. query           → synthesized understanding
8. rag_workflow    → structured analysis (supports response_shape)
9. knowledge_agent → deep research
```

## Project Structure

```
Mimir/
├── mimir.py                    # Main CLI entry point
├── mcp_server_llamaindex.py    # MCP server (tool definitions, server lifecycle)
├── src/mimir/                  # Core Python package
│   ├── config.py               # Unified config — single source of truth
│   ├── indexing.py             # Document indexing
│   ├── artifacts.py            # Pre-compiled artifact system
│   ├── knowledge_graph.py      # Code relationship extraction
│   ├── metrics.py              # Cost/token tracking
│   ├── openspace_bridge.py     # OpenSpace integration + **neural classifier**
│   ├── query_classifier.py     # **Phase 1 Neural Query Classifier** (10→8→2 network)
│   ├── query_classifier_model.pkl # Trained model (1.1KB)
│   ├── sdk_cache.py           # SDK doc cache
│   ├── shared_index.py         # Cross-codebase search
│   ├── watcher.py              # File watcher
│   └── ...
├── scripts/                    # Utility scripts
│   ├── mimir-init.py           # Installer — global setup + per-project init
│   ├── mimir-projects.py       # Multi-project management
│   ├── generate_artifacts.py   # Artifact generator
│   ├── full_index.py           # Full index script
│   └── jcode/                  # Jcode bridge
├── langgraph/                  # LangGraph workflows
│   ├── workflows/
│   │   ├── rag.py              # RAG workflow (supports response_shape)
│   │   ├── knowledge_agent.py  # Knowledge agent
│   │   └── ...
│   └── langgraph.json          # LangGraph config
├── workflows/                  # Workflow examples
│   └── run_workflow.py
├── experiments/                 # Experiment scripts (NOT integrated)
│   ├── gnn_experiment.py        # GNN experiment (rejected — 58% accuracy)
│   ├── gnn_meaningful_experiment.py  # Improved GNN (still rejected)
│   └── RESULTS_SUMMARY.md     # GNN experiment conclusions
├── docs/                       # Documentation (indexed)
├── opencode-config/            # OpenCode configuration
│   ├── opencode.json
│   └── agent/                  # Subagent configs
├── mimir-demo/                 # Demo web app (React + TypeScript)
│   ├── src/
│   │   ├── components/
│   │   │   ├── NeuralEvolution.tsx  # **Phase 1 Demo** — animations, cost calc
│   │   │   └── ...
│   │   ├── data/
│   │   │   ├── neural_evolution.ts   # Phase 1 data (CodeExample patterns)
│   │   │   └── ...
│   │   └── styles/
│   │       ├── index.css
│   │       └── neural.css         # Phase 1 styles
│   └── ...
├── web/                        # Web components
│   ├── sidecar/                # Python sidecar server
│   └── ...
├── .mimir/                     # Per-project config (optional)
├── .knowledge/                 # Vector index + SDK cache (auto-created)
│   ├── llamaindex/
│   ├── sdk-cache/
│   ├── artifacts/              # Pre-compiled artifacts
│   │   ├── manifest.json      # Artifact dependency tracking
│   │   └── *.json            # Individual artifacts
│   └── evals/                  # Eval harness questions
│       └── questions.json
├── PHASE1_COMPLETE.md           # Phase 1 summary
├── FUTURE_PHASES.md             # Roadmap for Phases 2-4
└── AGENTS.md                    # This file
```

## Configuration

Resolution order: env vars → `.mimir/config.json` → defaults.

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small"
}
```

All fields optional. Defaults work for most projects.

## Key Source Files

| File | Purpose |
|------|---------|
| `mcp_server_llamaindex.py` | MCP server — tool definitions, server lifecycle |
| `src/mimir/config.py` | Unified config — `MimirConfig` class, `get_config()` |
| `src/mimir/indexing.py` | Document indexing — full, incremental, file-level |
| `src/mimir/artifacts.py` | Pre-compiled artifacts — `create_artifact()`, `get_artifact()`, manifest |
| `src/mimir/openspace_bridge.py` | OpenSpace integration — `MimirOpenSpaceBridge`, `enrich_task_for_openspace()` |
| `src/mimir/query_classifier.py` | **Phase 1 Neural Query Classifier** — `SimpleQueryClassifier`, `classify_query()` |
| `src/mimir/sdk_cache.py` | SDK doc cache — Context7 API, TTL, local storage |
| `src/mimir/shared_index.py` | Cross-codebase search — `SharedIndexRegistry`, `merge_results()` |
| `src/mimir/knowledge_graph.py` | Code relationship extraction — `CombinedExtractor`, `extract_code_relationships()` |
| `src/mimir/metrics.py` | Cost/token tracking — `TokenTracker`, `MetricsTracker`, `QueryMetrics` |
| `src/mimir/watcher.py` | File watcher — `MimirFileWatcher`, `detect_changed_files()` |
| `scripts/generate_artifacts.py` | Artifact generator — creates pre-compiled knowledge |
| `scripts/mimir-init.py` | Installer — global setup + per-project init |
| `langgraph/workflows/rag.py` | RAG workflow — retrieve → generate, supports response_shape |
| `langgraph/workflows/knowledge_agent.py` | Knowledge agent — multi-step research |

## Jcode Bridge

Mimir includes a built-in Jcode bridge (`scripts/jcode/mimir-bridge.py`) that auto-registers Mimir tools with the Jcode agent server.

### What it does

| Action | File | Purpose |
|--------|------|---------|
| Skill registration | `~/.jcode/skills/mimir-{project}.json` | All Mimir tools available to Jcode |
| System prompt | `~/.jcode/prompts/mimir-{project}.md` | Usage instructions for agents |
| MCP server config | `~/.jcode/mcp.json` | Points to Mimir MCP server |

### Quick setup

```bash
# From within a Mimir-enabled project:
python scripts/jcode/mimir_bridge.py --auto
```

### CLI options

```bash
python scripts/jcode/mimir_bridge.py --register-skill    # Register skill only
python scripts/jcode/mimir_bridge.py --inject-prompt     # Inject system prompt only
python scripts/jcode/mimir_bridge.py --check             # Check current status
python scripts/jcode/mimir_bridge.py --unregister        # Remove all Mimir config
```

---

## Budget Controls

Mimir MCP tools support budget limits to control token usage and costs:

```python
# In MCP tools: search, query, rag_workflow
max_tokens: int = None       # Token budget for this request
max_cost_usd: float = None  # Cost budget in USD

# Example: Limit to $0.10 per request
rag_workflow(
    query="...",
    max_tokens=500,
    max_cost_usd=0.10
)
```

Budget checking uses `metrics.py` (`QueryMetrics`, `TokenTracker`) to track usage over the last 24 hours. Warnings are issued when <10% budget remains.

---

## Declarative Query Shape (KnowQL-Inspired)

The `rag_workflow` tool supports a `response_shape` parameter for structured outputs:

```python
response_shape = json.dumps({
    "components": [{"name": "...", "purpose": "..."}],
    "data_flow": "...",
    "key_files": ["..."]
})

# Returns JSON matching the schema instead of prose
rag_workflow(query="...", response_shape=response_shape)
```

**Benefits:**
- Reduces token usage (JSON vs prose)
- Machine-readable outputs for programmatic use
- Inspired by KnowQL's declarative query approach

---

## Eval Harness

Measure RAG system accuracy, token usage, and cost:

```bash
# Run all evals
mimir evaluate --eval-file .knowledge/evals/questions.json --output results.json

# Run specific question
mimir evaluate --question-id rag_architecture

# Update gold answers from current system state
mimir evaluate --update-gold
```

### Eval Question Format

```json
[
  {
    "id": "rag_architecture",
    "question": "What type of RAG system does Mimir have?",
    "expected_artifact": "rag_architecture",
    "max_tokens": 5000,
    "response_shape": "{\"key\": \"...\"}",
    "gold_answer": {
      "structure.retrieval.type": "hybrid"
    }
  },
  {
    "id": "indexing_architecture",
    "question": "How does Mimir's incremental indexing work?",
    "expected_artifact": "indexing_architecture"
  },
  {
    "id": "artifact_system",
    "question": "How does the artifact dependency tracking system work?",
    "expected_artifact": "artifact_system"
  }
]
```

**Features:**
- Tries `get_artifact` first (if `expected_artifact` set)
- Falls back to `rag_workflow` (if langchain/langgraph available)
- Compares answers to `gold_answer` using dot-notation key matching
- Tracks token usage in results

---

## Installation

```bash
# Global (once)
python ~/Documents/Mimir/mimir.py install

# Per-project (in each project)
cd /your/project
python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests

# Uninstall
python ~/Documents/Mimir/mimir.py uninstall
```

## Self-Improvement Loop

Mimir can analyze and improve itself using its own tools:

```bash
# 1. Check current state
mimir health
mimir stats

# 2. Rebuild stale artifacts
python scripts/generate_artifacts.py --all

# 3. Run eval harness to validate
mimir evaluate --eval-file .knowledge/evals/questions.json --output results.json

# 4. Use RAG workflow for deep analysis
# (Call mcp__mimir-Mimir__rag_workflow with analysis queries)

# 5. Check for stale documentation
# (Use search/query to find outdated content)
```

**Self-Analysis Results (2026-05-19):**
- ✅ Eval harness: 100% pass rate (3/3)
- ✅ All artifacts rebuilt and fresh
- ✅ No TODO/FIXME markers in Python code
- ✅ Python syntax validation passed
- ✅ Documentation up-to-date (checked dates in docs/)

**Identified Improvement Areas:**
- Consider adding configurable chunking strategies
- Enhance error handling in async operations
- Add more eval questions for broader coverage
- Consider performance optimizations for hybrid retrieval

## When to Skip Mimir

- Typo fixes in known files
- Single-file changes where you already know the content
- Pure bash operations (ls, git status, etc.)

## Subagents

ContextScout, CoderAgent, and TaskManager have Mimir tools built-in. When spawning them, tell them to call `enrich_task()` first.

## Recursive Development

When working on Mimir itself, use Mimir to understand Mimir. Every task starts with `enrich_task()`. Failed queries = documentation gaps to fix.
