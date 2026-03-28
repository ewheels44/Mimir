#!/usr/bin/env python3
"""
Per-project setup and full indexing script for Mimir knowledge base.

Usage:
    python .opencode/setup.py              # Setup and index project
    python .opencode/setup.py --reindex    # Force rebuild index

This script:
    1. Sets up docs/ and .knowledge/ directories
    2. Reads .mimir/config.json for code directories
    3. Indexes with intelligent exclusions for cache files
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))

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


def get_openrouter_api_key() -> str | None:
    if api_key := os.environ.get("OPENROUTER_API_KEY"):
        return api_key

    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if auth_path.exists():
        try:
            with open(auth_path) as f:
                auth_data = json.load(f)
            if openrouter := auth_data.get("openrouter"):
                return openrouter.get("key")
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def detect_project_root() -> Path:
    cwd = Path.cwd().resolve()
    markers = [".opencode", ".git", "pyproject.toml", "package.json"]

    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


def load_project_config(project_root: Path) -> dict:
    config_path = project_root / ".mimir" / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def full_index(project_root: Path, force_reindex: bool = False) -> int:
    """
    Full index with intelligent exclusions.

    Returns:
        0 on success, 1 on error
    """
    from mcp_server_llamaindex import ServerConfig, KnowledgeServer
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext

    # Set up environment for the server
    os.environ["PROJECT_ROOT"] = str(project_root)
    os.environ["KNOWLEDGE_DIR"] = str(project_root / ".knowledge" / "llamaindex")

    config = ServerConfig.from_env()
    server = KnowledgeServer(config)

    if force_reindex and config.knowledge_dir.exists():
        print(f"Clearing existing index at {config.knowledge_dir}...")
        shutil.rmtree(config.knowledge_dir)
        config.knowledge_dir.mkdir(parents=True, exist_ok=True)

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
        return 1

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

    print("\n✅ Indexing complete!")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Setup and index project for Mimir knowledge base"
    )
    parser.add_argument(
        "--reindex", action="store_true", help="Clear and rebuild index"
    )
    parser.add_argument(
        "--add", metavar="DIR", help="Add documents from DIR to existing index"
    )
    args = parser.parse_args()

    project_root = detect_project_root()
    print(f"🎯 Project root: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    mimir_config_dir = project_root / ".mimir"

    # Create directories
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    mimir_config_dir.mkdir(exist_ok=True)

    # Create default config if it doesn't exist
    config_path = mimir_config_dir / "config.json"
    if not config_path.exists():
        default_config = {
            "docs_dir": "docs",
            "code_dirs": [],
            "knowledge_dir": ".knowledge/llamaindex",
            "embedding_model": "text-embedding-3-small",
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)
        print(f"📝 Created default config: {config_path}")

    print(f"📁 Knowledge base: {knowledge_dir}")
    print(f"📁 Documents: {docs_dir}")

    api_key = get_openrouter_api_key()
    if not api_key:
        print("\n⚠️  Warning: OpenRouter API key not found")
        print("   Set OPENROUTER_API_KEY environment variable")
        print("   Or log in to opencode: opencode auth openrouter")
        return 1

    os.environ["OPENROUTER_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    print("\n🔑 OpenRouter API key found")

    if args.add:
        source_dir = Path(args.add)
        if not source_dir.exists():
            print(f"\n❌ Directory not found: {source_dir}")
            return 1
        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No existing index found. Run without --add first.")
            return 1
        print(f"\n➕ Adding documents from {source_dir}...")
        try:
            from mcp_server_llamaindex import ServerConfig, KnowledgeServer
            from llama_index.core import (
                SimpleDirectoryReader,
                load_index_from_storage,
                StorageContext,
            )

            os.environ["PROJECT_ROOT"] = str(project_root)
            os.environ["KNOWLEDGE_DIR"] = str(knowledge_dir)

            config = ServerConfig.from_env()

            # Initialize KnowledgeServer to set up embedding model
            server = KnowledgeServer(config)

            storage_context = StorageContext.from_defaults(
                persist_dir=str(knowledge_dir)
            )
            index = load_index_from_storage(storage_context)

            reader = SimpleDirectoryReader(
                str(source_dir),
                recursive=True,
                filename_as_id=True,
                exclude=EXCLUDE_PATTERNS,
            )
            new_docs = reader.load_data()

            if not new_docs:
                print("   No documents found to add")
                return 0

            for doc in new_docs:
                index.insert(doc)
            index.storage_context.persist(persist_dir=str(knowledge_dir))

            print(f"   Added {len(new_docs)} documents")
            print("\n✅ Incremental indexing complete!")
            return 0
        except Exception as e:
            print(f"\n❌ Error adding documents: {e}")
            return 1

    # Check for existing index
    if (knowledge_dir / "index_store.json").exists() and not args.reindex:
        print("\n✅ Knowledge base already exists")
        response = input("   Rebuild from docs/? [y/N]: ")
        if response.lower() != "y":
            print("   Skipping reindex")
            return 0
        args.reindex = True

    # Check if we have anything to index
    has_docs = docs_dir.exists() and any(docs_dir.iterdir())
    project_config = load_project_config(project_root)
    has_code_dirs = bool(project_config.get("code_dirs", []))

    if not has_docs and not has_code_dirs:
        print("\n⚠️  No documents found in docs/ and no code_dirs configured")
        print("\n📖 Next steps:")
        print("   1. Add documents to docs/")
        print("   2. Or configure code_dirs in .mimir/config.json")
        print("   3. Run: python .opencode/setup.py")
        return 0

    # Run full indexing
    try:
        result = full_index(project_root, force_reindex=args.reindex)
        if result != 0:
            return result
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("   Make sure Mimir dependencies are installed:")
        print(f"   cd {MIMIR_DIR} && pip install -r requirements.txt")
        return 1
    except Exception as e:
        print(f"\n❌ Error during indexing: {e}")
        return 1

    # Show config info
    project_config = load_project_config(project_root)
    if project_config.get("code_dirs"):
        print(
            f"\n📂 Code directories configured: {', '.join(project_config['code_dirs'])}"
        )
    else:
        print(
            "\n💡 Tip: To also index source code, add code_dirs to .mimir/config.json"
        )
        print('   Example: {"code_dirs": ["src", "tests"]}')

    print("\n📖 Usage:")
    print("   - Query knowledge base via OpenCode")
    print(
        '   - Or run: python ~/Documents/Mimir/mcp_server_llamaindex.py --query "your question"'
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
