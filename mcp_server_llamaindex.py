#!/usr/bin/env python3
"""
Workspace-aware LlamaIndex MCP server for per-project knowledge bases.

Usage:
    python mcp_server_llamaindex.py                          # Run MCP server
    python mcp_server_llamaindex.py --index [DIR]            # Index documents
    python mcp_server_llamaindex.py --reindex                # Rebuild index
    python mcp_server_llamaindex.py --query "question"       # One-shot query
    python mcp_server_llamaindex.py --stats                  # Show statistics

Environment:
    PROJECT_ROOT: Override auto-detected project root
    KNOWLEDGE_DIR: Vector index storage path
    DOCS_DIR: Documents directory
    CODE_DIRS: Comma-separated list of code directories to index (e.g., "src,lib,tests")
    EMBEDDING_MODEL: OpenAI-compatible model name (default: text-embedding-3-small)
    OPENAI_API_KEY: API key (can use OPENROUTER_API_KEY instead)
    OPENAI_BASE_URL: API base URL (default: OpenAI, use https://openrouter.ai/api/v1 for OpenRouter)
    OPENROUTER_API_KEY: Alternative to OPENAI_API_KEY for OpenRouter
"""

import argparse
import asyncio
import atexit
import json
import logging
import os
import shutil
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

# Ensure src directory is in sys.path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR / "src"

# Remove current directory from sys.path to avoid shadowing mimir package
current_dir = str(SCRIPT_DIR)
if current_dir in sys.path:
    sys.path.remove(current_dir)

# Add both MIMIR_ROOT and MIMIR_ROOT/src to support both import styles:
# - from mimir... (needs MIMIR_ROOT/src in path)
# - from src.mimir... (needs MIMIR_ROOT in path)
# IMPORTANT: Add SRC_DIR first (index 0) so it has priority over SCRIPT_DIR
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(1, str(SCRIPT_DIR))


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for Mimir."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Check if already configured
    if logging.getLogger().handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logging.basicConfig(
        level=log_level,
        handlers=[handler],
        force=True,
    )

    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


# Try to import file watcher (graceful degradation)
try:
    from mimir.watcher import MimirFileWatcher

    WATCHER_AVAILABLE = True
except ImportError:
    MimirFileWatcher = None
    WATCHER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "watchdog not installed - file watcher disabled"
    )

import contextlib  # noqa: E402

from llama_index.core import (  # noqa: E402
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.embeddings.openai import OpenAIEmbedding  # noqa: E402
from llama_index.llms.openai import OpenAI as OpenAILike  # noqa: E402
from mcp.server.fastmcp import FastMCP, Context  # noqa: E402

from mimir.config import MimirConfig, get_config  # noqa: E402
from mimir.metrics import get_tracker  # noqa: E402
from mimir.artifacts import get_artifact as artifacts_get_artifact, list_artifacts as artifacts_list_artifacts, load_manifest  # noqa: E402
from mimir.shared_index import (  # noqa: E402
    SharedIndexRegistry,
)
from mimir.query_cache import QueryCache  # noqa: E402

QUERY_CACHE = None

def get_query_cache(project_root: Path) -> Optional[QueryCache]:
    """Get or create query cache instance."""
    global QUERY_CACHE
    if QUERY_CACHE is None:
        QUERY_CACHE = QueryCache(project_root)
    return QUERY_CACHE


def create_server_config() -> MimirConfig:
    """Create MimirConfig for the MCP server."""
    return get_config()


class KnowledgeServer:
    def __init__(self, config: MimirConfig):
        self.config = config
        self.project_root = config.project_root
        self.knowledge_dir = config.knowledge_dir
        self.docs_dir = config.docs_dir
        self.code_dirs = list(config.code_dirs)
        self.embedding_model = config.embedding_model
        self.llm_model = config.llm_model
        self.api_key = config.api_key
        self.api_base = config.api_base
        self._index: Optional[VectorStoreIndex] = None
        self._watcher: Optional[MimirFileWatcher] = None
        self._index_lock = threading.Lock()
        self._setup_llama_index()
        self._shared_registry = SharedIndexRegistry(
            config.shared_indexes,
            config.embedding_model,
        )

    def _setup_llama_index(self) -> None:
        """Configure LlamaIndex with models from config."""
        # Set OPENAI_API_KEY env var so LlamaIndex's internal validation passes.
        # This is needed because LlamaIndex checks os.environ.get("OPENAI_API_KEY")
        # even when we pass api_key explicitly.
        os.environ["OPENAI_API_KEY"] = self.config.api_key
        if self.config.api_base:
            os.environ["OPENAI_BASE_URL"] = self.config.api_base

        embed_kwargs = {
            "model": self.config.embedding_model,
            "api_key": self.config.api_key,
        }
        llm_kwargs = {"api_key": self.config.api_key}
        if self.config.api_base:
            embed_kwargs["api_base"] = self.config.api_base
            llm_kwargs["api_base"] = self.config.api_base

        Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
        # Use a faster model for query synthesis to avoid timeouts
        Settings.llm = OpenAILike(model=self.config.llm_model, **llm_kwargs)

        self.config.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def get_index(self) -> Optional[VectorStoreIndex]:
        # Fast path: return cached index without lock
        if self._index is not None:
            return self._index

        # Slow path: load index with lock
        with self._index_lock:
            # Double-check after acquiring lock
            if self._index is not None:
                return self._index

            if (self.config.knowledge_dir / "index_store.json").exists():
                storage_context = StorageContext.from_defaults(
                    persist_dir=str(self.config.knowledge_dir)
                )
                self._index = load_index_from_storage(storage_context)
            elif self.config.docs_dir.exists():
                self._index = self._create_index()

            return self._index

    def _create_index(self) -> VectorStoreIndex:
        from mimir.indexing import index_with_progress, add_file_to_index

        # Get custom exclude patterns from config
        custom_patterns = (
            list(self.config.exclude_patterns) if self.config.exclude_patterns else None
        )

        success = index_with_progress(
            project_root=self.project_root,
            docs_dir=self.docs_dir,
            code_dirs=self.code_dirs,
            knowledge_dir=self.knowledge_dir,
            force_reindex=False,
            verbose=True,
            custom_exclude_patterns=custom_patterns,
        )

        if not success:
            raise ValueError("Failed to create index")

        # Index individual files from config (e.g., mcp_server_llamaindex.py)
        individual_files = self.config.files
        if individual_files:
            print(f"Indexing {len(individual_files)} individual file(s) from config...")
            for file_path_str in individual_files:
                file_path = Path(file_path_str)
                if not file_path.is_absolute():
                    file_path = self.project_root / file_path
                if file_path.exists():
                    add_file_to_index(
                        file_path, self.knowledge_dir, verbose=False,
                        project_root=self.project_root
                    )
                else:
                    print(f"  ⚠️  File not found: {file_path}")

        storage_context = StorageContext.from_defaults(
            persist_dir=str(self.knowledge_dir)
        )
        return load_index_from_storage(storage_context)

    def search(self, query: str, top_k: int = 5) -> str:
        start_time = time.time()
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        # Hybrid retrieval: vector similarity + BM25 keyword fallback
        try:
            from llama_index.retrievers.bm25 import BM25Retriever

            vector_retriever = index.as_retriever(similarity_top_k=top_k * 2)
            bm25_retriever = BM25Retriever.from_defaults(
                index=index, similarity_top_k=top_k
            )

            vector_nodes = vector_retriever.retrieve(query)
            bm25_nodes = bm25_retriever.retrieve(query)

            # Merge and deduplicate by node_id, preferring vector results
            seen_ids: set[str] = set()
            nodes = []
            for node in vector_nodes + bm25_nodes:
                nid = node.node_id
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    nodes.append(node)
                if len(nodes) >= top_k:
                    break
        except ImportError:
            # Fallback to vector-only if BM25 unavailable
            try:
                nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
            except Exception as e:
                return self._format_search_error(e, "vector retriever")
        except Exception as e:
            return self._format_search_error(e, "hybrid retriever")

        duration_ms = int((time.time() - start_time) * 1000)

        # Track metrics - record_query will calculate realistic costs
        try:
            tracker = get_tracker(self.project_root)
            tracker.record_query(
                query_type="search",
                query_text=query,
                docs_retrieved=len(nodes),
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # Don't let metrics break the search

        if not nodes:
            return "No relevant documents found."

        results = []
        for i, node in enumerate(nodes, 1):
            source = node.metadata.get("file_name", "unknown")
            score = node.score if hasattr(node, "score") else 0.0
            text = node.text[:500] + "..." if len(node.text) > 500 else node.text
            results.append(f"[{i}] {source} (score: {score:.3f})\n{text}")

        # Enhance with knowledge graph context if available
        try:
            from mimir.knowledge_graph import load_knowledge_graph
            import json

            kg = load_knowledge_graph(self.project_root)
            if kg and kg.get("relationships"):
                # Extract potential entity names from query
                query_terms = [q.strip() for q in query.split() if len(q.strip()) > 3]

                # Find nodes matching query terms
                matching_nodes = []
                for node in kg.get("nodes", []):
                    node_name = node.get("id", "")
                    if any(term.lower() in node_name.lower() for term in query_terms):
                        matching_nodes.append(node_name)

                if matching_nodes:
                    # Get neighbors for top matching node
                    top_node = matching_nodes[0]
                    neighbors = self._get_graph_neighbors(kg, top_node, depth=1)

                    if neighbors:
                        results.append(f"\n\n[Knowledge Graph Context]")
                        results.append(f"Node '{top_node}' is connected to:")
                        for neighbor in neighbors[:5]:  # Limit to 5 neighbors
                            results.append(f"  - {neighbor}")
        except Exception:
            pass  # Don't let graph enhancement break search

        return "\n\n".join(results)

    def _get_graph_neighbors(self, kg: dict, node_id: str, depth: int = 1) -> list[str]:
        """Get neighbor node IDs for a given node."""
        neighbors = []
        relationships = kg.get("relationships", [])

        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            if source == node_id:
                neighbors.append(f"{target} ({rel.get('type', 'connected')})")
            elif target == node_id:
                neighbors.append(f"{source} ({rel.get('type', 'connected')})")

        return neighbors[:10]  # Limit results

    def _format_search_error(self, e: Exception, context: str) -> str:
        """Format search errors with helpful messages."""
        error_type = type(e).__name__
        error_msg = str(e)

        # API authentication errors
        if "AuthenticationError" in error_type or "401" in error_msg:
            return (
                "Error: API authentication failed. Please check your API key.\n"
                "Set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable,\n"
                "or ensure the MCP server has access to the API key."
            )

        # NumPy shape errors (malformed embeddings)
        if "inhomogeneous shape" in error_msg or "array element" in error_msg:
            return (
                "Error: Received malformed embeddings from API. This usually means:\n"
                "1. The API key may be invalid or not set\n"
                "2. The API returned an error response instead of embeddings\n"
                "3. There may be a model mismatch (check embedding_model config)\n"
                "Try reindexing with: python mcp_server_llamaindex.py --reindex"
            )

        # Rate limiting or API errors
        if "RateLimitError" in error_type or "429" in error_msg:
            return "Error: API rate limit exceeded. Please try again later."

        return f"Error during search ({context}): {error_type}: {error_msg}"

    def query(self, question: str) -> str:
        start_time = time.time()
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        try:
            query_engine = index.as_query_engine()
            response = query_engine.query(question)
            result = str(response)
            duration_ms = int((time.time() - start_time) * 1000)

            # Track metrics - record_query will calculate realistic costs
            tracker = get_tracker(self.project_root)
            tracker.record_query(
                query_type="query",
                query_text=question,
                duration_ms=duration_ms,
            )

            return result
        except Exception as e:
            return self._format_search_error(e, "query engine")

    def index_documents(self, docs_dir: Optional[Path] = None) -> str:
        from mimir.indexing import index_with_progress

        target_dir = docs_dir or self.docs_dir

        if not target_dir.exists():
            return f"Documents directory not found: {target_dir}"

        # Get custom exclude patterns from config
        custom_patterns = (
            list(self.config.exclude_patterns) if self.config.exclude_patterns else None
        )

        with self._index_lock:
            success = index_with_progress(
                project_root=self.project_root,
                docs_dir=self.docs_dir,
                code_dirs=self.code_dirs,
                knowledge_dir=self.knowledge_dir,
                force_reindex=False,
                verbose=True,
                custom_exclude_patterns=custom_patterns,
            )

            # Index individual files from config (e.g., mimir.py, mcp_server_llamaindex.py)
            individual_files = self.config.files
            if individual_files:
                from mimir.indexing import add_file_to_index

                print(
                    f"  Indexing {len(individual_files)} individual file(s) from config..."
                )
                for file_path_str in individual_files:
                    file_path = Path(file_path_str)
                    if not file_path.is_absolute():
                        file_path = self.project_root / file_path
                    if file_path.exists():
                        add_file_to_index(
                            file_path,
                            self.knowledge_dir,
                            verbose=False,
                            project_root=self.project_root,
                        )
                    else:
                        print(f"    ⚠️  File not found: {file_path}")

            if success:
                self._index = None
                return f"Successfully indexed {target_dir}"
            return "Error indexing documents"

    def add_documents(self, source_dir: Path) -> str:
        from mimir.indexing import add_directory_with_progress

        if not source_dir.exists():
            return f"Source directory not found: {source_dir}"

        # Get custom exclude patterns from config
        custom_patterns = (
            list(self.config.exclude_patterns) if self.config.exclude_patterns else None
        )

        with self._index_lock:
            success = add_directory_with_progress(
                source_dir=source_dir,
                knowledge_dir=self.knowledge_dir,
                verbose=True,
                custom_exclude_patterns=custom_patterns,
            )

            if success:
                self._index = None
                return f"Successfully added documents from {source_dir}"
            return "Error adding documents"

    def remove_file(self, source_file: Path) -> str:
        from mimir.indexing import remove_file_from_index

        resolved = source_file.resolve()
        if not resolved.exists():
            # Still attempt removal — file may have been deleted from disk
            pass

        with self._index_lock:
            success = remove_file_from_index(
                source_file=resolved,
                knowledge_dir=self.knowledge_dir,
                verbose=True,
            )

            if success:
                self._index = None
                return f"Successfully removed {resolved} from index"
            return f"File not found in index: {resolved}"

    def remove_directory(self, source_dir: Path) -> str:
        from mimir.indexing import remove_directory_from_index

        resolved = source_dir.resolve()
        if not resolved.exists():
            return f"Directory not found: {resolved}"

        with self._index_lock:
            success = remove_directory_from_index(
                source_dir=resolved,
                knowledge_dir=self.knowledge_dir,
                verbose=True,
            )

            if success:
                self._index = None
                return f"Successfully removed directory {resolved} from index"
            return f"Failed to remove directory from index: {resolved}"

    def get_stats(self) -> dict:
        index = self.get_index()
        stats = {
            "project_root": str(self.project_root),
            "knowledge_dir": str(self.knowledge_dir),
            "docs_dir": str(self.docs_dir),
            "code_dirs": [str(d) for d in self.code_dirs],
            "has_index": index is not None,
        }

        if index is not None:
            stats["document_count"] = len(index.storage_context.docstore.docs)

        total_source_files = 0
        if self.docs_dir.exists():
            files = list(self.docs_dir.rglob("*"))
            total_source_files += len([f for f in files if f.is_file()])

        for code_dir in self.code_dirs:
            if code_dir.exists():
                files = list(code_dir.rglob("*"))
                total_source_files += len([f for f in files if f.is_file()])

        stats["source_files"] = total_source_files

        return stats

    def start_watcher(self) -> dict:
        if not WATCHER_AVAILABLE:
            return {"status": "error", "message": "watchdog not installed"}

        if self._watcher is not None and self._watcher.status()["running"]:
            return {"status": "running", "message": "watcher already running"}

        index = self.get_index()
        if index is None:
            return {
                "status": "error",
                "message": "no index found, cannot start watcher",
            }

        watched_dirs = [self.docs_dir] + self.code_dirs
        watched_dirs = [d for d in watched_dirs if d.exists()]

        if not watched_dirs:
            return {"status": "error", "message": "no directories to watch"}

        self._watcher = MimirFileWatcher(
            project_root=self.project_root,
            watched_dirs=watched_dirs,
            knowledge_dir=self.knowledge_dir,
            index_lock=self._index_lock,
        )
        self._watcher.start()
        return {"status": "running"}

    def stop_watcher(self) -> dict:
        if self._watcher is None:
            return {"status": "stopped", "message": "watcher not initialized"}

        self._watcher.stop()
        return {"status": "stopped"}

    def get_watcher_status(self) -> dict:
        if not WATCHER_AVAILABLE:
            return {
                "status": "error",
                "message": "watchdog not installed",
                "watched_dirs": [],
                "last_trigger": None,
                "changes_processed": 0,
            }

        if self._watcher is None:
            return {
                "status": "stopped",
                "watched_dirs": [],
                "last_trigger": None,
                "changes_processed": 0,
            }

        watcher_status = self._watcher.status()
        return {
            "status": "running" if watcher_status["running"] else "stopped",
            "watched_dirs": watcher_status["watched_dirs"],
            "last_trigger": (
                watcher_status["last_reindex_result"].get("timestamp")
                if watcher_status["last_reindex_result"]
                else None
            ),
            "changes_processed": watcher_status["reindex_count"],
        }


def create_mcp_server(server: KnowledgeServer) -> FastMCP:
    mcp = FastMCP("mimir-knowledge")

    # Default timeout for tool calls (seconds)
    TOOL_TIMEOUT = 30

    async def _with_timeout(coro, timeout: int = TOOL_TIMEOUT) -> str:
        """Wrap a coroutine with a timeout, returning an error string on timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except TimeoutError:
            return f"Error: Request timed out after {timeout}s. Try a simpler query."

    async def _notify_jcode_usage(ctx: Context, tool_name: str) -> None:
        """Send a notification to Jcode client when Mimir tools are used."""
        try:
            # Get client info if available
            client_info = ""
            if hasattr(ctx, 'client_id') and ctx.client_id:
                client_info = f" from {ctx.client_id}"
            
            # Send info notification to client
            await ctx.info(
                f"Mimir is being used by Jcode{client_info} - Tool: {tool_name}"
            )
        except Exception:
            # Don't let notification errors break the tool execution
            pass

    def _check_budget(budget_tokens: int = None, budget_usd: float = None) -> dict:
        """Check if we have enough budget remaining.
        
        Returns: dict with 'ok' (bool), 'warning' (str or None), 'remaining' (dict)
        """
        if budget_tokens is None and budget_usd is None:
            return {"ok": True, "warning": None, "remaining": {}}
        
        try:
            from mimir.metrics import get_tracker
            tracker = get_tracker()
            summary = tracker.get_summary(days=1)  # Last 24 hours
            
            warnings = []
            
            if budget_usd is not None:
                remaining_usd = budget_usd - summary.get("total_cost", 0)
                if remaining_usd <= 0:
                    return {
                        "ok": False,
                        "warning": f"Budget exceeded: ${summary.get('total_cost', 0):.4f} / ${budget_usd:.4f}",
                        "remaining": {"usd": remaining_usd}
                    }
                elif remaining_usd < budget_usd * 0.1:  # Less than 10% remaining
                    warnings.append(f"Budget warning: ${remaining_usd:.4f} remaining ({(remaining_usd/budget_usd)*100:.0f}%)")
            
            return {"ok": True, "warning": "; ".join(warnings) if warnings else None, "remaining": {}}
        except Exception as e:
            return {"ok": True, "warning": f"Budget check failed: {e}", "remaining": {}}

    def _format_budget_info(budget_tokens: int = None, budget_usd: float = None) -> str:
        """Format budget info for response."""
        info = []
        if budget_tokens:
            info.append(f"Token budget: {budget_tokens}")
        if budget_usd:
            info.append(f"Cost budget: ${budget_usd:.4f}")
        return " | ".join(info) if info else ""

    @mcp.tool()
    async def search(query: str, top_k: int = 5, max_tokens: int = None, max_cost_usd: float = None, ctx: Context = None) -> str:
        """Search the project knowledge base using semantic similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return (default: 5)
            max_tokens: Optional token budget for this request
            max_cost_usd: Optional cost budget in USD for this request
        """
        await _notify_jcode_usage(ctx, "search")
        
        # Check budget
        budget_check = _check_budget(max_tokens, max_cost_usd)
        if not budget_check["ok"]:
            return f"Error: {budget_check['warning']}"
        
        result = await _with_timeout(
            asyncio.to_thread(server.search, query, top_k)
        )
        
        # Append budget warning if any
        if budget_check.get("warning"):
            result = f"[Budget Warning: {budget_check['warning']}]\n\n{result}"
        
        return result

    @mcp.tool()
    async def query(question: str, max_tokens: int = None, max_cost_usd: float = None, ctx: Context = None) -> str:
        """Ask a question about the project.

        Args:
            question: The question to ask.
            max_tokens: Optional token budget for this request.
            max_cost_usd: Optional cost budget in USD for this request.
        """
        await _notify_jcode_usage(ctx, "query")

        # Check budget
        budget_check = _check_budget(max_tokens, max_cost_usd)
        if not budget_check["ok"]:
            return f"Error: {budget_check['warning']}"

        result = await _with_timeout(
            asyncio.to_thread(server.query, question)
        )

        # Append budget warning if any
        if budget_check.get("warning"):
            result = f"[Budget Warning: {budget_check['warning']}]\n\n{result}"

        return result

    @mcp.tool()
    async def reindex(ctx: Context = None) -> str:
        """Rebuild the knowledge base from the docs directory."""
        await _notify_jcode_usage(ctx, "reindex")
        return await _with_timeout(
            asyncio.to_thread(server.index_documents), timeout=120
        )

    @mcp.tool()
    async def remove_file(file_path: str, ctx: Context = None) -> str:
        """Remove a specific file from the knowledge base index.

        Args:
            file_path: Absolute or relative path of the file to remove from the index.
        """
        await _notify_jcode_usage(ctx, "remove_file")
        path = Path(file_path)
        if not path.is_absolute():
            path = server.project_root / path
        return await _with_timeout(
            asyncio.to_thread(server.remove_file, path)
        )

    @mcp.tool()
    async def stats(ctx: Context = None) -> str:
        """Get statistics about the knowledge base."""
        await _notify_jcode_usage(ctx, "stats")
        return json.dumps(server.get_stats(), indent=2)

    @mcp.tool()
    async def cache_stats(ctx: Context = None) -> str:
        """Get query cache statistics."""
        await _notify_jcode_usage(ctx, "cache_stats")
        cache = get_query_cache(server.project_root)
        if cache is None:
            return json.dumps({"error": "Query cache not available"})
        return json.dumps(cache.stats(), indent=2)

    @mcp.tool()
    async def cache_clear(ctx: Context = None) -> str:
        """Clear all cached query results."""
        await _notify_jcode_usage(ctx, "cache_clear")
        cache = get_query_cache(server.project_root)
        if cache is None:
            return "Query cache not available"
        count = cache.invalidate()
        return f"Cleared {count} cached entries"

    @mcp.tool()
    async def cache_cleanup(ctx: Context = None) -> str:
        """Remove expired cache entries."""
        await _notify_jcode_usage(ctx, "cache_cleanup")
        cache = get_query_cache(server.project_root)
        if cache is None:
            return "Query cache not available"
        count = cache.cleanup()
        return f"Cleaned up {count} expired cache entries"

    @mcp.tool()
    async def rag_workflow(query: str, response_shape: str = None, max_tokens: int = None, max_cost_usd: float = None, ctx: Context = None) -> str:
        """Structured retrieve→generate pipeline for complex analysis.

        Args:
            query: The query for the RAG pipeline.
            response_shape: Optional JSON schema for structured output (KnowQL-inspired).
                When provided, the LLM will return a JSON object matching this schema.
            max_tokens: Optional token budget for this request.
            max_cost_usd: Optional cost budget in USD for this request.
        """
        await _notify_jcode_usage(ctx, "rag_workflow")

        # Check budget
        budget_check = _check_budget(max_tokens, max_cost_usd)
        if not budget_check["ok"]:
            return f"Error: {budget_check['warning']}"

        from langchain_core.messages import HumanMessage

        from langgraph.workflows.rag import graph as rag_graph

        async def _run_rag():
            config = {"configurable": {"thread_id": "mcp-rag"}}
            result = await rag_graph.ainvoke(
                {"messages": [HumanMessage(content=query)], "response_shape": response_shape}, config
            )
            return result["messages"][-1].content

        result = await _with_timeout(_run_rag())

        # Append budget warning if any
        if budget_check.get("warning"):
            result = f"[Budget Warning: {budget_check['warning']}]\n\n{result}"

        return result

    @mcp.tool()
    async def knowledge_agent(question: str, ctx: Context = None) -> str:
        """Multi-step agentic research for deep exploration."""
        await _notify_jcode_usage(ctx, "knowledge_agent")
        from langchain_core.messages import HumanMessage

        from langgraph.workflows.knowledge_agent import graph as agent_graph

        async def _run_agent():
            config = {"configurable": {"thread_id": "mcp-agent"}}
            result = await agent_graph.ainvoke(
                {"messages": [HumanMessage(content=question)]}, config
            )
            return result["messages"][-1].content

        return await _with_timeout(_run_agent())

    @mcp.tool()
    async def enrich_task(task: str, top_k: int = 5, ctx: Context = None) -> str:
        """Search Mimir for project context relevant to an OpenSpace task.

        Call this BEFORE executing tasks to get project-specific context
        (conventions, APIs, patterns) that generic skills lack.

        Args:
            task: Task description in natural language.
            top_k: Number of context chunks to retrieve (default: 5).
        """
        await _notify_jcode_usage(ctx, "enrich_task")
        from src.mimir.openspace_bridge import enrich_task_for_openspace

        def _enrich():
            result = enrich_task_for_openspace(task, server.project_root)

            # Add status field to distinguish empty results from errors
            if not result.get("success", False):
                result["status"] = "error"
            elif result.get("result_count", 0) == 0:
                result["status"] = "no_results"
                result["suggestion"] = (
                    "Try a broader query or check if the index has been built"
                )
            else:
                result["status"] = "ok"

            return json.dumps(result, ensure_ascii=False, indent=2)

        return await _with_timeout(asyncio.to_thread(_enrich))

    @mcp.tool()
    async def openspace_health(ctx: Context = None) -> str:
        """Check if the Mimir ↔ OpenSpace bridge is healthy.

        Returns bridge status, circuit breaker state, and index availability.
        Call this before depending on enrich_task.
        """
        await _notify_jcode_usage(ctx, "openspace_health")
        from src.mimir.openspace_bridge import get_bridge

        def _health():
            bridge = get_bridge(server.project_root)
            return json.dumps(bridge.health_check(), indent=2)

        return await _with_timeout(asyncio.to_thread(_health))

    @mcp.tool()
    async def sdk_cache_get(library: str, topic: str = "general", ctx: Context = None) -> str:
        """Get SDK documentation from local cache (fetches from Context7 if stale).

        Use this to get up-to-date docs for any library/framework without
        burning tokens on repeated API calls. Docs are cached for 7 days.

        Args:
            library: Library name (e.g., "stripe", "nextjs", "react").
            topic: Specific topic to fetch (e.g., "checkout sessions", "routing").
        """
        await _notify_jcode_usage(ctx, "sdk_cache_get")
        from src.mimir.sdk_cache import SDKCache

        def _get_docs():
            cache = SDKCache(server.project_root)
            docs = cache.get(library, topic)
            if docs:
                return docs
            return json.dumps(
                {
                    "error": f"No docs found for {library}/{topic}",
                    "suggestion": "Try a different topic or check the library name",
                }
            )

        return await _with_timeout(asyncio.to_thread(_get_docs))

    @mcp.tool()
    async def sdk_cache_list(ctx: Context = None) -> str:
        """List all cached SDK documentation libraries with freshness info.

        Returns a list of cached libraries, their freshness status, and topics.
        """
        await _notify_jcode_usage(ctx, "sdk_cache_list")
        from src.mimir.sdk_cache import SDKCache

        cache = SDKCache(server.project_root)
        cached = cache.list_cached()
        return json.dumps(cached, indent=2)

    @mcp.tool()
    async def health_check(ctx: Context = None) -> str:
        """Check Mimir server health and configuration status.

        Returns diagnostic information about the server state,
        including index availability, configuration summary, and any warnings.
        """
        await _notify_jcode_usage(ctx, "health_check")
        config = get_config()
        warnings = config.validate()

        knowledge_dir = config.knowledge_dir
        has_index = (knowledge_dir / "index_store.json").exists()

        # Check manifest freshness
        index_timestamp = None
        manifest_path = knowledge_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                index_timestamp = manifest.get("last_updated")
            except (json.JSONDecodeError, OSError):
                pass

        # Watcher availability
        watcher_info = {
            "available": WATCHER_AVAILABLE,
            "running": False,
        }
        if WATCHER_AVAILABLE and server._watcher is not None:
            with contextlib.suppress(Exception):
                watcher_info["running"] = server._watcher.status()["running"]
        if not WATCHER_AVAILABLE:
            warnings.append(
                "watchdog not installed — auto-reindex disabled; run: pip install watchdog"
            )

        result = {
            "status": "healthy" if (has_index and config.api_key) else "degraded",
            "has_index": has_index,
            "has_api_key": bool(config.api_key),
            "index_timestamp": index_timestamp,
            "project_root": str(config.project_root),
            "embedding_model": config.embedding_model,
            "llm_model": config.llm_model,
            "watcher": watcher_info,
            "warnings": warnings,
            "config_summary": config.to_dict(),
        }

        return json.dumps(result, indent=2)

    # ── Graph query tools (proxy to Rust web server) ────────────────────────

    def _web_url(path: str) -> str:
        """Build URL for the Rust web server graph API."""
        import os

        port = os.environ.get("MIMIR_WEB_PORT", "8000")
        return f"http://localhost:{port}{path}"

    def _web_get(path: str, params: dict | None = None) -> str:
        """GET request to the Rust web server. Returns JSON string."""
        from urllib.error import URLError
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen

        url = _web_url(path)
        if params:
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url = f"{url}?{qs}"
        try:
            req = Request(url)
            with urlopen(req, timeout=10) as resp:
                return resp.read().decode()
        except URLError as exc:
            return json.dumps(
                {
                    "error": "Graph server unavailable",
                    "detail": str(exc.reason),
                    "suggestion": "Start the web UI: cd web && ./dev.sh",
                }
            )

    @mcp.tool()
    async def graph_query(source: str, target: str, ctx: Context = None) -> str:
        """Find the shortest weighted path between two modules or entities.

        Uses Dijkstra with relationship-type weights:
          calls/has_method = 1.0, inherits_from = 1.5,
          imports_from = 2.0, imports_module = 3.0

        Use this for structural questions like "how does X reach Y?"
        or "what connects module A to module B?"

        Args:
            source: Source module path or entity name (e.g., "src/auth/middleware").
            target: Target module path or entity name (e.g., "src/rate_limiter/service").
        """
        await _notify_jcode_usage(ctx, "graph_query")
        return _web_get("/api/graph/path", {"source": source, "target": target})

    @mcp.tool()
    async def graph_neighbors(
        node_id: str, depth: int = 1, relation_type: str | None = None, ctx: Context = None
    ) -> str:
        """Find what modules or entities are connected to a node.

        Returns neighbors up to `depth` hops away, optionally filtered
        by relationship type (imports_module, imports_from, calls,
        inherits_from, has_method).

        Args:
            node_id: Module path or entity name to explore.
            depth: How many hops out to search (1-5, default 1).
            relation_type: Optional filter — only show this relationship type.
        """
        await _notify_jcode_usage(ctx, "graph_neighbors")
        return _web_get(
            "/api/graph/neighbors",
            {"node_id": node_id, "depth": str(depth), "relation_type": relation_type},
        )

    @mcp.tool()
    async def graph_stats(ctx: Context = None) -> str:
        """Get statistics about the code knowledge graph.

        Returns node/edge/entity counts, relationship type breakdown,
        language distribution, and the most connected nodes.
        """
        await _notify_jcode_usage(ctx, "graph_stats")
        return _web_get("/api/graph/stats")

    @mcp.tool()
    async def get_artifact(artifact_id: str, ctx: Context = None) -> str:
        """Get a pre-compiled artifact by ID.

        Pre-compiled artifacts are structured knowledge about the project
        (e.g., architectural summaries) that are served directly without
        retrieval, inspired by Pinecone Nexus's approach.

        Args:
            artifact_id: Artifact identifier (e.g., "rag_architecture").
        """
        await _notify_jcode_usage(ctx, "get_artifact")
        artifact = artifacts_get_artifact(artifact_id, server.project_root)
        if artifact:
            return json.dumps(artifact, indent=2, ensure_ascii=False)
        return json.dumps({
            "error": f"Artifact not found: {artifact_id}",
            "available_artifacts": list(artifacts_list_artifacts(server.project_root).keys())
        })

    @mcp.tool()
    async def list_artifacts(ctx: Context = None) -> str:
        """List all available pre-compiled artifacts.

        Returns artifact IDs, versions, staleness status, and dependency counts.
        """
        await _notify_jcode_usage(ctx, "list_artifacts")
        return json.dumps(artifacts_list_artifacts(server.project_root), indent=2, ensure_ascii=False)

    return mcp


def find_available_port(start_port: int = 8001, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port."""
    import socket

    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"Could not find available port in range {start_port}-{start_port + max_attempts}"
    )


class WatcherStatusHandler(BaseHTTPRequestHandler):
    _server_instance: Optional["KnowledgeServer"] = None

    def do_GET(self):
        if self.path == "/api/watcher/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = (
                self._server_instance.get_watcher_status()
                if self._server_instance
                else {
                    "status": "stopped",
                    "watched_dirs": [],
                    "last_trigger": None,
                    "changes_processed": 0,
                }
            )
            self.wfile.write(json.dumps(status).encode())
        elif self.path == "/api/watcher/stop":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self._server_instance:
                result = self._server_instance.stop_watcher()
            else:
                result = {"status": "stopped"}
            self.wfile.write(json.dumps(result).encode())
        elif self.path == "/api/watcher/start":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self._server_instance:
                result = self._server_instance.start_watcher()
            else:
                result = {"status": "error", "message": "server not initialized"}
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_watcher_server(
    port: Optional[int] = None, server: Optional[KnowledgeServer] = None
) -> HTTPServer:
    """Start the watcher status HTTP server.

    Args:
        port: Port to use (default: env WATCHER_PORT or 8001, auto-increments if busy)
        server: KnowledgeServer instance for status queries

    Returns:
        Running HTTPServer instance
    """
    if port is None:
        port = int(os.environ.get("WATCHER_PORT", "8001"))

    try:
        actual_port = find_available_port(port)
        if actual_port != port:
            print(
                f"[Knowledge Server] Port {port} busy, using {actual_port}",
                file=sys.stderr,
            )
    except RuntimeError as e:
        print(f"[Knowledge Server] Error: {e}", file=sys.stderr)
        raise

    WatcherStatusHandler._server_instance = server
    http_server = HTTPServer(("", actual_port), WatcherStatusHandler)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    print(
        f"[Knowledge Server] Watcher status server on port {actual_port}",
        file=sys.stderr,
    )
    return http_server


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Mimir Knowledge MCP Server")
    parser.add_argument(
        "--index", metavar="DIR", nargs="?", const=True, help="Index documents"
    )
    parser.add_argument(
        "--reindex", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--add", metavar="DIR", help="Add documents from DIR to existing index"
    )
    parser.add_argument("--remove", metavar="FILE", help="Remove a file from the index")
    parser.add_argument(
        "--remove-dir",
        metavar="DIR",
        help="Remove all files from a directory from the index",
    )
    parser.add_argument("--query", metavar="QUESTION", help="Query the knowledge base")
    parser.add_argument(
        "--stats", action="store_true", help="Show knowledge base statistics"
    )
    parser.add_argument(
        "--metrics", action="store_true", help="Show cost metrics report"
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio", help="Transport mode"
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP port")

    args = parser.parse_args()

    config = create_server_config()

    # Validate configuration before starting
    validation_warnings = config.validate()
    for warning in validation_warnings:
        print(f"[Knowledge Server] ⚠️  {warning}", file=sys.stderr)

    if not config.api_key:
        print(
            "[Knowledge Server] ❌ No API key configured — "
            "set OPENROUTER_API_KEY or OPENAI_API_KEY, or run: opencode auth openrouter",
            file=sys.stderr,
        )
        print(
            "[Knowledge Server]    "
            "Server will start in degraded mode (indexing/embedding will fail)",
            file=sys.stderr,
        )

    server = KnowledgeServer(config)

    if args.index:
        docs_dir = Path(args.index) if isinstance(args.index, str) else None
        print(server.index_documents(docs_dir))
        return

    if args.reindex:
        if config.knowledge_dir.exists():
            from mimir.indexing import backup_index

            backup = backup_index(config.knowledge_dir)
            if backup:
                print(f"Backed up existing index → {backup}")
            else:
                print("No existing index to back up")
            shutil.rmtree(config.knowledge_dir)
            config.knowledge_dir.mkdir(parents=True, exist_ok=True)
        print(server.index_documents())
        return

    if args.add:
        source_dir = Path(args.add)
        print(server.add_documents(source_dir))
        return

    if args.remove:
        source_file = Path(args.remove)
        print(server.remove_file(source_file))
        return

    if args.remove_dir:
        source_dir = Path(args.remove_dir)
        print(server.remove_directory(source_dir))
        return

    if args.query:
        print(server.query(args.query))
        return

    if args.stats:
        print(json.dumps(server.get_stats(), indent=2))
        return

    if args.metrics:
        from src.mimir.metrics import format_report

        print(format_report(days=30))
        return

    try:
        http_server = start_watcher_server(server=server)
    except Exception as e:
        print(
            f"[Knowledge Server] Failed to start watcher server: {e}", file=sys.stderr
        )
        print(
            "[Knowledge Server] Continuing without watcher status server...",
            file=sys.stderr,
        )
        http_server = None

    def shutdown_watcher(signum=None, frame=None):
        if server._watcher is not None:
            server.stop_watcher()
        if http_server is not None:
            http_server.shutdown()

    atexit.register(shutdown_watcher)
    signal.signal(signal.SIGINT, shutdown_watcher)
    signal.signal(signal.SIGTERM, shutdown_watcher)

    index = server.get_index()
    if index is not None and WATCHER_AVAILABLE:
        watcher_result = server.start_watcher()
        if watcher_result.get("status") == "running":
            print("[Knowledge Server] File watcher started", file=sys.stderr)
        else:
            print(
                f"[Knowledge Server] Watcher not started: {watcher_result.get('message', 'unknown')}",
                file=sys.stderr,
            )
    elif not WATCHER_AVAILABLE:
        print(
            "[Knowledge Server] Watcher disabled (watchdog not installed)",
            file=sys.stderr,
        )

    mcp = create_mcp_server(server)
    try:
        print(
            f"[Knowledge Server] MCP server starting (transport: {args.transport})...",
            file=sys.stderr,
            flush=True,
        )
        import traceback
        try:
            mcp.run(transport=args.transport)
        except SystemExit as e:
            print(f"[Knowledge Server] SystemExit: {e}", file=sys.stderr, flush=True)
            raise
        except Exception as e:
            print(f"[Knowledge Server] MCP server error: {e}", file=sys.stderr, flush=True)
            traceback.print_exc()
            raise
    except Exception as e:
        print(f"[Knowledge Server] Outer error: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        import traceback
        print(f"[Knowledge Server] SystemExit in __main__: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(e.code if e.code is not None else 0)
    except KeyboardInterrupt:
        print("\n[Knowledge Server] Shutting down...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"[Knowledge Server] Fatal error in __main__: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)
