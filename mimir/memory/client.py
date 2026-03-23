"""Memory client wrapping Mem0 OSS for the Three-Layer AI Context System."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from mem0 import Memory
except ImportError:
    raise ImportError("mem0ai package is required. Install with: pip install mem0ai")


MEMORY_TYPES = ["preference", "decision", "convention", "episodic", "correction"]


class MemoryClient:
    """Wrapper around Mem0 OSS for managing persistent memory with custom types."""

    def __init__(self, config_path: str = ".mimir/config.yaml"):
        """Initialize the MemoryClient with Mem0 and local Qdrant.

        Args:
            config_path: Path to the Mimir config file.
        """
        self.config = self._load_config(config_path)
        self.project_name = self.config.get("project_name", "Mimir")
        self.embedding_model = self.config.get("embedding_model", "text-embedding-3-small")
        self.qdrant_path = self._get_qdrant_path()

        self._memory = self._init_memory()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            return {"project_name": "Mimir", "embedding_model": "text-embedding-3-small"}

        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _get_qdrant_path(self) -> str:
        """Get Qdrant local path from config or schema."""
        qdrant_config_path = Path("schema/qdrant_config.yaml")
        if qdrant_config_path.exists():
            with open(qdrant_config_path) as f:
                config = yaml.safe_load(f) or {}
                if config.get("local_mode"):
                    return config.get("path", ".mimir/qdrant")

        return ".mimir/qdrant"

    def _init_memory(self) -> Memory:
        """Initialize Mem0 Memory with local Qdrant vector store."""
        api_key = os.environ.get("OPENAI_API_KEY")

        collection_name = f"{self.project_name}_memories"

        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": collection_name,
                    "path": self.qdrant_path,
                    "embedding_model_dims": 1536,
                    "on_disk": True,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": self.embedding_model,
                },
            },
            "version": "v1.1",
        }

        if api_key:
            config["llm"] = {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini",
                    "api_key": api_key,
                },
            }

        return Memory.from_config(config)

    def add(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add memories with custom metadata including memory type.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            user_id: User identifier for scoping memories.
            metadata: Optional metadata dict. Must include 'type' key with one of:
                preference, decision, convention, episodic, correction.

        Returns:
            Dict containing 'results' list of added/updated memories.

        Raises:
            ValueError: If memory type is not valid.
        """
        if metadata is None:
            metadata = {}

        memory_type = metadata.get("type")
        if memory_type and memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory type: {memory_type}. Must be one of: {MEMORY_TYPES}")

        try:
            result = self._memory.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata,
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to add memory: {e}") from e

    def search(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search memories with optional similarity threshold.

        Args:
            query: Search query string.
            user_id: User identifier to scope search.
            limit: Maximum number of results to return.
            threshold: Minimum similarity score (0.0-1.0) for results.

        Returns:
            List of memory dicts with 'id', 'memory', 'score', and 'metadata' keys.

        Raises:
            ValueError: If user_id is not provided.
        """
        if not user_id:
            raise ValueError("user_id is required for search")

        try:
            result = self._memory.search(
                query=query,
                user_id=user_id,
                limit=limit,
                threshold=threshold,
            )

            memories = result.get("results", [])

            if threshold is not None:
                memories = [m for m in memories if m.get("score", 0) >= threshold]

            return memories
        except Exception as e:
            raise RuntimeError(f"Failed to search memories: {e}") from e

    def delete(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id: ID of the memory to delete.

        Returns:
            Dict with 'message' confirming deletion.

        Raises:
            ValueError: If memory_id is not provided.
        """
        if not memory_id:
            raise ValueError("memory_id is required for deletion")

        try:
            result = self._memory.delete(memory_id=memory_id)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to delete memory: {e}") from e

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory by ID.

        Args:
            memory_id: ID of the memory to retrieve.

        Returns:
            Memory dict or None if not found.
        """
        if not memory_id:
            raise ValueError("memory_id is required")

        try:
            return self._memory.get(memory_id=memory_id)
        except Exception as e:
            raise RuntimeError(f"Failed to get memory: {e}") from e

    def get_all(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all memories for a user.

        Args:
            user_id: User identifier.
            limit: Maximum number of memories to return.

        Returns:
            List of memory dicts.
        """
        if not user_id:
            raise ValueError("user_id is required")

        try:
            result = self._memory.get_all(user_id=user_id, limit=limit)
            return result.get("results", [])
        except Exception as e:
            raise RuntimeError(f"Failed to get all memories: {e}") from e
