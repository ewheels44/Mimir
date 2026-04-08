# Mimir — Agent Reference

> Rules are in RULES.md (4 rules). This file is reference material — read when needed.

## What Mimir Is

A per-project knowledge base that gives AI agents memory. Three layers:

```
LlamaIndex (vector search) ← MCP (tool bridge) ← LangGraph (workflows)
```

Each project gets its own index at `.knowledge/llamaindex/`. The MCP server auto-detects which project you're in.

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
| `mimir-knowledge_reindex` | Rebuild the full index | After major changes |
| `mimir-knowledge_health_check` | Check server status | Debugging |
| `mimir-knowledge_stats` | Index statistics | Check what's indexed |
| `openspace_search_skills` | Find evolved skills | Before executing |
| `openspace_execute_task` | Run a task with skill guidance | Skill-guided execution |

## Tool Priority

```
1. enrich_task     → project memory (always first)
2. sdk_cache_get   → library docs (before guessing)
3. search          → find by meaning
4. query           → synthesized understanding
5. rag_workflow    → structured analysis
6. knowledge_agent → deep research
```

## Project Structure

```
.mimir/config.json          # Per-project config (optional, defaults work)
.knowledge/llamaindex/      # Vector index (auto-created)
.knowledge/sdk-cache/       # Cached SDK docs
.knowledge/code_relationships.json  # Knowledge graph
docs/                       # Indexed documentation
.opencode/mimir-index.py    # Project indexing script
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
| `src/mimir/openspace_bridge.py` | OpenSpace integration — circuit breaker, cache, content filter |
| `src/mimir/sdk_cache.py` | SDK doc cache — Context7 API, TTL, local storage |
| `src/mimir/shared_index.py` | Cross-codebase search — shared index composition |
| `src/mimir/knowledge_graph.py` | Code relationship extraction — AST + tree-sitter |
| `src/mimir/metrics.py` | Cost/token tracking — per-component breakdown |
| `src/mimir/watcher.py` | File watcher — auto-reindex on changes |
| `mimir-init.py` | Installer — global setup + per-project init |
| `langgraph/workflows/rag.py` | RAG workflow — retrieve → generate |
| `langgraph/workflows/knowledge_agent.py` | Knowledge agent — multi-step research |

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
