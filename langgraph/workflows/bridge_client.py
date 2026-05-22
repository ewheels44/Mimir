"""
Bridge Client - Simplified adapter for mimir_bridge.py

Provides tools that langgraph workflows can use by calling
the thin CLI bridge directly.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import Tool


def get_bridge_path() -> Path:
    """Get the path to mimir_bridge.py."""
    from mimir.config import get_config
    return get_config().mimir_root / "mimir_bridge.py"


def call_bridge(action: str, params: dict = None) -> dict:
    """Call the mimir_bridge.py with a JSON request.
    
    Returns:
        Parsed JSON response as dict
    """
    if params is None:
        params = {}
    
    request = json.dumps({"action": action, "params": params})
    bridge_path = get_bridge_path()
    
    result = subprocess.run(
        ["python3", str(bridge_path)],
        input=request,
        capture_output=True,
        text=True,
        timeout=30,
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"Bridge error: {result.stderr}")
    
    return json.loads(result.stdout)


def search(query: str, top_k: int = 5) -> str:
    """Search the knowledge base."""
    result = call_bridge("search", {"query": query, "top_k": top_k})
    if result.get("status") == "ok":
        items = result.get("results", [])
        return json.dumps(items)
    return result.get("error", "Unknown error")


def query(question: str) -> str:
    """Query the knowledge base."""
    result = call_bridge("query", {"question": question})
    if result.get("status") == "ok":
        return result.get("answer", "")
    return result.get("error", "Unknown error")


def get_stats() -> str:
    """Get knowledge base statistics."""
    result = call_bridge("stats")
    return json.dumps(result)


def get_tools() -> list[Tool]:
    """Get LangChain tools that wrap the bridge actions."""
    return [
        Tool(
            name="search",
            func=search,
            description="Semantic search over the knowledge base. Returns relevant code/docs.",
        ),
        Tool(
            name="query",
            func=query,
            description="RAG question answering. Synthesizes an answer from the knowledge base.",
        ),
        Tool(
            name="stats",
            func=get_stats,
            description="Get knowledge base statistics.",
        ),
    ]
