# Mimir — Persistent Knowledge Base for AI Agents

A semantic knowledge base that gives your AI agents instant access to your codebase, eliminating repeated discovery and context loss between sessions.

**Now embedded directly in [ecode](https://github.com/ewheels44/ecode) (a fork of [Jcode](https://github.com/1jehuang/jcode)) — no MCP server needed.**

---

## Quick Start

```bash
# 1. Clone Mimir
git clone https://github.com/ewheels44/Mimir.git ~/Mimir
# Or any location: git clone https://github.com/ewheels44/Mimir.git /path/to/your/Mimir

# 2. Run the install script
cd ~/Mimir
bash install.sh

# 3. Start a new shell or source your config
# (The installer will tell you if you need to do this)

# 4. Initialize a project for indexing
cd ~/Projects/YourProject
mimir init --code-dirs=src,tests

# 5. Index your project
mimir index

# 6. Start ecode — your agents now have semantic search.
```

### Install Script Options

```bash
bash install.sh                  # Install with defaults
bash install.sh --skip-web      # Skip building web UI (Rust + React)
bash install.sh --skip-hooks    # Skip git hooks installation
bash install.sh --force         # Force reinstallation
bash install.sh --help          # Show all options
```

The install script:
- Checks prerequisites (Python 3.12+, uv, Node.js, Rust)
- Sets up a Python virtual environment
- Installs all Python dependencies
- Optionally builds web components (Rust server + React client)
- Installs git hooks for auto-indexing
- Configures your shell PATH

To uninstall:
```bash
bash uninstall.sh              # Basic uninstall
bash uninstall.sh --purge      # Remove all data (knowledge bases, etc.)
```

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

## Core Architecture

Mimir combines three layers to give AI agents persistent, intelligent context:

### Hybrid RAG (Retrieval-Augmented Generation)

Mimir uses **hybrid retrieval** (vector + sparse) with LangGraph orchestration:

```
Query: "How does auth work?"
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                 Hybrid Retrieval                         │
│  ┌──────────────────┐    ┌──────────────────────────┐  │
│  │ Vector Search    │    │ Sparse Search (BM25)     │  │
│  │ Semantic match   │    │ Keyword match            │  │
│  └──────────────────┘    └──────────────────────────┘  │
│                   │                                     │
│                   ▼                                     │
│          Merge & Deduplicate (prefer vector)            │
└──────────────────────┬──────────────────────────────────┘
                       │ feeds into
                       ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph Orchestration                     │
│  • rag_workflow: retrieve → generate (2-step)           │
│  • knowledge_agent: multi-step agentic research         │
└──────────────────────┬──────────────────────────────────┘
                       │ uses
                       ▼
              LLM (OpenRouter) + Token Tracking
```

**Key components:**
- **Vector search**: LlamaIndex with `text-embedding-3-small` (configurable)
- **Sparse search**: BM25Retriever for keyword matching
- **LangGraph workflows**: `rag_workflow` (simple 2-step) or `knowledge_agent` (multi-step agentic)
- **Budget controls**: Limit tokens/costs per request via `max_tokens` and `max_cost_usd`

### Pre-Compiled Artifacts

For frequently-asked architectural questions, Mimir serves **pre-compiled knowledge** (inspired by Pinecone Nexus) instead of running retrieval every time:

```python
# Tries artifact first (instant, zero token cost)
get_artifact("rag_architecture")

# Falls back to rag_workflow if artifact missing/stale
rag_workflow(query="...")
```

**How artifacts work:**
1. **Generate**: Python functions in `scripts/generate_artifacts.py` create structured JSON summaries
2. **Store**: `.knowledge/artifacts/*.json` with `manifest.json` for dependency tracking
3. **Track dependencies**: Each artifact knows which source files it depends on
4. **Invalidate**: TTL (1 hour) + file watcher detects dependency changes
5. **Rebuild**: Lazy strategy — rebuilt on next query (not eager)

**Available artifacts:**
| Artifact ID | Content |
|-------------|---------|
| `rag_architecture` | RAG system design and components |
| `indexing_architecture` | Indexing system design |
| `artifact_system` | Artifact system itself |

**Benefits:** ⚡ Instant answers • 💰 Zero token cost • 🔄 Auto-invalidation when source changes

### Query Router (Standalone)

The **query router** (`src/mimir/query_router`) is the routing layer that classifies and routes every `enrich_task` call:

```
User task
    │
    ▼
_classify_query()  ──→  structural?  ──→  Knowledge Graph (Dijkstra)
    │                         │
    │  (keyword → neural →    │  (no path found)
    │   keyword fallback)     ▼
    │                   Vector Search (LlamaIndex)
    │
    └──→ semantic ────────→  Vector Search (LlamaIndex)
```

**Decision chain:**
1. **Keyword pre-check** (free) — 2+ structural keywords → instant routing
2. **Neural classifier** (10→8→2 NN, ~$0.000001) — handles uncertain cases
3. **Keyword fallback** (free) — final deterministic check

**Guardrails (all self-contained, zero external deps):**
- Circuit breaker: 3 failures → 60s cooldown
- LRU cache: 128 entries, 10min TTL
- Content filter: blocks sensitive data (API keys, IPs, private keys)
- Freshness scoring: exponential decay over 168h

📖 Full architecture: [docs/query-routing-architecture.md](docs/query-routing-architecture.md)

### Knowledge Graph

For structural questions ("How does X connect to Y?"), Mimir extracts code relationships using AST + tree-sitter:

```
Code → AST + tree-sitter → Relationships → Rust Graph Server (Weighted Dijkstra)
```

**Tools:** `graph_query(source, target)` • `graph_neighbors(node)` • `graph_stats()`

**Relationship weights** (stronger coupling = lower weight):
| Relationship | Weight | Meaning |
|-------------|--------|---------|
| `calls` / `has_method` | 1.0 | Direct function/method call |
| `inherits_from` | 1.5 | Class inheritance |
| `imports_from` | 2.0 | Specific symbol import |
| `imports_module` | 3.0 | Whole-module import |

---

**In summary, Mimir gives agents:**
- **Semantic search** → "What does auth do?" (vector + BM25 hybrid)
- **Structured answers** → "Explain the RAG architecture" (artifacts or rag_workflow)
- **Structural understanding** → "How does auth reach the database?" (graph query with Dijkstra)
- **External docs** → "How do I use Stripe checkout?" (SDK cache with 7-day TTL)

---

## ecode Integration

Mimir is now **embedded directly into ecode**, a fork of Jcode. This means:
- No MCP server setup required
- Mimir tools are native to ecode
- Direct function calls instead of MCP transport
- Simplified architecture with better performance

### Using Mimir Tools in ecode

Once your project is indexed, ecode agents can call Mimir tools directly:

```
# In ecode conversation:
mimir(action="enrich_task", params={"task": "Implement JWT auth"})
mimir(action="search", params={"query": "database connection pooling"})
mimir(action="query", params={"question": "How does the caching layer work?"})
mimir(action="graph_query", params={"source": "auth middleware", "target": "database pool"})
mimir(action="sdk_cache_get", params={"library": "stripe", "topic": "checkout sessions"})
```

### ecode-Specific Features

Since Mimir is embedded in ecode, you get:
- **Native tool access** — No MCP bridge overhead
- **Direct function calls** — `mimir(action=..., params=...)` instead of HTTP/MCP transport
- **Tighter integration** — ecode's agent system has direct access to Mimir's internals
- **Better performance** — No serialization/deserialization overhead

---

## Fresh System Installation

### Prerequisites

| Requirement | How to Install | Verify |
|-------------|----------------|--------|
| **Python 3.12+** | `brew install python` or [python.org](https://python.org) | `python3 --version` |
| **uv package manager** | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **OpenRouter API key** | [openrouter.ai](https://openrouter.ai) → Settings → Keys | — |

Note: ecode (jcode fork) is only needed if you want to use Mimir with an editor. The install script and CLI work independently.

### Installation

```bash
# 1. Clone Mimir
git clone https://github.com/ewheels44/Mimir.git ~/Mimir
# Or any location: git clone https://github.com/ewheels44/Mimir.git /your/preferred/path

# 2. Run the install script
cd ~/Mimir
bash install.sh

# The script will:
# - Check prerequisites (Python, uv, Node.js, Rust)
# - Set up Python virtual environment
# - Install all dependencies
# - Optionally build web UI components
# - Install git hooks for auto-indexing
# - Configure your shell PATH

# 3. Start a new shell or source your config
# (The installer will tell you if you need to do this)

# 4. Set your API key (if not already configured)
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
# Or add it to ~/.zshrc / ~/.bashrc for persistence
```

### Install Script Options

```bash
bash install.sh                  # Install with defaults
bash install.sh --skip-web      # Skip building web UI (Rust + React)
bash install.sh --skip-hooks    # Skip git hooks installation
bash install.sh --force         # Force reinstallation
bash install.sh --help          # Show all options
```

### Next Steps

```bash
# 1. Initialize a project for indexing
cd ~/Projects/YourProject
mimir init --code-dirs=src,tests

# 2. Index your project
mimir index

# 3. Start using Mimir with ecode or CLI
mimir search "How does auth work?"
```

### Step 4: Index Your Content

```bash
# Add documentation
echo "# My Project Architecture" > docs/README.md

# Index docs only
mimir index

# Add source code (optional)
# Edit .mimir/config.json:
#   {"code_dirs": ["src", "tests"]}
mimir index --reindex

# Or add incrementally
mimir index --add src
```

### Step 5: Start ecode

```bash
cd ~/ecode
ecode
# Mimir tools are now available directly
```

---

## Project Setup

### Initialize a New Project

```bash
cd ~/Projects/YourProject
mimir init --code-dirs=src,tests
```

This creates:
```
YourProject/
├── docs/                    # Your documentation
├── .knowledge/llamaindex/   # Vector index (auto-generated)
├── .mimir/
│   ├── config.json          # Project configuration
│   └── AGENTS.md            # Local Mimir docs
└── .opencode/
    └── mimir-index.py       # Indexing script
```

### Index Your Content

```bash
# Add documentation
echo "# My Project Architecture" > docs/README.md

# Index docs only
mimir index

# Add source code (optional)
# Edit .mimir/config.json:
#   {"code_dirs": ["src", "tests"]}
mimir index --reindex

# Or add incrementally
mimir index --add src
```

### Query Your Knowledge Base

```bash
# One-shot search
mimir search "How does auth work?"

# RAG workflow
mimir rag "Explain the database layer"

# Knowledge agent
mimir agent "Find all API endpoints"

# Via ecode (automatic)
# Just ask questions — agents use Mimir tools directly
```

### Enable Auto-Indexing (Recommended)

Install the git hook so your knowledge base stays current automatically:

```bash
# Install in current project
bash /path/to/Mimir/scripts/install-git-hooks.sh

# Install in a specific project
bash /path/to/Mimir/scripts/install-git-hooks.sh /path/to/project

# Install in all Mimir projects
bash /path/to/Mimir/scripts/install-git-hooks.sh --all
```

After installation, every `git commit` triggers a background incremental reindex. No manual steps needed.

---

## Auto-Indexing

Mimir keeps your knowledge base current automatically via git hooks.

### How It Works

```
git commit
    │
    ▼
post-commit hook fires (background, non-blocking)
    │
    ▼
Checks if docs/ files changed in this commit
    │
    ├── No docs changes → skip (instant exit)
    │
    ▼
Detects changed files (SHA-256 content hashing)
    │
    ▼
Incremental reindex (only changed files)
    │
    ▼
Knowledge base updated — agents see fresh context
```

The post-commit hook (`scripts/git-hooks/post-commit`) is a lightweight bash
script that only triggers reindexing when documentation files under `docs/`
change. Source code changes alone don't trigger a reindex — edit `.mimir/config.json`
to add `code_dirs` if you want code changes tracked too.

### Features

- **Zero manual steps** — runs after every commit
- **Docs-aware** — only triggers when `docs/` content changes (configurable)
- **Content-aware** — only reindexes files whose content actually changed
- **Non-blocking** — runs synchronously but completes in seconds
- **Lock-protected** — prevents concurrent reindex runs
- **macOS compatible** — works on macOS and Linux

### Logs

```bash
# Check reindex activity
cat .mimir/reindex.log

# Check tracked files
mimir stats
```

---

## SDK Documentation Cache

Mimir caches SDK documentation locally so agents get current API references without repeated API calls.

### How It Works

```
Agent needs Stripe docs
    │
    ▼
Check .knowledge/sdk-cache/stripe/
    │
    ├── Fresh (< 7 days) → Use cached docs (instant)
    │
    └── Stale or missing → Fetch from Context7 API → Cache locally
```

### CLI Commands

| Command | Purpose |
|---------|---------|
| `mimir cache list` | List all cached libraries with freshness info |
| `mimir cache get stripe --topic "checkout sessions"` | Get docs for a library |
| `mimir cache refresh stripe --topic "webhooks"` | Force refresh |

### Cache Location

```
.knowledge/sdk-cache/
├── stripe/
│   ├── checkout-sessions.md
│   └── meta.json          # { "fetched_at": "...", "ttl_days": 7 }
├── react/
│   ├── usestate-hooks.md
│   └── meta.json
└── ...
```

---

## Knowledge Graph Query

Mimir extracts code relationships (imports, calls, inheritance) into a queryable knowledge graph with **weighted Dijkstra path-finding**. This gives agents structural understanding of your codebase — not just semantic similarity.

### How It Works

```
Code extraction (AST + tree-sitter)
    │
    ▼
code_relationships.json (entities + relationships)
    │
    ▼
Rust graph server (weighted Dijkstra, BFS neighbors, stats)
    │
    ▼
Mimir tools (graph_query, graph_neighbors, graph_stats)
```

### Semantic Search vs Graph Query

| Question Type | Tool | Example |
|---------------|------|---------|
| "What does auth do?" | `search` (semantic) | Finds docs/code about auth |
| "How does auth reach the database?" | `graph_query` (structural) | Traces import/call chain |
| "What depends on this module?" | `graph_neighbors` (topology) | Lists direct connections |
| "What are the most connected files?" | `graph_stats` | Shows hub modules |

### Edge Weights

Relationships are weighted by coupling strength — Dijkstra finds the **strongest coupling path**, not just the shortest:

| Relationship | Weight | Meaning |
|-------------|--------|---------|
| `calls` | 1.0 | Direct function/method call |
| `has_method` | 1.0 | Structural (class → method) |
| `inherits_from` | 1.5 | Class inheritance |
| `imports_from` | 2.0 | Specific symbol import |
| `imports_module` | 3.0 | Whole-module import |

External nodes (stdlib, third-party) are excluded from path-finding — only internal project connections are traced.

### Requirements

The graph query tools require the **Rust web server** to be running:

```bash
cd /path/to/Mimir/web
./dev.sh --project /path/to/your/project
```

The Mimir tools proxy graph queries to the Rust server via HTTP (`localhost:8000`). If the web server isn't running, graph tools return a clear error with instructions.

---

## Skills

Mimir includes seed skills that give agents immediate knowledge for common tasks.

### Available Skills

| Skill | Purpose |
|-------|---------|
| `mimir-knowledge` | Search the project knowledge base before executing tasks |
| `unified-query` | Single entry point — searches SDK cache and Mimir automatically |
| `sdk-onboarding` | Guide for onboarding developers to any SDK or library |
| `sdk-integration-pattern` | Common patterns for integrating external SDKs (config, errors, testing) |
| `find-and-follow-pattern` | "How do I add a new X?" — find existing patterns and follow them |
| `codebase-analysis-workflow` | Systematic codebase analysis in 5 steps |
| `system-health-check` | Comprehensive system diagnostics |
| `fde-customer-onboarding` | Fast onboarding to a customer's codebase (FDE) |
| `fde-call-prep` | Pre-call briefing with relevant code, patterns, and questions (FDE) |
| `fde-technical-writeup` | Post-call customer-facing documentation (FDE) |
| `fde-handoff` | Engagement-to-team transfer documentation (FDE) |
| `fde-shared-index` | Cross-codebase search with shared SDK indices (FDE) |

### Unified Query

The `unified-query` skill automatically hits all knowledge layers:

```
Your question
    │
    ▼
Layer 1: SDK Doc Cache ────── "Do I have fresh docs for this?"
    │
    ▼
Layer 2: Mimir Knowledge ──── "What does the project codebase say?"
    │
    ▼
Layer 3: Synthesize ───────── Combined answer with source attribution
```

### SDK Onboarding Flow

For new developers learning a project's SDK integrations:

```
Dev: "How do I add Stripe checkout to the billing page?"

1. Mimir: Finds existing payment code in the project
2. SDK cache: Fetches live Stripe API docs
3. Skill: Guides integration following project patterns
4. Agent: Proposes plan using all three sources
5. Dev: Approves → Agent implements
```

---

## FDE Toolkit

Mimir includes a complete toolkit for Forward Deployed Engineers managing multiple customer engagements.

### Shared Index Composition

Reference large SDKs (indexed once globally) alongside customer code in a single query. Results are tagged with their source so the LLM never confuses reference docs with customer code.

```
~/.mimir/shared-indexes/           ← Global store (indexed ONCE)
├── acme-sdk/
│   └── llamaindex/
└── stripe-sdk/
    └── llamaindex/

~/customer-a/                      ← References shared index
├── .mimir/config.json
│   └── shared_indexes: { "acme-sdk": "~/.mimir/shared-indexes/acme-sdk/llamaindex" }
└── .knowledge/llamaindex/         ← Customer code only
```

**Setup:**

```bash
# 1. Index a shared SDK (once, globally)
mimir index --shared-index ~/path/to/sdk/ --name acme-sdk

# 2. List available shared indices
mimir index --shared-list

# 3. Add to your project's .mimir/config.json:
#    "shared_indexes": { "acme-sdk": "~/.mimir/shared-indexes/acme-sdk/llamaindex" }
```

**Searching with scope:**

```
# Search everything (local + shared)
mimir(action="search", params={"query": "voice pipeline", "scope": "all"})

# Search only customer code
mimir(action="search", params={"query": "voice pipeline", "scope": "local"})

# Search only the SDK
mimir(action="search", params={"query": "voice pipeline", "scope": "shared:acme-sdk"})
```

**Results are source-tagged:**

```
[1] [ACME SDK] agents/voice_pipeline.py (score: 0.91)
    Voice pipeline: STT → LLM → TTS...

[2] [YOUR CODE] src/auth/middleware.ts (score: 0.82)
    JWT validation for voice endpoints...
```

### Multi-Project Management

Manage multiple customer engagements with isolated knowledge bases:

```bash
# Register projects
mimir projects add ~/Projects/customer-a --name customer-a
mimir projects add ~/Projects/customer-b --name customer-b

# List all projects
mimir projects list

# Switch context
mimir projects switch customer-a

# Check status of all projects
mimir projects status

# Auto-discover projects in common locations
mimir projects discover
```

```
$ mimir projects list
Name                 Status     Index    Last Accessed
------------------------------------------------------------
customer-a           ✓          ✓        2026-04-07
customer-b           ✓          ✗        never
```

### Customer Call Prep

Generate a structured briefing before a customer call:

```bash
# Generate a structured briefing before a customer call
mimir prep "video latency issues"
mimir prep "payment integration" --customer acme-corp
```

The briefing includes:
1. **Relevant Code Sections** — key files and functions related to the topic
2. **Known Patterns** — how this codebase handles this type of functionality
3. **Questions to Ask** — clarifying questions based on what's in the code
4. **Common Pitfalls** — integration risks and edge cases
5. **Proposed Approach** — high-level recommendation
6. **Things to Verify** — what to check during the call

### Session Diff

See what you learned in recent sessions:

```bash
# What happened in the last day?
mimir diff

# Last 3 days
mimir diff --days 3
```

The report includes:
- Knowledge base status (freshness, coverage)
- Activity summary (query types, costs)
- What you learned (topics explored)
- Focus areas for next session

### Handoff Documentation

Generate a handoff document when transferring to the permanent team:

```bash
# Generate for current directory
mimir handoff

# Generate for a registered project
mimir handoff --project customer-a

# With engagement summary
mimir handoff --project customer-a \
  --summary "Built video calling integration using WebRTC" \
  --customer "Acme Corp"

# Custom output path
mimir handoff --project customer-a -o docs/handoff.md
```

The handoff document includes 9 sections:
1. Project Overview
2. Tech Stack
3. Architecture
4. Key Files
5. What Was Built
6. Integration Points
7. How to Extend
8. Knowledge Base (how to use it)
9. Next Steps

---

## Usage Examples

### In ecode Sessions

```
User: "How does authentication work?"
Agent: [Calls mimir with action="search"] → Finds auth.py, middleware.py, jwt.ts
Agent: "The auth flow uses JWT with refresh tokens..."

User: "Find all database migrations"
Agent: [Calls mimir with action="query"] → Returns migration files and patterns

User: "What changed in the API recently?"
Agent: [Calls mimir with action="rag_workflow"] → Structured analysis with sources
```

### Available Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `search` | Semantic search | Finding files by concept |
| `query` | Natural language Q&A | Understanding architecture |
| `rag_workflow` | Structured reasoning | Complex analysis |
| `knowledge_agent` | Agentic exploration | Deep research tasks |
| `graph_query` | Weighted Dijkstra path between modules | "How does X connect to Y?" |
| `graph_neighbors` | BFS neighbors with depth/type filter | "What depends on this?" |
| `graph_stats` | Graph overview (nodes, edges, top connected) | "What are the hub files?" |
| `stats` | Index statistics | Checking coverage |
| `reindex` | Rebuild index | After major changes |
| `sdk_cache_get` | Get SDK docs | Fetching library documentation |
| `sdk_cache_list` | List cached SDKs | Checking what's cached |
| `enrich_task` | Project context for tasks | Before executing any task |
| `task_health` | Check query router + config | Before depending on enrich_task |
| `health_check` | Server health + config diagnostics | Debugging setup issues |

### How It Works

Since Mimir is embedded in ecode, the integration is straightforward:

```python
# ecode calls Mimir tools directly (no MCP overhead)
mimir(action="search", params={"query": "authentication patterns"})
mimir(action="enrich_task", params={"task": "Implement JWT auth"})
mimir(action="graph_query", params={"source": "auth.py", "target": "database.py"})
```

---

## Working Configuration Example

Here's a complete working setup with ecode:

### Directory Structure

```
/path/to/Mimir/           # Central installation
├── mimir                   # Unified CLI (all commands)
├── src/mimir/               # Core modules
│   ├── config.py                 # Unified configuration (MimirConfig)
│   ├── utils.py                  # Shared utilities
│   ├── indexing.py               # Document indexing
│   ├── shared_index.py           # Shared index composition
│   ├── sdk_cache.py              # SDK doc caching
│   ├── knowledge_graph.py        # Code relationship extraction
│   ├── query_router.py           # Query router (standalone, zero ecode deps)
│   ├── artifacts.py              # Pre-compiled knowledge artifacts
│   ├── handoff.py                # Handoff document generator
│   ├── projects.py               # Multi-project management
│   ├── metrics.py                # Cost tracking
│   ├── token_callback.py         # LangChain callback for actual token usage
│   └── watcher.py                # File watcher
├── tests/                   # Test suite
├── langgraph/               # Workflows
│   ├── workflows/
│   │   ├── rag.py                # Basic RAG workflow (with token tracking)
│   │   ├── knowledge_agent.py    # Agentic exploration (with token tracking)
│   │   ├── call_prep.py          # Customer call briefing (with token tracking)
│   │   ├── session_diff.py       # Session diff report (with token tracking)
│   │   └── utils.py              # Shared workflow utilities
│   └── cli.py                    # Workflow CLI
├── scripts/                 # Utilities
│   ├── generate_artifacts.py     # Artifact generators
│   ├── git-hooks/                # Auto-index git hooks
│   └── install-git-hooks.sh      # Hook installer
└── web/                     # Rust web server + React UI
    ├── server/                    # Rust graph server
    └── sidecar/                   # Python sidecar for ecode integration

~/Projects/AnyProject/       # Any project using Mimir
├── docs/
├── .knowledge/
│   ├── llamaindex/               # Vector index
│   └── sdk-cache/                # Cached SDK docs
├── .mimir/
│   ├── config.json               # Project config (includes shared_indexes)
│   ├── index_state.json          # File hash tracking
│   └── reindex.log               # Auto-index logs
└── HANDOFF.md                    # Generated handoff doc (if created)

~/.mimir/                    # Global Mimir data
├── shared-indexes/               # Shared SDK indices
│   ├── acme-sdk/llamaindex/
│   └── stripe-sdk/llamaindex/
└── projects.json                 # Multi-project registry
```

### Project Config: `.mimir/config.json`

All configuration flows through a single source of truth: `src/mimir/config.py` (`MimirConfig`).

**Resolution order** (highest priority first):
1. Environment variables
2. `.mimir/config.json` (project-level)
3. Defaults

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small",
  "llm_model": "google/gemini-3.1-flash-lite-preview",
  "sdk_cache_ttl_days": 7,
  "shared_indexes": {
    "acme-sdk": "~/.mimir/shared-indexes/acme-sdk/llamaindex"
  }
}
```

### Environment Variable Overrides

Any config value can be overridden via environment variables:

| Variable | Config Key | Default |
|----------|-----------|---------|
| `OPENROUTER_API_KEY` | API key | — |
| `OPENAI_API_KEY` | API key (fallback) | — |
| `OPENAI_BASE_URL` | API base URL | `https://openrouter.ai/api/v1` |
| `EMBEDDING_MODEL` | `embedding_model` | `text-embedding-3-small` |
| `MIMIR_LLM_MODEL` | `llm_model` | `google/gemini-3.1-flash-lite-preview` |
| `PROJECT_ROOT` | Project root | Auto-detected |
| `MIMIR_ROOT` | Mimir install dir | Auto-detected |
| `MIMIR_SDK_CACHE_TTL` | `sdk_cache_ttl_days` | `7` |

### Shared Index Configuration

Shared indices are configured in `.mimir/config.json` (not env vars):

```json
{
  "shared_indexes": {
    "acme-sdk": "~/.mimir/shared-indexes/acme-sdk/llamaindex",
    "stripe-sdk": "~/.mimir/shared-indexes/stripe-sdk/llamaindex"
  }
}
```

| CLI Command | Purpose |
|-------------|---------|
| `mimir index --shared-index DIR --name NAME` | Index a directory as a shared reference |
| `mimir index --shared-list` | List available shared indices |
| `mimir(action="search", params={"query": "...", "scope": "all"})` | Search local + all shared indices |
| `mimir(action="search", params={"query": "...", "scope": "local"})` | Search only local project code |
| `mimir(action="search", params={"query": "...", "scope": "shared:NAME"})` | Search only a specific shared index |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Entry Points                                           │
│  mimir │ langgraph/cli.py │ ecode (embedded)    │
└──────────────────────┬──────────────────────────────────┘
                       │ all use
                       ▼
┌─────────────────────────────────────────────────────────┐
│  MimirConfig (src/mimir/config.py)                      │
│  Single source of truth for ALL settings                │
│  env vars → .mimir/config.json → defaults               │
└──────────────────────┬──────────────────────────────────┘
                       │ provides config to
           ┌───────────┼───────────┐
           ▼           ▼           ▼
    ┌────────────┐ ┌────────┐ ┌──────────┐
    │ ecode      │ │Query   │ │ LangGraph│
    │ (embedded) │ │Router  │ │(RAG,     │
    │            │ │(standalone)│ │ agent)   │
    └─────┬──────┘ └───┬────┘ └────┬─────┘
          │            │           │
          └────────────┼───────────┘
                       ▼
              ┌─────────────────┐
              │   LlamaIndex    │
              │  (Vector Store) │
              └─────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Rust Web Server (web/server/)                          │
│  Graph query engine (Dijkstra, BFS neighbors, stats)    │
│  Proxied by Mimir tools for graph_* queries              │
│  Serves React UI for visualization                      │
└─────────────────────────────────────────────────────────┘
```

**Key Components**:
- **MimirConfig**: Unified configuration — one class, all settings, all entry points
- **ecode Integration**: Mimir is embedded directly in ecode (no MCP server needed)
- **Query Router** (`src/mimir/query_router.py`): Standalone routing — classification, graph/vector search, circuit breaker, caching, content filtering
- **Rust Web Server**: Graph query engine with weighted Dijkstra path-finding, serves the React UI
- **LlamaIndex**: Document ingestion, chunking, embeddings, vector storage
- **LangGraph**: Advanced RAG workflows and agentic exploration

---

## Web UI

Visual interface for exploring your knowledge base:

```bash
# Development mode
cd /path/to/Mimir/web
./dev.sh --project /path/to/your/project

# Production build
./build.sh
./server/target/release/mimir-web --project /path/to/project
```

Features:
- Interactive knowledge graph visualization
- Semantic search interface
- Cost metrics dashboard
- Document relationship exploration
- Graph query API (`/api/graph/path`, `/api/graph/neighbors`, `/api/graph/stats`)

---

## Cost Tracking

Mimir tracks usage and calculates savings:

```bash
# View 30-day report
mimir metrics

# View last 7 days
mimir metrics --days 7
```

**Typical Savings**: 60-80% reduction in token costs vs. traditional exploration.

---

## CLI Reference

All commands go through a single entry point: `mimir`

```bash
mimir <command>
```

### Core

| Command | Purpose |
|---------|---------|
| `mimir init` | Initialize a project for Mimir |
| `mimir stats` | Show index statistics |
| `mimir health` | Check configuration and status |

### Indexing

| Command | Purpose |
|---------|---------|
| `mimir index` | Index documents |
| `mimir index --reindex` | Rebuild index from scratch |
| `mimir index --add DIR` | Add directory to existing index |
| `mimir index --shared-index DIR --name NAME` | Index as shared reference |
| `mimir index --shared-list` | List shared indices |

### Search & Analysis

| Command | Purpose |
|---------|---------|
| `mimir search "query"` | One-shot semantic search |
| `mimir rag "question"` | RAG workflow |
| `mimir agent "question"` | Knowledge agent workflow |

### FDE Workflows

| Command | Purpose |
|---------|---------|
| `mimir prep "topic"` | Customer call briefing |
| `mimir prep "topic" --customer NAME` | Call briefing with customer name |
| `mimir diff` | Session diff (last day) |
| `mimir diff --days 3` | Session diff (last 3 days) |
| `mimir handoff` | Generate handoff doc |
| `mimir handoff --project NAME --customer "..."` | Handoff for specific project |

### Multi-Project

| Command | Purpose |
|---------|---------|
| `mimir projects list` | List registered projects |
| `mimir projects add PATH` | Register a project |
| `mimir projects add PATH --name NAME` | Register with custom name |
| `mimir projects remove NAME` | Unregister a project |
| `mimir projects switch NAME` | Switch to a project |
| `mimir projects status` | Show all project status |
| `mimir projects discover` | Find projects in common locations |

### SDK Cache

| Command | Purpose |
|---------|---------|
| `mimir cache list` | List cached libraries |
| `mimir cache get LIBRARY` | Get SDK docs (fetches if stale) |
| `mimir cache get LIBRARY --topic TOPIC` | Get specific topic |
| `mimir cache refresh LIBRARY` | Force refresh |
| `mimir cache invalidate LIBRARY` | Remove cached docs |

### Metrics

| Command | Purpose |
|---------|---------|
| `mimir metrics` | Cost report (30 days) |
| `mimir metrics --days 7` | Cost report (7 days) |

---

## Troubleshooting

### Quick Diagnosis

```bash
mimir health
```

This returns:
- Configuration summary
- Index availability and freshness
- API key presence
- Validation warnings

### "No module named 'llama_index'"

The CLI can run with either `uv` or plain `python3`. If both are missing:

```bash
cd /path/to/Mimir
uv sync
```

### "OPENROUTER_API_KEY not set"

```bash
# Check what MimirConfig sees:
cd /path/to/YourProject
python -c "from src.mimir.config import get_config, reset_config; reset_config(); c = get_config(); print(c.to_dict())"
```

### "Knowledge base not found"

```bash
# Check configuration
mimir health

# Index the project
mimir index
```

### Workflow Token Tracking

All LangGraph workflows (`rag`, `agent`, `prep`, `session-diff`) now track **actual token usage** via `TokenUsageCallbackHandler` (in `src/mimir/token_callback.py`). This hooks into LangChain's callback system to capture real prompt/completion token counts from API responses, replacing previous estimates. Metrics are automatically recorded per query.

---

## Documentation

- **[AGENTS.md](AGENTS.md)** — Comprehensive agent documentation (indexing, workflows, API reference)
- **[docs/](docs/)** — Additional documentation

---

## Changelog (Recent)

Notable changes in the current version:

| Change | Impact |
|--------|--------|
| **Embedded in ecode** | Mimir is now embedded directly in ecode (jcode fork) — no MCP server needed |
| **CLI renamed** | `mimir.py` → `mimir` to clarify CLI-only role |
| **Removed MCP dependencies** | Dropped `langchain-mcp-adapters` and MCP server code |
| **Direct function calls** | ecode calls Mimir tools directly instead of via MCP transport |
| **Simplified architecture** | Better performance, less overhead, tighter integration |
| **LangGraph token tracking** | `TokenUsageCallbackHandler` captures actual token usage from API calls in all workflows |
| **Batch indexing** | Documents indexed in batches to reduce API calls and memory usage |

---

## License

MIT
