"""
Shared utilities for LangGraph workflows.

Handles OpenRouter API configuration and MCP client setup.
"""

import json
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient


def get_openrouter_config() -> Tuple[str, str]:
    """Get OpenRouter API key and base URL.

    Returns:
        Tuple of (api_key, base_url)
    """
    # Try environment variables first
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "OPENAI_API_KEY", ""
    )
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    if api_key:
        return api_key, base_url

    # Try opencode auth file
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if auth_path.exists():
        try:
            with open(auth_path) as f:
                auth_data = json.load(f)
            if openrouter := auth_data.get("openrouter"):
                return openrouter.get("key", ""), "https://openrouter.ai/api/v1"
        except (json.JSONDecodeError, KeyError):
            pass

    return "", base_url


def create_llm(
    model: str = "google/gemini-3.1-flash-lite-preview",
    temperature: float = 0,
    callbacks=None,
) -> ChatOpenAI:
    """Create a LangChain LLM configured for OpenRouter.

    Args:
        model: Model name (OpenRouter format like "google/gemini-3.1-flash-lite-preview")
        temperature: Sampling temperature
        callbacks: Optional list of callback handlers for token tracking

    Returns:
        Configured ChatOpenAI instance
    """
    api_key, base_url = get_openrouter_config()

    if not api_key:
        raise ValueError(
            "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable "
            "or log in with: opencode auth openrouter"
        )

    kwargs = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": base_url,
    }

    if callbacks:
        kwargs["callbacks"] = callbacks

    return ChatOpenAI(**kwargs)


def get_mcp_server_path() -> Path:
    """Get the path to the MCP server script."""
    return Path.home() / "Documents" / "Mimir" / "mcp_server_llamaindex.py"


def get_mcp_env(project_root: Optional[Path] = None) -> dict:
    """Get environment variables for MCP server.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        Dictionary of environment variables
    """
    if project_root is None:
        project_root = detect_project_root()

    api_key, base_url = get_openrouter_config()

    return {
        "PROJECT_ROOT": str(project_root),
        "KNOWLEDGE_DIR": str(project_root / ".knowledge" / "llamaindex"),
        "DOCS_DIR": str(project_root / "docs"),
        "OPENROUTER_API_KEY": api_key,
        "OPENAI_BASE_URL": base_url,
    }


def detect_project_root() -> Path:
    """Detect project root from current directory."""
    for env_var in ["PROJECT_ROOT", "WORKSPACE_FOLDER"]:
        if path := os.environ.get(env_var):
            return Path(path).resolve()

    cwd = Path.cwd().resolve()
    markers = ["opencode.json", ".opencode", ".git", "pyproject.toml", "package.json"]

    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


def get_mcp_config(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Get MCP client configuration.

    Centralizes the MCP server configuration that was previously duplicated
    in knowledge_agent.py and rag.py.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        Dictionary with MCP server configuration for MultiServerMCPClient
    """
    if project_root is None:
        project_root = detect_project_root()

    server_path = get_mcp_server_path()
    env = get_mcp_env(project_root)

    # Use virtual environment Python if available, otherwise fall back to system Python
    venv_python = project_root / ".venv" / "bin" / "python"
    python_command = str(venv_python) if venv_python.exists() else "python"

    return {
        "llamaindex": {
            "command": python_command,
            "args": [str(server_path)],
            "transport": "stdio",
            "env": env,
        }
    }


def get_mcp_client(project_root: Optional[Path] = None) -> MultiServerMCPClient:
    """Get an MCP client instance.

    Note: As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient no longer
    supports context manager usage. Use client.get_tools() directly instead.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        MultiServerMCPClient instance

    Example:
        client = get_mcp_client()
        tools = await client.get_tools()
        # ... use tools ...
    """
    config = get_mcp_config(project_root)
    return MultiServerMCPClient(config)
