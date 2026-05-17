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
.artifacts/rag_architecture.json     # RAG system architecture
.artifacts/indexing_architecture.json # Indexing system architecture
.artifacts/manifest.json               # Dependency tracking
```

Artifacts track which source files they depend on, and auto-invalidate when those files change (via the file watcher).

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
| `mimir-knowledge_graph_query` | Weighted Dijkstra path between two nodes | "How does X connect to Y?" |
| `mimir-knowledge_graph_neighbors` | BFS neighbors with depth/type filter | "What depends on this?" |
| `mimir-knowledge_graph_stats` | Graph overview (nodes, edges, top connected) | "What's the most connected module?" |
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
│   ├── openspace_bridge.py     # OpenSpace integration
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
├── docs/                       # Documentation (indexed)
├── opencode-config/            # OpenCode configuration
│   ├── opencode.json
│   └── agent/                  # Subagent configs
├── mimir-demo/                 # Demo web app (React + TypeScript)
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
| `src/mimir/config.py` | Unified config — single source of truth |
| `src/mimir/indexing.py` | Document indexing — full, incremental, file-level |
| `src/mimir/artifacts.py` | Pre-compiled artifacts — dependency tracking, staleness |
| `src/mimir/openspace_bridge.py` | OpenSpace integration — circuit breaker, cache, content filter |
| `src/mimir/sdk_cache.py` | SDK doc cache — Context7 API, TTL, local storage |
| `src/mimir/shared_index.py` | Cross-codebase search — shared index composition |
| `src/mimir/knowledge_graph.py` | Code relationship extraction — AST + tree-sitter |
| `src/mimir/metrics.py` | Cost/token tracking — per-component breakdown |
| `src/mimir/watcher.py` | File watcher — auto-reindex on changes, invalidates artifacts |
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

Budget checking uses `metrics.py` to track usage over the last 24 hours. Warnings are issued when <10% budget remains.

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

## When to Skip Mimir

- Typo fixes in known files
- Single-file changes where you already know the content
- Pure bash operations (ls, git status, etc.)

## Subagents

ContextScout, CoderAgent, and TaskManager have Mimir tools built-in. When spawning them, tell them to call `enrich_task()` first.

## Recursive Development

When working on Mimir itself, use Mimir to understand Mimir. Every task starts with `enrich_task()`. Failed queries = documentation gaps to fix.
