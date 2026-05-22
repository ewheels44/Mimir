"""
Shared utilities for LangGraph workflows.

Handles OpenRouter API configuration and MCP client setup.
"""

from pathlib import Path
from typing import Any, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI


def create_llm(
    model: Optional[str] = None,
    temperature: float = 0,
    callbacks=None,
) -> ChatOpenAI:
    """Create a LangChain LLM configured for OpenRouter."""
    from mimir.config import get_config

    config = get_config()

    if model is None:
        model = config.llm_model

    api_key = config.api_key
    base_url = config.api_base

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
    """Get the path to the bridge script."""
    from mimir.config import get_config

    return get_config().mimir_root / "mimir_bridge.py"


def get_mcp_server_python_path() -> Path:
    """Get the Python path for running the bridge.

    Returns the directory containing mimir_bridge.py
    so that imports work correctly.
    """
    from mimir.config import get_config

    return get_config().mimir_root


def get_mcp_env(project_root: Optional[Path] = None) -> dict:
    """Get environment variables for bridge.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        Dictionary of environment variables
    """
    from mimir.config import get_config

    if project_root is None:
        project_root = detect_project_root()

    config = get_config()

    return {
        "PROJECT_ROOT": str(project_root),
        "KNOWLEDGE_DIR": str(project_root / ".knowledge" / "llamaindex"),
        "DOCS_DIR": str(project_root / "docs"),
        "OPENROUTER_API_KEY": config.api_key,
        "OPENAI_BASE_URL": config.api_base,
    }


def detect_project_root() -> Path:
    """Detect project root from unified config."""
    from mimir.config import get_config

    return get_config().project_root


def get_mcp_config(project_root: Optional[Path] = None) -> dict[str, Any]:
    """Get MCP client configuration.

    Centralizes the bridge configuration that was previously duplicated
    in knowledge_agent.py and rag.py.

    Args:
        project_root: Project root directory (auto-detected if not provided)

    Returns:
        Dictionary with bridge configuration for MultiServerMCPClient
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


def get_mcp_client(project_root: Optional[Path] = None):
    """Get tools wrapped as an object with get_tools() method.
    
    Args:
        project_root: Project root directory (auto-detected if not provided)
        
    Returns:
        Object with get_tools() method for compatibility with workflow patterns
    """
    from .bridge_client import get_tools
    
    class ToolsAdapter:
        def get_tools(self):
            return get_tools()
    
    return ToolsAdapter()
