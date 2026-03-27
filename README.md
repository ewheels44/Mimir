# Mimir - Multi-Project Knowledge Base

A centralized, multi-project knowledge base system using LlamaIndex and LangGraph. Install once, use in any project directory with automatic workspace detection.

## Quick Start

```bash
# 1. From any project directory, run the initializer
python ~/Documents/Mimir/setup_knowledge_mcp.py

# 2. Add documents to docs/

# 3. Index them (includes cache exclusions automatically)
python .opencode/setup.py

# 4. Query your knowledge base
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does authentication work?"

# 5. Or use LangGraph workflows
python ~/Documents/Mimir/langgraph/cli.py rag "How does authentication work?"
```

## What's New

### Incremental Indexing
Add new directories without re-indexing everything:
```bash
python .opencode/setup.py --add src
python .opencode/setup.py --add tests
```

### LangGraph Workflows
Two powerful workflows for querying your knowledge base:
- **RAG Workflow**: Simple retrieve → generate
- **Knowledge Agent**: Agentic workflow with tool usage

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
├── setup_knowledge_mcp.py           # Multi-project initializer
├── langgraph/                       # LangGraph workflows
│   ├── cli.py                       # CLI for running workflows
│   └── workflows/                   # RAG and Knowledge Agent
│       ├── rag.py
│       ├── knowledge_agent.py
│       └── utils.py
├── requirements.txt                 # Python dependencies
└── .opencode/
    └── setup.py                     # Per-project setup script

Your Project/                         # Any project directory
├── docs/                            # Your documentation
├── .knowledge/llamaindex/           # Project-specific vector index
├── .mimir/config.json               # Project configuration
├── .mimir/AGENTS.md                 # Local copy of Mimir AGENTS.md
├── .opencode/setup.py               # Auto-generated setup script
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
python .opencode/setup.py

# Force rebuild
python .opencode/setup.py --reindex

# Add specific directory
python .opencode/setup.py --add src

# Via MCP server
python ~/Documents/Mimir/mcp_server_llamaindex.py --add tests
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
python ~/Documents/Mimir/setup_knowledge_mcp.py

# Creates:
#   - docs/
#   - .knowledge/llamaindex/
#   - .mimir/config.json
#   - .mimir/AGENTS.md
#   - .opencode/setup.py
#   - opencode.json (AGENTS.md chaining config - customize as needed)
```

### Index Documents

```bash
# Add files to docs/, then:
python .opencode/setup.py

# Or force reindex:
python .opencode/setup.py --reindex

# Add a specific directory:
python .opencode/setup.py --add src
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
python .opencode/setup.py --reindex
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
| `setup_knowledge_mcp.py` | Multi-project initializer |
| `.opencode/setup.py` | Per-project setup and indexing |
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
