"""Shared index composition for cross-codebase search.

Enables FDEs to reference large SDKs (indexed once globally) alongside
customer code (indexed per-project) in a single query.

Shared indices live at ~/.mimir/shared-indexes/{name}/llamaindex/
Projects reference them via .mimir/config.json shared_indexes field.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TaggedNode:
    """A search result with source attribution."""

    text: str
    score: float
    source: str  # "local", "shared:livekit-sdk", etc.
    file_name: str

    @property
    def source_tag(self) -> str:
        """Human-readable source tag for display."""
        if self.source == "local":
            return "[YOUR CODE]"
        elif self.source.startswith("shared:"):
            name = self.source.replace("shared:", "")
            return f"[{name.upper()} SDK]"
        return f"[{self.source.upper()}]"

    def to_prompt_chunk(self) -> str:
        """Format for LLM context injection."""
        return (
            f"{self.source_tag} {self.file_name} (score={self.score:.3f})\n{self.text}"
        )


class SharedIndexRegistry:
    """Lazy-loading registry for shared indices.

    Loads shared indices on demand, validates embedding model compatibility,
    and caches loaded indices for subsequent queries.
    """

    def __init__(self, shared_configs: dict[str, Path], embedding_model: str):
        """Initialize registry with shared index configurations.

        Args:
            shared_configs: Map of name -> path for shared indices
            embedding_model: Current project's embedding model (for validation)
        """
        self._configs = {k: Path(v).expanduser() for k, v in shared_configs.items()}
        self._embedding_model = embedding_model
        self._indices: dict = {}
        self._loaded: set[str] = set()

    def get(self, name: str):
        """Load and cache a shared index by name.

        Returns None if index not found or embedding model mismatch.
        """
        if name in self._loaded:
            return self._indices.get(name)

        path = self._configs.get(name)
        if not path or not (path / "index_store.json").exists():
            logger.warning("Shared index '%s' not found at %s, skipping", name, path)
            return None

        # Validate embedding model match
        manifest = self._load_manifest(path)
        stored_model = manifest.get("embedding_model", "unknown")
        if stored_model != self._embedding_model:
            logger.error(
                "Shared index '%s' uses %s but project uses %s. Re-index one to match.",
                name,
                stored_model,
                self._embedding_model,
            )
            return None

        try:
            from llama_index.core import StorageContext, load_index_from_storage

            storage_context = StorageContext.from_defaults(persist_dir=str(path))
            self._indices[name] = load_index_from_storage(storage_context)
            self._loaded.add(name)
            return self._indices[name]
        except Exception as e:
            logger.error("Failed to load shared index '%s': %s", name, e)
            return None

    def get_all(self) -> dict:
        """Load all configured shared indices.

        Returns dict of name -> index for successfully loaded indices.
        """
        for name in list(self._configs.keys()):
            self.get(name)
        return dict(self._indices)

    def available(self) -> list[str]:
        """List names of configured shared indices."""
        return list(self._configs.keys())

    def status(self) -> dict:
        """Get status of all configured shared indices.

        Returns dict with path, existence, embedding model, and load status.
        """
        result = {}
        for name, path in self._configs.items():
            exists = (path / "index_store.json").exists()
            manifest = self._load_manifest(path) if exists else {}
            result[name] = {
                "path": str(path),
                "exists": exists,
                "embedding_model": manifest.get("embedding_model", "unknown"),
                "loaded": name in self._loaded,
            }
        return result

    def _load_manifest(self, path: Path) -> dict:
        """Load manifest.json from a shared index directory.

        Returns empty dict if not found or invalid.
        """
        manifest_path = path / "manifest.json"
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}


def merge_results(nodes_by_source: dict[str, list], top_k: int) -> list[TaggedNode]:
    """Merge results from multiple indices by score.

    Args:
        nodes_by_source: Map of source name -> list of nodes
        top_k: Maximum number of results to return

    Returns:
        List of TaggedNode sorted by score (highest first)
    """
    all_nodes = []
    for source, nodes in nodes_by_source.items():
        for node in nodes:
            score = node.score if hasattr(node, "score") and node.score else 0.0
            text = node.text if hasattr(node, "text") else str(node)
            file_name = (
                node.metadata.get("file_name", "unknown")
                if hasattr(node, "metadata")
                else "unknown"
            )
            all_nodes.append(
                TaggedNode(
                    text=text,
                    score=score,
                    source=source,
                    file_name=file_name,
                )
            )

    all_nodes.sort(key=lambda n: n.score, reverse=True)
    return all_nodes[:top_k]


def format_tagged_results(nodes: list[TaggedNode]) -> str:
    """Format results with source tags for LLM consumption.

    Args:
        nodes: List of TaggedNode to format

    Returns:
        Formatted string with numbered results and source tags
    """
    if not nodes:
        return "No results found."

    formatted = []
    for i, node in enumerate(nodes, 1):
        text = node.text[:500] + "..." if len(node.text) > 500 else node.text
        formatted.append(
            f"[{i}] {node.source_tag} {node.file_name} (score: {node.score:.3f})\n{text}"
        )

    return "\n\n".join(formatted)


def validate_scope(scope: str, available: list[str]) -> tuple[bool, str]:
    """Validate scope parameter against available indices.

    Args:
        scope: Scope string ("all", "local", or "shared:{name}")
        available: List of available shared index names

    Returns:
        Tuple of (is_valid, error_message)
    """
    if scope == "all":
        return True, ""
    if scope == "local":
        return True, ""
    if scope.startswith("shared:"):
        name = scope.replace("shared:", "")
        if name in available:
            return True, ""
        available_str = ", ".join(available) if available else "none"
        return False, f"Unknown shared index '{name}'. Available: {available_str}"
    return False, f"Invalid scope '{scope}'. Use 'all', 'local', or 'shared:{{name}}'"
