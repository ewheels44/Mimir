# Mimir Knowledge Base

This is the Mimir multi-project knowledge base system.

## Overview

Mimir provides a centralized knowledge base that can be used across multiple projects.
It uses:
- LlamaIndex for document indexing and retrieval
- MCP (Model Context Protocol) for integration with OpenCode
- OpenRouter for embeddings

## Usage

Run the setup script in any project directory:

```bash
python ~/Documents/Mimir/setup_knowledge_mcp.py
```

This creates:
- `docs/` - Add your documentation here
- `.knowledge/llamaindex/` - Vector index storage
- `.opencode/setup.py` - Project-specific setup script
