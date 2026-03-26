# Mimir - Multi-Project Knowledge Base

A centralized, multi-project knowledge base system using LlamaIndex and MCP. Install once, use in any project directory with automatic workspace detection.

## Quick Start

```bash
# 1. From any project directory, run the initializer
python ~/Documents/Mimir/setup_knowledge_mcp.py

# 2. Add documents to docs/

# 3. Index them
python .opencode/setup.py

# 4. Query your knowledge base
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does authentication work?"
```

## Structure

```
~/Documents/Mimir/                   # Central installation
├── mcp_server_llamaindex.py         # MCP server (shared across projects)
├── setup_knowledge_mcp.py           # Multi-project initializer
├── requirements.txt                 # Python dependencies
└── .opencode/
    └── setup.py                     # Per-project setup script template

Your Project/                         # Any project directory
├── docs/                            # Your documentation
├── .knowledge/llamaindex/           # Project-specific vector index
└── .opencode/setup.py               # Auto-generated setup script
```

## Features

- **Multi-Project**: One Mimir installation serves unlimited projects
- **Workspace-Aware**: Auto-detects project root via `.opencode/`, `.git/`, markers
- **Per-Project Isolation**: Each project has its own vector store in `.knowledge/`
- **OpenCode Integration**: Pre-configured MCP server
- **OpenRouter Support**: Uses OpenRouter for embeddings (no OpenAI key needed)

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ROOT` | Auto-detected | Override project root detection |
| `KNOWLEDGE_DIR` | `.knowledge/llamaindex` | Vector index storage |
| `DOCS_DIR` | `docs/` | Documents to index |
| `CODE_DIRS` | (none) | Comma-separated code directories to index (e.g., `src,tests,lib`) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI-compatible embedding model |
| `OPENROUTER_API_KEY` | From `~/.local/share/opencode/auth.json` | API key for embeddings |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | API base URL |

### OpenCode Integration

The MCP server is already configured in your global `~/.config/opencode/opencode.json`:

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

## Usage

### Initialize a New Project

```bash
cd ~/Documents/YourProject
python ~/Documents/Mimir/setup_knowledge_mcp.py

# Creates:
#   - docs/
#   - .knowledge/llamaindex/
#   - .opencode/setup.py
```

### Index Documents

```bash
# Add files to docs/, then:
python .opencode/setup.py

# Or force reindex:
python .opencode/setup.py --force
```

### Index Source Code

By default, Mimir only indexes your `docs/` directory. To also index your source code:

```bash
# Index docs + src directory
export CODE_DIRS=src
python ~/Documents/Mimir/mcp_server_llamaindex.py --reindex

# Index multiple directories
export CODE_DIRS=src,tests,lib
python ~/Documents/Mimir/mcp_server_llamaindex.py --reindex
```

**With OpenCode**: Add to your `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "mimir-knowledge": {
      "environment": {
        "PROJECT_ROOT": "${workspaceFolder}",
        "CODE_DIRS": "src,tests",
        "DOCS_DIR": "${workspaceFolder}/docs"
      }
    }
  }
}
```

Now you can search both documentation and code:

```
"Find where the authentication middleware is defined"
"How does the error handling work in src/utils?"
"Show me all functions that use the database"
```

### CLI Queries

```bash
# From anywhere, targeting current project
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "What is the architecture?"

# Check stats
python ~/Documents/Mimir/mcp_server_llamaindex.py --stats

# Rebuild index
python ~/Documents/Mimir/mcp_server_llamaindex.py --reindex
```

### In OpenCode

The MCP tools are automatically available:

```
Search the knowledge base for authentication patterns
```

## How It Works

1. **Project Detection**: Server walks up from CWD looking for `.opencode/`, `.git/`, `pyproject.toml`, etc.
2. **Per-Project Storage**: Each project gets its own `.knowledge/llamaindex/` directory
3. **Centralized Server**: Single `mcp_server_llamaindex.py` handles all projects
4. **OpenRouter Embeddings**: Uses OpenRouter API for text embeddings via OpenAI-compatible endpoint

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

## Adding to a New Project

```bash
cd ~/Documents/NewProject
python ~/Documents/Mimir/setup_knowledge_mcp.py
echo "# My Project Docs" > docs/README.md
python .opencode/setup.py
```

## Files

| File | Purpose |
|------|---------|
| `mcp_server_llamaindex.py` | MCP server with OpenRouter support |
| `setup_knowledge_mcp.py` | Multi-project initializer |
| `.opencode/setup.py` | Per-project setup template |

## License

MIT
