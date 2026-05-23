#!/usr/bin/env python3
"""
Mimir CLI - Unified command-line interface for Mimir.

Usage:
    mimir init [--code-dirs=...] [--project-root=...]    # Initialize a project
    mimir index [--reindex] [--add DIR]                 # Index the project
    mimir search "query"                                   # Search knowledge base
    mimir health                                           # Check configuration
    mimir install          # Global install (deprecated, use install.sh)
    mimir uninstall        # Global uninstall
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Mimir root directory
MIMIR_ROOT = Path(__file__).resolve().parent.parent

# Ensure mimir root is in path for imports
src_path = str(MIMIR_ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# ─── Constants ────────────────────────────────────────────────────────────

MIMIR_RULES_START = "<!-- MIMIR_RULES_START -->"
MIMIR_RULES_END = "<!-- MIMIR_RULES_END -->"

MIMIR_RULES_BLOCK = f"""
{MIMIR_RULES_START}
## MIMIR RULES (4 ONLY)

### 1. MIMIR FIRST
Before any task, call `mimir(action="enrich_task", params={{"task": "..."}})`. 
This is my memory — without it I'm guessing. No exceptions.

### 2. CONTEXT BEFORE CODE
Before writing/editing:
- Code → read `~/.config/opencode/context/core/standards/code-quality.md`
- Docs → read `~/.config/opencode/context/core/standards/documentation.md`
- Tests → read `~/.config/opencode/context/core/standards/test-coverage.md`
- Review → read `~/.config/opencode/context/core/workflows/code-review.md`

If it's bash-only, skip this.

### 3. ASK FIRST
Never run bash/write/edit without showing a plan and getting approval. 
Read/list/glob/grep are fine without asking.

### 4. CHECK SKILLS
Before executing, check if the task matches an available skill. 
If yes, load it with the skill tool. If no match, proceed with tools directly.

{MIMIR_RULES_END}
"""


# ─── Path Detection ─────────────────────────────────────────────────────────

def find_mimir_root() -> Optional[Path]:
    """Detect where Mimir is installed."""
    if env := os.environ.get("MIMIR_ROOT"):
        p = Path(env).resolve()
        if p.exists():
            return p
    
    this_file = Path(__file__).resolve().parent.parent
    if (this_file / "pyproject.toml").exists():
        return this_file
    
    return None


def detect_project_root(provided_path: Optional[str] = None) -> Path:
    """Detect project root by walking up from cwd looking for marker files."""
    if provided_path:
        return Path(provided_path).resolve()
    
    cwd = Path.cwd().resolve()
    markers = [
        ".git",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "opencode.json",
    ]
    
    current = cwd
    while current != current.parent:
        if any((current / m).exists() for m in markers):
            return current
        current = current.parent
    
    return cwd


# ─── Init Command ─────────────────────────────────────────────────────────

def create_mimir_config(project_root: Path, code_dirs: Optional[list] = None) -> Path:
    """Create .mimir/config.json for a project."""
    mimir_dir = project_root / ".mimir"
    mimir_dir.mkdir(exist_ok=True)
    
    config = {
        "docs_dir": "docs",
        "knowledge_dir": ".knowledge/llamaindex",
        "embedding_model": "text-embedding-3-small",
    }
    
    if code_dirs:
        config["code_dirs"] = code_dirs
    
    config_path = mimir_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    return config_path


def cmd_init(args):
    """Initialize a project for Mimir."""
    mimir_root = find_mimir_root()
    if not mimir_root:
        print("❌ Could not detect Mimir installation directory.")
        return 1
    
    project_root = detect_project_root(args.project_root)
    print(f"\n🎯 Initializing Mimir for project: {project_root}")
    
    # Parse code directories
    code_dirs_list = None
    if args.code_dirs:
        code_dirs_list = [d.strip() for d in args.code_dirs.split(",")]
    
    # Create .mimir/config.json
    print("\n📁 Creating .mimir/config.json...")
    config_path = create_mimir_config(project_root, code_dirs_list)
    print(f"   ✓ Created: {config_path}")
    
    # Create necessary directories
    print("\n📁 Creating directories...")
    docs_dir = project_root / "docs"
    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    
    for d, desc in [
        (docs_dir, "Documents"),
        (knowledge_dir, "Knowledge base"),
    ]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ {desc}: {d}")
    
    print(f"\n✅ Project initialized successfully!")
    
    # Optionally index
    if args.index:
        print(f"\n🔄 Starting initial index...")
        return cmd_index(args)
    
    print(f"\nNext steps:")
    print(f"  1. Run: mimir index")
    print(f"  2. Run: mimir health (to verify configuration)")
    
    return 0


# ─── Index Command ────────────────────────────────────────────────────────

def cmd_index(args):
    """Index the project knowledge base."""
    from mimir.config import MimirConfig
    from mimir.server import KnowledgeServer
    
    project_root = detect_project_root(args.project_root)
    print(f"\n📚 Indexing project: {project_root}")
    
    try:
        config = MimirConfig.load(project_root=project_root)
        server = KnowledgeServer(config)
        
        # Determine what to index
        if args.add:
            # Add specific directory
            dir_path = project_root / args.add
            if not dir_path.exists():
                print(f"❌ Directory not found: {dir_path}")
                return 1
            print(f"   Indexing directory: {args.add}")
            result = server.index_documents(Path(args.add))
        else:
            # Index everything (docs + code_dirs)
            print(f"   Indexing all configured directories...")
            result = server.index_documents()
        
        print(f"\n✅ {result}")
        return 0
        
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        return 1


# ─── Search Command ──────────────────────────────────────────────────────

def cmd_search(args):
    """Search the knowledge base."""
    from mimir.config import MimirConfig
    from mimir.server import KnowledgeServer
    
    project_root = detect_project_root(args.project_root)
    
    try:
        config = MimirConfig.load(project_root=project_root)
        server = KnowledgeServer(config)
        
        results = server.search(args.query, top_k=args.top_k)
        
        if not results:
            print("No results found.")
            return 0
        
        print(f"\n🔍 Search results for: {args.query}")
        print(f"{'='*60}")
        print(results)
        return 0
        
    except Exception as e:
        print(f"❌ Search failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


# ─── Health Command ─────────────────────────────────────────────────────

def cmd_health(args):
    """Check Mimir configuration and health."""
    from mimir.config import MimirConfig
    
    project_root = detect_project_root(args.project_root)
    
    try:
        config = MimirConfig.load(project_root=project_root)
        
        print(f"\n🏥 Mimir Health Check")
        print(f"{'='*60}")
        print(f"Project root: {config.project_root}")
        print(f"Mimir root: {config.mimir_root}")
        print(f"API key: {'✓ Set' if config.api_key else '✗ Not set'}")
        print(f"Embedding model: {config.embedding_model}")
        print(f"LLM model: {config.llm_model}")
        print(f"Docs dir: {config.docs_dir} {'✓' if config.docs_dir.exists() else '✗ Not found'}")
        print(f"Knowledge dir: {config.knowledge_dir} {'✓' if config.knowledge_dir.exists() else '✗ Not found'}")
        
        warnings = config.validate()
        if warnings:
            print(f"\n⚠️  Warnings:")
            for w in warnings:
                print(f"  - {w}")
        else:
            print(f"\n✅ All checks passed!")
        
        return 0
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return 1


# ─── Install/Uninstall Commands ─────────────────────────────────────────

def cmd_install(args):
    """Global install — set up system-wide Mimir configuration."""
    print("\n🌍 Global Mimir install...")
    
    opencode_config_dir = Path.home() / ".config" / "opencode"
    opencode_config_dir.mkdir(parents=True, exist_ok=True)
    
    system_context = opencode_config_dir / "system-context.md"
    
    if system_context.exists() and not args.force:
        content = system_context.read_text()
        if MIMIR_RULES_START in content:
            print(f"   ⏭️  Mimir rules already present in system-context.md")
        else:
            with open(system_context, "a") as f:
                f.write(MIMIR_RULES_BLOCK)
            print(f"   ✓ Appended Mimir rules to: {system_context}")
    else:
        system_context.write_text(MIMIR_RULES_BLOCK.lstrip())
        print(f"   ✓ Created: {system_context}")
    
    print(f"\n✅ Global install complete!")
    return 0


def cmd_uninstall(args):
    """Uninstall — restore backed up configs."""
    print("\n🧹 Uninstalling Mimir...")
    
    opencode_config_dir = Path.home() / ".config" / "opencode"
    system_context = opencode_config_dir / "system-context.md"
    
    if system_context.exists():
        content = system_context.read_text()
        if MIMIR_RULES_START in content and MIMIR_RULES_END in content:
            before = content.split(MIMIR_RULES_START)[0]
            after = content.split(MIMIR_RULES_END)[1]
            system_context.write_text(before.rstrip() + after)
            print(f"   ✓ Removed Mimir rules from: {system_context}")
    
    print(f"\n✅ Uninstall complete.")
    return 0


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Mimir - Persistent Knowledge Base for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # init
    init_parser = subparsers.add_parser("init", help="Initialize a project for Mimir")
    init_parser.add_argument("--code-dirs", help="Comma-separated list of code directories")
    init_parser.add_argument("--project-root", help="Project directory (default: auto-detect)")
    init_parser.add_argument("--index", action="store_true", help="Run initial index after init")
    
    # index
    index_parser = subparsers.add_parser("index", help="Index the project knowledge base")
    index_parser.add_argument("--reindex", action="store_true", help="Force full reindex")
    index_parser.add_argument("--add", help="Add a specific directory to the index")
    index_parser.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # search
    search_parser = subparsers.add_parser("search", help="Search the knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    search_parser.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # health
    health_parser = subparsers.add_parser("health", help="Check Mimir configuration")
    health_parser.add_argument("--project-root", help="Project directory (default: auto-detect)")
    
    # install (global)
    install_parser = subparsers.add_parser("install", help="Global install (deprecated)")
    install_parser.add_argument("--force", action="store_true", help="Force reinstall")
    
    # uninstall (global)
    subparsers.add_parser("uninstall", help="Global uninstall")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Dispatch to command handler
    handlers = {
        "init": cmd_init,
        "index": cmd_index,
        "search": cmd_search,
        "health": cmd_health,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
    }
    
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"❌ Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
