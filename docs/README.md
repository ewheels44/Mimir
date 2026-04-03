# Mimir Knowledge Base

This is the Mimir multi-project knowledge base system.

## Overview

Mimir provides a centralized knowledge base that can be used across multiple projects.
It uses:
- **LlamaIndex** for document indexing and retrieval
- **MCP (Model Context Protocol)** for integration with OpenCode
- **OpenRouter** for embeddings and LLM inference
- **LangGraph** for advanced RAG workflows and agentic patterns
- **Rust + React** for the Web UI (knowledge graph visualization)

## Quick Start

### Initialize a New Project

Run the setup script in any project directory:

```bash
cd ~/Documents/YourProject
python ~/Documents/Mimir/mimir-init.py
```

This creates:
- `docs/` - Add your documentation here
- `.knowledge/llamaindex/` - Vector index storage
- `.knowledge/cost_metrics.jsonl` - Usage and cost tracking
- `.mimir/config.json` - Project configuration
- `.opencode/mimir-index.py` - Per-project indexing script
- `.opencode/skills/mimir.md` - Mimir skill for subagents

### Index Documents

```bash
# Index docs/ directory
python .opencode/mimir-index.py

# Add source code directories
python .opencode/mimir-index.py --add src
python .opencode/mimir-index.py --add tests

# Force full rebuild
python .opencode/mimir-index.py --reindex
```

### Query Your Knowledge Base

```bash
# Direct query via MCP server
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does authentication work?"

# RAG workflow
python ~/Documents/Mimir/langgraph/cli.py rag "How does authentication work?"

# Knowledge Agent (agentic exploration)
python ~/Documents/Mimir/langgraph/cli.py agent "Find all API endpoints"

# View cost metrics
python ~/Documents/Mimir/langgraph/cli.py metrics --days 7
```

### Launch Web UI

```bash
# Development mode (Rust + Vite)
cd ~/Documents/Mimir/web
./dev.sh --project /path/to/your/project

# Production mode
./build.sh
./server/target/release/mimir-web --project /path/to/your/project
```

Opens at http://localhost:5173 (dev) or http://localhost:8000 (production).

## Documentation

- [Main README.md](../README.md) - Comprehensive documentation
- [AGENTS.md](../AGENTS.md) - Agent configuration and usage guide
- [Web UI README](../web/server/README.md) - Web UI architecture and development

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  LangGraph (Orchestration)                             │
│  - RAG workflows                                       │
│  - Knowledge Agent                                     │
│  - Cost tracking                                       │
└──────────────┬──────────────────────────────────────────┘
               │ MCP Protocol
               ▼
┌─────────────────────────────────────────────────────────┐
│  LlamaIndex (Retrieval)                                │
│  - VectorStoreIndex                                     │
│  - Semantic search                                      │
│  - Incremental indexing                                 │
└──────────────┬──────────────────────────────────────────┘
               │ File Watching
               ▼
┌─────────────────────────────────────────────────────────┐
│  Web UI (Visualization)                                │
│  - Rust/Axum backend                                    │
│  - React + Cytoscape frontend                           │
│  - Knowledge graph visualization                        │
└─────────────────────────────────────────────────────────┘
```
