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
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

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
        all_documents = []

        if self.config.docs_dir.exists():
            docs = SimpleDirectoryReader(
                str(self.config.docs_dir), recursive=True
            ).load_data()
            all_documents.extend(docs)

        for code_dir in self.config.code_dirs:
            if code_dir.exists():
                try:
                    code_docs = SimpleDirectoryReader(
                        str(code_dir),
                        recursive=True,
                        filename_as_id=True,
                    ).load_data()
                    all_documents.extend(code_docs)
                except Exception as e:
                    print(
                        f"[Knowledge Server] Warning: Could not index {code_dir}: {e}",
                        file=sys.stderr,
                    )

        if not all_documents:
            raise ValueError("No documents found to index")

        storage_context = StorageContext.from_defaults()
        index = VectorStoreIndex.from_documents(
            all_documents, storage_context=storage_context
        )
        index.storage_context.persist(persist_dir=str(self.config.knowledge_dir))

        return index

    def search(self, query: str, top_k: int = 5) -> str:
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)

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
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        try:
            # Use a shorter timeout-friendly approach
            query_engine = index.as_query_engine()
            response = query_engine.query(question)
            return str(response)
        except Exception as e:
            return f"Error querying knowledge base: {e}. Try using 'search' instead for faster results."

    def index_documents(self, docs_dir: Optional[Path] = None) -> str:
        target_dir = docs_dir or self.config.docs_dir

        if not target_dir.exists():
            return f"Documents directory not found: {target_dir}"

        try:
            self._index = self._create_index()
            return f"Successfully indexed {target_dir}"
        except Exception as e:
            return f"Error indexing: {e}"

    def add_documents(self, source_dir: Path) -> str:
        if not source_dir.exists():
            return f"Source directory not found: {source_dir}"

        if not (self.config.knowledge_dir / "index_store.json").exists():
            return "No existing index found. Run --index to create one first."

        try:
            storage_context = StorageContext.from_defaults(
                persist_dir=str(self.config.knowledge_dir)
            )
            self._index = load_index_from_storage(storage_context)

            new_docs = SimpleDirectoryReader(
                str(source_dir), recursive=True, filename_as_id=True
            ).load_data()

            if not new_docs:
                return f"No documents found in {source_dir}"

            for doc in new_docs:
                self._index.insert(doc)

            self._index.storage_context.persist(
                persist_dir=str(self.config.knowledge_dir)
            )

            return f"Added {len(new_docs)} documents from {source_dir}"
        except Exception as e:
            return f"Error adding documents: {e}"

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

    mcp = create_mcp_server(server)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
