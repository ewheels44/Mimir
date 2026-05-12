#!/usr/bin/env python3
"""
Full index script with cache exclusions for Mimir knowledge base.

Usage:
    python ~/Documents/Mimir/full_index.py              # Index current project
    python ~/Documents/Mimir/full_index.py --reindex    # Force reindex

This script reads .mimir/config.json and indexes docs/ + code_dirs
with intelligent exclusions for cache files, images, and binaries.
"""

import argparse
import os
import sys
from pathlib import Path

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))

os.environ["PROJECT_ROOT"] = str(Path.cwd())
os.environ["KNOWLEDGE_DIR"] = str(Path.cwd() / ".knowledge" / "llamaindex")

EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".github",
    ".gitignore",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.mp4",
    "*.webm",
    "*.mov",
    "*.mp3",
    "*.wav",
    "*.ogg",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.rar",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.tflite",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "uv.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    ".DS_Store",
    "Thumbs.db",
    "test-results",
    "playwright-report",
    "blob-report",
]


def main():
    parser = argparse.ArgumentParser(
        description="Index project for Mimir knowledge base"
    )
    parser.add_argument(
        "--reindex", action="store_true", help="Clear and rebuild index"
    )
    args = parser.parse_args()

    if args.reindex:
        import shutil

        knowledge_dir = Path(".knowledge/llamaindex")
        if knowledge_dir.exists():
            print(f"Clearing existing index at {knowledge_dir}...")
            shutil.rmtree(knowledge_dir)
            knowledge_dir.mkdir(parents=True, exist_ok=True)

    print("Loading config and creating server...")
    from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex

    from mcp_server_llamaindex import KnowledgeServer
    from mimir.config import MimirConfig

    config = MimirConfig.load()
    KnowledgeServer(config)

    print(f"\nIndexing with exclusions: {len(EXCLUDE_PATTERNS)} patterns")

    all_documents = []

    if config.docs_dir.exists():
        print(f"\n1. Indexing {config.docs_dir}/...")
        reader = SimpleDirectoryReader(
            str(config.docs_dir), recursive=True, exclude=EXCLUDE_PATTERNS
        )
        docs = reader.load_data()
        all_documents.extend(docs)
        print(f"   Loaded {len(docs)} documents")

    for code_dir in config.code_dirs:
        if code_dir.exists():
            print(f"\n2. Indexing {code_dir.name}/...")
            try:
                reader = SimpleDirectoryReader(
                    str(code_dir),
                    recursive=True,
                    filename_as_id=True,
                    exclude=EXCLUDE_PATTERNS,
                )
                code_docs = reader.load_data()
                all_documents.extend(code_docs)
                print(f"   Loaded {len(code_docs)} documents")
            except Exception as e:
                print(f"   Warning: Could not index {code_dir}: {e}")

    print(f"\nTotal documents to index: {len(all_documents)}")

    if len(all_documents) == 0:
        print("No documents found!")
        sys.exit(1)

    print("\nCreating VectorStoreIndex...")
    storage_context = StorageContext.from_defaults()
    index = VectorStoreIndex.from_documents(
        all_documents, storage_context=storage_context
    )

    print("Persisting index...")
    index.storage_context.persist(persist_dir=str(config.knowledge_dir))

    print("\nTesting search...")
    retriever = index.as_retriever(similarity_top_k=3)
    nodes = retriever.retrieve("test query")
    print(f"Test search returned {len(nodes)} results")

    print("\nIndexing complete!")


if __name__ == "__main__":
    main()
