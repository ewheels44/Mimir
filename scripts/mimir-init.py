#!/usr/bin/env python3
"""
mimir-init.py - Initialize Mimir for any project or install globally.

Two modes:
  1. Global install (run once): Sets up MCP server and system rules
  2. Per-project init (run in each project): Creates directories and indexes

Per-project setup creates:
  - .mimir/config.json     - Project-specific Mimir settings
  - .opencode/mimir-index.py - Delegates to central Mimir install
  - .mimir/AGENTS.md      - Mimir usage documentation

The .jcode/mcp.json uses a unique server name (mimir-{project-name}) to avoid
conflicts when working on multiple projects. It also sets PROJECT_ROOT so the
MCP server knows which project it's serving.

Usage:
    # Global install (run once after cloning Mimir)
    python ~/Documents/Mimir/mimir.py install

    # Per-project init (run in each project you want to index)
    cd /path/to/your/project
    python ~/Documents/Mimir/mimir.py init
    python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests

    # Uninstall (restores backed up configs)
    python ~/Documents/Mimir/mimir.py uninstall
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Mimir root directory
MIMIR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MIMIR_ROOT / "src"))


# ─── Constants ────────────────────────────────────────────────────────────────

MIMIR_RULES_START = "<!-- MIMIR_RULES_START -->"
MIMIR_RULES_END = "<!-- MIMIR_RULES_END -->"

MIMIR_RULES_BLOCK = f"""
{MIMIR_RULES_START}
## MIMIR RULES (3 ONLY)

### 1. MIMIR FIRST
Before any task, use `mimir(action="enrich_task", params={...})`. This is my memory — without it I'm guessing. No exceptions.

Artifacts: For common architectural questions, Mimir serves pre-compiled artifacts (instant, zero token cost):
- `rag_architecture` - RAG system design, LangGraph workflows, LLM config
- `indexing_architecture` - Indexing system, incremental updates, file watcher
- `artifact_system` - Artifact dependency tracking, staleness, TTL
- `code_chunking` - AST-aware code chunking strategies
- `knowledge_graph_integration` - Knowledge graph + search integration
- `query_caching` - Query cache system with TTL

These are auto-triggered by keywords in your task (e.g., "rag", "indexing", "artifact").

### 2. CONTEXT BEFORE CODE
Before writing/editing:
- Code → read `~/.config/opencode/context/core/standards/code-quality.md`
- Docs → read `~/.config/opencode/context/core/standards/documentation.md`
- Tests → read `~/.config/opencode/context/core/standards/test-coverage.md`
- Review → read `~/.config/opencode/context/core/workflows/code-review.md`
- Delegation → read `~/.config/opencode/context/core/workflows/task-delegation-basics.md`

If it's bash-only, skip this.

### 3. ASK FIRST
Never run bash/write/edit/task without showing a plan and getting approval. Read/list/glob/grep are fine without asking.

{MIMIR_RULES_END}
"""