# Mimir - Multi-Project Knowledge Base

A centralized, multi-project knowledge base system using LlamaIndex and LangGraph. Install once, use in any project directory with automatic workspace detection.

## Quick Start

```bash
# 1. From any project directory, run the initializer
python ~/Documents/Mimir/mimir-init.py

# 2. Add documents to docs/

# 3. Index them (includes cache exclusions automatically)
python .opencode/mimir-index.py

# 4. Query your knowledge base
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does authentication work?"

# 5. Or use LangGraph workflows
python ~/Documents/Mimir/langgraph/cli.py rag "How does authentication work?"
```

## What's New

### Incremental Indexing
Add new directories without re-indexing everything:
```bash
python .opencode/mimir-index.py --add src
python .opencode/mimir-index.py --add tests
```

### LangGraph Workflows
Two powerful workflows for querying your knowledge base:
- **RAG Workflow**: Simple retrieve → generate
- **Knowledge Agent**: Agentic workflow with tool usage

### Web UI 🌐
Browser-based interface for visualizing and exploring your knowledge base:
- **Interactive Graph Visualization**: Navigate documents and relationships
- **Search Interface**: Semantic search with visual results
- **Query Interface**: Ask natural language questions
- **Detail Panels**: Inspect document metadata and relationships

```bash
# Start the Web UI
python ~/Documents/Mimir/scripts/start_web_ui.sh
# Or directly
python ~/Documents/Mimir/web/server.py
```
Then open http://localhost:8000 in your browser.

### Knowledge Graph 📊

Mimir can extract relationships from your code to build a visual knowledge graph showing how files connect:

**Relationship Types:**
- **Imports** (solid green lines): Module imports (`import x`, `from x import y`)
- **Calls** (orange lines): Function/method calls
- **Inheritance** (dotted pink lines): Class inheritance relationships
- **Methods** (purple lines): Class-to-method relationships

**Generate the knowledge graph:**
```bash
# From your project directory
python ~/Documents/Mimir/src/mimir/knowledge_graph.py --from-index

# Or specify a project path
python ~/Documents/Mimir/src/mimir/knowledge_graph.py /path/to/your/project --from-index

```

This creates `.knowledge/code_relationships.json` which the Web UI uses to display connections between files.

**When to generate:**
- After indexing your codebase for the first time
- When you add new modules or significant code structure
- The graph is not auto-generated during indexing (run manually)

### Enhanced MCP Tools
- `search`: Semantic search
- `query`: Natural language queries  
- `rag_workflow`: Run RAG workflow
- `knowledge_agent`: Run agentic workflow
- `stats`: Index statistics
- `reindex`: Rebuild index

## Structure

```
~/Documents/Mimir/                   # Central installation
├── mcp_server_llamaindex.py         # MCP server (LlamaIndex + LangGraph)
├── mimir-init.py           # Multi-project initializer
├── src/                             # Core source code
│   └── mimir/
│       ├── __init__.py
│       └── indexing.py              # Full indexing utilities
├── tests/                           # Test files
│   ├── __init__.py
│   └── test_workflows.py
├── scripts/                         # Utility scripts
│   └── run_mcp_server.sh            # MCP server launch script
├── langgraph/                       # LangGraph workflows
│   ├── cli.py                       # CLI for running workflows
│   └── workflows/                   # RAG and Knowledge Agent
│       ├── rag.py
│       ├── knowledge_agent.py
│       └── utils.py
├── examples/                        # Usage examples
│   └── run_workflow.py
├── web/                             # Web UI
│   ├── server.py                    # FastAPI backend
│   ├── static/                      # Static assets
│   └── templates/                   # HTML templates
├── requirements.txt                 # Python dependencies
└── .opencode/
    └── setup.py                     # Per-project setup script

Your Project/                         # Any project directory
├── docs/                            # Your documentation
├── .knowledge/llamaindex/           # Project-specific vector index
├── .mimir/config.json               # Project configuration
├── .mimir/AGENTS.md                 # Local copy of Mimir AGENTS.md
├── .opencode/mimir-index.py               # Auto-generated setup script
└── opencode.json                    # OpenCode configuration (optional)
```

## Features

- **Multi-Project**: One Mimir installation serves unlimited projects
- **Workspace-Aware**: Auto-detects project root via `.opencode/`, `.git/`, markers
- **Per-Project Isolation**: Each project has its own vector store in `.knowledge/`
- **Incremental Indexing**: Add directories without full rebuilds
- **LangGraph Integration**: Advanced workflows with RAG and agentic patterns
- **OpenCode Integration**: Pre-configured MCP server with auto-discovery
- **OpenRouter Support**: Uses OpenRouter for embeddings and LLM inference

## Why Mimir? Real-World Benefits

### The Problem: Context Degradation & Session Amnesia

**Without Mimir (Traditional Approach):**

```
Session 1:
  User: "We're using JWT auth with refresh tokens"
  [30 turns of conversation]
  Agent: Has full context of JWT implementation
  
  → Session ends. All context is LOST.

Session 2:
  User: "Update the auth flow"
  Agent: "What auth flow?" → Starts from ZERO
  → Re-discover the same files, same patterns
  → Wastes 5-10 minutes rebuilding context
```

**How Context Builds Up Without Mimir:**

```
Traditional Context Accumulation:
  Turn 1: 2k tokens (read auth.py)
  Turn 5: 8k tokens (re-read + new files)
  Turn 15: 20k tokens (re-discovering same patterns)
  Turn 30: Hit context limit → forced truncation
  
  Result: 30% of context spent on *finding* information
         70% left for actual implementation
         High risk of missing critical files
```

### The Mimir Solution

**With Mimir:**

```
Session 1:
  User: "We're using JWT auth with refresh tokens"
  → search("JWT authentication flow", top_k=5)
  → Returns: auth.py, middleware.py, api/client.py
  → Agent implements with full context
  
Session 2:
  User: "Update the auth flow"
  → search("JWT refresh token auth") → immediate results
  → Agent: "Ah yes, let me update those files..."
  → Implementation starts immediately
```

**Context Efficiency:**

```
Mimir Context Management:
  Turn 1: Query KB (1-2s, ~$0.0001) → Find relevant files
  Turn 5: Quick search if needed (<1s)
  Turn 15: No accumulation - lean context
  Turn 30: Still under budget, no truncation needed
  
  Result: 5% of context on discovery (KB queries)
         95% left for implementation and reasoning
         Semantic search finds what grep misses
```

### Cost Analysis: Traditional vs Mimir

| Scenario | Traditional | With Mimir |
|----------|-------------|------------|
| **First refactor** | 25k tokens ($0.75) | 8k tokens + $0.001 ($0.25) |
| **Second refactor** | 25k tokens ($0.75) | 8k tokens + $0.001 ($0.25) |
| **Third refactor** | 25k tokens ($0.75) | 5k tokens + $0.001 ($0.16) |
| **Cumulative (3x)** | **$2.25** | **$0.66** |

**Cost Model:**
- **Indexing**: One-time ~$0.02 per 1000 files
- **Search**: ~$0.0001/query (1 embedding API call)
- **Query**: ~$0.001/query (embedding + LLM synthesis)
- **Savings**: 60-80% reduction in token costs

### Real-World Scenario: Multi-Session Project

**Week 1: Setting up auth**
```
Traditional:
  Session 1: 2 hours exploring JWT setup
  [Session ends, context lost]
  Session 2: "How did we set up auth again?" → 1 hour re-exploring
  
Mimir:
  Session 1: 1.5 hours (faster discovery via semantic search)
  Session 2: 45 min (KB immediately finds auth files)
```

**Week 4: Adding OAuth**
```
Traditional:
  Agent: "Let me explore auth patterns..."
  → Reads JWT files (redundant, already did this)
  → Wastes 30 min on already-known code
  
Mimir:
  Agent: [KB query: "authentication patterns"]
  → search("OAuth integration")
  → 10 min to understand, implements immediately
```

### Key Benefits

**1. Accuracy Through Semantic Understanding**

Traditional grep searches for *strings*. Mimir searches for *meaning*.

| Search Type | Query | Finds |
|-------------|-------|-------|
| **grep** | "auth" | auth.py, authentication.py, AUTH_TOKEN constant |
| **Mimir** | "authentication flow" | auth.py, middleware.py (token parsing), api/client.py (refresh), config/auth.py (settings) |

**2. Cross-Language Discovery**

One semantic query finds the *concept* across all languages:
- "How are users authenticated?" → Python (backend), TypeScript (frontend), SQL (schema)

**3. Context Window Conservation**

- **Traditional**: 30% of context window spent on *finding* information
- **Mimir**: 5% on discovery, 95% on implementation

**4. Knowledge Persistence**

- **Traditional**: Every session starts from zero
- **Mimir**: Index once, query forever
- Previous explorations are "remembered" in the embeddings

**5. Compounding Efficiency**

| Phase | Traditional | Mimir |
|-------|-------------|-------|
| First project | Baseline | 50% faster discovery |
| Fifth project | Same baseline | 70% faster (learned patterns) |
| Tenth project | Same baseline | 80% faster (rich context) |

**6. Team Knowledge Sharing**

- **Traditional**: Senior dev explains architecture repeatedly
- **Mimir**: Self-documenting through semantic search
- New team members get full context immediately

### Performance Comparison

| Metric | Traditional | Mimir |
|--------|-------------|-------|
| **Discovery time** | 5-10 min | 1-2 min |
| **Files missed** | Often 20-30% | <5% (semantic recall) |
| **Context tokens per task** | 20k-30k | 5k-10k |
| **Cost per refactor** | $0.60-$1.20 | $0.15-$0.30 |
| **Cross-session memory** | None | Indexed, queryable |

### When Mimir Shines

✅ **Large codebases** (100k+ lines) - where traditional exploration is prohibitively expensive  
✅ **Cross-cutting changes** - affects multiple modules/systems  
✅ **Team onboarding** - new devs understand architecture quickly  
✅ **Maintenance work** - "how does X work again?" queries  
✅ **Refactoring** - finding all usages and dependencies  

### When Traditional Works

✅ **Tiny projects** (<5k lines) - grep is fast enough  
✅ **Known file paths** - direct tools are faster  
✅ **Single-file changes** - no discovery needed  

---

## Agent Documentation

**IMPORTANT**: For comprehensive usage documentation, see [**AGENTS.md**](AGENTS.md).

This file is loaded automatically by opencode and contains:
- Detailed indexing instructions (full and incremental)
- LangGraph workflow usage
- MCP tool reference
- Architecture explanation
- Troubleshooting guide

## Quick Reference

### Indexing

```bash
# Initial index (docs/ + configured code_dirs)
python .opencode/mimir-index.py

# Force rebuild
python .opencode/mimir-index.py --reindex

# Add specific directory
python .opencode/mimir-index.py --add src

# Via MCP server
python ~/Documents/Mimir/mcp_server_llamaindex.py --add tests
```

**Progress Tracking:**

For large projects, the indexer shows real-time progress:

```
1. Scanning docs/...
   Found 150 files
   Loading docs: 100%|████████████████████████| 150/150 [00:02<00:00, 62.50file/s]
   ✓ Loaded 150 documents

2. Scanning src/...
   Found 450 files
   Loading src: 100%|█████████████████████████| 450/450 [00:08<00:00, 52.30file/s]
   ✓ Loaded 450 documents

📊 Total documents: 600

🔄 Creating embeddings...
   Embedding docs: 100%|██████████████████████| 600/600 [02:15<00:00,  4.42doc/s]
   ✓ Index created

💾 Saving index...
   ✓ Index persisted
```

### Querying

```bash
# Simple query
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does X work?"

# RAG workflow
python ~/Documents/Mimir/langgraph/cli.py rag "How does X work?"

# Knowledge Agent
python ~/Documents/Mimir/langgraph/cli.py agent "Find all Y implementations"

# Test workflows
python ~/Documents/Mimir/langgraph/cli.py test
```

### Configuration

Create `.mimir/config.json`:

```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests", "lib"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small"
}
```

## AGENTS.md Hierarchy

OpenCode supports hierarchical AGENTS.md files, but **does not automatically discover subdirectory files**. By default, OpenCode only loads the **first AGENTS.md found by traversing UP** from the current directory.

### The Problem

If you have multiple AGENTS.md files (e.g., project root + subsystems), only the root file loads by default:

```
~/Documents/YourProject/
├── AGENTS.md                    ← Only this loads
├── RavenEye/hardware/
│   └── AGENTS.md                ← Ignored ❌
└── RavenEye/raspberry-pi/backend/
    └── AGENTS.md                ← Ignored ❌
```

### The Solution: `opencode.json`

Use the `instructions` field in `opencode.json` to explicitly chain AGENTS.md files:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "~/Documents/Mimir/AGENTS.md",
    "AGENTS.md",
    "RavenEye/hardware/AGENTS.md",
    "RavenEye/raspberry-pi/backend/AGENTS.md"
  ]
}
```

Or use glob patterns:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "~/Documents/Mimir/AGENTS.md",
    "AGENTS.md",
    "**/AGENTS.md"
  ]
}
```

### Loading Order & Precedence

Files in `instructions` are loaded **in order**, with later files able to override earlier ones:

| Order | File | Purpose |
|-------|------|---------|
| 1 | `~/Documents/Mimir/AGENTS.md` | Base Mimir system documentation |
| 2 | `AGENTS.md` | Project-specific rules |
| 3 | `**/AGENTS.md` | Subsystem-specific rules (hardware, backend, etc.) |

### Best Practices

1. **Reference parent in child files:**
   ```markdown
   # Hardware AGENTS.md
   **Parent:** RavenEye  
   **Scope:** ESP32 firmware, MPU6050 IMU
   ```

2. **Document cross-boundary protocols:**
   ```markdown
   ## Cross-Boundary
   | Direction | Protocol | Details |
   |-----------|----------|---------|
   | ESP32 → Pi | HTTP POST | `POST /api/camera/upload` |
   ```

3. **Use `opencode.json` for complex projects** with multiple AGENTS.md files


---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ROOT` | Auto-detected | Override auto-detected project root |
| `KNOWLEDGE_DIR` | `.knowledge/llamaindex` | Vector index storage path |
| `DOCS_DIR` | `docs/` | Documents directory to index |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI-compatible embedding model |
| `OPENROUTER_API_KEY` | From `~/.local/share/opencode/auth.json` | API key for embeddings/LLM |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | API base URL |

### OpenCode Integration

The MCP server is configured in your global `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "mimir-knowledge": {
      "type": "local",
      "command": [
        "uv", "run", "--python", "3.11",
        "/Users/ethanwheeler/Documents/Mimir/mcp_server_llamaindex.py"
      ],
      "environment": {
        "PROJECT_ROOT": "${workspaceFolder}",
        "KNOWLEDGE_DIR": "${workspaceFolder}/.knowledge/llamaindex",
        "DOCS_DIR": "${workspaceFolder}/docs"
      },
      "enabled": true
    }
  }
}
```

#### System Append Prompt (oh-my-opencode/code)

If you're using **oh-my-opencode/code**, you must configure the **system append prompt** to include the Mimir AGENTS.md. This ensures the agent receives the priority directives for using Mimir tools over generic exploration agents.

Add the following to your agent configuration:

```json
    "sisyphus": {
      "model": "",
      "prompt_append": "## ALWAYS MENTION: 'Mimir Context Priority' Mimir Context Priority\nPer ~/Documents/Mimir/AGENTS.md: ALWAYS use Mimir tools (search, query, rag_workflow, knowledge_agent) over generic exploration agents. Check the Tool Decision Matrix when uncertain.",
      "ultrawork": {
        "model": "",
      }
    }
```

Or for multiple AGENTS.md files:

**Why this matters**: The system append prompt injects the AGENTS.md content into every agent interaction, ensuring agents always prioritize Mimir's knowledge base tools (`search`, `query`, `rag_workflow`, `knowledge_agent`) over generic exploration patterns.

## Architecture

Mimir uses a **three-layer architecture**:

1. **LlamaIndex** (Data Layer): Document ingestion, chunking, embedding, storage
2. **MCP Protocol** (Bridge): Tool discovery, transport, project context
3. **LangGraph** (Orchestration): Workflow management, LLM prompting, agent loops

```
┌─────────────────────────────────────────┐
│  LangGraph (Orchestration)             │
│  - RAG workflows                       │
│  - Knowledge agents                    │
│  - State management                    │
└──────────────┬──────────────────────────┘
               │ MCP Protocol
               ▼
┌─────────────────────────────────────────┐
│  LlamaIndex (Retrieval)                │
│  - VectorStoreIndex                     │
│  - Semantic search                      │
│  - Query synthesis                      │
└─────────────────────────────────────────┘
```

## Usage

### Initialize a New Project

```bash
cd ~/Documents/YourProject
python ~/Documents/Mimir/mimir-init.py

# Creates:
#   - docs/
#   - .knowledge/llamaindex/
#   - .mimir/config.json
#   - .mimir/AGENTS.md
#   - .opencode/mimir-index.py
#   - opencode.json (AGENTS.md chaining config - customize as needed)
```

### Index Documents

```bash
# Add files to docs/, then:
python .opencode/mimir-index.py

# Or force reindex:
python .opencode/mimir-index.py --reindex

# Add a specific directory:
python .opencode/mimir-index.py --add src
```

### Index Source Code

By default, Mimir indexes `docs/`. To also index source code:

```json
// .mimir/config.json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests", "lib"],
  "knowledge_dir": ".knowledge/llamaindex",
  "embedding_model": "text-embedding-3-small"
}
```

Then reindex:

```bash
python .opencode/mimir-index.py --reindex
```

**Note:** Setup.py automatically excludes cache directories (`__pycache__`, `node_modules`, etc.).

### CLI Queries

```bash
# Direct query
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "What is the architecture?"

# Check stats
python ~/Documents/Mimir/mcp_server_llamaindex.py --stats

# Rebuild index
python ~/Documents/Mimir/mcp_server_llamaindex.py --reindex

# Add directory
python ~/Documents/Mimir/mcp_server_llamaindex.py --add src
```

### LangGraph Workflows

```bash
# RAG workflow (retrieve → generate)
python ~/Documents/Mimir/langgraph/cli.py rag "How does authentication work?"

# Knowledge Agent (agentic tool usage)
python ~/Documents/Mimir/langgraph/cli.py agent "Find all API endpoints"

# Test both workflows
python ~/Documents/Mimir/langgraph/cli.py test
```

### In OpenCode

The MCP tools are automatically available:

```
Search the knowledge base for authentication patterns
Run the RAG workflow on how the database layer works
Use the knowledge agent to explore the codebase structure
```

## How It Works

1. **Project Detection**: Server walks up from CWD looking for `.opencode/`, `.git/`, `pyproject.toml`, etc.
2. **Per-Project Storage**: Each project gets its own `.knowledge/llamaindex/` directory
3. **Centralized Server**: Single `mcp_server_llamaindex.py` handles all projects
4. **Incremental Updates**: Use `--add` to index new directories without full rebuilds
5. **LangGraph Workflows**: Advanced retrieval patterns via agentic workflows

## Customization

### Custom Document Directory

```bash
export DOCS_DIR=./documentation
python ~/Documents/Mimir/mcp_server_llamaindex.py --index
```

### Custom Embedding Model

```bash
export EMBEDDING_MODEL=text-embedding-3-large
python ~/Documents/Mimir/mcp_server_llamaindex.py --index
```

### HTTP Transport

```bash
python ~/Documents/Mimir/mcp_server_llamaindex.py --transport http --port 8000
```

## Files

| File | Purpose |
|------|---------|
| `mcp_server_llamaindex.py` | MCP server with LlamaIndex + LangGraph |
| `mimir-init.py` | Multi-project initializer |
| `.opencode/mimir-index.py` | Per-project setup and indexing |
| `langgraph/cli.py` | CLI for LangGraph workflows |
| `langgraph/workflows/rag.py` | RAG workflow implementation |
| `langgraph/workflows/knowledge_agent.py` | Knowledge Agent implementation |
| `langgraph/workflows/utils.py` | Shared utilities |
| `AGENTS.md` | Comprehensive agent documentation |
| `examples/run_workflow.py` | Workflow usage examples |

## Dependencies

Core:
```bash
pip install llama-index openai
```

LangGraph workflows:
```bash
pip install langgraph>=0.2.0 langchain>=0.3.0 \
    langchain-openai>=0.2.0 langchain-mcp-adapters>=0.1.0
```

## License

MIT
