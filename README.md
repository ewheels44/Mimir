# Mimir — Persistent Knowledge Base for AI Agents

A semantic knowledge base that gives your AI agents instant access to your codebase, eliminating repeated discovery and context loss between sessions.

**Works with**: [Jcode](https://github.com/1jehuang/jcode) • [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode) • [OpenAgents](https://github.com/darrenhinde/OpenAgentsControl)

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ewheels44/Mimir.git ~/Mimir
# Or any location you prefer: git clone https://github.com/ewheels44/Mimir.git /path/to/your/Mimir

# 2. Global install (once — sets up MCP server + system rules)
python /path/to/Mimir/mimir.py install

# 3. Per-project (in each project you want to index)
cd ~/Projects/YourProject
python /path/to/Mimir/mimir.py init --code-dirs=src,tests

# 4. Restart OpenCode — your agents now have semantic search.
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

## Jcode Integration

Mimir includes a built-in Jcode bridge for seamless integration with the [Jcode](https://github.com/1jehuang/jcode) agent server.

### Quick Setup

```bash
# 1. Start Jcode
jcode

# 2. In another terminal, install Mimir and auto-configure Jcode
cd ~/Projects/YourProject
python /path/to/Mimir/mimir-init.py --jcode
```

This does three things:
1. **Registers a Jcode skill** → `~/.jcode/skills/mimir-{project}.json` with all Mimir tools
2. **Injects a system prompt** → `~/.jcode/prompts/mimir-{project}.md` with usage instructions
3. **Registers the MCP server** → `~/.jcode/mcp.json` with the Mimir MCP server config

### Manual Configuration

If you prefer to configure things by editing files:

**MCP Config** (`~/.jcode/mcp.json`):
```json
{
  "servers": {
    "mimir-my-project": {
      "command": "python3",
      "args": ["/path/to/Mimir/mcp_server_llamaindex.py"],
      "env": {
        "PROJECT_ROOT": "/path/to/your/project",
        "PYTHONPATH": "/path/to/Mimir/src"
      }
    }
  }
}
```

**Per-project config** (`.jcode/mcp.json` in project root) works too — same format.

### Using Mimir Tools in Jcode

Once configured, Jcode agents can call Mimir tools directly:

```
/mcp reload                    # Pick up new MCP servers

# Then in conversation:
mimir-knowledge_enrich_task("Implement JWT auth")
mimir-knowledge_search("database connection pooling")
mimir-knowledge_query("How does the caching layer work?")
mimir-knowledge_graph_query("auth middleware", "database pool")
mimir-knowledge_sdk_cache_get("stripe", "checkout sessions")
```

### Checking Status

```bash
# From within a Mimir-enabled project:
python /path/to/Mimir/scripts/jcode/mimir_bridge.py --check

# Or register manually:
python /path/to/Mimir/scripts/jcode/mimir_bridge.py --auto
```

Alternatively, verify Jcode integration from any project:

```bash
mimir jcode --check
```

---

## Fresh System Installation

### Prerequisites

| Requirement | How to Install | Verify |
|-------------|----------------|--------|
| **Python 3.11+** | `brew install python` or [python.org](https://python.org) | `python3 --version` |
| **uv package manager** | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `uv --version` |
| **oh-my-opencode** | See [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode) | `opencode --version` |
| **OpenRouter API key** | [openrouter.ai](https://openrouter.ai) → Settings → Keys | — |

### Step 1: Clone Mimir

```bash
git clone https://github.com/ewheels44/Mimir.git ~/Mimir
# Or any location: git clone https://github.com/ewheels44/Mimir.git /your/preferred/path
```

### Step 2: Configure OpenRouter API Key

```bash
# Option A: Set environment variable (add to ~/.zshrc or ~/.bashrc)
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# Option B: Use opencode auth (recommended)
opencode auth openrouter
# Paste your key when prompted
```

### Step 3: Global Install

```bash
python /path/to/Mimir/mimir.py install
```

This does three things automatically:
1. Backs up your existing `~/.config/opencode/opencode.json` and `system-context.md`
2. Adds the Mimir MCP server to your global config (preserves existing entries)
3. Injects Mimir rules into your system context (marker-based, clean uninstall)

To uninstall later: `python /path/to/Mimir/mimir.py uninstall`

### Step 4: Verify Installation

```bash
# Restart OpenCode, then check tools are available
cd /path/to/Mimir
opencode
# Ask: "What tools are available?"
```

---

## Project Setup

### Initialize a New Project

```bash
cd ~/Projects/YourProject
python /path/to/Mimir/mimir.py init --code-dirs=src,tests
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
python /path/to/Mimir/mimir.py index

# Add source code (optional)
# Edit .mimir/config.json:
#   {"code_dirs": ["src", "tests"]}
python /path/to/Mimir/mimir.py index --reindex

# Or add incrementally
python /path/to/Mimir/mimir.py index --add src
```

### Query Your Knowledge Base

```bash
# One-shot search
python /path/to/Mimir/mimir.py search "How does auth work?"

# RAG workflow
python /path/to/Mimir/mimir.py rag "Explain the database layer"

# Knowledge agent
python /path/to/Mimir/mimir.py agent "Find all API endpoints"

# FDE workflows
python /path/to/Mimir/mimir.py prep "video latency issues"
python /path/to/Mimir/mimir.py diff --days 1

# Via opencode (automatic)
# Just ask questions — agents use Mimir tools automatically
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
python /path/to/Mimir/mimir.py stats
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

### MCP Tools

| Tool | Purpose |
|------|---------|
| `sdk_cache_get` | Get SDK docs (fetches + caches if stale) |
| `sdk_cache_list` | List all cached libraries with freshness info |

### Usage

```
# In opencode sessions — agents use these automatically
"How do I create a Stripe checkout session?"
# → Agent calls sdk_cache_get(library="stripe", topic="checkout sessions")
# → Gets live API docs, cached for 7 days
```

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

### CLI

```bash
# List cached libraries
python /path/to/Mimir/mimir.py cache list

# Get docs for a library
python /path/to/Mimir/mimir.py cache get stripe --topic "checkout sessions"

# Force refresh
python /path/to/Mimir/mimir.py cache refresh stripe --topic "webhooks"
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
Rust graph server (weighted Dijkstra, BFS neighbors)
    │
    ▼
MCP tools (graph_query, graph_neighbors, graph_stats)
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

### MCP Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `graph_query` | Find shortest weighted path between two modules | "How does watcher.py reach indexing.py?" |
| `graph_neighbors` | Explore connections around a node | "What does config.py import?" |
| `graph_stats` | Graph overview (counts, top connected) | "What are the hub files?" |

### Usage

```
# In opencode sessions — agents use these automatically for structural questions
"How does the MCP server reach the SDK cache?"
# → Agent calls graph_query(source="mcp_server_llamaindex.py", target="src/mimir/sdk_cache.py")
# → Returns: direct calls edge, cost 1.0

"What depends on config.py?"
# → Agent calls graph_neighbors(node_id="src/mimir/config.py", depth=1)
# → Returns: list of modules that import or call config.py
```

### Requirements

The graph query tools require the **Rust web server** to be running:

```bash
cd /path/to/Mimir/web
./dev.sh --project /path/to/your/project
```

The MCP server proxies graph queries to the Rust server via HTTP (`localhost:8000`). If the web server isn't running, graph tools return a clear error with instructions.

---

## Skills

Mimir includes seed skills that give agents immediate knowledge for common tasks.

### Available Skills

| Skill | Purpose |
|-------|---------|
| `mimir-knowledge` | Search the project knowledge base before executing tasks |
| `unified-query` | Single entry point — searches OpenSpace skills, SDK cache, and Mimir automatically |
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
Layer 1: OpenSpace Skills ─── "Do I already know the answer?"
    │
    ▼
Layer 2: SDK Doc Cache ────── "Do I have fresh docs for this?"
    │
    ▼
Layer 3: Mimir Knowledge ──── "What does the project codebase say?"
    │
    ▼
Layer 4: Synthesize ───────── Combined answer with source attribution
```

### SDK Onboarding Flow

For new developers learning a project's SDK integrations:

```
Dev: "How do I add Stripe checkout to the billing page?"

1. Mimir: Finds existing payment code in the project
2. SDK cache: Fetches live Stripe API docs
3. Skill: Guides integration following project patterns
4. Agent: Proposes plan using all three sources
5. Dev: Approves → Agent implements → OpenSpace learns
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
python /path/to/Mimir/mimir.py index --shared-index ~/path/to/sdk/ --name acme-sdk

# 2. List available shared indices
python /path/to/Mimir/mimir.py index --shared-list

# 3. Add to your project's .mimir/config.json:
#    "shared_indexes": { "acme-sdk": "~/.mimir/shared-indexes/acme-sdk/llamaindex" }
```

**Searching with scope:**

```
# Search everything (local + shared)
search(query="voice pipeline", scope="all")

# Search only customer code
search(query="voice pipeline", scope="local")

# Search only the SDK
search(query="voice pipeline", scope="shared:acme-sdk")
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
python /path/to/Mimir/mimir.py projects add ~/Projects/customer-a --name customer-a
python /path/to/Mimir/mimir.py projects add ~/Projects/customer-b --name customer-b

# List all projects
python /path/to/Mimir/mimir.py projects list

# Switch context
python /path/to/Mimir/mimir.py projects switch customer-a

# Check status of all projects
python /path/to/Mimir/mimir.py projects status

# Auto-discover projects in common locations
python /path/to/Mimir/mimir.py projects discover
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
python /path/to/Mimir/mimir.py prep "video latency issues"
python /path/to/Mimir/mimir.py prep "payment integration" --customer acme-corp
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
python /path/to/Mimir/mimir.py diff

# Last 3 days
python /path/to/Mimir/mimir.py diff --days 3
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
python /path/to/Mimir/mimir.py handoff

# Generate for a registered project
python /path/to/Mimir/mimir.py handoff --project customer-a

# With engagement summary
python /path/to/Mimir/mimir.py handoff --project customer-a \
  --summary "Built video calling integration using WebRTC" \
  --customer "Acme Corp"

# Custom output path
python /path/to/Mimir/mimir.py handoff --project customer-a -o docs/handoff.md
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

### In opencode Sessions

```
User: "How does authentication work?"
Agent: [Calls mimir-knowledge/search] → Finds auth.py, middleware.py, jwt.ts
Agent: "The auth flow uses JWT with refresh tokens..."

User: "Find all database migrations"
Agent: [Calls mimir-knowledge/query] → Returns migration files and patterns

User: "What changed in the API recently?"
Agent: [Calls mimir-knowledge/rag_workflow] → Structured analysis with sources
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
| `enrich_task` | Project context for tasks | Before executing OpenSpace tasks |
| `openspace_health` | Check Mimir-OpenSpace bridge | Before depending on enrich_task |
| `health_check` | Server health + config diagnostics | Debugging setup issues |

### Subagent Context (Critical)

When spawning subagents, they **don't inherit** Mimir context. But now they have Mimir tool permissions built-in!

**For subagents with built-in Mimir permissions (ContextScout, CoderAgent, TaskManager):**

```typescript
// CORRECT - Just include instructions in your prompt
task(
    subagent_type="ContextScout",
    prompt="Find authentication patterns. Use mimir-knowledge_search for project-specific queries."
)

// WRONG - load_skills parameter does NOT exist
task(
    subagent_type="ContextScout",
    load_skills=["mimir"],  // ❌ This parameter doesn't exist!
    prompt="Find authentication patterns..."
)
```

**For other subagents (explore, librarian), embed Mimir instructions in the prompt:**

```typescript
task(
    subagent_type="explore",
    run_in_background=true,
    prompt="Find authentication patterns. IMPORTANT: Use mimir-knowledge_search for project-specific queries instead of grep when available."
)
```

### How It Works

The install script (`mimir.py init`) copies Mimir-enhanced agent definitions to `~/.config/opencode/agent/`. These definitions include:

- `mimir-knowledge_search` — Semantic search across indexed docs/code
- `mimir-knowledge_query` — Synthesized answers from knowledge base
- `mimir-knowledge_enrich_task` — Project-specific context before executing
- `mimir-knowledge_sdk_cache_get` — Current API docs from cache

This ensures subagents can use Mimir tools without needing a `load_skills` parameter.

---

## Working Configuration Example

Here's a complete working setup from a real installation:

### Directory Structure

```
/path/to/Mimir/           # Central installation
├── mimir.py                       # Unified CLI (all commands)
├── mcp_server_llamaindex.py       # MCP server (used by mimir server)
├── mimir-init.py                  # Project initializer (used by mimir init)
├── mimir-projects.py              # Multi-project CLI (used by mimir projects)
├── scripts/
│   ├── run_mcp_server.sh         # MCP wrapper script
│   ├── git-hooks/
│   │   └── post-commit           # Auto-index git hook
│   ├── install-git-hooks.sh      # Hook installer
│   └── mimir-reindex-hook.py     # Hook reindex logic
├── src/mimir/               # Core modules
│   ├── config.py                 # Unified configuration (MimirConfig)
│   ├── utils.py                  # Shared utilities
│   ├── indexing.py               # Document indexing
│   ├── shared_index.py           # Shared index composition
│   ├── sdk_cache.py              # SDK doc caching
│   ├── knowledge_graph.py        # Code relationship extraction
│   ├── openspace_bridge.py       # OpenSpace integration (circuit breaker, caching)
│   ├── handoff.py                # Handoff document generator
│   ├── projects.py               # Multi-project management
│   ├── metrics.py                # Cost tracking
│   ├── token_callback.py         # LangChain callback for actual token usage
│   └── watcher.py                # File watcher
├── tests/                   # Test suite (264 tests)
│   ├── test_config.py
│   ├── test_indexing.py
│   ├── test_metrics.py
│   ├── test_openspace_bridge.py
│   ├── test_sdk_cache.py
│   └── test_utils.py
├── langgraph/               # Workflows
│   ├── workflows/
│   │   ├── rag.py                # Basic RAG workflow (with token tracking)
│   │   ├── knowledge_agent.py    # Agentic exploration (with token tracking)
│   │   ├── call_prep.py          # Customer call briefing (with token tracking)
│   │   ├── session_diff.py       # Session diff report (with token tracking)
│   │   └── utils.py              # Shared workflow utilities
│   └── cli.py                    # Workflow CLI
├── skills/                  # Agent skills
│   ├── mimir-knowledge/          # Knowledge base search
│   ├── unified-query/            # Multi-layer query orchestration
│   ├── sdk-onboarding/           # SDK onboarding guide
│   ├── sdk-integration-pattern/  # Integration patterns
│   ├── find-and-follow-pattern/  # Pattern discovery
│   ├── fde-customer-onboarding/  # FDE: fast codebase onboarding
│   ├── fde-call-prep/            # FDE: pre-call briefing
│   ├── fde-technical-writeup/    # FDE: post-call documentation
│   ├── fde-handoff/              # FDE: engagement handoff
│   └── fde-shared-index/         # FDE: shared index setup
└── opencode-plugin/         # System context plugin

~/Projects/AnyProject/       # Any project using Mimir
├── docs/
├── .knowledge/
│   ├── llamaindex/               # Vector index
│   └── sdk-cache/                # Cached SDK docs
├── .mimir/
│   ├── config.json               # Project config (includes shared_indexes)
│   ├── index_state.json          # File hash tracking
│   └── reindex.log               # Auto-index logs
├── .opencode/mimir-index.py
└── HANDOFF.md                    # Generated handoff doc (if created)

~/.mimir/                    # Global Mimir data
├── shared-indexes/               # Shared SDK indices
│   ├── acme-sdk/llamaindex/
│   └── stripe-sdk/llamaindex/
└── projects.json                 # Multi-project registry
```

### Global Config: `~/.config/opencode/opencode.json`

After running `mimir-init.py --install`, your config will include:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mimir-knowledge": {
      "command": ["/path/to/Mimir/scripts/run_mcp_server.sh"],
      "args": [],
      "env": {
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

The installer auto-detects your Mimir path — no manual editing needed.

### Jcode Bridge Commands

```bash
# Verify Jcode integration status
mimir jcode --check

# Quick setup (registers skill, prompt, and MCP config)
python /path/to/Mimir/scripts/jcode/mimir_bridge.py --auto

# Clean up all Mimir Jcode config
python /path/to/Mimir/scripts/jcode/mimir_bridge.py --unregister
```

### Auth Config: `~/.local/share/opencode/auth.json`

```json
{
  "openrouter": {
    "type": "api",
    "key": "sk-or-v1-your-key-here"
  }
}
```

### System Context Plugin: `~/.config/opencode/plugin/system-prompt.ts`

```typescript
import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "fs/promises"
import { execSync } from "child_process"
import { homedir } from "os"

const ENABLED = true
const PROMPT_FILE = `${homedir()}/.config/opencode/prompts/system-context.md`
const REMINDER_INTERVAL = 6
const MIMIR_REMINDER_TEXT = `[System Reminder]: **Mimir Context**: Remember to leverage Mimir tools (search, query, rag_workflow, knowledge_agent) for code exploration.`

// ... plugin implementation injects context on session start
```

### System Context: `~/.config/opencode/prompts/system-context.md`

The installer injects Mimir rules using markers for clean uninstall:

```markdown
# System Context
...

## MIMIR RULES (5 ONLY)

### 1. MIMIR FIRST
Before any task, call `mimir-knowledge_enrich_task()`.

### 2. CONTEXT BEFORE CODE
Before writing/editing, read the relevant standards file.

### 3. ASK FIRST
Never run bash/write/edit/task without approval.

### 4. CHECK SKILLS
Load matching skills before executing.

### 5. GRAPH FIRST
For structural questions ("how does X connect to Y?"), use `graph_query` or `graph_neighbors` before reading files.
<!-- MIMIR_RULES_END -->
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
  },
  "bridge": {
    "enabled": true,
    "cache_maxsize": 128,
    "cache_ttl_seconds": 600,
    "circuit_breaker_threshold": 3,
    "circuit_breaker_reset_seconds": 60,
    "search_timeout_seconds": 30.0,
    "max_context_tokens": 2500,
    "top_k": 5
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
| `MIMIR_OPENSPACE_ENABLED` | `bridge.enabled` | `true` |
| `MIMIR_BRIDGE_CACHE_SIZE` | `bridge.cache_maxsize` | `128` |
| `MIMIR_BRIDGE_CACHE_TTL` | `bridge.cache_ttl_seconds` | `600` |
| `MIMIR_BRIDGE_CB_THRESHOLD` | `bridge.circuit_breaker_threshold` | `3` |
| `MIMIR_BRIDGE_CB_RESET` | `bridge.circuit_breaker_reset_seconds` | `60` |
| `MIMIR_BRIDGE_TIMEOUT` | `bridge.search_timeout_seconds` | `30` |
| `MIMIR_BRIDGE_MAX_TOKENS` | `bridge.max_context_tokens` | `2500` |
| `MIMIR_BRIDGE_TOP_K` | `bridge.top_k` | `5` |
| `MIMIR_WEB_PORT` | Rust web server port | `8000` |

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
| `search(query="...", scope="all")` | Search local + all shared indices |
| `search(query="...", scope="local")` | Search only local project code |
| `search(query="...", scope="shared:NAME")` | Search only a specific shared index |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Entry Points                                           │
│  mcp_server_llamaindex.py │ langgraph/cli.py │ mimir-init.py
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
    │ MCP Server │ │ Bridge │ │ LangGraph│
    │ (search,   │ │(OpenSp)│ │(RAG,     │
    │  query,    │ │        │ │ agent)   │
    │  graph_*)  │ │        │ │          │
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
│  Proxied by MCP server for graph_* tools                │
│  Serves React UI for visualization                      │
└─────────────────────────────────────────────────────────┘
```

**Key Components**:
- **MimirConfig**: Unified configuration — one class, all settings, all entry points
- **MCP Server**: Tool discovery and transport (search, query, graph_query, health_check, etc.)
- **Rust Web Server**: Graph query engine with weighted Dijkstra path-finding, serves the React UI
- **OpenSpace Bridge**: Integration with self-evolving skill engine (circuit breaker, caching, content filtering)
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
python /path/to/Mimir/mimir.py metrics

# View last 7 days
python /path/to/Mimir/mimir.py metrics --days 7
```

**Typical Savings**: 60-80% reduction in token costs vs. traditional exploration.

---

## CLI Reference

All commands go through a single entry point: `mimir.py`

```bash
python /path/to/Mimir/mimir.py <command>
```

### Core

| Command | Purpose |
|---------|---------|
| `mimir init` | Initialize a project for Mimir |
| `mimir server` | Run the MCP server |
| `mimir health` | Check configuration and status |
| `mimir stats` | Show index statistics |

### Indexing

| Command | Purpose |
|---------|---------|
| `mimir index` | Index documents |
| `mimir index --reindex` | Rebuild index from scratch |
| `mimir index --add DIR` | Add directory to existing index |
| `mimir index --remove FILE` | Remove file from index |
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
python /path/to/Mimir/mimir.py health
```

This returns:
- Server status (healthy/degraded)
- Index availability and freshness
- API key presence
- Configuration summary
- Validation warnings

### "No module named 'llama_index'"

The MCP server can run with either `uv` or plain `python3`. If both are missing:

```bash
cd /path/to/Mimir
uv sync
```

### "OPENROUTER_API_KEY not set"

```bash
# Check auth file
cat ~/.local/share/opencode/auth.json

# Or set environment variable
export OPENROUTER_API_KEY="sk-or-v1-your-key"

# Or check what MimirConfig sees:
cd /path/to/Mimir
python -c "from src.mimir.config import get_config, reset_config; reset_config(); c = get_config(); print(c.to_dict())"
```

### "Knowledge base not found"

```bash
# Check what MimirConfig resolves to:
cd /path/to/your/project
python /path/to/Mimir/mimir.py health

# Index the project
python /path/to/Mimir/mimir.py index
```

### MCP server not starting

```bash
# Check the wrapper script
/path/to/Mimir/scripts/run_mcp_server.sh --help

# Check logs (opencode shows MCP logs in console)
# The wrapper now supports both uv and plain python3
```

### Subagents with Built-in Permissions

The following subagents have Mimir tool permissions built-in automatically — no `load_skills` parameter needed:

| Subagent | Built-in Tools |
|----------|---------------|
| `ContextScout` | `mimir-knowledge_search`, `mimir-knowledge_enrich_task` |
| `CoderAgent` | `mimir-knowledge_search`, `mimir-knowledge_enrich_task` |
| `TaskManager` | `mimir-knowledge_search`, `mimir-knowledge_enrich_task` |

**Usage** — just include instructions in your prompt:

```typescript
// CORRECT — just add instructions, no special parameter needed
task(
    subagent_type="ContextScout",
    prompt="Find authentication patterns. Use mimir-knowledge_search for project-specific queries."
)

// WRONG — this parameter does NOT exist
task(
    subagent_type="ContextScout",
    load_skills=["mimir"],  // ❌ Does not exist!
    prompt="Find authentication patterns..."
)
```

For other subagents (explore, librarian, etc.), embed Mimir instructions directly in the prompt:

```typescript
task(
    subagent_type="explore",
    prompt="Find patterns. IMPORTANT: Use mimir-knowledge_search for project-specific queries instead of grep."
)
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
| **Unified CLI** (`mimir.py`) | All commands through single entry point: `install`, `uninstall`, `init`, `server`, `index`, `search`, `rag`, `agent`, `prep`, `diff`, `metrics`, `projects`, `handoff`, `cache`, `list`, `health` |
| **Git hook rewrite** | Now checks for `docs/` file changes before triggering reindex — faster, no false positives |
| **LangGraph token tracking** | `TokenUsageCallbackHandler` captures actual token usage from API calls in all workflows |
| **Subagent tool permissions** | ContextScout, CoderAgent, TaskManager have built-in Mimir tool permissions — no `load_skills` needed |
| **Production installer** | `mimir.py install` backs up config, sets up MCP server, and injects system context rules |
| **OpenSpace bridge hardening** | Circuit breaker (3 failures → 60s cooldown), caching (128 entries, 10min TTL), timeout (30s) |
| **Weighted Dijkstra graph queries** | `graph_query` finds strongest-coupling paths between modules, not just shortest |
| **Demo app redesign** | Animated architecture diagram, theme toggle, flow diagram, state inspector |
| **Batch indexing** | Documents indexed in batches to reduce API calls and memory usage |

---

## License

MIT
