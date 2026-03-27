# Mimir Knowledge Base - Agent Documentation

This document provides comprehensive guidance for AI assistants using the Mimir knowledge base system. It covers indexing strategies, querying patterns, LangGraph workflows, and architectural concepts.

**Last Updated**: 2026-03-26

For venv use `~/Documents/Mimir/.venv/bin/activate`
If missing any use uv to install

example uv pip install <package>

---

## Quick Reference Card

| Task | Command |
|------|---------|
| **Full index** | `python .opencode/setup.py` |
| **Force rebuild** | `python .opencode/setup.py --reindex` |
| **Add directory** | `python .opencode/setup.py --add <dir>` |
| **Simple query** | `python ~/Documents/Mimir/mcp_server_llamaindex.py --query "..."` |
| **RAG workflow** | `python ~/Documents/Mimir/langgraph/cli.py rag "..."` |
| **Knowledge Agent** | `python ~/Documents/Mimir/langgraph/cli.py agent "..."` |
| **Check stats** | `python ~/Documents/Mimir/mcp_server_llamaindex.py --stats` |

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Indexing Strategies](#indexing-strategies)
3. [Querying Patterns](#querying-patterns)
4. [LangGraph Workflows](#langgraph-workflows)
5. [MCP Tools Reference](#mcp-tools-reference)
6. [Architecture Deep Dive](#architecture-deep-dive)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## System Overview

Mimir is a **three-layer knowledge base system**:

```
┌─────────────────────────────────────────────┐
│  Layer 3: LangGraph (Orchestration)         │
│  - Workflow state management                │
│  - LLM prompting & generation               │
│  - Tool binding & agent loops               │
└──────────────┬────────────────────────────────┘
               │ MCP Protocol
               ▼
┌─────────────────────────────────────────────┐
│  Layer 2: MCP Server (Bridge)              │
│  - Tool discovery & invocation             │
│  - Project context management              │
│  - Transport layer (stdio/http)            │
└──────────────┬────────────────────────────────┘
               │ LlamaIndex API
               ▼
┌─────────────────────────────────────────────┐
│  Layer 1: LlamaIndex (Data Layer)            │
│  - VectorStoreIndex storage                  │
│  - Document chunking & embedding             │
│  - Semantic search                           │
└─────────────────────────────────────────────┘
```

### Key Capabilities

1. **Semantic Search**: Find relevant documents by meaning, not just keywords
2. **RAG Workflows**: Structured retrieve → generate pipelines
3. **Agentic Querying**: LLM decides when/what to retrieve
4. **Incremental Indexing**: Add documents without full rebuilds
5. **Multi-Project**: Single installation serves unlimited projects

---

## Indexing Strategies

### Full Index (Initial Setup)

Indexes `docs/` directory plus any `code_dirs` configured in `.mimir/config.json`:

```bash
python .opencode/setup.py
```

**What it does:**
1. Reads `.mimir/config.json` for configuration
2. Loads documents from `docs_dir` and `code_dirs`
3. Chunks and embeds using OpenRouter
4. Stores in `.knowledge/llamaindex/`
5. Automatically excludes cache files, images, binaries

**When to use:**
- First time setup
- After significant changes to multiple directories
- When you want a clean, consistent index

### Force Rebuild

Clear existing index and rebuild from scratch:

```bash
python .opencode/setup.py --reindex
```

**When to use:**
- Index corruption
- Changing embedding models
- Major refactoring of codebase
- Troubleshooting search quality issues

### Incremental Indexing (Add Directory)

Add new documents without re-indexing existing content:

```bash
# Add a single directory
python .opencode/setup.py --add src
python .opencode/setup.py --add tests
python .opencode/setup.py --add /path/to/docs

# Via MCP server directly
python ~/Documents/Mimir/mcp_server_llamaindex.py --add src
```

**How it works:**
1. Loads existing index from disk
2. Reads new documents from specified directory
3. Chunks and embeds new documents
4. Inserts into existing index via `index.insert()`
5. Persists updated index

**⚠️ Duplicate Documents Warning:**

The incremental `add` uses LlamaIndex's `insert()` method. Duplicate documents (same filename) might create duplicates in the index unless LlamaIndex's deduplication kicks in.

**To avoid duplicates:**
- Track which files are already indexed
- Use `refresh_ref_docs()` instead of `insert()`
- Or accept some duplication (usually harmless for search)

**When to use incremental:**
- Adding a new module/package
- Indexing test files separately
- Incremental updates during development

### Excluded Patterns

Full indexing automatically excludes:

| Category | Patterns |
|----------|----------|
| **Cache** | `__pycache__`, `*.pyc`, `.pytest_cache`, `.mypy_cache` |
| **Venv** | `.venv`, `venv`, `.env` |
| **Git** | `.git`, `.github` |
| **Node** | `node_modules` |
| **Media** | `*.png`, `*.jpg`, `*.svg`, `*.mp4`, `*.mp3` |
| **Fonts** | `*.woff`, `*.woff2`, `*.ttf` |
| **Binaries** | `*.pt`, `*.pth`, `*.onnx`, `*.tflite` |
| **Docs** | `*.pdf`, `*.zip`, `*.tar`, `*.gz` |
| **Locks** | `package-lock.json`, `yarn.lock`, `uv.lock` |
| **Minified** | `*.min.js`, `*.min.css`, `*.map` |
| **OS** | `.DS_Store`, `Thumbs.db` |

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

**Fields:**
- `docs_dir`: Documentation directory (default: "docs")
- `code_dirs`: List of source code directories to index
- `knowledge_dir`: Where to store the vector index
- `embedding_model`: OpenAI-compatible model name

---

## Querying Patterns

### When to Use Each Tool

| Tool | Use When | Returns |
|------|----------|---------|
| `search` | You need raw context, files, or similarity scores | Document chunks with scores |
| `query` | You want a synthesized answer | Natural language response |
| `rag_workflow` | You want structured retrieval + generation | Workflow-managed response |
| `knowledge_agent` | Complex query needing multiple steps | Agent-reasoned response |

### Pattern 1: Direct Search (Simple)

Best for finding specific files or code:

```python
# Via MCP
results = await mcp_client.call_tool("search", {
    "query": "authentication middleware",
    "top_k": 5
})
```

**Use for:**
- Finding where a function is defined
- Locating configuration files
- Getting raw context for your own analysis

### Pattern 2: Direct Query (Synthesized)

Best for high-level questions:

```bash
python ~/Documents/Mimir/mcp_server_llamaindex.py \
    --query "How does error handling work in this codebase?"
```

**Use for:**
- Architecture overview questions
- Understanding patterns across files
- Quick summaries

### Pattern 3: RAG Workflow (Structured)

Best when you want explicit retrieve → generate separation:

```bash
python ~/Documents/Mimir/langgraph/cli.py rag \
    "How does the authentication system work?"
```

**What happens:**
1. Retrieve node: Searches knowledge base
2. Generate node: LLM synthesizes answer using retrieved context
3. Clean separation of concerns

**Use for:**
- Questions with clear retrieval needs
- When you want to see what was retrieved
- Debugging retrieval quality

### Pattern 4: Knowledge Agent (Agentic)

Best for complex exploration:

```bash
python ~/Documents/Mimir/langgraph/cli.py agent \
    "Find all database-related files and explain the data layer architecture"
```

**What happens:**
1. Check node: Verifies index exists, gets stats
2. Agent node: LLM decides what tools to call
3. May make multiple searches/queries
4. Synthesizes final answer

**Use for:**
- Multi-step research
- When you're not sure what to search for
- Exploring relationships between components

---

## LangGraph Workflows

**Status**: ✅ Production Ready

### Overview

LangGraph workflows provide advanced retrieval patterns beyond simple search:

1. **RAG Workflow**: Linear retrieve → generate pipeline
2. **Knowledge Agent**: Dynamic agent that decides what to retrieve

Both workflows use **OpenRouter** for LLM inference.

### Architecture

```
User Query
    │
    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Retrieve   │────▶│   Generate  │────▶│    End      │
│   (Node)    │     │   (Node)    │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       │ MCP Client ──▶ MCP Server ──▶ LlamaIndex
       │
       │ Retrieves documents from VectorStoreIndex
```

### 1. RAG Workflow

**File**: `langgraph/workflows/rag.py`

Simple two-node graph:

```
retrieve ──▶ generate ──▶ END
```

**Implementation:**
```python
from langgraph.workflows.rag import graph
from langchain_core.messages import HumanMessage

async def run():
    config = {"configurable": {"thread_id": "1"}}
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="How does X work?")]},
        config
    )
    print(result["messages"][-1].content)
```

**State Schema:**
```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: list[str]  # Retrieved documents
```

**When to use:**
- Simple questions with clear retrieval needs
- When you want predictable behavior
- Debugging retrieval quality

### 2. Knowledge Agent Workflow

**File**: `langgraph/workflows/knowledge_agent.py`

Agentic workflow with tool binding:

```
check_knowledge ──▶ agent ──▶ (conditional) ──▶ agent (loop) ──▶ END
                        │
                        └────▶ if tool_calls
```

**Implementation:**
```python
from langgraph.workflows.knowledge_agent import graph

result = await graph.ainvoke(
    {"messages": [HumanMessage(content="Explore the codebase"])},
    config
)
```

**State Schema:**
```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict  # Index metadata
```

**When to use:**
- Complex research questions
- When optimal retrieval strategy is unclear
- Multi-step exploration

### Running Workflows

**Option 1: CLI**

```bash
# RAG workflow
python ~/Documents/Mimir/langgraph/cli.py rag "Your question"

# Knowledge Agent
python ~/Documents/Mimir/langgraph/cli.py agent "Your question"

# Test both
python ~/Documents/Mimir/langgraph/cli.py test
```

**Option 2: Python API**

```python
import asyncio
from langgraph.workflows.rag import graph
from langchain_core.messages import HumanMessage

async def main():
    config = {"configurable": {"thread_id": "1"}}
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="How does auth work?")]},
        config
    )
    print(result["messages"][-1].content)

asyncio.run(main())
```

**Option 3: Via MCP**

```python
# Via MCP client
await mcp_client.call_tool("rag_workflow", {"query": "..."})
await mcp_client.call_tool("knowledge_agent", {"question": "..."})
```

### Configuration

**Environment:**
- `OPENROUTER_API_KEY`: Required for LLM access
- `OPENAI_BASE_URL`: Defaults to OpenRouter

**Default Model:**
- `google/gemini-3.1-flash-lite-preview` (fast, cost-effective)

**To change model:**
Edit `langgraph/workflows/utils.py`:
```python
llm = create_llm(model="anthropic/claude-3.5-sonnet", temperature=0)
```

### Example Script

See `examples/run_workflow.py` for complete usage examples.

---

## MCP Tools Reference

### Available Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `search` | `query` (str), `top_k` (int) | Semantic similarity search |
| `query` | `question` (str) | Natural language query with synthesis |
| `stats` | - | Get index statistics |
| `reindex` | - | Rebuild the entire index |
| `rag_workflow` | `query` (str) | Run RAG workflow |
| `knowledge_agent` | `question` (str) | Run Knowledge Agent workflow |

### Tool Details

#### search

Semantic search across indexed documents.

**Parameters:**
- `query` (required): Search query string
- `top_k` (optional): Number of results (default: 5)

**Returns:**
Formatted string with `[rank] filename (score)` and document excerpt.

**Example:**
```python
result = await mcp_client.call_tool("search", {
    "query": "authentication middleware",
    "top_k": 3
})
```

#### query

Ask a natural language question, get synthesized answer.

**Parameters:**
- `question` (required): Question to answer

**Returns:**
Synthesized answer using retrieved context.

**Example:**
```python
result = await mcp_client.call_tool("query", {
    "question": "How does error handling work?"
})
```

#### stats

Get information about the knowledge base.

**Returns:**
JSON with:
- `project_root`: Project directory
- `has_index`: Whether index exists
- `document_count`: Number of indexed chunks
- `source_files`: Number of source files
- `docs_dir`, `code_dirs`: Indexed directories

**Example:**
```bash
python ~/Documents/Mimir/mcp_server_llamaindex.py --stats
```

#### rag_workflow

Run the complete RAG workflow.

**Parameters:**
- `query` (required): Question to answer

**Returns:**
Synthesized answer after retrieval and generation.

**Example:**
```python
result = await mcp_client.call_tool("rag_workflow", {
    "query": "Explain the architecture"
})
```

#### knowledge_agent

Run the Knowledge Agent workflow.

**Parameters:**
- `question` (required): Question to explore

**Returns:**
Agent-synthesized answer after potential multiple tool calls.

**Example:**
```python
result = await mcp_client.call_tool("knowledge_agent", {
    "question": "Find all API endpoints"
})
```

---

## Architecture Deep Dive

### How LlamaIndex and LangGraph Work Together

#### Separation of Concerns

| Component | Responsibility |
|-----------|---------------|
| **LlamaIndex** | Document ingestion, chunking, embedding, storage, retrieval |
| **MCP** | Tool interface, transport, project context, discovery |
| **LangGraph** | Workflow orchestration, state management, LLM prompting |

#### Data Flow

```
1. User Query
       │
       ▼
2. LangGraph State
       │ (TypedDict with messages, context)
       ▼
3. Retrieve Node
       │ Spawns MCP Client
       │ ──▶ MCP Server
       │     ──▶ LlamaIndex
       │         ──▶ VectorStoreIndex
       │             ──▶ Retrieved Docs
       │         ◄──
       │     ◄──
       │ ◄──
       ▼
4. LangGraph State (updated with context)
       │
       ▼
5. Generate Node
       │ LLM (OpenRouter)
       │ Prompt: context + query
       │ ──▶ Generated Response
       │ ◄──
       ▼
6. User Response
```

#### Why MCP?

**Pros:**
- Clean interface boundary
- Tool discovery at runtime
- Transport flexibility (stdio/http)
- Multiple clients can use same server

**Cons:**
- Process spawning overhead
- Latency from IPC
- No shared state between calls

**Alternative:** Import LlamaIndex directly in LangGraph nodes (faster but tightly coupled).

#### Index Lifecycle

```
Document Files
       │
       ▼
SimpleDirectoryReader
       │
       ▼
Chunks + Metadata
       │
       ▼
OpenAIEmbedding (via OpenRouter)
       │
       ▼
VectorStoreIndex (in memory)
       │
       ▼
Persist to .knowledge/llamaindex/
       │
       ▼
Load on-demand via load_index_from_storage()
```

### Project Detection

Both systems detect project root the same way:

1. Check `PROJECT_ROOT` or `WORKSPACE_FOLDER` env vars
2. Walk up directory tree looking for markers:
   - `opencode.json`
   - `.opencode/`
   - `.git/`
   - `pyproject.toml`
   - `package.json`
3. Use current working directory if no markers found

This ensures consistency between indexing and querying.

### State Management

#### RAG Workflow State

```python
{
    "messages": [
        HumanMessage(content="User query"),
        AIMessage(content="Assistant response")
    ],
    "context": [
        "Retrieved document 1...",
        "Retrieved document 2..."
    ]
}
```

Managed by:
- `add_messages` reducer for messages (appends, not replaces)
- Direct assignment for context

#### Knowledge Agent State

```python
{
    "messages": [
        HumanMessage(content="User query"),
        AIMessage(content="Agent thinking...", tool_calls=[...]),
        ToolMessage(content="Tool result"),
        AIMessage(content="Final response")
    ],
    "knowledge_stats": {
        "has_index": True,
        "document_count": 150,
        "source_files": 45,
        "project_root": "/path/to/project"
    }
}
```

#### Persistence

- `MemorySaver` checkpoint: In-memory, session-only
- For production: Use PostgresSaver or RedisSaver
- Checkpoints enable:
  - Conversation continuity
  - Time-travel debugging
  - Human-in-the-loop interrupts

---

## Best Practices

### Indexing

1. **Start with docs/**
   - Keep documentation in dedicated directory
   - Index code separately when needed

2. **Use incremental adds for development**
   ```bash
   python .opencode/setup.py --add src  # Add source
   # ... work on src ...
   python .opencode/setup.py --add src  # Re-add after changes
   ```

3. **Full rebuild for major changes**
   - After refactoring
   - When changing embedding models
   - If search quality degrades

4. **Configure code_dirs in .mimir/config.json**
   ```json
   {
     "code_dirs": ["src", "tests", "lib"]
   }
   ```

### Querying

1. **Use `search` for finding code**
   - Function definitions
   - File locations
   - Specific implementations

2. **Use `query` for understanding**
   - Architecture questions
   - Pattern explanations
   - High-level overviews

3. **Use `rag_workflow` for complex queries**
   - Multi-step reasoning
   - When context quality matters
   - Debugging retrieval

4. **Use `knowledge_agent` for exploration**
   - "Find all X and explain Y"
   - When retrieval strategy is unclear
   - Research-style questions

### Workflow Design

1. **Prefer RAG for predictable queries**
   - Simpler, faster
   - Easier to debug
   - Deterministic retrieval

2. **Use Knowledge Agent for autonomy**
   - When LLM should decide what to retrieve
   - Complex multi-step questions
   - Exploration tasks

3. **Check stats before querying**
   ```bash
   python ~/Documents/Mimir/mcp_server_llamaindex.py --stats
   ```

4. **Iterate on retrieval**
   - If results are poor, try rephrasing
   - Check if relevant files are indexed
   - Adjust `top_k` parameter

### Performance

1. **Index once, query many**
   - Indexing is expensive (embeddings API calls)
   - Querying is fast (local vector search)

2. **Use appropriate `top_k`**
   - Default (5): Good balance
   - Increase (10-20): For broad questions
   - Decrease (3): For specific lookups

3. **Monitor OpenRouter usage**
   - Embeddings: One call per document chunk
   - LLM: One call per query (RAG) or more (Agent)

### Troubleshooting

1. **"No knowledge base found"**
   - Run `python .opencode/setup.py`
   - Check `.mimir/config.json` exists
   - Verify `docs/` has content

2. **Poor search results**
   - Try different query phrasing
   - Increase `top_k`
   - Check if files are indexed: `--stats`
   - Consider full rebuild: `--reindex`

3. **LangGraph errors**
   - Verify `OPENROUTER_API_KEY` is set
   - Check dependencies: `pip install -r requirements.txt`
   - Try `python ~/Documents/Mimir/langgraph/cli.py test`

4. **MCP connection errors**
   - Verify server path is correct
   - Check Python environment has dependencies
   - Try direct CLI: `--query "test"`

---

## Troubleshooting

### Common Issues

#### Issue: "No module named 'mcp'"

**Solution:**
```bash
pip install mcp>=1.0.0
```

#### Issue: "No knowledge base found"

**Diagnosis:**
```bash
python ~/Documents/Mimir/mcp_server_llamaindex.py --stats
```

**Solutions:**
1. Check if index exists:
   ```bash
   ls .knowledge/llamaindex/
   ```

2. Create index:
   ```bash
   python .opencode/setup.py
   ```

3. Check config:
   ```bash
   cat .mimir/config.json
   ```

#### Issue: "OpenRouter API key not found"

**Solutions:**
1. Set environment variable:
   ```bash
   export OPENROUTER_API_KEY="your-key"
   ```

2. Or login with opencode:
   ```bash
   opencode auth openrouter
   ```

3. Verify auth file:
   ```bash
   cat ~/.local/share/opencode/auth.json
   ```

#### Issue: "LangGraph workflow failed"

**Diagnosis:**
```bash
python ~/Documents/Mimir/langgraph/cli.py test
```

**Solutions:**
1. Install dependencies:
   ```bash
   pip install langgraph langchain langchain-openai langchain-mcp-adapters
   ```

2. Check model availability:
   - Verify `google/gemini-3.1-flash-lite-preview` is available on OpenRouter
   - Or change model in `langgraph/workflows/utils.py`

3. Check server path:
   - Verify `~/Documents/Mimir/mcp_server_llamaindex.py` exists

#### Issue: Poor search quality

**Diagnosis:**
```bash
# Check what's indexed
python ~/Documents/Mimir/mcp_server_llamaindex.py --stats

# Test direct search
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "test"
```

**Solutions:**
1. **Rephrase query**: Try synonyms or different wording
2. **Increase top_k**: More results = better recall
3. **Check indexed files**: Are relevant files in `code_dirs`?
4. **Full rebuild**: `python .opencode/setup.py --reindex`
5. **Check exclusions**: Are files excluded by pattern?

#### Issue: "Duplicate documents in index"

**Cause:**
Incremental adds with `insert()` don't deduplicate automatically.

**Solutions:**
1. **Accept it**: Usually harmless for search quality
2. **Full rebuild**: `python .opencode/setup.py --reindex`
3. **Use refresh**: Modify server to use `refresh_ref_docs()` instead of `insert()`

---

## Advanced Topics

### Custom Embedding Models

Edit `.mimir/config.json`:
```json
{
  "embedding_model": "text-embedding-3-large"
}
```

Trade-offs:
- `text-embedding-3-small`: Fast, cheap, good quality
- `text-embedding-3-large`: Better quality, more expensive
- `text-embedding-ada-002`: Legacy, still good

### Custom LLM Models for LangGraph

Edit `langgraph/workflows/utils.py`:
```python
llm = create_llm(model="anthropic/claude-3.5-sonnet", temperature=0)
```

Good options on OpenRouter:
- `google/gemini-3.1-flash-lite-preview`: Fast, cheap
- `anthropic/claude-3.5-sonnet`: High quality
- `openai/gpt-4o-mini`: Balanced

### Persistent Checkpoints

For production, replace `MemorySaver`:

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Instead of MemorySaver()
checkpointer = PostgresSaver(conn_string="postgresql://...")
graph = workflow.compile(checkpointer=checkpointer)
```

### Direct LlamaIndex Access

If MCP overhead is problematic, import directly:

```python
from llama_index.core import VectorStoreIndex, load_index_from_storage

index = load_index_from_storage(
    storage_context=StorageContext.from_defaults(
        persist_dir=".knowledge/llamaindex"
    )
)
results = index.as_retriever().retrieve("query")
```

**Trade-off:** Faster but loses tool discovery and transport flexibility.

---

## Reference

### File Locations

| File | Purpose |
|------|---------|
| `~/Documents/Mimir/mcp_server_llamaindex.py` | MCP server |
| `~/Documents/Mimir/.opencode/setup.py` | Per-project setup |
| `~/Documents/Mimir/langgraph/cli.py` | Workflow CLI |
| `~/Documents/Mimir/langgraph/workflows/rag.py` | RAG workflow |
| `~/Documents/Mimir/langgraph/workflows/knowledge_agent.py` | Knowledge Agent |
| `~/Documents/Mimir/langgraph/workflows/utils.py` | Shared utilities |
| `./.mimir/config.json` | Project configuration |
| `./.knowledge/llamaindex/` | Vector index |
| `./AGENTS.md` | This documentation |

### Dependencies

**Core:**
```
llama-index>=0.11.0
openai
mcp>=1.0.0
```

**LangGraph:**
```
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-mcp-adapters>=0.1.0
```

### Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | From auth file |
| `PROJECT_ROOT` | No | Auto-detected |
| `KNOWLEDGE_DIR` | No | `.knowledge/llamaindex` |
| `DOCS_DIR` | No | `docs` |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` |

---

## Summary

Mimir provides a powerful knowledge base system with three usage modes:

1. **Simple**: Direct search/query via MCP tools
2. **Structured**: RAG workflows for predictable retrieval
3. **Agentic**: Knowledge Agent for complex exploration

The three-layer architecture (LlamaIndex → MCP → LangGraph) provides clean separation of concerns while enabling advanced retrieval patterns.

**Quick Start**: `python .opencode/setup.py`

**Documentation**: This file (AGENTS.md)

**Examples**: `~/Documents/Mimir/examples/run_workflow.py`
