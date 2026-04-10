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

from src.mimir.utils import EXCLUDE_PATTERNS, should_exclude as _should_exclude


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
    file_hashes: Optional[dict] = None,
) -> None:
    manifest = load_manifest(knowledge_dir)

    dir_key = str(directory.resolve())

    if is_incremental and dir_key in manifest["indexed_directories"]:
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
        if file_hashes:
            manifest["indexed_directories"][dir_key]["file_hashes"] = file_hashes
        elif "file_hashes" in existing:
            manifest["indexed_directories"][dir_key]["file_hashes"] = existing[
                "file_hashes"
            ]
    else:
        manifest["indexed_directories"][dir_key] = {
            "path": str(directory),
            "files": sorted(files),
            "file_count": len(files),
            "document_count": document_count,
            "last_indexed": datetime.now().isoformat(),
            "indexed_at": datetime.now().isoformat(),
        }
        if file_hashes:
            manifest["indexed_directories"][dir_key]["file_hashes"] = file_hashes

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


# =============================================================================
# SHA-256 File Hash Functions
# =============================================================================

import hashlib

MAX_FILE_SIZE_FOR_HASHING = 50 * 1024 * 1024  # 50MB threshold


def compute_file_hash(file_path: Path) -> Optional[str]:
    """
    Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file to hash

    Returns:
        Hex-encoded SHA-256 hash string, or None if file is too large or unreadable
    """
    try:
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE_FOR_HASHING:
            print(
                f"   Warning: Skipping large file {file_path.name} ({file_size / 1024 / 1024:.1f}MB > 50MB)"
            )
            return None

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except (IOError, OSError) as e:
        print(f"   Warning: Could not hash {file_path}: {e}")
        return None


def get_index_state_path(project_root: Path) -> Path:
    """Get the path to the index state file."""
    return project_root / ".mimir" / "index_state.json"


def load_hash_state(project_root: Path) -> dict:
    """
    Load the hash state from .mimir/index_state.json.

    Args:
        project_root: Root directory of the project

    Returns:
        Dictionary with file_hashes: {file_path: sha256_hex}
    """
    state_path = get_index_state_path(project_root)
    if state_path.exists():
        try:
            with open(state_path) as f:
                state = json.load(f)
                # Ensure backward compatibility - return empty dict if file_hashes missing
                if "file_hashes" not in state:
                    return {"file_hashes": {}}
                return state
        except (json.JSONDecodeError, IOError):
            pass
    return {"file_hashes": {}}


def save_hash_state(project_root: Path, state: dict) -> None:
    """
    Save the hash state to .mimir/index_state.json.

    Args:
        project_root: Root directory of the project
        state: Dictionary with file_hashes and optional metadata
    """
    state_path = get_index_state_path(project_root)
    state["last_updated"] = datetime.now().isoformat()

    # Ensure .mimir directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def detect_changed_files(
    project_root: Path,
    watched_dirs: List[Path],
    update_state: bool = True,
    custom_exclude_patterns: Optional[List[str]] = None,
) -> dict:
    previous_state = load_hash_state(project_root)
    previous_hashes = previous_state.get("file_hashes", {})

    current_hashes = {}
    all_files = []

    # Merge default and custom patterns
    all_patterns = EXCLUDE_PATTERNS[:]
    if custom_exclude_patterns:
        all_patterns.extend(custom_exclude_patterns)

    for watched_dir in watched_dirs:
        if not watched_dir.exists():
            continue
        for file_path in watched_dir.rglob("*"):
            if file_path.is_file() and not _should_exclude(
                file_path, custom_exclude_patterns
            ):
                rel_path = str(file_path.resolve())
                all_files.append(rel_path)
                file_hash = compute_file_hash(file_path)
                if file_hash is not None:
                    current_hashes[rel_path] = file_hash

    previous_files = set(previous_hashes.keys())
    current_files = set(current_hashes.keys())

    added = [Path(p) for p in current_files - previous_files]
    deleted = [Path(p) for p in previous_files - current_files]

    modified = []
    for path in current_files & previous_files:
        if current_hashes[path] != previous_hashes[path]:
            modified.append(Path(path))

    if update_state:
        save_hash_state(project_root, {"file_hashes": current_hashes})

    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
    }


def index_with_progress(
    project_root: Path,
    docs_dir: Path,
    code_dirs: List[Path],
    knowledge_dir: Path,
    force_reindex: bool = False,
    verbose: bool = True,
    custom_exclude_patterns: Optional[List[str]] = None,
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
        custom_exclude_patterns: Additional patterns to exclude (merged with defaults)

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

    # Merge default and custom exclude patterns
    all_exclude_patterns = EXCLUDE_PATTERNS[:]
    if custom_exclude_patterns:
        all_exclude_patterns.extend(custom_exclude_patterns)

    if force_reindex and knowledge_dir.exists():
        if verbose:
            print(f"Clearing existing index at {knowledge_dir}...")
        shutil.rmtree(knowledge_dir)
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        clear_manifest(knowledge_dir)

    if verbose:
        pattern_count = len(all_exclude_patterns)
        custom_count = len(custom_exclude_patterns) if custom_exclude_patterns else 0
        print(
            f"\nIndexing with exclusions: {pattern_count} patterns ({custom_count} custom)"
        )

    all_documents = []
    directory_files = {}  # Track files per directory for manifest

    if docs_dir.exists():
        if verbose:
            print(f"\n1. Scanning {docs_dir}/...")
        reader = SimpleDirectoryReader(
            str(docs_dir), recursive=True, exclude=all_exclude_patterns
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
                    exclude=all_exclude_patterns,
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


def _get_stable_doc_id(file_path: Path) -> str:
    """Generate a stable document ID based on absolute file path."""
    return f"file://{file_path.resolve()}"


def _use_refresh_ref_docs(index) -> bool:
    """Check if the index supports refresh_ref_docs method."""
    return hasattr(index, "refresh_ref_docs") and callable(
        getattr(index, "refresh_ref_docs")
    )


def _refresh_or_insert_doc(index, doc, verbose: bool = True) -> bool:
    """
    Insert a document using refresh_ref_docs if available, or fallback to
    delete + insert pattern.

    Args:
        index: The VectorStoreIndex
        doc: Document to insert
        verbose: Whether to print debug info

    Returns:
        True if successful
    """
    if _use_refresh_ref_docs(index):
        try:
            refreshed = index.refresh_ref_docs([doc])
            if verbose:
                status = "updated" if refreshed[0] else "inserted"
                print(f"      ↳ {status}: {doc.doc_id}")
            return True
        except Exception as e:
            if verbose:
                print(f"      ↳ refresh_ref_docs failed: {e}, using fallback")
            # Fall through to fallback

    # Fallback: delete then insert
    try:
        doc_id = doc.doc_id
        # Check if doc exists before deleting
        docstore = index.storage_context.docstore
        if doc_id in docstore.docs:
            index.delete_ref_doc(doc_id, delete_from_docstore=True)
            if verbose:
                print(f"      ↳ deleted existing: {doc_id}")
        index.insert(doc)
        if verbose:
            print(f"      ↳ inserted: {doc_id}")
        return True
    except Exception as e:
        if verbose:
            print(f"      ↳ fallback failed: {e}")
        return False


def add_directory_with_progress(
    source_dir: Path,
    knowledge_dir: Path,
    verbose: bool = True,
    custom_exclude_patterns: Optional[List[str]] = None,
) -> bool:
    """
    Add documents from a directory to existing index with progress bars.
    Uses stable doc_ids to prevent duplicates.

    Args:
        source_dir: Directory to add
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output
        custom_exclude_patterns: Additional patterns to exclude (merged with defaults)

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

    # Merge default and custom exclude patterns
    all_exclude_patterns = EXCLUDE_PATTERNS[:]
    if custom_exclude_patterns:
        all_exclude_patterns.extend(custom_exclude_patterns)

    if verbose:
        print(f"\n➕ Adding documents from {source_dir}...")

    storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
    index = load_index_from_storage(storage_context)

    reader = SimpleDirectoryReader(
        str(source_dir),
        recursive=True,
        filename_as_id=True,
        exclude=all_exclude_patterns,
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
                for d in doc:
                    # Set stable doc_id based on file path
                    file_path = Path(str(resource))
                    d.doc_id = _get_stable_doc_id(file_path)
                    d.metadata = d.metadata or {}
                    d.metadata["file_path"] = str(file_path.resolve())
                    new_docs.append(d)
                    _refresh_or_insert_doc(index, d, verbose=False)
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
                    # Set stable doc_id based on file path
                    file_path = Path(str(resource))
                    d.doc_id = _get_stable_doc_id(file_path)
                    d.metadata = d.metadata or {}
                    d.metadata["file_path"] = str(file_path.resolve())
                    _refresh_or_insert_doc(index, d, verbose=False)
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
    project_root: Optional[Path] = None,
) -> bool:
    """
    Add a single file to existing index.

    Args:
        source_file: File to add
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output
        project_root: Optional project root for hash state tracking

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
                "file_path": str(source_file.resolve()),
                "file_name": file_name,
                "file_type": source_file.suffix,
            },
            id_=_get_stable_doc_id(source_file),
        )

        _refresh_or_insert_doc(index, doc, verbose=verbose)

        # Update manifest - use parent directory as key
        parent_dir = source_file.parent
        add_to_manifest(
            knowledge_dir, parent_dir, [str(source_file)], 1, is_incremental=True
        )

        if verbose:
            print("   ✓ File indexed")
            print("   ✓ Manifest updated")

        index.storage_context.persist(persist_dir=str(knowledge_dir))

        # Update hash state for incremental change detection
        if project_root:
            file_hash = compute_file_hash(source_file)
            if file_hash:
                state = load_hash_state(project_root)
                state["file_hashes"][str(source_file.resolve())] = file_hash
                save_hash_state(project_root, state)
                if verbose:
                    print("   ✓ Hash state updated")

        if verbose:
            print("\n✅ File added successfully!")

        return True

    except Exception as e:
        if verbose:
            print(f"   ❌ Failed to index file: {e}")
        return False


def remove_from_manifest(knowledge_dir: Path, file_path: Path) -> bool:
    """Remove a file from the indexing manifest.

    Args:
        knowledge_dir: Where the index is stored
        file_path: Absolute path of the file to remove

    Returns:
        True if the file was found and removed from manifest, False otherwise
    """
    manifest = load_manifest(knowledge_dir)
    resolved = str(file_path.resolve())
    found = False

    for dir_key, info in list(manifest["indexed_directories"].items()):
        files = info.get("files", [])
        if resolved in files:
            files.remove(resolved)
            info["files"] = files
            info["file_count"] = len(files)
            info["document_count"] = max(0, info.get("document_count", 1) - 1)
            info["last_indexed"] = datetime.now().isoformat()
            found = True

            # Remove directory entry if no files left
            if not files:
                del manifest["indexed_directories"][dir_key]

    if found:
        manifest["total_documents"] = sum(
            entry.get("document_count", 0)
            for entry in manifest["indexed_directories"].values()
        )
        save_manifest(knowledge_dir, manifest)

    return found


def remove_file_from_index(
    source_file: Path,
    knowledge_dir: Path,
    verbose: bool = True,
) -> bool:
    """Remove a single file from the existing index.

    Searches by stable doc_id first (file:// URI), then falls back to
    matching by file_path metadata for documents indexed via SimpleDirectoryReader.

    Args:
        source_file: File to remove (matched by absolute path)
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        from llama_index.core import (
            load_index_from_storage,
            StorageContext,
        )
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

    if not (knowledge_dir / "index_store.json").exists():
        if verbose:
            print("❌ No existing index found.")
        return False

    resolved = source_file.resolve()
    resolved_str = str(resolved)

    if verbose:
        print(f"\n🗑️  Removing file from index: {resolved}")

    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
        index = load_index_from_storage(storage_context)

        docstore = index.storage_context.docstore

        # Strategy 1: Try stable doc_id (used by add_file_to_index)
        doc_id = _get_stable_doc_id(resolved)
        if doc_id in docstore.docs:
            index.delete_ref_doc(doc_id, delete_from_docstore=True)
            if verbose:
                print("   ✓ Removed from vector index (matched by doc_id)")
        else:
            # Strategy 2: Search by file_path metadata (used by SimpleDirectoryReader)
            matched_ids = [
                did
                for did, doc in docstore.docs.items()
                if getattr(doc, "metadata", {}).get("file_path") == resolved_str
            ]

            if not matched_ids:
                if verbose:
                    print(f"   ⚠️  File not found in index: {resolved_str}")
                return False

            for did in matched_ids:
                index.delete_ref_doc(did, delete_from_docstore=True)
            if verbose:
                print(
                    f"   ✓ Removed {len(matched_ids)} node(s) from vector index "
                    "(matched by file_path metadata)"
                )

        # Update manifest
        manifest_updated = remove_from_manifest(knowledge_dir, resolved)
        if verbose and manifest_updated:
            print("   ✓ Manifest updated")
        elif verbose:
            print("   ⚠️  File not found in manifest (already removed from index)")

        index.storage_context.persist(persist_dir=str(knowledge_dir))

        if verbose:
            print("   ✓ Index persisted")
            print("\n✅ File removed successfully!")

        return True

    except Exception as e:
        if verbose:
            print(f"   ❌ Failed to remove file: {e}")
        return False


def remove_directory_from_index(
    source_dir: Path,
    knowledge_dir: Path,
    verbose: bool = True,
) -> bool:
    """Remove all files from a directory from the existing index.

    Optimized to load the index once, remove all files, then persist once.

    Args:
        source_dir: Directory to remove (all files recursively)
        knowledge_dir: Where the existing index is stored
        verbose: Whether to print progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        from llama_index.core import (
            load_index_from_storage,
            StorageContext,
        )
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        return False

    if not (knowledge_dir / "index_store.json").exists():
        if verbose:
            print("❌ No existing index found.")
        return False

    resolved_dir = source_dir.resolve()
    if not resolved_dir.exists():
        if verbose:
            print(f"❌ Directory not found: {resolved_dir}")
        return False

    if verbose:
        print(f"\n🗑️  Removing directory from index: {resolved_dir}")

    # Load manifest to find all files in this directory
    manifest = load_manifest(knowledge_dir)
    files_to_remove = []

    # Find all files that belong to this directory
    for dir_key, info in manifest.get("indexed_directories", {}).items():
        for file_path in info.get("files", []):
            file_path_obj = Path(file_path)
            try:
                # Check if file is under the directory being removed
                if (
                    resolved_dir in file_path_obj.parents
                    or file_path_obj.parent == resolved_dir
                ):
                    files_to_remove.append(file_path_obj)
            except (OSError, ValueError):
                # Skip files that can't be resolved
                continue

    if not files_to_remove:
        if verbose:
            print("   ⚠️  No files from this directory found in index")
        return True

    if verbose:
        print(f"   Found {len(files_to_remove)} files to remove")

    # Load index once
    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
        index = load_index_from_storage(storage_context)
        docstore = index.storage_context.docstore
    except Exception as e:
        if verbose:
            print(f"❌ Failed to load index: {e}")
            print("   The index may be corrupted. Try running: mimir index --reindex")
        return False

    # Remove all files from the index
    removed_count = 0
    for file_path in files_to_remove:
        resolved_file = file_path.resolve()
        resolved_str = str(resolved_file)

        # Try stable doc_id first
        doc_id = _get_stable_doc_id(resolved_file)
        if doc_id in docstore.docs:
            index.delete_ref_doc(doc_id, delete_from_docstore=True)
            removed_count += 1
        else:
            # Try matching by file_path metadata
            matched_ids = [
                did
                for did, doc in docstore.docs.items()
                if getattr(doc, "metadata", {}).get("file_path") == resolved_str
            ]
            for did in matched_ids:
                index.delete_ref_doc(did, delete_from_docstore=True)
                removed_count += 1

    # Update manifest once for all files
    for file_path in files_to_remove:
        resolved_file = file_path.resolve()
        # Remove from manifest
        for dir_key, info in list(manifest["indexed_directories"].items()):
            files = info.get("files", [])
            resolved_str = str(resolved_file.resolve())
            if resolved_str in files:
                files.remove(resolved_str)
                info["files"] = files
                info["file_count"] = len(files)
                info["document_count"] = max(0, info.get("document_count", 1) - 1)
                info["last_indexed"] = datetime.now().isoformat()

                # Remove directory entry if no files left
                if not files:
                    del manifest["indexed_directories"][dir_key]

    # Update total documents count
    manifest["total_documents"] = sum(
        entry.get("document_count", 0)
        for entry in manifest["indexed_directories"].values()
    )

    # Save manifest
    save_manifest(knowledge_dir, manifest)

    # Persist index once
    try:
        index.storage_context.persist(persist_dir=str(knowledge_dir))
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Warning: Failed to persist index: {e}")
            print("   Manifest updated, but index may need reindexing")

    if verbose:
        print(f"   ✓ Removed {removed_count} documents from index")
        print("\n✅ Directory removed successfully!")

    return removed_count > 0


def incremental_reindex(
    project_root: Path,
    watched_dirs: List[Path],
    knowledge_dir: Path,
    verbose: bool = False,
) -> dict:
    import logging

    logger = logging.getLogger(__name__)

    result = {
        "added_count": 0,
        "modified_count": 0,
        "deleted_count": 0,
        "success": False,
    }

    if not (knowledge_dir / "index_store.json").exists():
        logger.warning("No existing index found. Run full index first.")
        return result

    try:
        from llama_index.core import (
            load_index_from_storage,
            StorageContext,
            Document,
        )
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return result

    changes = detect_changed_files(project_root, watched_dirs, update_state=True)
    added = changes["added"]
    modified = changes["modified"]
    deleted = changes["deleted"]

    if len(added) + len(modified) + len(deleted) == 0:
        logger.debug("No changes detected, skipping reindex")
        result["success"] = True
        return result

    logger.info(
        f"Incremental reindex: +{len(added)} modified:{len(modified)} -{len(deleted)}"
    )

    try:
        storage_context = StorageContext.from_defaults(persist_dir=str(knowledge_dir))
        index = load_index_from_storage(storage_context)

        for file_path in added + modified:
            if _should_exclude(file_path):
                logger.debug(f"Skipping excluded file: {file_path}")
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                doc = Document(
                    text=content,
                    metadata={
                        "file_path": str(file_path.resolve()),
                        "file_name": file_path.name,
                        "file_type": file_path.suffix,
                    },
                    id_=_get_stable_doc_id(file_path),
                )
                _refresh_or_insert_doc(index, doc, verbose=verbose)
                if file_path in added:
                    result["added_count"] += 1
                else:
                    result["modified_count"] += 1
                logger.debug(f"Indexed: {file_path}")
            except UnicodeDecodeError:
                logger.debug(f"Skipping binary file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to index {file_path}: {e}")

        for file_path in deleted:
            try:
                doc_id = _get_stable_doc_id(file_path)
                docstore = index.storage_context.docstore
                if doc_id in docstore.docs:
                    index.delete_ref_doc(doc_id, delete_from_docstore=True)
                    result["deleted_count"] += 1
                    logger.debug(f"Removed from index: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove {file_path} from index: {e}")

        index.storage_context.persist(persist_dir=str(knowledge_dir))
        result["success"] = True
        result["timestamp"] = datetime.now().isoformat()

        logger.info(
            f"Incremental reindex complete: "
            f"+{result['added_count']} ~{result['modified_count']} -{result['deleted_count']}"
        )

    except Exception as e:
        logger.error(f"Incremental reindex failed: {e}")

    return result
