"""KnowledgeServer — core Mimir knowledge base server.

Provides search, query, indexing, and stats functionality.
Previously lived in mcp_server_llamaindex.py; extracted here
when MCP server was removed in favor of the thin CLI bridge.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from llama_index.core import (
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as OpenAILike

from src.mimir.config import MimirConfig
from src.mimir.metrics import get_tracker
from src.mimir.shared_index import SharedIndexRegistry

logger = logging.getLogger(__name__)

# Try to import file watcher (graceful degradation)
try:
    from src.mimir.watcher import MimirFileWatcher

    WATCHER_AVAILABLE = True
except ImportError:
    MimirFileWatcher = None
    WATCHER_AVAILABLE = False


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
        Settings.llm = OpenAILike(model=self.config.llm_model, **llm_kwargs)

        self.config.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def get_index(self) -> Optional[VectorStoreIndex]:
        if self._index is not None:
            return self._index

        with self._index_lock:
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
        from src.mimir.indexing import index_with_progress, add_file_to_index

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
                        project_root=self.project_root,
                    )
                else:
                    print(f"  File not found: {file_path}")

        storage_context = StorageContext.from_defaults(
            persist_dir=str(self.knowledge_dir)
        )
        return load_index_from_storage(storage_context)

    def search(self, query: str, top_k: int = 5) -> str:
        start_time = time.time()
        index = self.get_index()
        if index is None:
            return "No knowledge base found. Run with --index to create one."

        try:
            from llama_index.retrievers.bm25 import BM25Retriever

            vector_retriever = index.as_retriever(similarity_top_k=top_k * 2)
            bm25_retriever = BM25Retriever.from_defaults(
                index=index, similarity_top_k=top_k
            )

            vector_nodes = vector_retriever.retrieve(query)
            bm25_nodes = bm25_retriever.retrieve(query)

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
            try:
                nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
            except Exception as e:
                return self._format_search_error(e, "vector retriever")
        except Exception as e:
            return self._format_search_error(e, "hybrid retriever")

        duration_ms = int((time.time() - start_time) * 1000)

        try:
            tracker = get_tracker(self.project_root)
            tracker.record_query(
                query_type="search",
                query_text=query,
                docs_retrieved=len(nodes),
                duration_ms=duration_ms,
            )
        except Exception:
            pass

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
            import json as _json
            graph_path = self.project_root / ".knowledge" / "code_relationships.json"
            if graph_path.exists():
                with open(graph_path) as f:
                    kg = _json.load(f)
                if kg and kg.get("relationships"):
                    query_terms = [q.strip() for q in query.split() if len(q.strip()) > 3]
                    matching_entities = []
                    for entity_id in kg.get("entities", {}):
                        if any(term.lower() in entity_id.lower() for term in query_terms):
                            matching_entities.append(entity_id)

                    if matching_entities:
                        top_entity = matching_entities[0]
                        neighbors = self._get_graph_neighbors(kg, top_entity, depth=1)
                        if neighbors:
                            results.append("\n\n[Knowledge Graph Context]")
                            results.append(f"Entity '{top_entity}' is connected to:")
                            for neighbor in neighbors[:5]:
                                results.append(f"  - {neighbor}")
        except Exception:
            pass

        return "\n\n".join(results)

    def _get_graph_neighbors(self, kg: dict, node_id: str, depth: int = 1) -> list[str]:
        neighbors = []
        relationships = kg.get("relationships", [])
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            if source == node_id:
                neighbors.append(f"{target} ({rel.get('type', 'connected')})")
            elif target == node_id:
                neighbors.append(f"{source} ({rel.get('type', 'connected')})")
        return neighbors[:10]

    def _format_search_error(self, e: Exception, context: str) -> str:
        error_type = type(e).__name__
        error_msg = str(e)

        if "AuthenticationError" in error_type or "401" in error_msg:
            return (
                "Error: API authentication failed. Please check your API key.\n"
                "Set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable."
            )

        if "inhomogeneous shape" in error_msg or "array element" in error_msg:
            return (
                "Error: Received malformed embeddings from API.\n"
                "1. The API key may be invalid or not set\n"
                "2. The API returned an error response instead of embeddings\n"
                "3. There may be a model mismatch (check embedding_model config)"
            )

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
        from src.mimir.indexing import index_with_progress

        target_dir = docs_dir or self.docs_dir

        if not target_dir.exists():
            return f"Documents directory not found: {target_dir}"

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

            individual_files = self.config.files
            if individual_files:
                from src.mimir.indexing import add_file_to_index

                print(f"  Indexing {len(individual_files)} individual file(s) from config...")
                for file_path_str in individual_files:
                    file_path = Path(file_path_str)
                    if not file_path.is_absolute():
                        file_path = self.project_root / file_path
                    if file_path.exists():
                        add_file_to_index(
                            file_path, self.knowledge_dir, verbose=False,
                            project_root=self.project_root,
                        )
                    else:
                        print(f"    File not found: {file_path}")

            if success:
                self._index = None
                return f"Successfully indexed {target_dir}"
            return "Error indexing documents"

    def add_documents(self, source_dir: Path) -> str:
        from src.mimir.indexing import add_directory_with_progress

        if not source_dir.exists():
            return f"Source directory not found: {source_dir}"

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
        from src.mimir.indexing import remove_file_from_index

        resolved = source_file.resolve()

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
        from src.mimir.indexing import remove_directory_from_index

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
            return {"status": "error", "message": "no index found, cannot start watcher"}

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
