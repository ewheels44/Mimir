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
from mcp.server.fastmcp import FastMCP  # noqa: E402

from mimir.config import MimirConfig, get_config  # noqa: E402
from mimir.metrics import get_tracker  # noqa: E402
from mimir.shared_index import (  # noqa: E402
    SharedIndexRegistry,
)


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
        from mimir.indexing import index_with_progress

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
            nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
        duration_ms = int((time.time() - start_time) * 1000)

        # Track metrics - record_query will calculate realistic costs
        tracker = get_tracker(self.project_root)
        tracker.record_query(
            query_type="search",
            query_text=query,
            docs_retrieved=len(nodes),
            duration_ms=duration_ms,
        )

        if not nodes:
            return "No relevant documents found."

        results = []
        for i, node in enumerate(nodes, 1):
            source = node.metadata.get("file_name", "unknown")
            score = node.score if hasattr(node, "score") else 0.0
            text = node.text[:500] + "..." if len(node.text) > 500 else node.text
            results.append(f"[{i}] {source} (score: {score:.3f})\n{text}")

        return "\n\n".join(results)

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
            return f"Error querying knowledge base: {e}. Try using 'search' instead for faster results."

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

    @mcp.tool()
    async def search(query: str, top_k: int = 5) -> str:
        """Search the project knowledge base using semantic similarity."""
        return await _with_timeout(
            asyncio.to_thread(server.search, query, top_k)
        )

    @mcp.tool()
    async def query(question: str) -> str:
        """Ask a question about the project."""
        return await _with_timeout(
            asyncio.to_thread(server.query, question)
        )

    @mcp.tool()
    async def reindex() -> str:
        """Rebuild the knowledge base from the docs directory."""
        return await _with_timeout(
            asyncio.to_thread(server.index_documents), timeout=120
        )

    @mcp.tool()
    async def remove_file(file_path: str) -> str:
        """Remove a specific file from the knowledge base index.

        Args:
            file_path: Absolute or relative path of the file to remove from the index.
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = server.project_root / path
        return await _with_timeout(
            asyncio.to_thread(server.remove_file, path)
        )

    @mcp.tool()
    async def stats() -> str:
        """Get statistics about the knowledge base."""
        return json.dumps(server.get_stats(), indent=2)

    @mcp.tool()
    async def rag_workflow(query: str) -> str:
        from langchain_core.messages import HumanMessage

        from langgraph.workflows.rag import graph as rag_graph

        async def _run_rag():
            config = {"configurable": {"thread_id": "mcp-rag"}}
            result = await rag_graph.ainvoke(
                {"messages": [HumanMessage(content=query)]}, config
            )
            return result["messages"][-1].content

        return await _with_timeout(_run_rag())

    @mcp.tool()
    async def knowledge_agent(question: str) -> str:
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
    async def enrich_task(task: str, top_k: int = 5) -> str:
        """Search Mimir for project context relevant to an OpenSpace task.

        Call this BEFORE executing tasks to get project-specific context
        (conventions, APIs, patterns) that generic skills lack.

        Args:
            task: Task description in natural language.
            top_k: Number of context chunks to retrieve (default: 5).
        """
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
    async def openspace_health() -> str:
        """Check if the Mimir ↔ OpenSpace bridge is healthy.

        Returns bridge status, circuit breaker state, and index availability.
        Call this before depending on enrich_task.
        """
        from src.mimir.openspace_bridge import get_bridge

        def _health():
            bridge = get_bridge(server.project_root)
            return json.dumps(bridge.health_check(), indent=2)

        return await _with_timeout(asyncio.to_thread(_health))

    @mcp.tool()
    async def sdk_cache_get(library: str, topic: str = "general") -> str:
        """Get SDK documentation from local cache (fetches from Context7 if stale).

        Use this to get up-to-date docs for any library/framework without
        burning tokens on repeated API calls. Docs are cached for 7 days.

        Args:
            library: Library name (e.g., "stripe", "nextjs", "react").
            topic: Specific topic to fetch (e.g., "checkout sessions", "routing").
        """
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
    async def sdk_cache_list() -> str:
        """List all cached SDK documentation libraries with freshness info.

        Returns a list of cached libraries, their freshness status, and topics.
        """
        from src.mimir.sdk_cache import SDKCache

        cache = SDKCache(server.project_root)
        cached = cache.list_cached()
        return json.dumps(cached, indent=2)

    @mcp.tool()
    async def health_check() -> str:
        """Check Mimir server health and configuration status.

        Returns diagnostic information about the server state,
        including index availability, configuration summary, and any warnings.
        """
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
    async def graph_query(source: str, target: str) -> str:
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
        return _web_get("/api/graph/path", {"source": source, "target": target})

    @mcp.tool()
    async def graph_neighbors(
        node_id: str, depth: int = 1, relation_type: str | None = None
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
        return _web_get(
            "/api/graph/neighbors",
            {"node_id": node_id, "depth": str(depth), "relation_type": relation_type},
        )

    @mcp.tool()
    async def graph_stats() -> str:
        """Get statistics about the code knowledge graph.

        Returns node/edge/entity counts, relationship type breakdown,
        language distribution, and the most connected nodes.
        """
        return _web_get("/api/graph/stats")

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
        )
        mcp.run(transport=args.transport)
    except Exception as e:
        print(f"[Knowledge Server] MCP server error: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Knowledge Server] Shutting down...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"[Knowledge Server] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
