# Mimir — Persistent Knowledge Base for AI Agents

A semantic knowledge base that gives your AI agents instant access to your codebase, eliminating repeated discovery and context loss between sessions.

**Works with**: [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode) • [OpenAgents](https://github.com/darrenhinde/OpenAgentsControl)

---

## Quick Start

Already have oh-my-opencode installed? Skip to [Project Setup](#project-setup).

```bash
# Initialize any project
cd ~/Projects/YourProject
python ~/Documents/Mimir/mimir-init.py

# Add docs and index
echo "# My Project" > docs/README.md
python .opencode/mimir-index.py

# Done. Your agents now have semantic search.
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
git clone https://github.com/ewheels44/Mimir.git ~/Documents/Mimir
```

### Step 2: Configure OpenRouter API Key

```bash
# Option A: Set environment variable (add to ~/.zshrc or ~/.bashrc)
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"

# Option B: Use opencode auth (recommended)
opencode auth openrouter
# Paste your key when prompted
```

### Step 3: Configure Global MCP Server

Add Mimir to your global `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mimir-knowledge": {
      "type": "local",
      "command": ["/Users/YOUR_USERNAME/Documents/Mimir/scripts/run_mcp_server.sh"],
      "enabled": true,
      "environment": {
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1"
      }
    }
  }
}
```

**Important**: Replace `YOUR_USERNAME` with your actual username.

### Step 4: (Optional) Install System Context Plugin

For automatic context injection into every session:

```bash
# The plugin injects system context on session start
cp -r ~/Documents/Mimir/opencode-plugin/plugin ~/.config/opencode/
cp -r ~/Documents/Mimir/opencode-plugin/prompts ~/.config/opencode/
```

Then customize `~/.config/opencode/prompts/system-context.md` for your needs.

### Step 5: Verify Installation

```bash
# Check MCP server starts
~/Documents/Mimir/scripts/run_mcp_server.sh --help

# Should see MCP tools available when you start opencode
cd ~/Documents/Mimir
opencode
# Then ask: "What tools are available?"
```

---

## Project Setup

### Initialize a New Project

```bash
cd ~/Projects/YourProject
python ~/Documents/Mimir/mimir-init.py
```

This creates:
```
YourProject/
├── docs/                    # Your documentation
├── .knowledge/llamaindex/   # Vector index (auto-generated)
├── .mimir/
│   ├── config.json          # Project configuration
│   └── AGENTS.md            # Local Mimir docs
├── .opencode/
│   ├── mimir-index.py       # Indexing script
│   └── skills/mimir.md      # Subagent skill
└── opencode.json            # AGENTS.md chaining config
```

### Index Your Content

```bash
# Add documentation
echo "# My Project Architecture" > docs/README.md

# Index docs only
python .opencode/mimir-index.py

# Add source code (optional)
# Edit .mimir/config.json:
#   {"code_dirs": ["src", "tests"]}
python .opencode/mimir-index.py --reindex

# Or add incrementally
python .opencode/mimir-index.py --add src
```

### Query Your Knowledge Base

```bash
# Via CLI
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does auth work?"

# Via LangGraph workflows
python ~/Documents/Mimir/langgraph/cli.py rag "Explain the database layer"
python ~/Documents/Mimir/langgraph/cli.py agent "Find all API endpoints"

# FDE workflows
python ~/Documents/Mimir/langgraph/cli.py prep "video latency issues"
python ~/Documents/Mimir/langgraph/cli.py session-diff --days 1

# Via opencode (automatic)
# Just ask questions — agents use Mimir tools automatically
```

### Enable Auto-Indexing (Recommended)

Install the git hook so your knowledge base stays current automatically:

```bash
# Install in current project
bash ~/Documents/Mimir/scripts/install-git-hooks.sh

# Install in a specific project
bash ~/Documents/Mimir/scripts/install-git-hooks.sh /path/to/project

# Install in all Mimir projects
bash ~/Documents/Mimir/scripts/install-git-hooks.sh --all
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
Detects changed files (SHA-256 content hashing)
    │
    ▼
Incremental reindex (only changed files)
    │
    ▼
Knowledge base updated — agents see fresh context
```

### Features

- **Zero manual steps** — runs after every commit
- **Content-aware** — only reindexes files whose content actually changed
- **Non-blocking** — runs in background, never blocks git operations
- **Lock-protected** — prevents concurrent reindex runs
- **macOS compatible** — works on macOS and Linux

### Logs

```bash
# Check reindex activity
cat .mimir/reindex.log

# Check tracked files
python .opencode/mimir-index.py --list
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
python src/mimir/sdk_cache.py list

# Get docs for a library
python src/mimir/sdk_cache.py get stripe --topic "checkout sessions"

# Force refresh
python src/mimir/sdk_cache.py refresh stripe --topic "webhooks"
```

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
├── livekit-sdk/
│   └── llamaindex/
└── stripe-sdk/
    └── llamaindex/

~/customer-a/                      ← References shared index
├── .mimir/config.json
│   └── shared_indexes: { "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex" }
└── .knowledge/llamaindex/         ← Customer code only
```

**Setup:**

```bash
# 1. Index a shared SDK (once, globally)
python ~/Documents/Mimir/mcp_server_llamaindex.py --shared-index ~/path/to/sdk/ --name livekit-sdk

# 2. List available shared indices
python ~/Documents/Mimir/mcp_server_llamaindex.py --shared-list

# 3. Add to your project's .mimir/config.json:
#    "shared_indexes": { "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex" }
```

**Searching with scope:**

```
# Search everything (local + shared)
search(query="voice pipeline", scope="all")

# Search only customer code
search(query="voice pipeline", scope="local")

# Search only the SDK
search(query="voice pipeline", scope="shared:livekit-sdk")
```

**Results are source-tagged:**

```
[1] [LIVEKIT SDK] agents/voice_pipeline.py (score: 0.91)
    Voice pipeline: STT → LLM → TTS...

[2] [YOUR CODE] src/auth/middleware.ts (score: 0.82)
    JWT validation for voice endpoints...
```

### Multi-Project Management

Manage multiple customer engagements with isolated knowledge bases:

```bash
# Register projects
python ~/Documents/Mimir/mimir-projects.py add ~/Projects/customer-a --name customer-a
python ~/Documents/Mimir/mimir-projects.py add ~/Projects/customer-b --name customer-b

# List all projects
python ~/Documents/Mimir/mimir-projects.py list

# Switch context
python ~/Documents/Mimir/mimir-projects.py switch customer-a

# Check status of all projects
python ~/Documents/Mimir/mimir-projects.py status

# Auto-discover projects in common locations
python ~/Documents/Mimir/mimir-projects.py discover
```

```
$ mimir-projects.py list
Name                 Status     Index    Last Accessed
------------------------------------------------------------
customer-a           ✓          ✓        2026-04-07
customer-b           ✓          ✗        never
```

### Customer Call Prep

Generate a structured briefing before a customer call:

```bash
# Via LangGraph workflow
python ~/Documents/Mimir/langgraph/cli.py prep "video latency issues"
python ~/Documents/Mimir/langgraph/cli.py prep "payment integration" --customer acme-corp
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
python ~/Documents/Mimir/langgraph/cli.py session-diff

# Last 3 days
python ~/Documents/Mimir/langgraph/cli.py session-diff --days 3
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
python ~/Documents/Mimir/mimir-projects.py handoff

# Generate for a registered project
python ~/Documents/Mimir/mimir-projects.py handoff customer-a

# With engagement summary
python ~/Documents/Mimir/mimir-projects.py handoff customer-a \
  --summary "Built video calling integration using LiveKit" \
  --customer "Acme Corp"

# Custom output path
python ~/Documents/Mimir/mimir-projects.py handoff customer-a -o docs/handoff.md
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

The install script (`mimir-init.py`) copies Mimir-enhanced agent definitions to `~/.config/opencode/agent/`. These definitions include:

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
~/Documents/Mimir/           # Central installation
├── mcp_server_llamaindex.py       # MCP server + CLI
├── mimir-init.py                  # Project initializer
├── mimir-projects.py              # Multi-project CLI
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
│   │   ├── rag.py                # Basic RAG workflow
│   │   ├── knowledge_agent.py    # Agentic exploration
│   │   ├── call_prep.py          # Customer call briefing
│   │   ├── session_diff.py       # Session diff report
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
│   ├── livekit-sdk/llamaindex/
│   └── stripe-sdk/llamaindex/
└── projects.json                 # Multi-project registry
```

### Global Config: `~/.config/opencode/opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "openrouter/minimax/minimax-m2.7",
  "mcp": {
    "mimir-knowledge": {
      "type": "local",
      "command": ["/Users/ethanwheeler/Documents/Mimir/scripts/run_mcp_server.sh"],
      "enabled": true,
      "environment": {
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
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

```markdown
# System Context

This context is injected at the start of every session.

## Session Info
- **Date**: {{date}}
- **Git Branch**: {{git_branch}}
- **Working Directory**: {{cwd}}
- **Platform**: {{platform}}

## Instructions
MUST SAY **Mimir Loaded**

Read ~/Documents/Mimir/docs/mimir-sys-prompt.txt
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
    "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex"
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

### Shared Index Configuration

Shared indices are configured in `.mimir/config.json` (not env vars):

```json
{
  "shared_indexes": {
    "livekit-sdk": "~/.mimir/shared-indexes/livekit-sdk/llamaindex",
    "stripe-sdk": "~/.mimir/shared-indexes/stripe-sdk/llamaindex"
  }
}
```

| CLI Command | Purpose |
|-------------|---------|
| `mcp_server_llamaindex.py --shared-index DIR --name NAME` | Index a directory as a shared reference |
| `mcp_server_llamaindex.py --shared-list` | List available shared indices |
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
    │  health)   │ │        │ │          │
    └─────┬──────┘ └───┬────┘ └────┬─────┘
          │            │           │
          └────────────┼───────────┘
                       ▼
              ┌─────────────────┐
              │   LlamaIndex    │
              │  (Vector Store) │
              └─────────────────┘
```

**Key Components**:
- **MimirConfig**: Unified configuration — one class, all settings, all entry points
- **MCP Server**: Tool discovery and transport (search, query, health_check, etc.)
- **OpenSpace Bridge**: Integration with self-evolving skill engine (circuit breaker, caching, content filtering)
- **LlamaIndex**: Document ingestion, chunking, embeddings, vector storage
- **LangGraph**: Advanced RAG workflows and agentic exploration

---

## Web UI

Visual interface for exploring your knowledge base:

```bash
# Development mode
cd ~/Documents/Mimir/web
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

---

## Cost Tracking

Mimir tracks usage and calculates savings:

```bash
# View 30-day report
python ~/Documents/Mimir/langgraph/cli.py metrics

# View last 7 days
python ~/Documents/Mimir/langgraph/cli.py metrics --days 7
```

**Typical Savings**: 60-80% reduction in token costs vs. traditional exploration.

---

## CLI Reference

### MCP Server (`mcp_server_llamaindex.py`)

```bash
python mcp_server_llamaindex.py                    # Run MCP server
python mcp_server_llamaindex.py --index [DIR]      # Index documents
python mcp_server_llamaindex.py --reindex          # Rebuild index
python mcp_server_llamaindex.py --query "question" # One-shot query
python mcp_server_llamaindex.py --stats            # Show statistics
python mcp_server_llamaindex.py --shared-index DIR --name NAME  # Index shared SDK
python mcp_server_llamaindex.py --shared-list      # List shared indices
```

### LangGraph Workflows (`langgraph/cli.py`)

```bash
python langgraph/cli.py rag "question"             # RAG workflow
python langgraph/cli.py agent "question"           # Knowledge agent
python langgraph/cli.py prep "topic"               # Customer call briefing
python langgraph/cli.py prep "topic" --customer NAME
python langgraph/cli.py session-diff               # Session diff (last day)
python langgraph/cli.py session-diff --days 3      # Session diff (last 3 days)
python langgraph/cli.py metrics                    # Cost report (30 days)
python langgraph/cli.py metrics --days 7           # Cost report (7 days)
```

### Multi-Project (`mimir-projects.py`)

```bash
python mimir-projects.py list                      # List registered projects
python mimir-projects.py add /path/to/project      # Register a project
python mimir-projects.py add /path --name NAME --description "..."
python mimir-projects.py remove NAME               # Unregister a project
python mimir-projects.py switch NAME               # Switch to a project
python mimir-projects.py status                    # Show all project status
python mimir-projects.py discover                  # Find projects in common locations
python mimir-projects.py handoff [NAME]            # Generate handoff doc
python mimir-projects.py handoff NAME --summary "..." --customer "..." -o output.md
```

---

## Troubleshooting

### Quick Diagnosis

Use the `health_check` MCP tool to diagnose issues:

```
# In opencode — ask the agent:
"Run the health_check tool"
```

This returns:
- Server status (healthy/degraded)
- Index availability and freshness
- API key presence
- Configuration summary
- Validation warnings

### "No module named 'llama_index'"

The MCP server uses `uv` to manage dependencies automatically. If this fails:

```bash
cd ~/Documents/Mimir
uv sync
```

### "OPENROUTER_API_KEY not set"

```bash
# Check auth file
cat ~/.local/share/opencode/auth.json

# Or set environment variable
export OPENROUTER_API_KEY="sk-or-v1-your-key"

# Or check what MimirConfig sees:
cd ~/Documents/Mimir
python -c "from src.mimir.config import get_config, reset_config; reset_config(); c = get_config(); print(c.to_dict())"
```

### "Knowledge base not found"

```bash
# Check what MimirConfig resolves to:
cd /path/to/your/project
python -c "from src.mimir.config import get_config, reset_config; reset_config(); c = get_config(); print('knowledge_dir:', c.knowledge_dir); print('warnings:', c.validate())"

# Make sure you've indexed the project
python .opencode/mimir-index.py
```

### MCP server not starting

```bash
# Check the wrapper script
~/Documents/Mimir/scripts/run_mcp_server.sh --help

# Check logs (opencode shows MCP logs in console)
```

### Subagents not using Mimir

Subagents now have Mimir tool permissions built-in. Just include instructions in your prompt:

```typescript
task(
    subagent_type="ContextScout",
    prompt="Find authentication patterns. Use mimir-knowledge_search for project-specific queries."
)
```

For subagents without built-in Mimir permissions (explore, librarian), embed instructions:

```typescript
task(
    subagent_type="explore",
    prompt="Find patterns. IMPORTANT: Use mimir-knowledge_search for project-specific queries instead of grep."
)
```

---

## Documentation

- **[AGENTS.md](AGENTS.md)** — Comprehensive agent documentation (indexing, workflows, API reference)
- **[docs/](docs/)** — Additional documentation

---

## License

MIT
