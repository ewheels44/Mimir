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

Mimir provides **two entry points** for different use cases:

```
┌─────────────────────────────────────────────────────────┐
│  Entry Points                                           │
│  ┌──────────────────┐  ┌──────────────────────────┐   │
│  │ mimir_bridge.py  │  │ langgraph/cli.py         │   │
│  │ (JSON stdin/stdout│  │ (Terminal CLI            │   │
│  │  for ecode/jcode)│  │  rag, agent, prep, diff)│   │
│  └─────────┬────────┘  └───────────┬──────────────┘   │
└────────────┼──────────────────────┼────────────────────┘
             │                      │
             ▼                      ▼
┌─────────────────────────────────────────────────────────┐
│  LangGraph Workflows (langgraph/workflows/)             │
│  • rag.py → RAG workflow (2-step retrieve + generate)   │
│  • knowledge_agent.py → Multi-step agentic research     │
│  • call_prep.py → Customer call briefing               │
│  • session_diff.py → Session comparison                │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Core Components                                         │
│  • LlamaIndex (vector store + BM25 sparse search)       │
│  • Query Router (classification + routing)              │
│  • Knowledge Graph (code relationships)                  │
│  • SDK Cache (external library docs)                    │
└─────────────────────────────────────────────────────────┘
```

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
| `search` | Semantic search (vector + BM25 hybrid) |
| `query` | Natural language Q&A |
| `rag_workflow` | Structured RAG (2-step) |
| `knowledge_agent` | Multi-step agentic research |
| `enrich_task` | Get project context before tasks |
| `reindex` | Rebuild the knowledge base |
| `remove_file` | Remove file from index |
| `stats` | Index statistics |
| `task_health` | Check query router health |
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
# Index documentation
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

# Check index status
echo '{"action":"stats","params":{}}' | python3 mimir_bridge.py
```

### Auto-Indexing (Optional)

Install git hooks to automatically reindex on commits:

```bash
bash scripts/install-git-hooks.sh
```

---

## Web UI (Optional)

Visual interface for exploring your knowledge base:

```bash
cd /path/to/Mimir/web
./dev.sh --project /path/to/your/project
```

Features:
- Interactive knowledge graph visualization
- Semantic search interface
- Cost metrics dashboard
- Document relationship exploration

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Entry Points                                           │
│  mimir_bridge.py (JSON) │ langgraph/cli.py (CLI)     │
└──────────────────────┬──────────────────────────────────┘
                       │ use
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LangGraph Workflows                                     │
│  rag.py │ knowledge_agent.py │ call_prep.py           │
└──────────────────────┬──────────────────────────────────┘
                       │ use
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Core Components                                         │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ LlamaIndex   │  │ Query       │  │ Knowledge  │  │
│  │ (Vector +    │  │ Router      │  │ Graph     │  │
│  │  BM25)      │  │ (Smart      │  │ (Code     │  │
│  │              │  │  Routing)   │  │  Relations)│  │
│  └──────────────┘  └─────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────┘
                       │ stores to / reads from
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Storage                                                 │
│  .knowledge/llamaindex/   (vector index)                │
│  .knowledge/sdk-cache/    (SDK documentation)            │
│  .mimir/config.json       (project config)               │
└─────────────────────────────────────────────────────────┘
```

**Key Files:**

```
/path/to/Mimir/
├── mimir_bridge.py           # JSON bridge (ecode/jcode)
├── langgraph/
│   ├── workflows/
│   │   ├── rag.py                # RAG workflow
│   │   ├── knowledge_agent.py    # Agentic research
│   │   ├── call_prep.py         # Call briefing
│   │   └── session_diff.py      # Session comparison
│   └── cli.py                    # Terminal CLI
├── src/mimir/
│   ├── config.py                 # Unified configuration
│   ├── indexing.py              # Document indexing
│   ├── query_router.py          # Smart query routing
│   ├── knowledge_graph.py        # Code relationships
│   ├── sdk_cache.py             # SDK documentation cache
│   └── metrics.py               # Cost tracking
├── web/
│   ├── server/                    # Rust graph server
│   └── client/                   # React UI
└── scripts/
    └── install-git-hooks.sh      # Auto-indexing hooks
```

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
  "sdk_cache_ttl_days": 7
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

---

## Troubleshooting

### Check Installation

```bash
# Verify Python environment
cd ~/Mimir
source .venv/bin/activate
python -c "import llama_index; print('✓ LlamaIndex OK')"

# Test the bridge
echo '{"action":"stats","params":{}}' | python3 mimir_bridge.py
```

### "No module named 'llama_index'"

```bash
cd ~/Mimir
uv sync
```

### "OPENROUTER_API_KEY not set"

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key"
# Or add to ~/.zshrc for persistence
```

### "Knowledge base not found"

```bash
# Index your project first
cd /path/to/your/project
# (See "Indexing Your Project" section above)
```

---

## Cost Tracking

Mimir tracks usage and calculates savings:

```bash
python langgraph/cli.py metrics --days 30
```

**Typical Savings**: 60-80% reduction in token costs vs. traditional exploration.

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

---

## License

MIT
