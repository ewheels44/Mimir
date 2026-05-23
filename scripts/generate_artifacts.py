#!/usr/bin/env python3
"""Generate pre-compiled artifacts for Mimir.

This script analyzes Mimir's source code to generate structured artifacts
that can be served directly to queries, inspired by Pinecone Nexus's
pre-compiled knowledge approach.

Usage:
    python scripts/generate_artifacts.py --all
    python scripts/generate_artifacts.py --artifact rag_architecture
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure src directory is in path
SCRIPT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = SCRIPT_DIR / "src"

# Add both SCRIPT_DIR and SRC_DIR to handle both import styles
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(1, str(SCRIPT_DIR))

from mimir.artifacts import create_artifact, get_artifact, list_artifacts


def generate_rag_architecture_artifact() -> dict:
    """Generate artifact: RAG system architectural summary."""
    return {
        "artifact_type": "architectural_summary",
        "component": "rag_system",
        "description": "Mimir's RAG (Retrieval-Augmented Generation) system architecture",
        "keywords": [
            "rag", "retrieval", "hybrid search", "vector search", "bm25", "retriever",
            "rag workflow", "knowledge agent", "langgraph", "llm", "token tracking",
        ],
        "structure": {
            "retrieval": {
                "type": "hybrid",
                "vector": {
                    "engine": "LlamaIndex VectorStoreIndex",
                    "embedding_model": "text-embedding-3-small (configurable)",
                    "provider": "OpenAI-compatible API"
                },
                "sparse": {
                    "engine": "BM25Retriever (from llama_index.retrievers.bm25)",
                    "fallback": "vector-only if BM25 unavailable"
                },
                "merge_strategy": "deduplicate by node_id, prefer vector results",
                "default_top_k": 5
            },
            "orchestration": {
                "engine": "LangGraph",
                "workflows": [
                    {
                        "name": "rag_workflow",
                        "file": "langgraph/workflows/rag.py",
                        "steps": ["retrieve", "generate"],
                        "description": "Simple 2-step RAG: retrieve context then generate answer"
                    },
                    {
                        "name": "knowledge_agent",
                        "file": "langgraph/workflows/knowledge_agent.py",
                        "steps": ["check_knowledge", "agent", "execute_tools", "cleanup"],
                        "description": "Multi-step agentic research with tool use loop"
                    }
                ]
            },
            "llm": {
                "provider": "OpenAI-compatible API",
                "model": "configurable via llm_model config",
                "default": "google/gemini-3.1-flash-lite-preview",
                "token_tracking": "TokenUsageCallbackHandler (src/mimir/token_callback.py)"
            },
            "query_interfaces": {
                "search": {
                    "type": "MCP tool",
                    "description": "Semantic similarity search with hybrid retrieval",
                    "returns": "text chunks with scores and source file names"
                },
                "query": {
                    "type": "MCP tool",
                    "description": "Direct LlamaIndex query engine synthesis",
                    "returns": "prose answer synthesized from retrieved context"
                },
                "rag_workflow": {
                    "type": "MCP tool",
                    "description": "Structured retrieve->generate pipeline via LangGraph",
                    "returns": "synthesized answer with token usage metadata"
                },
                "knowledge_agent": {
                    "type": "MCP tool",
                    "description": "Multi-step agentic research",
                    "returns": "comprehensive answer after iterative tool use"
                }
            },
            "indexing": {
                "engine": "LlamaIndex SimpleDirectoryReader + VectorStoreIndex",
                "storage": ".knowledge/llamaindex/",
                "incremental": "supported via file watcher + hash tracking",
                "manifest": ".knowledge/llamaindex/manifest.json"
            },
            "additional_features": {
                "code_knowledge_graph": {
                    "description": "Tree-sitter extracted relationships",
                    "tools": ["graph_query", "graph_neighbors", "graph_stats"],
                    "relationship_types": ["calls", "imports_from", "inherits_from", "has_method"]
                },
                "sdk_cache": {
                    "description": "External library docs cached for 7 days via Context7",
                    "tools": ["sdk_cache_get", "sdk_cache_list"]
                },
                "metrics": {
                    "description": "Per-component cost and token tracking",
                    "storage": ".knowledge/cost_metrics.jsonl"
                }
            }
        },
        "source_files": [
            "langgraph/workflows/rag.py",
            "langgraph/workflows/knowledge_agent.py",
            "src/mimir/server.py",
            "src/mimir/indexing.py",
            "src/mimir/token_callback.py"
        ],
        "generated_at": "2026-05-16T01:46:00Z"
    }


def generate_indexing_architecture_artifact() -> dict:
    """Generate artifact: Indexing system architectural summary."""
    return {
        "artifact_type": "architectural_summary",
        "component": "indexing_system",
        "description": "Mimir's document indexing and incremental update system",
        "keywords": [
            "indexing", "index", "reindex", "incremental", "file watcher", "watchdog",
            "document id", "doc_id", "change detection", "hash",
        ],
        "structure": {
            "indexing_modes": {
                "full_reindex": {
                    "function": "index_with_progress()",
                    "file": "src/mimir/indexing.py",
                    "description": "Full rebuild from docs_dir + code_dirs"
                },
                "incremental_reindex": {
                    "function": "incremental_reindex()",
                    "file": "src/mimir/indexing.py",
                    "description": "Update index based on file hash changes"
                },
                "add_directory": {
                    "function": "add_directory_with_progress()",
                    "description": "Add documents from a new directory to existing index"
                },
                "add_file": {
                    "function": "add_file_to_index()",
                    "description": "Add a single file to existing index"
                },
                "remove_file": {
                    "function": "remove_file_from_index()",
                    "description": "Remove a file from index by path or doc_id"
                }
            },
            "change_detection": {
                "method": "SHA-256 file hashes",
                "state_file": ".mimir/index_state.json",
                "fields": ["added", "modified", "deleted"],
                "optimization": "mtime quick check to skip unchanged directories"
            },
            "document_id_strategy": {
                "type": "stable doc_id",
                "format": "file://{absolute_path}",
                "purpose": "prevent duplicates, enable efficient updates"
            },
            "file_watcher": {
                "implementation": "watchdog (src/mimir/watcher.py)",
                "debounce_seconds": 2.0,
                "kg_debounce_seconds": 5.0,
                "triggers": ["incremental_reindex", "knowledge_graph_update"]
            }
        },
        "source_files": [
            "src/mimir/indexing.py",
            "src/mimir/watcher.py",
            "src/mimir/server.py"
        ],
        "generated_at": "2026-05-16T01:46:00Z"
    }


def generate_artifact_system_artifact() -> dict:
    """Generate artifact: Artifact dependency tracking system."""
    return {
        "artifact_type": "architectural_summary",
        "component": "artifact_system",
        "description": "Mimir's pre-compiled artifact system with dependency tracking",
        "keywords": [
            "artifact", "pre-compiled", "stale", "ttl", "dependency tracking",
            "manifest", "invalidation",
        ],
        "structure": {
            "storage": {
                "manifest": ".knowledge/artifacts/manifest.json",
                "artifacts": ".knowledge/artifacts/*.json"
            },
            "staleness_checks": ["source_file_changes", "TTL_expiry"],
            "ttl_seconds": 3600,
            "invalidation_trigger": "file_watcher",
            "rebuild_strategy": "lazy_rebuild_on_query",
            "eager_rebuild": False
        },
        "source_files": [
            "src/mimir/artifacts.py",
            "src/mimir/server.py"
        ],
        "generated_at": "2026-05-17T02:16:00Z"
    }


def generate_code_chunking_artifact() -> dict:
    """Generate artifact: Code chunking strategies."""
    return {
        "artifact_type": "implementation_summary",
        "component": "chunking_system",
        "description": "Mimir's AST-aware code chunking for better retrieval",
        "keywords": [
            "chunking", "chunk", "ast", "tree-sitter", "python chunker",
            "code chunk", "split",
        ],
        "chunking_strategy": "AST-aware",
        "python_chunking": "PythonASTChunker",
        "multilang_chunking": "TreeSitterChunker",
        "chunker_router": "IntelligentChunker",
        "features": [
            "Functions/methods as separate chunks",
            "Classes split into header + methods",
            "Syntax-aware boundaries (no mid-function splits)",
            "Fallback to plain text for unknown types"
        ],
        "source_files": [
            "src/mimir/chunking.py"
        ]
    }


def generate_knowledge_graph_integration_artifact() -> dict:
    """Generate artifact: Knowledge graph integration with search."""
    return {
        "artifact_type": "integration_summary",
        "component": "search_plus_graph",
        "description": "How search tool uses knowledge graph for enhanced context",
        "keywords": [
            "knowledge graph", "graph query", "dijkstra", "relationship",
            "imports_from", "calls", "inherits_from",
        ],
        "kg_in_search": "enhanced with graph context",
        "relationship_types": ["imports_from", "calls", "inherits_from", "has_method"],
        "integration": {
            "trigger": "query terms match node names",
            "action": "append neighbor nodes to search results",
            "max_neighbors_shown": 5,
            "depth": 1
        },
        "source_files": [
            "src/mimir/server.py",
            "src/mimir/knowledge_graph.py"
        ]
    }


def generate_query_caching_artifact() -> dict:
    """Generate artifact: Query caching system."""
    return {
        "artifact_type": "caching_summary",
        "component": "query_cache",
        "description": "Query result caching to reduce redundant API calls",
        "keywords": [
            "cache", "query cache", "ttl", "expiration", "query_caching",
        ],
        "query_cache": "QueryCache with TTL",
        "cache_location": ".knowledge/query_cache/",
        "ttl_search": 3600,
        "ttl_query": 7200,
        "ttl_artifact": 86400,
        "features": [
            "Content-addressable (SHA-256 hash)",
            "TTL-based expiration",
            "Persistent storage",
            "Automatic cleanup of expired entries"
        ],
        "cache_tools": ["cache_stats", "cache_clear", "cache_cleanup"],
        "source_files": [
            "src/mimir/query_cache.py",
            "src/mimir/server.py"
        ]
    }


# Registry of artifact generators
ARTIFACT_GENERATORS = {
    "rag_architecture": generate_rag_architecture_artifact,
    "indexing_architecture": generate_indexing_architecture_artifact,
    "artifact_system": generate_artifact_system_artifact,
    "code_chunking": generate_code_chunking_artifact,
    "knowledge_graph_integration": generate_knowledge_graph_integration_artifact,
    "query_caching": generate_query_caching_artifact,
}


def generate_and_store(artifact_id: str) -> bool:
    """Generate and store an artifact."""
    if artifact_id not in ARTIFACT_GENERATORS:
        print(f"Unknown artifact: {artifact_id}")
        return False

    generator = ARTIFACT_GENERATORS[artifact_id]
    content = generator()

    # Determine dependencies from the artifact content
    depends_on = content.get("source_files", [])

    # Make paths absolute (relative to project root)
    project_root = Path.cwd()
    depends_on_abs = []
    for f in depends_on:
        path = project_root / f
        if path.exists():
            depends_on_abs.append(str(path))
        else:
            print(f"Warning: Source file not found: {path}")

    create_artifact(
        artifact_id=artifact_id,
        content=content,
        depends_on=depends_on_abs,
        ttl_seconds=3600,  # 1 hour TTL
        eager_rebuild=False,
    )

    print(f"Created artifact: {artifact_id}")
    return True


def generate_all():
    """Generate all artifacts."""
    for artifact_id in ARTIFACT_GENERATORS:
        generate_and_store(artifact_id)


def list_all():
    """List all artifacts."""
    artifacts = list_artifacts()
    if not artifacts:
        print("No artifacts found.")
        return

    print("Available artifacts:")
    for aid, info in artifacts.items():
        print(f"  - {aid} (v{info.get('version', '?')}, stale={info.get('stale', '?')})")


def main():
    parser = argparse.ArgumentParser(description="Generate Mimir artifacts")
    parser.add_argument("--all", action="store_true", help="Generate all artifacts")
    parser.add_argument("--artifact", type=str, help="Generate specific artifact")
    parser.add_argument("--list", action="store_true", help="List all artifacts")
    parser.add_argument("--get", type=str, help="Retrieve and print an artifact")

    args = parser.parse_args()

    if args.list:
        list_all()
    elif args.get:
        content = get_artifact(args.get)
        if content:
            print(json.dumps(content, indent=2, ensure_ascii=False))
        else:
            print(f"Artifact not found: {args.get}")
            sys.exit(1)
    elif args.artifact:
        if not generate_and_store(args.artifact):
            sys.exit(1)
    elif args.all:
        generate_all()
        print("\nAll artifacts generated successfully!")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
