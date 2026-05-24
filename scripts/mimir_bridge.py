#!/usr/bin/env python3
"""
Mimir - Unified CLI and jcode bridge.

Two modes:
1. JSON bridge mode: jcode subprocess (JSON piped to stdin, JSON returned on stdout)
2. CLI mode: `mimir init`, `mimir index`, `mimir search "query"`, etc.

In JSON mode, expects: {"action": "...", "params": {...}}
Returns: JSON response
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Mimir root directory (parent of scripts/)
MIMIR_ROOT = Path(__file__).resolve().parent.parent
src_path = str(MIMIR_ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# ─── JSON Protocol Handler (for jcode integration) ──────────────

def handle_json_protocol() -> bool:
    """Handle JSON protocol for jcode integration (stdin → stdout JSON).
    
    Returns:
        True if JSON was processed (exit the script)
        False if not in JSON mode (continue to CLI mode)
    """
    # Check if stdin has data available (not a terminal AND has piped data)
    if sys.stdin.isatty():
        return False  # Not in JSON mode
    
    # For non-tty stdin, try to read with timeout
    try:
        # Use select to check if stdin has data (Unix/macOS)
        import select
        if select.select([sys.stdin], [], [], 0.1)[0]:
            stdin_data = sys.stdin.read().strip()
            if not stdin_data:
                return False
        else:
            return False
    except (ImportError, AttributeError):
        # Fallback: just try to read (may block on some systems)
        import time
        time.sleep(0.1)
        if sys.stdin.isatty():
            return False
        stdin_data = sys.stdin.read().strip()
        if not stdin_data:
            return False
    
    try:
        data = json.loads(stdin_data)
        action = data.get("action", "")
        params = data.get("params", {})
        
        # JSON protocol handlers
        from mimir.config import MimirConfig
        
        def get_project_root():
            """Get project root from params or auto-detect."""
            if isinstance(params, dict) and "project_root" in params:
                return Path(params["project_root"])
            return Path.cwd()
        
        project_root = get_project_root()
        
        if action == "enrich_task":
            from mimir.query_router import route_task
            task = params.get("task", "") if isinstance(params, dict) else ""
            result = route_task(task, project_root=project_root)
            print(json.dumps({
                "status": "ok" if result.success else "error",
                "context": result.context,
                "results": [{"source": r.source, "score": r.score, "text": r.text} for r in result.results],
                "cache_hit": result.cache_hit,
                "elapsed_ms": result.elapsed_ms,
            }))
            return True
            
        elif action == "search":
            from mimir.server import KnowledgeServer
            config = MimirConfig.load(project_root=project_root)
            query = params.get("query", "") if isinstance(params, dict) else ""
            server = KnowledgeServer(config)
            results = server.search(query)
            print(json.dumps({"status": "ok", "results": results}))
            return True
            
        elif action == "query":
            from mimir.config import get_config, reset_config
            reset_config()
            config = get_config(project_root=project_root)
            question = params.get("question", "") if isinstance(params, dict) else ""
            if not question:
                print(json.dumps({"error": "Missing required parameter: question"}))
                return True
            try:
                from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage
                knowledge_dir = config.knowledge_dir
                if not (knowledge_dir / "index_store.json").exists():
                    print(json.dumps({"error": "No knowledge base found. Run reindex first.", "status": "no_index"}))
                    return True
                storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
                index = load_index_from_storage(storage_context)
                query_engine = index.as_query_engine()
                response = query_engine.query(question)
                print(json.dumps({"status": "ok", "answer": str(response)}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "rag_workflow":
            try:
                from langchain_core.messages import HumanMessage
                from langgraph.workflows.rag import graph as rag_graph
                query = params.get("query", "") if isinstance(params, dict) else ""
                response_shape = params.get("response_shape") if isinstance(params, dict) else None
                import asyncio
                async def _run():
                    config = {"configurable": {"thread_id": "bridge-rag"}}
                    result = await rag_graph.ainvoke(
                        {"messages": [HumanMessage(content=query)], "response_shape": response_shape},
                        config,
                    )
                    return result["messages"][-1].content
                answer = asyncio.run(_run())
                print(json.dumps({"status": "ok", "answer": answer}))
            except ImportError as e:
                print(json.dumps({"error": f"LangGraph not available: {e}", "status": "import_error"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "knowledge_agent":
            try:
                from langchain_core.messages import HumanMessage
                from langgraph.workflows.knowledge_agent import graph as agent_graph
                question = params.get("question", "") if isinstance(params, dict) else ""
                if not question:
                    print(json.dumps({"error": "Missing required parameter: question"}))
                    return True
                import asyncio
                async def _run():
                    config = {"configurable": {"thread_id": "bridge-agent"}}
                    result = await agent_graph.ainvoke(
                        {"messages": [HumanMessage(content=question)]}, config
                    )
                    return result["messages"][-1].content
                answer = asyncio.run(_run())
                print(json.dumps({"status": "ok", "answer": answer}))
            except ImportError as e:
                print(json.dumps({"error": f"LangGraph not available: {e}", "status": "import_error"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "reindex":
            from mimir.config import get_config, reset_config
            from mimir.indexing import index_with_progress
            reset_config()
            config = get_config(project_root=project_root)
            custom_patterns = list(config.exclude_patterns) if config.exclude_patterns else None
            try:
                success = index_with_progress(
                    project_root=config.project_root,
                    docs_dir=config.docs_dir,
                    code_dirs=config.code_dirs,
                    knowledge_dir=config.knowledge_dir,
                    force_reindex=params.get("force", False) if isinstance(params, dict) else False,
                    verbose=False,
                    custom_exclude_patterns=custom_patterns,
                )
                if success:
                    print(json.dumps({"status": "ok", "message": "Index rebuilt successfully"}))
                else:
                    print(json.dumps({"error": "Indexing failed", "status": "error"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "remove_file":
            from mimir.config import get_config, reset_config
            from mimir.indexing import remove_file_from_index
            reset_config()
            config = get_config(project_root=project_root)
            file_path = params.get("file_path", "") if isinstance(params, dict) else ""
            if not file_path:
                print(json.dumps({"error": "Missing required parameter: file_path"}))
                return True
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
                    print(json.dumps({"status": "ok", "message": f"Removed {resolved} from index"}))
                else:
                    print(json.dumps({"error": f"File not found in index: {resolved}", "status": "not_found"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "stats":
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
            # Try to get document count if index exists (may fail without API keys)
            if has_index:
                try:
                    from llama_index.core import StorageContext, load_index_from_storage
                    storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
                    index = load_index_from_storage(storage_context)
                    stats["document_count"] = len(index.storage_context.docstore.docs)
                except Exception:
                    stats["document_count"] = "unknown (API key required)"
            total_source_files = 0
            if config.docs_dir.exists():
                total_source_files += len([f for f in config.docs_dir.rglob("*") if f.is_file()])
            for code_dir in config.code_dirs:
                if code_dir.exists():
                    total_source_files += len([f for f in code_dir.rglob("*") if f.is_file()])
            stats["source_files"] = total_source_files
            print(json.dumps({"status": "ok", "stats": stats}))
            return True
            
        elif action == "task_health":
            from mimir.config import get_config, reset_config
            from mimir.query_router import RouterConfig
            reset_config()
            config = get_config(project_root=project_root)
            rc = RouterConfig.from_mimir_config(config)
            knowledge_dir = config.knowledge_dir
            has_index = (knowledge_dir / "index_store.json").exists()
            print(json.dumps({
                "status": "ok",
                "health": {
                    "enabled": rc.enabled,
                    "has_index": has_index,
                    "project_root": str(config.project_root),
                    "top_k": rc.top_k,
                    "cache_maxsize": rc.cache_maxsize,
                    "circuit_breaker_threshold": rc.circuit_breaker_threshold,
                    "neural_classifier_enabled": rc.neural_classifier_enabled,
                },
            }))
            return True
            
        elif action == "sdk_cache_get":
            from mimir.sdk_cache import SDKCache
            library = params.get("library", "") if isinstance(params, dict) else ""
            topic = params.get("topic", "general") if isinstance(params, dict) else "general"
            if not library:
                print(json.dumps({"error": "Missing required parameter: library"}))
                return True
            try:
                cache = SDKCache(project_root)
                docs = cache.get(library, topic)
                if docs:
                    print(json.dumps({"status": "ok", "library": library, "topic": topic, "docs": docs}))
                else:
                    print(json.dumps({
                        "error": f"No docs found for {library}/{topic}",
                        "status": "not_found",
                        "suggestion": "Try a different topic or check the library name",
                    }))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "sdk_cache_list":
            from mimir.sdk_cache import SDKCache
            try:
                cache = SDKCache(project_root)
                cached = cache.list_cached()
                print(json.dumps({"status": "ok", "cached": cached}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "cache_stats":
            try:
                from mimir.query_cache import QueryCache
                cache = QueryCache(project_root)
                print(json.dumps({"status": "ok", "cache_stats": cache.stats()}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "cache_clear":
            try:
                from mimir.query_cache import QueryCache
                cache = QueryCache(project_root)
                count = cache.invalidate()
                print(json.dumps({"status": "ok", "message": f"Cleared {count} cached entries"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        elif action == "cache_cleanup":
            try:
                from mimir.query_cache import QueryCache
                cache = QueryCache(project_root)
                count = cache.cleanup()
                print(json.dumps({"status": "ok", "message": f"Cleaned up {count} expired entries"}))
            except Exception as e:
                print(json.dumps({"error": str(e), "status": "error"}))
            return True
            
        else:
            print(json.dumps({"error": f"Unknown action: {action}", "available_actions": ["enrich_task", "search", "query", "rag_workflow", "knowledge_agent", "reindex", "remove_file", "stats", "task_health", "sdk_cache_get", "sdk_cache_list", "cache_stats", "cache_clear", "cache_cleanup"]}))
            return True
            
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return True


# ─── CLI Command Handlers ───────────────────────────────────

def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a project for Mimir."""
    from mimir.config import MimirConfig
    
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    print(f"\n🎯 Initializing Mimir for project: {project_root}")
    
    # Create .mimir/config.json
    mimir_dir = project_root / ".mimir"
    mimir_dir.mkdir(exist_ok=True)
    
    config = {
        "docs_dir": "docs",
        "knowledge_dir": ".knowledge/llamaindex",
        "embedding_model": "text-embedding-3-small",
    }
    
    if args.code_dirs:
        config["code_dirs"] = [d.strip() for d in args.code_dirs.split(",")]
    
    config_path = mimir_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"   ✓ Created: {config_path}")
    
    # Create necessary directories
    docs_dir = project_root / "docs"
    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    
    for d in [docs_dir, knowledge_dir]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ Created: {d}")
    
    print(f"\n✅ Project initialized successfully!")
    print(f"\nNext steps:")
    print(f"  1. Run: mimir index")
    print(f"  2. Run: mimir health")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Global install (deprecated)."""
    print("Warning: Global install is deprecated. Mimir now uses native jcode tool.")
    return 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall (deprecated)."""
    print("Warning: Uninstall is deprecated.")
    return 1


def cmd_server(args: argparse.Namespace) -> int:
    """MCP server (deprecated)."""
    print("MCP server is no longer supported.")
    print("Mimir now uses a native jcode tool via mimir_bridge.py.")
    return 1


def cmd_index(args: argparse.Namespace) -> int:
    """Index the project knowledge base."""
    from mimir.config import get_config, reset_config
    from mimir.indexing import index_with_progress
    
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    print(f"\n📚 Indexing project: {project_root}")
    
    try:
        reset_config()
        config = get_config(project_root=project_root)
        custom_patterns = list(config.exclude_patterns) if config.exclude_patterns else None
        
        force_reindex = args.reindex if hasattr(args, 'reindex') else False
        
        success = index_with_progress(
            project_root=config.project_root,
            docs_dir=config.docs_dir,
            code_dirs=config.code_dirs,
            knowledge_dir=config.knowledge_dir,
            force_reindex=force_reindex,
            verbose=True,
            custom_exclude_patterns=custom_patterns,
        )
        
        if success:
            print(f"\n✅ Index rebuilt successfully")
            return 0
        else:
            print(f"\n❌ Indexing failed")
            return 1
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        return 1


def cmd_search(args: argparse.Namespace) -> int:
    """Search the knowledge base."""
    from mimir.config import MimirConfig
    from mimir.server import KnowledgeServer
    
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    query = args.query
    top_k = args.top_k
    
    try:
        config = MimirConfig.load(project_root=project_root)
        server = KnowledgeServer(config)
        results = server.search(query, top_k=top_k)
        
        if not results:
            print("No results found.")
            return 0
        
        print(f"\n🔍 Search results for: {query}")
        print("=" * 60)
        for i, r in enumerate(results, 1):
            source = r.get("source", "?")
            score = r.get("score", 0)
            text = r.get("text", "")
            print(f"\n[{i}] {source} (score: {score:.3f})")
            print(f"{text[:200]}..." if len(text) > 200 else text)
        
        return 0
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return 1


def cmd_stats(args: argparse.Namespace) -> int:
    """Show index statistics."""
    from mimir.config import get_config, reset_config
    
    try:
        reset_config()
        config = get_config()
        knowledge_dir = config.knowledge_dir
        has_index = (knowledge_dir / "index_store.json").exists()
        
        stats = {
            "project_root": str(config.project_root),
            "knowledge_dir": str(config.knowledge_dir),
            "docs_dir": str(config.docs_dir),
            "code_dirs": [str(d) for d in config.code_dirs],
            "has_index": has_index,
        }
        
        # Get document count if index exists
        if has_index:
            try:
                from llama_index.core import StorageContext, load_index_from_storage
                storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
                index = load_index_from_storage(storage_context)
                stats["document_count"] = len(index.storage_context.docstore.docs)
            except Exception:
                stats["document_count"] = "unknown (API key required)"
        
        # Count source files
        total_source_files = 0
        if config.docs_dir.exists():
            total_source_files += len([f for f in config.docs_dir.rglob("*") if f.is_file()])
        for code_dir in config.code_dirs:
            if code_dir.exists():
                total_source_files += len([f for f in code_dir.rglob("*") if f.is_file()])
        stats["source_files"] = total_source_files
        
        print("\n📊 Index Statistics:")
        print("=" * 60)
        for key, value in stats.items():
            if isinstance(value, list):
                print(f"{key}: {', '.join(value)}")
            else:
                print(f"{key}: {value}")
        
        return 0
    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """List indexed files and optionally compare with git-tracked files."""
    try:
        from mimir.config import get_config, reset_config
        
        reset_config()
        config = get_config()
        knowledge_dir = config.knowledge_dir
        project_root = config.project_root
        
        # Check if index exists
        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No knowledge base found")
            print(f"   Expected: {knowledge_dir}")
            print("\n   Run: mimir index")
            return 1
        
        # If --git-tracked flag, show comparison
        if args.git_tracked:
            return _list_with_git_comparison(knowledge_dir, project_root)
        
        # Otherwise, show standard list
        # Load manifest
        manifest_path = knowledge_dir / "manifest.json"
        if not manifest_path.exists():
            print("\n❌ No manifest found")
            print(f"   Expected: {manifest_path}")
            return 1
        
        manifest = json.loads(manifest_path.read_text())
        
        print(f"\n📚 Indexed files in {project_root}")
        print("=" * 60)
        
        total_files = 0
        for dir_path, dir_info in manifest.get("indexed_directories", {}).items():
            files = dir_info.get("files", [])
            total_files += len(files)
            print(f"\n{dir_path} ({len(files)} files):")
            for f in files[:10]:  # Show first 10
                print(f"  {f}")
            if len(files) > 10:
                print(f"  ... and {len(files) - 10} more")
        
        print(f"\nTotal indexed files: {total_files}")
        return 0
        
    except Exception as e:
        print(f"Error listing files: {e}")
        return 1


def _list_with_git_comparison(knowledge_dir: Path, project_root: Path) -> int:
    """Show comparison between indexed files and git-tracked files."""
    import subprocess
    
    # Check if we're in a git repository
    git_dir = project_root / ".git"
    if not git_dir.exists():
        print("\n⚠️  Not a git repository")
        print("   Showing indexed files only:\n")
        return cmd_list(argparse.Namespace(git_tracked=False))
    
    # Load manifest
    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        print("\n❌ No manifest found")
        print(f"   Expected: {manifest_path}")
        return 1
    
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"\n❌ Error reading manifest: {e}")
        return 1
    
    # Get indexed files (relative paths)
    indexed_files = set()
    for dir_info in manifest.get("indexed_directories", {}).values():
        for file_path in dir_info.get("files", []):
            try:
                rel_path = Path(file_path).relative_to(project_root)
                indexed_files.add(str(rel_path))
            except ValueError:
                # File is outside project root, use absolute path
                indexed_files.add(file_path)
    
    # Get git-tracked files
    git_files = set()
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            git_files = (
                set(result.stdout.strip().split("\n"))
                if result.stdout.strip()
                else set()
            )
    except (
        subprocess.TimeoutExpired,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):
        print("\n⚠️  Git command failed")
        print("   Showing indexed files only:\n")
        return cmd_list(argparse.Namespace(git_tracked=False))
    
    # Calculate differences
    indexed_and_tracked = indexed_files & git_files
    indexed_not_tracked = indexed_files - git_files
    tracked_not_indexed = git_files - indexed_files
    
    # Print results
    print("\n" + "=" * 60)
    print("📚 INDEXED vs GIT-TRACKED FILES")
    print("=" * 60)
    
    # Indexed and tracked
    if indexed_and_tracked:
        print(f"\n✓ Indexed ({len(indexed_and_tracked)} files):")
        for f in sorted(indexed_and_tracked)[:20]:
            print(f"   {f}")
        if len(indexed_and_tracked) > 20:
            print(f"   ... and {len(indexed_and_tracked) - 20} more files")
    
    # Indexed but not tracked
    if indexed_not_tracked:
        print(f"\n✓ Indexed (not in git) ({len(indexed_not_tracked)} files):")
        for f in sorted(indexed_not_tracked)[:10]:
            print(f"   {f}")
        if len(indexed_not_tracked) > 10:
            print(f"   ... and {len(indexed_not_tracked) - 10} more files")
    
    # Tracked but not indexed
    if tracked_not_indexed:
        print(f"\n✗ Not indexed ({len(tracked_not_indexed)} files):")
        for f in sorted(tracked_not_indexed)[:30]:
            print(f"   {f}")
        if len(tracked_not_indexed) > 30:
            print(f"   ... and {len(tracked_not_indexed) - 30} more files")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Indexed: {len(indexed_files)} files")
    print(f"   Git-tracked: {len(git_files)} files")
    print(f"   Indexed & tracked: {len(indexed_and_tracked)} files")
    print(f"   Not indexed: {len(tracked_not_indexed)} files")
    print("=" * 60 + "\n")
    
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Check Mimir health and configuration."""
    try:
        from mimir.config import get_config, reset_config
        
        reset_config()
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
        
        status = "healthy" if (has_index and config.api_key) else "degraded"
        
        print(f"Status:         {status}")
        print(f"Project root:   {config.project_root}")
        print(f"Mimir root:     {config.mimir_root}")
        print(f"API key:        {'configured' if config.api_key else 'MISSING'}")
        print(f"Embedding:      {config.embedding_model}")
        print(f"LLM:            {config.llm_model}")
        print(f"Index:          {'exists' if has_index else 'NOT FOUND'}")
        if index_timestamp:
            print(f"Index updated:  {index_timestamp}")
        print(f"Docs dir:       {config.docs_dir}")
        print(f"Knowledge dir:  {config.knowledge_dir}")
        if config.code_dirs:
            print(f"Code dirs:      {', '.join(str(d) for d in config.code_dirs)}")
        if config.shared_indexes:
            print(f"Shared indices: {', '.join(config.shared_indexes.keys())}")
        
        if warnings:
            print("\nWarnings:")
            for w in warnings:
                print(f"  ⚠️  {w}")
        else:
            print("\n✅ No warnings")
        
        return 0 if status == "healthy" else 1
        
    except Exception as e:
        print(f"Error checking health: {e}")
        return 1


def cmd_rag(args: argparse.Namespace) -> int:
    """Run RAG workflow."""
    try:
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.rag import graph as rag_graph
        import asyncio
        
        query = args.query
        
        async def _run():
            config = {"configurable": {"thread_id": "cli-rag"}}
            result = await rag_graph.ainvoke(
                {"messages": [HumanMessage(content=query)], "response_shape": None},
                config,
            )
            return result["messages"][-1].content
        
        answer = asyncio.run(_run())
        print(answer)
        return 0
    except ImportError as e:
        print(f"Error: LangGraph not available: {e}")
        return 1
    except Exception as e:
        print(f"Error running RAG workflow: {e}")
        return 1


def cmd_agent(args: argparse.Namespace) -> int:
    """Run knowledge agent."""
    try:
        from langchain_core.messages import HumanMessage
        from langgraph.workflows.knowledge_agent import graph as agent_graph
        import asyncio
        
        query = args.query
        
        async def _run():
            config = {"configurable": {"thread_id": "cli-agent"}}
            result = await agent_graph.ainvoke(
                {"messages": [HumanMessage(content=query)]},
                config,
            )
            return result["messages"][-1].content
        
        answer = asyncio.run(_run())
        print(answer)
        return 0
    except ImportError as e:
        print(f"Error: LangGraph not available: {e}")
        return 1
    except Exception as e:
        print(f"Error running knowledge agent: {e}")
        return 1


def cmd_prep(args: argparse.Namespace) -> int:
    """Generate customer call briefing."""
    try:
        from langgraph.workflows.call_prep import generate_briefing
        import asyncio
        
        topic = args.topic
        customer = args.customer
        
        async def _run():
            return await generate_briefing(topic, customer)
        
        briefing = asyncio.run(_run())
        print(briefing)
        return 0
    except ImportError as e:
        print(f"Error: LangGraph not available: {e}")
        return 1
    except Exception as e:
        print(f"Error generating briefing: {e}")
        return 1


def cmd_diff(args: argparse.Namespace) -> int:
    """Session diff."""
    try:
        from langgraph.workflows.session_diff import get_session_diff
        import asyncio
        
        days = args.days
        
        async def _run():
            return await get_session_diff(days)
        
        diff = asyncio.run(_run())
        print(diff)
        return 0
    except ImportError as e:
        print(f"Error: LangGraph not available: {e}")
        return 1
    except Exception as e:
        print(f"Error getting session diff: {e}")
        return 1


def cmd_metrics(args: argparse.Namespace) -> int:
    """Cost and usage metrics."""
    try:
        from mimir.metrics import get_metrics
        
        days = args.days
        metrics = get_metrics(days)
        
        print("\n📊 Metrics Report:")
        print("=" * 60)
        print(f"Period: Last {days} days")
        print(f"Total cost: ${metrics.get('total_cost', 0):.2f}")
        print(f"Total tokens: {metrics.get('total_tokens', 0)}")
        print(f"Total queries: {metrics.get('total_queries', 0)}")
        return 0
    except Exception as e:
        print(f"Error getting metrics: {e}")
        return 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run eval harness."""
    import json
    from pathlib import Path
    
    eval_file = Path(args.eval_file)
    if not eval_file.exists():
        # Try relative to Mimir root
        eval_file = MIMIR_ROOT / args.eval_file
        if not eval_file.exists():
            print(f"Error: Eval file not found: {args.eval_file}")
            return 1
    
    try:
        with open(eval_file) as f:
            questions = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {eval_file}: {e}")
        return 1
    
    # Filter by question ID if specified
    if args.question_id:
        questions = [q for q in questions if q.get("id") == args.question_id]
        if not questions:
            print(f"Error: No question found with ID: {args.question_id}")
            return 1
    
    results = []
    total_tokens = {"prompt": 0, "completion": 0, "total": 0}
    
    for q in questions:
        q_id = q.get("id", "unknown")
        question = q.get("question", "")
        expected_artifact = q.get("expected_artifact")
        response_shape = q.get("response_shape")
        
        print(f"\n{'=' * 60}")
        print(f"Running eval: {q_id}")
        print(f"Question: {question}")
        print(f"{'=' * 60}")
        
        result = {
            "id": q_id,
            "question": question,
            "success": False,
            "answer": None,
        }
        
        # Try RAG workflow
        try:
            from langchain_core.messages import HumanMessage
            from langgraph.workflows.rag import graph as rag_graph
            import asyncio
            
            async def _run():
                config = {"configurable": {"thread_id": f"eval-{q_id}"}}
                return await rag_graph.ainvoke(
                    {
                        "messages": [HumanMessage(content=question)],
                        "response_shape": response_shape,
                    },
                    config,
                )
            
            rag_result = asyncio.run(_run())
            answer = rag_result["messages"][-1].content
            result["answer"] = answer
            result["success"] = True
            
            # Extract token usage
            token_usage = rag_result.get("token_usage", {})
            if token_usage:
                total_tokens["prompt"] += token_usage.get("prompt_tokens", 0)
                total_tokens["completion"] += token_usage.get("completion_tokens", 0)
                total_tokens["total"] += token_usage.get("total_tokens", 0)
            
            print(f"✓ RAG workflow completed")
        except Exception as e:
            print(f"✗ RAG workflow failed: {e}")
        
        results.append(result)
    
    # Print summary
    print(f"\n{'=' * 60}")
    print("Eval Results Summary")
    print(f"{'=' * 60}")
    print(f"Total questions: {len(results)}")
    success_count = sum(1 for r in results if r["success"])
    print(f"Successful: {success_count} ({success_count/len(results)*100:.0f}%)" if results else "N/A")
    
    if total_tokens["total"] > 0:
        print(f"\nTotal token usage:")
        print(f"  Prompt: {total_tokens['prompt']}")
        print(f"  Completion: {total_tokens['completion']}")
        print(f"  Total: {total_tokens['total']}")
    
    # Save results if output specified
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    return 0


def cmd_projects(args: argparse.Namespace) -> int:
    """Multi-project management."""
    try:
        from mimir.projects import ProjectManager
        
        manager = ProjectManager()
        
        if args.projects_action == "list":
            projects = manager.list_projects()
            if not projects:
                print("No projects registered.")
                return 0
            print("\n📁 Registered Projects:")
            print("=" * 60)
            for name, info in projects.items():
                print(f"\n{name}:")
                print(f"  Path: {info.get('path', '?')}")
                print(f"  Description: {info.get('description', 'No description')}")
                print(f"  Last indexed: {info.get('last_indexed', 'Never')}")
            return 0
        elif args.projects_action == "add":
            path = args.path
            name = args.name or Path(path).name
            description = args.description or ""
            success = manager.add_project(name, path, description)
            if success:
                print(f"✅ Added project: {name} ({path})")
                return 0
            else:
                print(f"❌ Failed to add project: {name}")
                return 1
        elif args.projects_action == "remove":
            success = manager.remove_project(args.name)
            if success:
                print(f"✅ Removed project: {args.name}")
                return 0
            else:
                print(f"❌ Project not found: {args.name}")
                return 1
        elif args.projects_action == "switch":
            success = manager.switch_project(args.name)
            if success:
                print(f"✅ Switched to project: {args.name}")
                return 0
            else:
                print(f"❌ Project not found: {args.name}")
                return 1
        elif args.projects_action == "status":
            status = manager.get_status()
            print("\n📊 Project Status:")
            print("=" * 60)
            for name, info in status.items():
                print(f"\n{name}:")
                print(f"  Path: {info.get('path', '?')}")
                print(f"  Indexed: {'Yes' if info.get('has_index') else 'No'}")
                print(f"  Last indexed: {info.get('last_indexed', 'Never')}")
            return 0
        elif args.projects_action == "discover":
            found = manager.discover_projects()
            if not found:
                print("No projects found in common locations.")
                return 0
            print("\n🔍 Found Projects:")
            print("=" * 60)
            for path in found:
                print(f"  {path}")
            return 0
        else:
            print(f"Unknown projects action: {args.projects_action}")
            return 1
    except Exception as e:
        print(f"Error managing projects: {e}")
        return 1


def cmd_handoff(args: argparse.Namespace) -> int:
    """Generate handoff documentation."""
    try:
        from mimir.handoff import generate_handoff
        
        project = args.project
        summary = args.summary
        customer = args.customer
        output = args.output or "HANDOFF.md"
        
        handoff_content = generate_handoff(project, summary, customer)
        
        with open(output, "w") as f:
            f.write(handoff_content)
        
        print(f"✅ Handoff document generated: {output}")
        return 0
    except Exception as e:
        print(f"Error generating handoff: {e}")
        return 1


def cmd_cache(args: argparse.Namespace) -> int:
    """SDK documentation cache management."""
    try:
        from mimir.sdk_cache import SDKCache
        
        project_root = Path.cwd()
        cache = SDKCache(project_root)
        
        if args.cache_action == "list":
            cached = cache.list_cached()
            if not cached:
                print("No cached SDKs.")
                return 0
            print("\n📚 Cached SDKs:")
            print("=" * 60)
            for entry in cached:
                library = entry.get("library", "?")
                fresh = entry.get("fresh", False)
                topics = entry.get("topics", [])
                print(f"  {library} ({'fresh' if fresh else 'stale'})")
                if topics:
                    print(f"    Topics: {', '.join(topics)}")
            return 0
        elif args.cache_action == "get":
            library = args.library
            topic = args.topic or "general"
            docs = cache.get(library, topic)
            if docs:
                print(f"\n📖 {library}/{topic}:\n")
                print(docs)
                return 0
            else:
                print(f"❌ No docs found for {library}/{topic}")
                return 1
        elif args.cache_action == "refresh":
            library = args.library
            topic = args.topic or "general"
            docs = cache.get(library, topic, force_refresh=True)
            if docs:
                print(f"✅ Refreshed {library}/{topic}")
                return 0
            else:
                print(f"❌ Failed to refresh {library}/{topic}")
                return 1
        elif args.cache_action == "invalidate":
            library = args.library
            success = cache.invalidate(library)
            if success:
                print(f"✅ Invalidated {library}")
                return 0
            else:
                print(f"❌ Failed to invalidate {library}")
                return 1
        else:
            print(f"Unknown cache action: {args.cache_action}")
            return 1
    except Exception as e:
        print(f"Error managing cache: {e}")
        return 1


# ─── Main ───────────────────────────────────────────────────────

def main():
    """Main entry point - handles both CLI and JSON modes."""
    # Try JSON protocol first (jcode integration)
    if handle_json_protocol():
        return 0
    
    # Otherwise, CLI mode
    parser = argparse.ArgumentParser(
        prog="mimir",
        description="Mimir - Persistent knowledge base for AI agents. Gives your AI assistants memory across sessions by indexing your project's documentation and code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Setup
  mimir init                             Initialize current project
  mimir init --code-dirs=src,tests       Init with source directories

  # Indexing
  mimir index                            Index project documents
  mimir index --reindex                  Rebuild index from scratch
  mimir list                             List all indexed files
  mimir list --git-tracked               Compare indexed vs git-tracked files

  # Search & Analysis
  mimir search "how does auth work?"     Semantic search across indexed content
  mimir rag "explain the database"       RAG workflow with structured reasoning
  mimir stats                            Show index statistics
  mimir health                           Check configuration and status

  # Multi-Project
  mimir projects list                    List registered projects
  mimir projects add ~/Projects/acme    Register a project

  # SDK Cache
  mimir cache list                       List cached SDKs
  mimir cache get stripe                 Fetch Stripe API docs""",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # ── init ──
    p = subparsers.add_parser("init", help="Initialize a project for Mimir")
    p.add_argument("--code-dirs", help="Comma-separated list of code directories")
    p.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # ── install ──
    p = subparsers.add_parser("install", help="Global install (deprecated)")
    p.add_argument("--force", action="store_true", help="Force install")
    
    # ── uninstall ──
    subparsers.add_parser("uninstall", help="Uninstall (deprecated)")
    
    # ── server ── (deprecated)
    p = subparsers.add_parser("server", help="MCP server (deprecated)")
    
    # ── index ──
    p = subparsers.add_parser("index", help="Index project documents")
    p.add_argument("--reindex", action="store_true", help="Force full reindex")
    p.add_argument("--add", help="Add a directory to the index")
    p.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # ── search ──
    p = subparsers.add_parser("search", help="Search the knowledge base")
    p.add_argument("query", help="Search query")
    p.add_argument("--top-k", type=int, default=5, help="Number of results")
    p.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # ── stats ──
    subparsers.add_parser("stats", help="Show index statistics")
    
    # ── list ──
    p = subparsers.add_parser("list", help="List indexed files")
    p.add_argument("--git-tracked", action="store_true", help="Compare with git-tracked files")
    
    # ── health ──
    p = subparsers.add_parser("health", help="Check Mimir health")
    p.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # ── rag ──
    p = subparsers.add_parser("rag", help="RAG workflow")
    p.add_argument("query", help="Question to answer")
    
    # ── agent ──
    p = subparsers.add_parser("agent", help="Knowledge agent")
    p.add_argument("query", help="Research question")
    
    # ── prep ──
    p = subparsers.add_parser("prep", help="Generate customer call briefing")
    p.add_argument("topic", help="Call topic")
    p.add_argument("--customer", help="Customer name")
    
    # ── diff ──
    p = subparsers.add_parser("diff", help="Session diff")
    p.add_argument("--days", type=int, default=1, help="Number of days to look back")
    
    # ── metrics ──
    p = subparsers.add_parser("metrics", help="Cost and usage metrics")
    p.add_argument("--days", type=int, default=30, help="Number of days to include")
    
    # ── evaluate ──
    p = subparsers.add_parser("evaluate", help="Run eval harness")
    p.add_argument("--eval-file", default="evals/questions.json", help="Eval file path")
    p.add_argument("--question-id", help="Run specific question by ID")
    p.add_argument("--output", help="Output file for results")
    
    # ── projects ──
    p = subparsers.add_parser("projects", help="Multi-project management")
    psp = p.add_subparsers(dest="projects_action", help="Project command")
    psp.add_parser("list", help="List projects")
    pa = psp.add_parser("add", help="Add project")
    pa.add_argument("path", help="Project path")
    pa.add_argument("--name", help="Project name")
    pa.add_argument("--description", help="Project description")
    pr = psp.add_parser("remove", help="Remove project")
    pr.add_argument("name", help="Project name")
    ps = psp.add_parser("switch", help="Switch project")
    ps.add_argument("name", help="Project name")
    psp.add_parser("status", help="Project status")
    psp.add_parser("discover", help="Discover projects")
    
    # ── handoff ──
    p = subparsers.add_parser("handoff", help="Generate handoff document")
    p.add_argument("--project", help="Project name")
    p.add_argument("--summary", help="Engagement summary")
    p.add_argument("--customer", help="Customer name")
    p.add_argument("--output", help="Output file path")
    
    # ── cache ──
    p = subparsers.add_parser("cache", help="SDK cache management")
    csp = p.add_subparsers(dest="cache_action", help="Cache command")
    csp.add_parser("list", help="List cached SDKs")
    cg = csp.add_parser("get", help="Get SDK docs")
    cg.add_argument("library", help="Library name")
    cg.add_argument("--topic", default="general", help="Documentation topic")
    cr = csp.add_parser("refresh", help="Refresh cached docs")
    cr.add_argument("library", help="Library name")
    cr.add_argument("--topic", default="general", help="Documentation topic")
    ci = csp.add_parser("invalidate", help="Invalidate cached docs")
    ci.add_argument("library", help="Library name")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Dispatch to command handler
    handlers = {
        "init": cmd_init,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "server": cmd_server,
        "index": cmd_index,
        "search": cmd_search,
        "stats": cmd_stats,
        "list": cmd_list,
        "health": cmd_health,
        "rag": cmd_rag,
        "agent": cmd_agent,
        "prep": cmd_prep,
        "diff": cmd_diff,
        "metrics": cmd_metrics,
        "evaluate": cmd_evaluate,
        "projects": cmd_projects,
        "handoff": cmd_handoff,
        "cache": cmd_cache,
    }
    
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"❌ Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
