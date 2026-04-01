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

import os
import sys
import json
import shutil
import argparse
import time
import threading
import atexit
import signal
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler

# Module-level RLock for thread-safe index access
_index_lock = threading.RLock()

# Try to import file watcher (graceful degradation)
try:
    from src.mimir.watcher import MimirFileWatcher

    WATCHER_AVAILABLE = True
except ImportError:
    MimirFileWatcher = None
    WATCHER_AVAILABLE = False
    import logging

    logging.getLogger(__name__).warning(
        "watchdog not installed - file watcher disabled"
    )

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))
from src.mimir.metrics import get_tracker

from mcp.server.fastmcp import FastMCP
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
    Settings,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai_like import OpenAILike


@dataclass(frozen=True)
class ServerConfig:
    project_root: Path
    knowledge_dir: Path
    docs_dir: Path
    code_dirs: list[Path]
    embedding_model: str
    api_key: str
    api_base: Optional[str]

    @classmethod
    def _get_api_key(cls) -> tuple[str, Optional[str]]:
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
            "OPENAI_API_KEY", ""
        )
        if api_key:
            return api_key, os.environ.get("OPENAI_BASE_URL")

        auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
        if auth_path.exists():
            try:
                with open(auth_path) as f:
                    auth_data = json.load(f)
                if openrouter := auth_data.get("openrouter"):
                    return openrouter.get("key", ""), "https://openrouter.ai/api/v1"
            except (json.JSONDecodeError, KeyError):
                pass

        return "", None

    @classmethod
    def _load_project_config(cls, project_root: Path) -> dict:
        config_path = project_root / ".mimir" / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    @classmethod
    def from_env(cls) -> "ServerConfig":
        project_root = cls._detect_project_root()
        api_key, api_base = cls._get_api_key()
        if api_key and not api_base:
            api_base = "https://openrouter.ai/api/v1"

        project_config = cls._load_project_config(project_root)

        docs_dir = Path(
            project_config.get("docs_dir")
            or os.environ.get("DOCS_DIR")
            or project_root / "docs"
        )
        if not docs_dir.is_absolute():
            docs_dir = project_root / docs_dir

        code_dirs = []
        if "code_dirs" in project_config:
            code_dirs = [Path(d) for d in project_config["code_dirs"]]
        elif code_dirs_env := os.environ.get("CODE_DIRS", ""):
            code_dirs = [Path(d.strip()) for d in code_dirs_env.split(",") if d.strip()]

        knowledge_dir = Path(
            project_config.get("knowledge_dir")
            or os.environ.get("KNOWLEDGE_DIR")
            or project_root / ".knowledge" / "llamaindex"
        )
        # Resolve relative paths against project_root
        if not knowledge_dir.is_absolute():
            knowledge_dir = project_root / knowledge_dir

        return cls(
            project_root=project_root,
            knowledge_dir=knowledge_dir,
            docs_dir=docs_dir,
            code_dirs=code_dirs,
            embedding_model=project_config.get("embedding_model")
            or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            api_key=api_key,
            api_base=api_base,
        )

    @staticmethod
    def _detect_project_root() -> Path:
        for env_var in ["PROJECT_ROOT", "WORKSPACE_FOLDER", "VSCODE_CWD"]:
            if path := os.environ.get(env_var):
                resolved = Path(path).resolve()
                if resolved.exists():
                    print(
                        f"[Knowledge Server] Project root from {env_var}: {resolved}",
                        file=sys.stderr,
                    )
                    return resolved

        cwd = Path.cwd().resolve()
        markers = [
            ".opencode",
            "opencode.json",
            ".git",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
        ]

        current = cwd
        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    print(
                        f"[Knowledge Server] Project root via {marker}: {current}",
                        file=sys.stderr,
                    )
                    return current
            current = current.parent

        print(f"[Knowledge Server] Using CWD: {cwd}", file=sys.stderr)
        return cwd


class KnowledgeServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self._index: Optional[VectorStoreIndex] = None
        self._watcher: Optional[MimirFileWatcher] = None

        embed_kwargs = {"model": config.embedding_model, "api_key": config.api_key}
        llm_kwargs = {"api_key": config.api_key}
        if config.api_base:
            embed_kwargs["api_base"] = config.api_base
            llm_kwargs["api_base"] = config.api_base

        Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
        # Use a faster model for query synthesis to avoid timeouts
        Settings.llm = OpenAILike(
            model="google/gemini-3.1-flash-lite-preview", **llm_kwargs
        )

        self.config.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def get_index(self) -> Optional[VectorStoreIndex]:
        # Fast path: return cached index without lock
        if self._index is not None:
            return self._index

        # Slow path: load index with lock
        with _index_lock:
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

        success = index_with_progress(
            project_root=self.config.project_root,
            docs_dir=self.config.docs_dir,
            code_dirs=self.config.code_dirs,
            knowledge_dir=self.config.knowledge_dir,
            force_reindex=False,
            verbose=True,
        )

        if not success:
            raise ValueError("Failed to create index")

        storage_context = StorageContext.from_defaults(
            persist_dir=str(self.config.knowledge_dir)
        )
        return load_index_from_storage(storage_context)

    def search(self, query: str, top_k: int = 5) -> str:
        start_time = time.time()
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
        duration_ms = int((time.time() - start_time) * 1000)

        # Track metrics - record_query will calculate realistic costs
        tracker = get_tracker(self.config.project_root)
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
            tracker = get_tracker(self.config.project_root)
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

        target_dir = docs_dir or self.config.docs_dir

        if not target_dir.exists():
            return f"Documents directory not found: {target_dir}"

        with _index_lock:
            success = index_with_progress(
                project_root=self.config.project_root,
                docs_dir=self.config.docs_dir,
                code_dirs=self.config.code_dirs,
                knowledge_dir=self.config.knowledge_dir,
                force_reindex=False,
                verbose=True,
            )

            if success:
                self._index = None
                return f"Successfully indexed {target_dir}"
            return "Error indexing documents"

    def add_documents(self, source_dir: Path) -> str:
        from mimir.indexing import add_directory_with_progress

        if not source_dir.exists():
            return f"Source directory not found: {source_dir}"

        with _index_lock:
            success = add_directory_with_progress(
                source_dir=source_dir,
                knowledge_dir=self.config.knowledge_dir,
                verbose=True,
            )

            if success:
                self._index = None
                return f"Successfully added documents from {source_dir}"
            return "Error adding documents"

    def get_stats(self) -> dict:
        index = self.get_index()
        stats = {
            "project_root": str(self.config.project_root),
            "knowledge_dir": str(self.config.knowledge_dir),
            "docs_dir": str(self.config.docs_dir),
            "code_dirs": [str(d) for d in self.config.code_dirs],
            "has_index": index is not None,
        }

        if index is not None:
            stats["document_count"] = len(index.storage_context.docstore.docs)

        total_source_files = 0
        if self.config.docs_dir.exists():
            files = list(self.config.docs_dir.rglob("*"))
            total_source_files += len([f for f in files if f.is_file()])

        for code_dir in self.config.code_dirs:
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

        watched_dirs = [self.config.docs_dir] + self.config.code_dirs
        watched_dirs = [d for d in watched_dirs if d.exists()]

        if not watched_dirs:
            return {"status": "error", "message": "no directories to watch"}

        self._watcher = MimirFileWatcher(
            project_root=self.config.project_root,
            watched_dirs=watched_dirs,
            knowledge_dir=self.config.knowledge_dir,
            index_lock=_index_lock,
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
    mcp = FastMCP("raveneye-knowledge")

    @mcp.tool()
    async def search(query: str, top_k: int = 5) -> str:
        """Search the project knowledge base using semantic similarity."""
        return server.search(query, top_k)

    @mcp.tool()
    async def query(question: str) -> str:
        """Ask a question about the project."""
        return server.query(question)

    @mcp.tool()
    async def reindex() -> str:
        """Rebuild the knowledge base from the docs directory."""
        return server.index_documents()

    @mcp.tool()
    async def stats() -> str:
        """Get statistics about the knowledge base."""
        return json.dumps(server.get_stats(), indent=2)

    @mcp.tool()
    async def rag_workflow(query: str) -> str:
        import asyncio
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.rag import graph as rag_graph

        config = {"configurable": {"thread_id": "mcp-rag"}}
        result = await rag_graph.ainvoke(
            {"messages": [HumanMessage(content=query)]}, config
        )
        return result["messages"][-1].content

    @mcp.tool()
    async def knowledge_agent(question: str) -> str:
        import asyncio
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.knowledge_agent import graph as agent_graph

        config = {"configurable": {"thread_id": "mcp-agent"}}
        result = await agent_graph.ainvoke(
            {"messages": [HumanMessage(content=question)]}, config
        )
        return result["messages"][-1].content

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
    parser = argparse.ArgumentParser(description="RavenEye Knowledge MCP Server")
    parser.add_argument(
        "--index", metavar="DIR", nargs="?", const=True, help="Index documents"
    )
    parser.add_argument(
        "--reindex", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--add", metavar="DIR", help="Add documents from DIR to existing index"
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

    config = ServerConfig.from_env()
    server = KnowledgeServer(config)

    if args.index:
        docs_dir = Path(args.index) if isinstance(args.index, str) else None
        print(server.index_documents(docs_dir))
        return

    if args.reindex:
        if config.knowledge_dir.exists():
            shutil.rmtree(config.knowledge_dir)
            config.knowledge_dir.mkdir(parents=True, exist_ok=True)
        print(server.index_documents())
        return

    if args.add:
        source_dir = Path(args.add)
        print(server.add_documents(source_dir))
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
