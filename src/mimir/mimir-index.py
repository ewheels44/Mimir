#!/usr/bin/env python3
"""
mimir-index.py - Index and reindex your project for Mimir knowledge base.

Usage:
    python .opencode/mimir-index.py              # Index project
    python .opencode/mimir-index.py --reindex    # Force rebuild index
    python .opencode/mimir-index.py --add src    # Add specific directory
    python .opencode/mimir-index.py --add-file file.txt  # Add single file
    python .opencode/mimir-index.py --remove-file file.txt  # Remove single file
    python .opencode/mimir-index.py --list       # Show indexed contents
    python .opencode/mimir-index.py --update     # Update this script
    python .opencode/mimir-index.py --no-knowledge-graph  # Skip KG extraction

Delegates init/reindex to mimir_bridge.py handlers and uses
src/mimir/indexing.py directly for add/add-file/remove-file/list.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
# Support both "from mimir..." and "from src.mimir..." import styles
# src/ must come first so "from mimir..." finds src/mimir/__init__.py,
# not the top-level mimir.py script at MIMIR_DIR
sys.path.insert(1, str(MIMIR_DIR))
sys.path.insert(0, str(MIMIR_DIR / "src"))


def detect_project_root() -> Path:
    cwd = Path.cwd().resolve()
    # Prefer .mimir/config.json as the most reliable Mimir project marker
    current = cwd
    while current != current.parent:
        if (current / ".mimir" / "config.json").exists():
            return current
        current = current.parent

    # Fall back to general project markers
    markers = [".opencode", ".git", "pyproject.toml", "package.json"]
    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


def resolve_project_root() -> Path:
    """Resolve project root by walking up from the bridge script location.

    The bridge script always lives inside or near the Mimir project root.
    We derive the root by walking up from the script's parent directory
    looking for .mimir/config.json, so the correct project is always
    targeted even if invoked from a different working directory.
    """
    bridge_dir = Path(__file__).resolve().parent
    current = bridge_dir
    while current != current.parent:
        if (current / ".mimir" / "config.json").exists():
            return current
        current = current.parent
    return detect_project_root()


def get_relative_or_absolute_path(file_path: Path, project_root: Path) -> str:
    """Return relative path if file is under project root, otherwise absolute path."""
    try:
        return str(file_path.relative_to(project_root))
    except ValueError:
        return str(file_path)


def format_time(iso_string: str) -> str:
    """Format ISO timestamp to human-readable string."""
    if not iso_string:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_string


def print_indexed_files(knowledge_dir: Path) -> int:
    """Print a listing of all indexed files and directories."""
    from mimir.indexing import load_manifest

    manifest = load_manifest(knowledge_dir)

    if not manifest.get("indexed_directories"):
        print("📭 No indexed files found")
        print("\n   Run: python .opencode/mimir-index.py")
        print("   Or:  python .opencode/mimir-index.py --add <directory>")
        return 1

    print("\n" + "=" * 60)
    print("📚 KNOWLEDGE BASE CONTENTS")
    print("=" * 60)
    print(f"\n📊 Total documents: {manifest.get('total_documents', 0)}")
    print(f"🕐 Last updated: {format_time(manifest.get('last_updated'))}\n")

    for dir_key, info in manifest["indexed_directories"].items():
        dir_name = info.get("path", dir_key)
        file_count = info.get("file_count", 0)
        doc_count = info.get("document_count", 0)
        last_indexed = format_time(info.get("last_indexed"))
        indexed_at = format_time(info.get("indexed_at"))

        print(f"\n📁 {dir_name}")
        print(f"   Files: {file_count} | Documents: {doc_count}")
        if last_indexed != indexed_at:
            print(f"   First indexed: {indexed_at}")
            print(f"   Last updated: {last_indexed}")
        else:
            print(f"   Indexed: {indexed_at}")

        # Show first few files
        files = info.get("files", [])
        if files:
            print(f"\n   Sample files:")
            for f in files[:5]:
                # Show relative path if possible
                try:
                    rel_path = Path(f).relative_to(Path(dir_name))
                    print(f"      • {rel_path}")
                except ValueError:
                    print(f"      • {Path(f).name}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more files")

    print("\n" + "=" * 60)
    print(f"📂 Indexed directories: {len(manifest['indexed_directories'])}")
    print("=" * 60 + "\n")
    return 0


def update_script(project_root: Path) -> int:
    """
    Update the local mimir-index.py from central Mimir installation.
    Creates a backup of the current script before updating.
    NEVER touches the knowledge base.
    """
    import shutil

    local_script = project_root / ".opencode" / "mimir-index.py"
    central_script = MIMIR_DIR / "src" / "mimir" / "mimir-index.py"

    # Verify we're running from the expected location
    if not local_script.exists():
        print("❌ Cannot update: not running from .opencode/mimir-index.py")
        print(f"   Expected: {local_script}")
        return 1

    # Verify central installation exists
    if not central_script.exists():
        print("❌ Central Mimir installation not found")
        print(f"   Expected: {central_script}")
        print("\n   Make sure Mimir is installed at ~/Documents/Mimir")
        return 1

    # Safety check: verify knowledge base is NOT being touched
    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    if not knowledge_dir.exists():
        print("⚠️  No knowledge base found at expected location")
        print(f"   Expected: {knowledge_dir}")
        response = input("   Continue anyway? [y/N]: ")
        if response.lower() != "y":
            return 0

    # Show current versions
    central_stat = central_script.stat()
    local_stat = local_script.stat()

    print(f"\n📦 Central Mimir: {central_script}")
    print(f"   Modified: {datetime.fromtimestamp(central_stat.st_mtime)}")
    print(f"\n📄 Local script: {local_script}")
    print(f"   Modified: {datetime.fromtimestamp(local_stat.st_mtime)}")

    # Check if update is needed
    if central_stat.st_mtime <= local_stat.st_mtime:
        print("\n✅ Already up to date!")
        return 0

    # Create backup
    backup_path = local_script.with_suffix(".py.backup")
    try:
        shutil.copy2(local_script, backup_path)
        print(f"\n💾 Backup created: {backup_path}")
    except Exception as e:
        print(f"\n⚠️  Warning: Could not create backup: {e}")
        response = input("   Continue without backup? [y/N]: ")
        if response.lower() != "y":
            return 1

    # Copy new version
    try:
        shutil.copy2(central_script, local_script)
        # Preserve executable permissions
        local_script.chmod(0o755)
        print("✅ Script updated successfully!")
        print(f"\n📋 Changes:")
        print(f"   Old: {datetime.fromtimestamp(local_stat.st_mtime)}")
        print(f"   New: {datetime.fromtimestamp(central_stat.st_mtime)}")
        print(f"\n🔄 Next time you run this command, the new version will be used.")
        return 0
    except Exception as e:
        print(f"\n❌ Update failed: {e}")
        print("\n🛟  Recovery:")
        if backup_path.exists():
            print(f"   Restore from backup: cp {backup_path} {local_script}")
        print(f"   Or re-run: python ~/Documents/Mimir/src/mimir/mimir-index.py --force")
        return 1


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
    parser.add_argument(
        "--add-file", metavar="FILE", help="Add a single file to existing index"
    )
    parser.add_argument(
        "--remove-file", metavar="FILE", help="Remove a single file from the index"
    )
    parser.add_argument(
        "--list", action="store_true", help="List all indexed files and directories"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update this script from central Mimir installation (preserves knowledge base)",
    )
    parser.add_argument(
        "--no-knowledge-graph",
        action="store_true",
        help="Skip knowledge graph relationship extraction",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-initialization or reindex"
    )
    args = parser.parse_args()

    project_root = detect_project_root()
    print(f"🎯 Project root: {project_root}")

    mimir_config_dir = project_root / ".mimir"
    mimir_config_dir.mkdir(parents=True, exist_ok=True)
    config_path = mimir_config_dir / "config.json"

    # ── Init: use bridge's handle_init so initialization is centralized ──
    if not args.reindex and not args.add and not args.add_file and not args.remove_file and not args.list:
        from mimir_bridge import handle_init

        result = handle_init(
            {"force": args.force},
            project_root,
        )
        if result.get("status") != "ok":
            print(f"❌ Init failed: {result.get('error', 'unknown')}")
            return 1

        # After init, proceed to index if docs or code_dirs exist
        from mimir.config import MimirConfig, reset_config

        reset_config()
        config = MimirConfig.load(project_root=project_root)
        code_dirs = list(config.code_dirs)
        has_docs = config.docs_dir.exists() and any(config.docs_dir.iterdir())
        has_code_dirs = bool(code_dirs)

        if not has_docs and not has_code_dirs:
            print("\n⚠️  No documents found in docs/ and no code_dirs configured")
            print("\n📖 Next steps:")
            print("   1. Add documents to docs/")
            print("   2. Or configure code_dirs in .mimir/config.json")
            print("   3. Run: python .opencode/mimir-index.py --reindex")
            return 0

        # Fall through to indexing below
        args.reindex = True  # trigger the reindex path

    # ── Reindex: use bridge's handle_reindex (includes knowledge graph) ──
    if args.reindex:
        from mimir_bridge import handle_reindex

        result = handle_reindex(
            {"force": args.force},
            project_root,
        )
        if result.get("status") != "ok":
            print(f"❌ Reindex failed: {result.get('error', 'unknown')}")
            return 1

        from mimir.config import MimirConfig, reset_config

        reset_config()
        config = MimirConfig.load(project_root=project_root)

        if not args.no_knowledge_graph and config.code_dirs:
            print(
                f"\n📂 Code directories configured: {', '.join(config.code_dirs)}"
            )
        else:
            print(
                "\n💡 Tip: To also index source code, add code_dirs to .mimir/config.json"
            )
            print('   Example: {"code_dirs": ["src", "tests"]}')

        print("\n📖 Next steps:")
        print("   - Query via OpenCode: Just start asking questions!")
        print("   - Web UI: cd ~/Documents/Mimir/web && ./dev.sh --project $(pwd)")
        print(
            "   - CLI: python ~/Documents/Mimir/mimir_bridge.py  (or use MCP tools)"
        )

        if not args.no_knowledge_graph:
            kg = result.get("knowledge_graph", {})
            if kg.get("total_relationships", 0) > 0:
                print("\n🔍 Knowledge Graph:")
                print(f"   - {kg.get('total_relationships', 0)} relationships from {kg.get('total_entities', 0)} entities")
                print("   - Relationships extracted to .knowledge/code_relationships.json")
                print("   - Start the Web UI to use graph_query/graph_neighbors MCP tools")

        print("\n📚 Documentation:")
        print("   - See README.md for complete usage guide")
        print("   - Run with --no-knowledge-graph to skip relationship extraction")
        print("   - Run with --reindex to rebuild from scratch")
        return 0

    # ── Add directory ──
    if args.add:
        from mimir.config import get_config, reset_config

        reset_config()
        config = get_config(project_root=project_root)
        knowledge_dir = config.knowledge_dir

        source_dir = Path(args.add)
        if not source_dir.exists():
            print(f"\n❌ Directory not found: {source_dir}")
            return 1
        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No existing index found. Run without --add first.")
            return 1

        dir_entry = get_relative_or_absolute_path(source_dir, project_root)
        try:
            with open(config_path) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            cfg = {}

        if "code_dirs" not in cfg:
            cfg["code_dirs"] = []
        if dir_entry not in cfg["code_dirs"]:
            cfg["code_dirs"].append(dir_entry)
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"📝 Added to code_dirs: {dir_entry}")

        from mimir.indexing import add_directory_with_progress

        success = add_directory_with_progress(source_dir, knowledge_dir, verbose=True)
        return 0 if success else 1

    # ── Add single file ──
    if args.add_file:
        from mimir.config import get_config, reset_config

        reset_config()
        config = get_config(project_root=project_root)
        knowledge_dir = config.knowledge_dir

        source_file = Path(args.add_file).resolve()
        if not source_file.exists():
            print(f"\n❌ File not found: {source_file}")
            return 1
        if not source_file.is_file():
            print(f"\n❌ Not a file: {source_file}")
            return 1
        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No existing index found. Run without --add-file first.")
            return 1

        file_entry = get_relative_or_absolute_path(source_file, project_root)
        try:
            with open(config_path) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            cfg = {}

        if "files" not in cfg:
            cfg["files"] = []
        if file_entry not in cfg["files"]:
            cfg["files"].append(file_entry)
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"📝 Added to config: {file_entry}")

        from mimir.indexing import add_file_to_index

        success = add_file_to_index(
            source_file, knowledge_dir, verbose=True, project_root=project_root
        )
        return 0 if success else 1

    # ── Remove file ──
    if args.remove_file:
        from mimir.config import get_config, reset_config

        reset_config()
        config = get_config(project_root=project_root)
        knowledge_dir = config.knowledge_dir

        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No existing index found.")
            return 1

        from mimir.indexing import remove_file_from_index

        source_file = Path(args.remove_file).resolve()

        # Also remove from config files list if present
        try:
            with open(config_path) as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            cfg = {}

        file_entry = get_relative_or_absolute_path(source_file, project_root)
        if "files" in cfg and file_entry in cfg["files"]:
            cfg["files"].remove(file_entry)
            with open(config_path, "w") as f:
                json.dump(cfg, f, indent=2)
            print(f"📝 Removed from config: {file_entry}")

        success = remove_file_from_index(source_file, knowledge_dir, verbose=True)
        return 0 if success else 1

    # ── List ──
    if args.list:
        from mimir.config import get_config, reset_config

        reset_config()
        config = get_config(project_root=project_root)
        knowledge_dir = config.knowledge_dir

        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No knowledge base found")
            print(f"   Expected: {knowledge_dir}")
            print("\n   Run: python .opencode/mimir-index.py")
            return 1
        return print_indexed_files(knowledge_dir)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())