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

# Via opencode (automatic)
# Just ask questions — agents use Mimir tools automatically
```

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

### Subagent Context (Critical)

When spawning subagents, they **don't inherit** Mimir context. Always load the skill:

```typescript
// CORRECT
task(
    subagent_type="explore",
    load_skills=["mimir"],
    prompt="Find authentication patterns..."
)

// WRONG - subagent will use grep instead of Mimir
task(
    subagent_type="explore",
    prompt="Find authentication patterns..."
)
```

---

## Working Configuration Example

Here's a complete working setup from a real installation:

### Directory Structure

```
~/Documents/Mimir/           # Central installation
├── mcp_server_llamaindex.py
├── mimir-init.py
├── scripts/
│   └── run_mcp_server.sh    # MCP wrapper script
├── src/mimir/               # Core modules
├── langgraph/               # Workflows
└── opencode-plugin/         # System context plugin

~/Projects/AnyProject/       # Any project using Mimir
├── docs/
├── .knowledge/llamaindex/
├── .mimir/config.json
└── .opencode/mimir-index.py
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

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small"
}
```

---

## Architecture

```
┌─────────────────────────────────────────┐
│  opencode Agent                         │
│  - Receives queries                     │
│  - Uses MCP tools automatically         │
└──────────────┬──────────────────────────┘
               │ MCP Protocol
               ▼
┌─────────────────────────────────────────┐
│  Mimir MCP Server                       │
│  - search, query, rag_workflow, etc.    │
│  - Project-aware (per-project indexes)  │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
┌─────────────┐ ┌─────────────┐
│ LlamaIndex  │ │ LangGraph   │
│ (Retrieval) │ │ (Workflows) │
└─────────────┘ └─────────────┘
```

**Key Components**:
- **LlamaIndex**: Document ingestion, chunking, embeddings, vector storage
- **MCP Protocol**: Tool discovery and transport between opencode and Mimir
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

## Troubleshooting

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
```

### "Knowledge base not found"

```bash
# Make sure you've indexed the project
cd /path/to/your/project
python .opencode/mimir-index.py
```

### MCP server not starting

```bash
# Check the wrapper script
~/Documents/Mimir/scripts/run_mcp_server.sh --help

# Check logs (opencode shows MCP logs in console)
```

### Subagents not using Mimir

Make sure you're loading the skill:

```typescript
task(subagent_type="explore", load_skills=["mimir"], prompt="...")
```

---

## Documentation

- **[AGENTS.md](AGENTS.md)** — Comprehensive agent documentation (indexing, workflows, API reference)
- **[docs/](docs/)** — Additional documentation

---

## License

MIT
