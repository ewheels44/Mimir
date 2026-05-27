#!/usr/bin/env python3
"""
mimir_bridge.py — Thin CLI bridge for Mimir knowledge base.

Replaces the MCP server with direct stdin/stdout JSON communication.
No MCP protocol, no JSON-RPC, no process lifecycle management.

Usage:
    echo '{"action":"search","params":{"query":"how does auth work"}}' | python3 mimir_bridge.py
    echo '{"action":"init"}' | python3 mimir_bridge.py          # Bootstrap a new project
    echo '{"action":"enrich_task","params":{"task":"implement JWT auth"}}' | python3 mimir_bridge.py
    echo '{"action":"stats"}' | python3 mimir_bridge.py

Environment:
    PROJECT_ROOT: Override auto-detected project root
    OPENROUTER_API_KEY: API key for embeddings/LLM
    OPENAI_API_KEY: Alternative to OPENROUTER_API_KEY
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

# ─── Path Setup ───────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
SRC_DIR = SCRIPT_DIR / "src"

# Remove current directory from sys.path to avoid shadowing
current_dir = str(SCRIPT_DIR)
if current_dir in sys.path:
    sys.path.remove(current_dir)

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(1, str(SCRIPT_DIR))

from mimir.utils import detect_project_root


def resolve_project_root(cli_override: str | None = None) -> Path:
    """Resolve project root from CLI override, bridge script location, env, or detection.

    Priority:
    1. --project-root CLI argument (explicit override)
    2. Bridge script location — derive project root from where mimir_bridge.py lives,
       walking up to find .mimir/config.json (most reliable; immune to caller's CWD)
    3. PROJECT_ROOT env var (only if pointing to a valid Mimir project)
    4. Auto-detection by walking up from cwd

    This prevents accidentally indexing a parent project (e.g. jcode) when the
    bridge is invoked from a nested non-Mimir project that happens to have its
    own .mimir/config.json.
    """
    if cli_override:
        return Path(cli_override).resolve()

    # Derive from bridge script's own location — most reliable signal
    # The bridge always lives inside or near the Mimir project root
    bridge_dir = Path(__file__).resolve().parent
    current = bridge_dir
    while current != current.parent:
        if (current / ".mimir" / "config.json").exists():
            return current
        current = current.parent

    # Fall back to PROJECT_ROOT env var (only trusted if valid Mimir project)
    if env := os.environ.get("PROJECT_ROOT"):
        resolved = Path(env).resolve()
        if (resolved / ".mimir" / "config.json").exists():
            return resolved

    return detect_project_root()


# ─── Action Handlers ──────────────────────────────────────────────────────────


def handle_init(params: dict, project_root: Path) -> dict:
    """Bootstrap a new project for Mimir knowledge base."""
    import json as _json

    force = params.get("force", False)

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    mimir_config_dir = project_root / ".mimir"

    # Create directories
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    mimir_config_dir.mkdir(exist_ok=True)

    # Create default config if missing or forced
    config_path = mimir_config_dir / "config.json"
    if force or not config_path.exists():
        default_config = {
            "docs_dir": "docs",
            "code_dirs": [],
            "files": [],
            "knowledge_dir": ".knowledge/llamaindex",
            "embedding_model": "text-embedding-3-small",
        }
        with open(config_path, "w") as f:
            _json.dump(default_config, f, indent=2)
        return {"status": "ok", "message": f"Created default config: {config_path}"}

    return {"status": "ok", "message": f"Config already exists: {config_path}"}


def handle_search(params: dict, project_root: Path) -> dict:
    """Semantic search over the knowledge base."""
    from mimir.config import get_config, reset_config

    reset_config()
    config = get_config(project_root=project_root)

    query = params.get("query", "")
    top_k = params.get("top_k", 5)

    if not query:
        return {"error": "Missing required parameter: query"}

    # Initialize LlamaIndex settings
    _setup_llama_index(config)

    from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage

    knowledge_dir = config.knowledge_dir
    if not (knowledge_dir / "index_store.json").exists():
        return {"error": "No knowledge base found. Run reindex first.", "status": "no_index"}

    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
        index = load_index_from_storage(storage_context)

        # Hybrid retrieval: vector + BM25
        try:
            from llama_index.retrievers.bm25 import BM25Retriever

            vector_retriever = index.as_retriever(similarity_top_k=top_k * 2)
            bm25_retriever = BM25Retriever.from_defaults(index=index, similarity_top_k=top_k)

            vector_nodes = vector_retriever.retrieve(query)
            bm25_nodes = bm25_retriever.retrieve(query)

            seen_ids = set()
            nodes = []
            for node in vector_nodes + bm25_nodes:
                nid = node.node_id
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    nodes.append(node)
                if len(nodes) >= top_k:
                    break
        except ImportError:
            nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)

        if not nodes:
            return {"status": "no_results", "results": []}

        results = []
        for node in nodes:
            source = node.metadata.get("file_name", "unknown")
            score = node.score if hasattr(node, "score") else 0.0
            text = node.text[:500] + "..." if len(node.text) > 500 else node.text
            results.append({"source": source, "score": round(score, 3), "text": text})

        return {"status": "ok", "results": results}

    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_enrich_task(params: dict, project_root: Path) -> dict:
    """Enrich a task with project context."""
    from mimir.query_router import route_task

    task = params.get("task", "")
    top_k = params.get("top_k", 5)

    if not task:
        return {"error": "Missing required parameter: task"}

    try:
        result = route_task(task, project_root=project_root, top_k=top_k)
        d = result.to_dict()

        if not d.get("success", False):
            d["status"] = "error"
        elif d.get("result_count", 0) == 0:
            d["status"] = "no_results"
            d["suggestion"] = "Try a broader query or check if the index has been built"
        else:
            d["status"] = "ok"

        return d
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_query(params: dict, project_root: Path) -> dict:
    """RAG question answering."""
    from mimir.config import get_config, reset_config

    reset_config()
    config = get_config(project_root=project_root)

    question = params.get("question", "")

    if not question:
        return {"error": "Missing required parameter: question"}

    _setup_llama_index(config)

    from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage

    knowledge_dir = config.knowledge_dir
    if not (knowledge_dir / "index_store.json").exists():
        return {"error": "No knowledge base found. Run reindex first.", "status": "no_index"}

    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
        index = load_index_from_storage(storage_context)
        query_engine = index.as_query_engine()
        response = query_engine.query(question)
        return {"status": "ok", "answer": str(response)}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_rag_workflow(params: dict, project_root: Path) -> dict:
    """Structured RAG pipeline via LangGraph."""
    try:
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.rag import graph as rag_graph
    except ImportError as e:
        return {"error": f"LangGraph not available: {e}", "status": "import_error"}

    query = params.get("query", "")
    response_shape = params.get("response_shape")

    if not query:
        return {"error": "Missing required parameter: query"}

    try:
        import asyncio

        async def _run():
            config = {"configurable": {"thread_id": "bridge-rag"}}
            result = await rag_graph.ainvoke(
                {"messages": [HumanMessage(content=query)], "response_shape": response_shape},
                config,
            )
            return result["messages"][-1].content

        answer = asyncio.run(_run())
        return {"status": "ok", "answer": answer}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_knowledge_agent(params: dict, project_root: Path) -> dict:
    """Multi-step agentic research via LangGraph."""
    try:
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.knowledge_agent import graph as agent_graph
    except ImportError as e:
        return {"error": f"LangGraph not available: {e}", "status": "import_error"}

    question = params.get("question", "")

    if not question:
        return {"error": "Missing required parameter: question"}

    try:
        import asyncio

        async def _run():
            config = {"configurable": {"thread_id": "bridge-agent"}}
            result = await agent_graph.ainvoke(
                {"messages": [HumanMessage(content=question)]}, config
            )
            return result["messages"][-1].content

        answer = asyncio.run(_run())
        return {"status": "ok", "answer": answer}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_reindex(params: dict, project_root: Path) -> dict:
    """Rebuild the knowledge base index."""
    from mimir.config import get_config, reset_config
    from mimir.indexing import index_with_progress
    from mimir.knowledge_graph import extract_code_relationships
    import json as _json

    reset_config()
    config = get_config(project_root=project_root)

    custom_patterns = list(config.exclude_patterns) if config.exclude_patterns else None

    try:
        success = index_with_progress(
            project_root=config.project_root,
            docs_dir=config.docs_dir,
            code_dirs=config.code_dirs,
            knowledge_dir=config.knowledge_dir,
            force_reindex=params.get("force", False),
            verbose=False,
            custom_exclude_patterns=custom_patterns,
        )
        if not success:
            return {"error": "Indexing failed", "status": "error"}

        # Extract knowledge graph
        knowledge_graph_dir = config.project_root / ".knowledge"
        knowledge_graph_dir.mkdir(parents=True, exist_ok=True)
        try:
            extractor = extract_code_relationships(
                config.project_root, from_index=True
            )
            stats = extractor.get_stats()
        except Exception:
            stats = {"total_relationships": 0, "total_entities": 0}

        return {
            "status": "ok",
            "message": f"Indexed {config.docs_dir}",
            "knowledge_graph": stats,
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_remove_file(params: dict, project_root: Path) -> dict:
    """Remove a file from the knowledge base index."""
    from mimir.config import get_config, reset_config
    from mimir.indexing import remove_file_from_index

    reset_config()
    config = get_config(project_root=project_root)

    file_path = params.get("file_path", "")
    if not file_path:
        return {"error": "Missing required parameter: file_path"}

    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = project_root / resolved

    try:
        success = remove_file_from_index(
            source_file=resolved,
            knowledge_dir=config.knowledge_dir,
            verbose=False,
        )
        if success:
            return {"status": "ok", "message": f"Removed {resolved} from index"}
        return {"error": f"File not found in index: {resolved}", "status": "not_found"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_stats(params: dict, project_root: Path) -> dict:
    """Get knowledge base statistics."""
    from mimir.config import get_config, reset_config

    reset_config()
    config = get_config(project_root=project_root)

    knowledge_dir = config.knowledge_dir
    has_index = (knowledge_dir / "index_store.json").exists()

    stats = {
        "project_root": str(config.project_root),
        "knowledge_dir": str(config.knowledge_dir),
        "docs_dir": str(config.docs_dir),
        "code_dirs": [str(d) for d in config.code_dirs],
        "has_index": has_index,
    }

    if has_index:
        try:
            from llama_index.core import StorageContext, load_index_from_storage

            storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
            index = load_index_from_storage(storage_context)
            stats["document_count"] = len(index.storage_context.docstore.docs)
        except Exception:
            stats["document_count"] = "unknown"

    total_source_files = 0
    if config.docs_dir.exists():
        total_source_files += len([f for f in config.docs_dir.rglob("*") if f.is_file()])
    for code_dir in config.code_dirs:
        if code_dir.exists():
            total_source_files += len([f for f in code_dir.rglob("*") if f.is_file()])
    stats["source_files"] = total_source_files

    return {"status": "ok", "stats": stats}


def handle_task_health(params: dict, project_root: Path) -> dict:
    """Check query router health."""
    from mimir.config import get_config, reset_config
    from mimir.query_router import RouterConfig

    reset_config()
    config = get_config(project_root=project_root)
    rc = RouterConfig.from_mimir_config(config)

    knowledge_dir = config.knowledge_dir
    has_index = (knowledge_dir / "index_store.json").exists()

    return {
        "status": "ok",
        "health": {
            "enabled": rc.enabled,
            "has_index": has_index,
            "project_root": str(config.project_root),
            "top_k": rc.top_k,
            "cache_maxsize": rc.cache_maxsize,
            "cache_similarity_threshold": rc.cache_similarity_threshold,
            "circuit_breaker_threshold": rc.circuit_breaker_threshold,
            "neural_classifier_enabled": rc.neural_classifier_enabled,
            "query_normalization_enabled": rc.query_normalization_enabled,
            "hybrid_confidence_min": rc.hybrid_confidence_min,
            "hybrid_confidence_max": rc.hybrid_confidence_max,
        },
    }


def handle_sdk_cache_get(params: dict, project_root: Path) -> dict:
    """Get SDK documentation from cache."""
    from mimir.sdk_cache import SDKCache

    library = params.get("library", "")
    topic = params.get("topic", "general")

    if not library:
        return {"error": "Missing required parameter: library"}

    try:
        cache = SDKCache(project_root)
        docs = cache.get(library, topic)
        if docs:
            return {"status": "ok", "library": library, "topic": topic, "docs": docs}
        return {
            "error": f"No docs found for {library}/{topic}",
            "status": "not_found",
            "suggestion": "Try a different topic or check the library name",
        }
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_sdk_cache_list(params: dict, project_root: Path) -> dict:
    """List cached SDK documentation."""
    from mimir.sdk_cache import SDKCache

    try:
        cache = SDKCache(project_root)
        cached = cache.list_cached()
        return {"status": "ok", "cached": cached}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_cache_stats(params: dict, project_root: Path) -> dict:
    """Get query cache statistics."""
    try:
        from mimir.query_cache import QueryCache

        cache = QueryCache(project_root)
        return {"status": "ok", "cache_stats": cache.stats()}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_cache_clear(params: dict, project_root: Path) -> dict:
    """Clear all cached query results."""
    try:
        from mimir.query_cache import QueryCache

        cache = QueryCache(project_root)
        count = cache.invalidate()
        return {"status": "ok", "message": f"Cleared {count} cached entries"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def handle_cache_cleanup(params: dict, project_root: Path) -> dict:
    """Remove expired cache entries."""
    try:
        from mimir.query_cache import QueryCache

        cache = QueryCache(project_root)
        count = cache.cleanup()
        return {"status": "ok", "message": f"Cleaned up {count} expired entries"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


# ─── LlamaIndex Setup ─────────────────────────────────────────────────────────


def _setup_llama_index(config) -> None:
    """Configure LlamaIndex with models from config."""
    from llama_index.core import Settings
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai import OpenAI as OpenAILike

    os.environ["OPENAI_API_KEY"] = config.api_key
    if config.api_base:
        os.environ["OPENAI_BASE_URL"] = config.api_base

    embed_kwargs = {
        "model": config.embedding_model,
        "api_key": config.api_key,
    }
    llm_kwargs = {"api_key": config.api_key}
    if config.api_base:
        embed_kwargs["api_base"] = config.api_base
        llm_kwargs["api_base"] = config.api_base

    Settings.embed_model = OpenAIEmbedding(**embed_kwargs)
    Settings.llm = OpenAILike(model=config.llm_model, **llm_kwargs)


# ─── Dispatch ─────────────────────────────────────────────────────────────────

HANDLERS = {
    "init": handle_init,
    "search": handle_search,
    "enrich_task": handle_enrich_task,
    "query": handle_query,
    "rag_workflow": handle_rag_workflow,
    "knowledge_agent": handle_knowledge_agent,
    "reindex": handle_reindex,
    "remove_file": handle_remove_file,
    "stats": handle_stats,
    "task_health": handle_task_health,
    "sdk_cache_get": handle_sdk_cache_get,
    "sdk_cache_list": handle_sdk_cache_list,
    "cache_stats": handle_cache_stats,
    "cache_clear": handle_cache_clear,
    "cache_cleanup": handle_cache_cleanup,
}


def main():
    # Read JSON from stdin
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            _output({"error": "Empty input. Expected JSON on stdin.", "status": "error"})
            sys.exit(1)
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        _output({"error": f"Invalid JSON: {e}", "status": "error"})
        sys.exit(1)

    action = request.get("action", "")
    params = request.get("params", {})

    # Allow --project-root CLI override (highest priority)
    cli_override = None
    if "--project-root" in sys.argv:
        idx = sys.argv.index("--project-root")
        if idx + 1 < len(sys.argv):
            cli_override = sys.argv[idx + 1]

    if not action:
        _output({"error": "Missing required field: action", "status": "error"})
        sys.exit(1)

    if action not in HANDLERS:
        _output({
            "error": f"Unknown action: {action}",
            "status": "error",
            "available_actions": sorted(HANDLERS.keys()),
        })
        sys.exit(1)

    # Resolve project root
    project_root = resolve_project_root(cli_override=cli_override)

    # Execute handler
    start = time.time()
    try:
        result = HANDLERS[action](params, project_root)
        elapsed_ms = int((time.time() - start) * 1000)
        result["_meta"] = {
            "action": action,
            "elapsed_ms": elapsed_ms,
            "project_root": str(project_root),
        }
        _output(result)
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        _output({
            "error": str(e),
            "status": "error",
            "traceback": traceback.format_exc(),
            "_meta": {
                "action": action,
                "elapsed_ms": elapsed_ms,
                "project_root": str(project_root),
            },
        })
        sys.exit(1)


def _output(data: dict) -> None:
    """Write JSON to stdout."""
    json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
