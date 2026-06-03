"""
Bridge Client — Direct KnowledgeServer API adapter for LangGraph workflows.

Previously used subprocess calls to mimir_bridge.py, which caused ~24s overhead
per tool call due to LlamaIndex re-initialization. Now uses the KnowledgeServer
Python API directly, keeping the index loaded in-process.

Provides the same tool interface (search, query, stats) for backward compatibility
with knowledge_agent.py and rag.py.
"""

import json
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import StructuredTool


# ── In-process KnowledgeServer (lazy singleton) ──────────────────────────────

_server_instance: Optional[Any] = None


def _get_server() -> Any:
    """Get or create the KnowledgeServer singleton (lazy, in-process).

    Returns the same KnowledgeServer instance across calls, keeping the
    LlamaIndex loaded in memory.
    """
    global _server_instance
    if _server_instance is not None:
        return _server_instance

    from mimir.config import get_config
    from mimir.server import KnowledgeServer

    config = get_config()
    _server_instance = KnowledgeServer(config)
    return _server_instance


# ── Tool implementations (direct API calls, no subprocess) ──────────────────


def search(query: str, top_k: int = 5) -> str:
    """Semantic search over the knowledge base.

    Returns a JSON string of results for backward compatibility with
    tool callers that expect the old bridge_client format.
    """
    server = _get_server()
    result = server.search(query, top_k=top_k)

    # server.search() returns a formatted string with [1] source (score)
    # items — parse it into structured JSON for callers that expect
    # the old format
    try:
        lines = [line.strip() for line in result.split("\n\n") if line.strip()]
        items = []
        for line in lines:
            if line.startswith("["):
                items.append({"text": line})
            elif line.startswith("[Knowledge Graph") or items:
                if items:
                    items[-1]["text"] += "\n" + line
                continue

        if items:
            return json.dumps(items)

        # Fallback: return raw text if parsing didn't work
        return result
    except Exception:
        return result


def query(question: str) -> str:
    """RAG question answering. Synthesizes an answer from the knowledge base."""
    server = _get_server()
    return server.query(question)


def get_stats(**kwargs) -> str:
    """Get knowledge base statistics as JSON string."""
    server = _get_server()
    stats = server.get_stats()
    return json.dumps(stats)


def read_file(file_path: str) -> str:
    """Read a file from the project.

    Use this to read the contents of specific files (like README.md, config files, etc.)
    when you need to analyze or update them. This is more reliable than searching for filenames.

    Args:
        file_path: Path relative to project root (e.g., "README.md", "docs/setup.md")
    """
    server = _get_server()
    from pathlib import Path

    project_root = Path(server.project_root)
    full_path = project_root / file_path

    # Security check: ensure the file is within the project
    try:
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(project_root.resolve())):
            return f"Error: Access denied. File must be within the project directory."
    except Exception:
        return f"Error: Invalid file path."

    if not full_path.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = full_path.read_text(encoding="utf-8")
        return f"[File: {file_path}]\n\n{content}"
    except UnicodeDecodeError:
        return f"Error: File appears to be binary: {file_path}"
    except Exception as e:
        return f"Error reading file: {e}"


# ── Tool registry ───────────────────────────────────────────────────────────


def get_tools() -> list:
    """Get LangChain tools that wrap the KnowledgeServer API directly."""
    return [
        StructuredTool.from_function(
            name="search",
            func=search,
            description="Semantic search over the knowledge base. Returns relevant code/docs.",
        ),
        StructuredTool.from_function(
            name="query",
            func=query,
            description="RAG question answering. Synthesizes an answer from the knowledge base.",
        ),
        StructuredTool.from_function(
            name="stats",
            func=get_stats,
            description="Get knowledge base statistics.",
        ),
        StructuredTool.from_function(
            name="read_file",
            func=read_file,
            description="Read a file from the project. Use this to read README.md, config files, or any specific file. Args: file_path (relative to project root).",
        ),
    ]