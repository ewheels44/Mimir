#!/usr/bin/env python3
"""
Unified indexing module for Mimir knowledge base.

This module provides the shared indexing logic with progress bars
used by both the CLI (mimir-index.py) and the MCP server.
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def get_progress_bar(iterable=None, desc="", total=None, unit="it", ncols=80):
    try:
        from tqdm import tqdm

        if sys.stdout.isatty():
            return tqdm(
                iterable=iterable,
                desc=desc,
                total=total,
                unit=unit,
                ncols=ncols,
            )
        else:
            return FallbackProgressBar(
                iterable=iterable, desc=desc, total=total, unit=unit
            )
    except ImportError:
        return FallbackProgressBar(iterable=iterable, desc=desc, total=total, unit=unit)


class FallbackProgressBar:
    def __init__(self, iterable=None, desc="", total=None, unit="it"):
        self.iterable = iterable
        self.desc = desc
        self.total = total
        self.unit = unit
        self.n = 0
        self._last_pct = -1

    def __iter__(self):
        if self.iterable is None:
            return iter([])
        for item in self.iterable:
            yield item
            self.update(1)
        self.close()

    def __enter__(self):
        if self.desc:
            print(f"   {self.desc}...", flush=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def update(self, n=1):
        self.n += n
        if self.total:
            pct = int(100 * self.n / self.total)
            if pct in [0, 25, 50, 75, 100] and pct != self._last_pct:
                print(
                    f"   {self.desc}: {self.n}/{self.total} {self.unit} ({pct}%)",
                    flush=True,
                )
                self._last_pct = pct

    def close(self):
        if self.total and self.n >= self.total:
            print(f"   {self.desc}: complete ({self.total} {self.unit})", flush=True)


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


def get_manifest_path(knowledge_dir: Path) -> Path:
    """Get the path to the manifest file."""
    return knowledge_dir / "manifest.json"


def load_manifest(knowledge_dir: Path) -> dict:
    """Load the indexing manifest if it exists."""
    manifest_path = get_manifest_path(knowledge_dir)
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "version": "1.0",
        "indexed_directories": {},
        "total_documents": 0,
        "last_updated": None,
    }


def save_manifest(knowledge_dir: Path, manifest: dict) -> None:
    """Save the indexing manifest."""
    manifest_path = get_manifest_path(knowledge_dir)
    manifest["last_updated"] = datetime.now().isoformat()
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def add_to_manifest(
    knowledge_dir: Path,
    directory: Path,
    files: List[str],
    document_count: int,
    is_incremental: bool = False,
) -> None:
    """Add or update a directory entry in the manifest."""
    manifest = load_manifest(knowledge_dir)

    dir_key = str(directory.resolve())

    if is_incremental and dir_key in manifest["indexed_directories"]:
        # Merge with existing entry
        existing = manifest["indexed_directories"][dir_key]
        existing_files = set(existing.get("files", []))
        new_files = set(files)
        merged_files = sorted(existing_files.union(new_files))

        manifest["indexed_directories"][dir_key] = {
            "path": str(directory),
            "files": merged_files,
            "file_count": len(merged_files),
            "document_count": existing.get("document_count", 0) + document_count,
            "last_indexed": datetime.now().isoformat(),
            "indexed_at": existing.get("indexed_at", datetime.now().isoformat()),
        }
    else:
        # New entry or full reindex
        manifest["indexed_directories"][dir_key] = {
            "path": str(directory),
            "files": sorted(files),
            "file_count": len(files),
            "document_count": document_count,
            "last_indexed": datetime.now().isoformat(),
            "indexed_at": datetime.now().isoformat(),
        }

    # Recalculate total
    manifest["total_documents"] = sum(
        entry.get("document_count", 0)
        for entry in manifest["indexed_directories"].values()
    )

    save_manifest(knowledge_dir, manifest)


def clear_manifest(knowledge_dir: Path) -> None:
    """Clear the manifest (used on full reindex)."""
    manifest = {
        "version": "1.0",
        "indexed_directories": {},
        "total_documents": 0,
        "last_updated": datetime.now().isoformat(),
    }
    save_manifest(knowledge_dir, manifest)


def list_indexed_files(knowledge_dir: Path) -> dict:
    """Get a detailed listing of all indexed files."""
    manifest = load_manifest(knowledge_dir)
    return manifest


def index_with_progress(
    project_root: Path,
    docs_dir: Path,
    code_dirs: List[Path],
    knowledge_dir: Path,
    force_reindex: bool = False,
    verbose: bool = True,
) -> bool:
    """
    Index documents with progress bars.

    Args:
        project_root: Project root directory
        docs_dir: Documentation directory
        code_dirs: List of source code directories
        knowledge_dir: Where to store the index
        force_reindex: Whether to clear existing index
        verbose: Whether to print progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        from llama_index.core import (
            SimpleDirectoryReader,
            VectorStoreIndex,
            StorageContext,
        )
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install llama-index tqdm")
        return False

    if force_reindex and knowledge_dir.exists():
        if verbose:
            print(f"Clearing existing index at {knowledge_dir}...")
        shutil.rmtree(knowledge_dir)
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        clear_manifest(knowledge_dir)

    if verbose:
        print(f"\nIndexing with exclusions: {len(EXCLUDE_PATTERNS)} patterns")

    all_documents = []
    directory_files = {}  # Track files per directory for manifest

    if docs_dir.exists():
        if verbose:
            print(f"\n1. Scanning {docs_dir}/...")
        reader = SimpleDirectoryReader(
            str(docs_dir), recursive=True, exclude=EXCLUDE_PATTERNS
        )
        resources = list(reader.list_resources())
        if verbose:
            print(f"   Found {len(resources)} files")

        if resources and verbose:
            print("   Loading documents...")
            docs = []
            for resource in get_progress_bar(
                resources, desc="   Loading docs", unit="file"
            ):
                try:
                    doc = reader.load_resource(resource)
                    docs.extend(doc)
                except Exception as e:
                    print(f"   ⚠️  Skipped {resource}: {e}", flush=True)
            all_documents.extend(docs)
            directory_files[docs_dir] = [str(r) for r in resources]
            print(f"   ✓ Loaded {len(docs)} documents")
        elif resources:
            for resource in resources:
                try:
                    doc = reader.load_resource(resource)
                    all_documents.extend(doc)
                except Exception:
                    pass
            directory_files[docs_dir] = [str(r) for r in resources]

    for code_dir in code_dirs:
        if code_dir.exists():
            if verbose:
                print(f"\n2. Scanning {code_dir.name}/...")
            try:
                reader = SimpleDirectoryReader(
                    str(code_dir),
                    recursive=True,
                    filename_as_id=True,
                    exclude=EXCLUDE_PATTERNS,
                )
                resources = list(reader.list_resources())
                if verbose:
                    print(f"   Found {len(resources)} files")

                if resources and verbose:
                    print("   Loading documents...")
                    code_docs = []
                    for resource in get_progress_bar(
                        resources,
                        desc=f"   Loading {code_dir.name}",
                        unit="file",
                    ):
                        try:
                            doc = reader.load_resource(resource)
                            code_docs.extend(doc)
                        except Exception as e:
                            print(f"   ⚠️  Skipped {resource}: {e}", flush=True)
                    all_documents.extend(code_docs)
                    directory_files[code_dir] = [str(r) for r in resources]
                    print(f"   ✓ Loaded {len(code_docs)} documents")
                elif resources:
                    for resource in resources:
                        try:
                            doc = reader.load_resource(resource)
                            all_documents.extend(doc)
                        except Exception:
                            pass
                    directory_files[code_dir] = [str(r) for r in resources]
            except Exception as e:
                if verbose:
                    print(f"   Warning: Could not index {code_dir}: {e}")

    if not all_documents:
        if verbose:
            print("❌ No documents found!")
        return False

    if verbose:
        print(f"\n📊 Total documents to index: {len(all_documents)}")
        print("\n🔄 Creating embeddings and building index...")

    storage_context = StorageContext.from_defaults()

    if verbose:
        if all_documents:
            index = VectorStoreIndex.from_documents(
                [all_documents[0]],
                storage_context=storage_context,
                show_progress=False,
            )

            if len(all_documents) > 1:
                with get_progress_bar(
                    total=len(all_documents) - 1,
                    desc="   Embedding docs",
                    unit="doc",
                ) as pbar:
                    for doc in all_documents[1:]:
                        index.insert(doc)
                        pbar.update(1)
            print("   ✓ Index created")
        else:
            index = VectorStoreIndex.from_documents(
                [], storage_context=storage_context, show_progress=False
            )
    else:
        index = VectorStoreIndex.from_documents(
            all_documents, storage_context=storage_context, show_progress=False
        )

    if verbose:
        print("\n💾 Saving index to disk...")
    index.storage_context.persist(persist_dir=str(knowledge_dir))
    if verbose:
        print("   ✓ Index persisted")

    # Save manifest with indexed file listing
    if verbose:
        print("\n📝 Saving manifest...")
    for dir_path, files in directory_files.items():
        # Count documents from this directory
        dir_doc_count = sum(
            1
            for doc in all_documents
            if str(dir_path) in getattr(doc, "metadata", {}).get("file_path", "")
            or str(dir_path) in str(getattr(doc, "doc_id", ""))
        )
        if dir_doc_count == 0:
            # Fallback: estimate based on file count
            dir_doc_count = len(files)
        add_to_manifest(knowledge_dir, dir_path, files, dir_doc_count)
    if verbose:
        print("   ✓ Manifest saved")

    if verbose:
        print("\n🧪 Testing search...")
        retriever = index.as_retriever(similarity_top_k=3)
        nodes = retriever.retrieve("test query")
        print(f"   ✓ Test search returned {len(nodes)} results")
        print("\n✅ Indexing complete!")

    return True


def add_directory_with_progress(
    source_dir: Path,
    knowledge_dir: Path,
    verbose: bool = True,
) -> bool:
    """
    Add documents from a directory to existing index with progress bars.

    Args:
        source_dir: Directory to add
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        from llama_index.core import (
            SimpleDirectoryReader,
            load_index_from_storage,
            StorageContext,
        )
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

    if not (knowledge_dir / "index_store.json").exists():
        if verbose:
            print("❌ No existing index found. Run full index first.")
        return False

    if verbose:
        print(f"\n➕ Adding documents from {source_dir}...")

    storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
    index = load_index_from_storage(storage_context)

    reader = SimpleDirectoryReader(
        str(source_dir),
        recursive=True,
        filename_as_id=True,
        exclude=EXCLUDE_PATTERNS,
    )

    resources = list(reader.list_resources())
    if verbose:
        print(f"   Found {len(resources)} files to add")

    if not resources:
        if verbose:
            print("   No documents found to add")
        return True

    resource_list = [str(r) for r in resources]

    if verbose:
        print("   Loading and embedding documents...")
        new_docs = []
        for resource in get_progress_bar(resources, desc="   Processing", unit="file"):
            try:
                doc = reader.load_resource(resource)
                new_docs.extend(doc)
                for d in doc:
                    index.insert(d)
            except Exception as e:
                print(f"   ⚠️  Skipped {resource}: {e}", flush=True)
        print(f"   ✓ Added {len(new_docs)} documents")

        # Update manifest for incremental addition
        add_to_manifest(
            knowledge_dir, source_dir, resource_list, len(new_docs), is_incremental=True
        )
        print("   ✓ Manifest updated")
        print("\n✅ Incremental indexing complete!")
    else:
        doc_count = 0
        for resource in resources:
            try:
                doc = reader.load_resource(resource)
                for d in doc:
                    index.insert(d)
                    doc_count += 1
            except Exception:
                pass
        # Update manifest even in non-verbose mode
        add_to_manifest(
            knowledge_dir, source_dir, resource_list, doc_count, is_incremental=True
        )

    index.storage_context.persist(persist_dir=str(knowledge_dir))
    return True


def add_file_to_index(
    source_file: Path,
    knowledge_dir: Path,
    verbose: bool = True,
) -> bool:
    """
    Add a single file to existing index.

    Args:
        source_file: File to add
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        from llama_index.core import (
            SimpleDirectoryReader,
            load_index_from_storage,
            StorageContext,
        )
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

    if not (knowledge_dir / "index_store.json").exists():
        if verbose:
            print("❌ No existing index found. Run full index first.")
        return False

    if verbose:
        print(f"\n📄 Adding file: {source_file}")

    storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
    index = load_index_from_storage(storage_context)

    # Check if file should be excluded
    file_name = source_file.name
    for pattern in EXCLUDE_PATTERNS:
        import fnmatch

        if fnmatch.fnmatch(file_name, pattern):
            if verbose:
                print(f"   ⚠️  File matches exclusion pattern: {pattern}")
            return False

    try:
        # Read file content directly
        try:
            content = source_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            if verbose:
                print("   ⚠️  File appears to be binary, skipping")
            return False

        from llama_index.core import Document

        doc = Document(
            text=content,
            metadata={
                "file_path": str(source_file),
                "file_name": file_name,
                "file_type": source_file.suffix,
            },
            id_=str(source_file),
        )

        index.insert(doc)

        # Update manifest - use parent directory as key
        parent_dir = source_file.parent
        add_to_manifest(
            knowledge_dir, parent_dir, [str(source_file)], 1, is_incremental=True
        )

        if verbose:
            print("   ✓ File indexed")
            print("   ✓ Manifest updated")
            print("\n✅ File added successfully!")

        index.storage_context.persist(persist_dir=str(knowledge_dir))
        return True

    except Exception as e:
        if verbose:
            print(f"   ❌ Failed to index file: {e}")
        return False
