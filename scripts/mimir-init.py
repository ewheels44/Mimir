#!/usr/bin/env python3
"""
mimir-init.py - Initialize Mimir for any project or install globally.

Two modes:
  1. Global install (run once): Sets up MCP server and system rules
  2. Per-project init (run in each project): Creates directories and indexes

Per-project setup creates:
  - .mimir/config.json     - Project-specific Mimir settings

The Mimir CLI automatically sets PROJECT_ROOT when running commands
so the bridge knows which project it's serving.

Usage:
    # Global install (run once after cloning Mimir)
    python ~/Documents/Mimir/mimir.py install

    # Per-project init (run in each project you want to index)
    cd /path/to/your/project
    python ~/Documents/Mimir/mimir.py init
    python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests

    # Uninstall (restores backed up configs)
    python ~/Documents/Mimir/mimir.py uninstall
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Mimir root directory
MIMIR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MIMIR_ROOT / "src"))


# ─── Constants ────────────────────────────────────────────────────────────────

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


# ─── Path Detection ───────────────────────────────────────────────────────────


def find_mimir_root() -> Path | None:
    """Detect where Mimir is installed."""
    if env := os.environ.get("MIMIR_ROOT"):
        p = Path(env).resolve()
        if p.exists():
            return p

    this_file = Path(__file__).resolve().parent.parent
    if (this_file / "mimir_cli.py").exists():
        return this_file

    return None


def detect_project_root(provided_path: str | None = None) -> Path:
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


# ─── Per-Project Init ─────────────────────────────────────────────────────────


def create_mimir_config(project_root: Path, code_dirs: list[str] | None = None) -> Path:
    """Create .mimir/config.json for a project.
    
    This config file is read by MimirConfig in src/mimir/config.py
    to set project-specific settings.
    """
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





def init_project(project_root: Path, mimir_root: Path, code_dirs: str | None = None) -> bool:
    """Initialize a project for Mimir knowledge base."""
    print(f"\n🎯 Initializing Mimir for project: {project_root}")

    # Parse code directories
    code_dirs_list = None
    if code_dirs:
        code_dirs_list = [d.strip() for d in code_dirs.split(",")]

    # Create .mimir/config.json
    print("\n📁 Creating .mimir/config.json...")
    config_path = create_mimir_config(project_root, code_dirs_list)
    print(f"   ✓ Created: {config_path}")

    # The Mimir CLI will set PROJECT_ROOT automatically when running commands
    print(f"\n   ℹ️  PROJECT_ROOT will be auto-detected when running mimir commands")

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
    print(f"\nNext steps:")
    print(f"  1. Run: mimir index")
    print(f"  2. Run: mimir health (to verify configuration)")
    
    return True


# ─── Global Install ───────────────────────────────────────────────────────────


def install_global(mimir_root: Path, force: bool = False) -> bool:
    """Global install — set up system-wide Mimir configuration."""
    print("\n🌍 Global Mimir install...")

    # Find opencode config directory
    opencode_config_dir = Path.home() / ".config" / "opencode"
    if not opencode_config_dir.exists():
        opencode_config_dir.mkdir(parents=True, exist_ok=True)

    # Update system-context.md with Mimir rules
    system_context = opencode_config_dir / "system-context.md"
    
    if system_context.exists() and not force:
        content = system_context.read_text()
        if MIMIR_RULES_START in content:
            print(f"   ⏭️  Mimir rules already present in system-context.md")
        else:
            # Append Mimir rules
            with open(system_context, "a") as f:
                f.write(MIMIR_RULES_BLOCK)
            print(f"   ✓ Appended Mimir rules to: {system_context}")
    else:
        # Create new system-context.md with Mimir rules
        system_context.write_text(MIMIR_RULES_BLOCK.lstrip())
        print(f"   ✓ Created: {system_context}")

    print(f"\n✅ Global install complete!")
    return True


# ─── Uninstall ────────────────────────────────────────────────────────────────


def uninstall(mimir_root: Path) -> bool:
    """Uninstall — restore backed up configs."""
    print("\n🧹 Uninstalling Mimir...")

    # Remove Mimir rules from system-context.md
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
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Mimir for a project or install globally."
    )
    
    # Global install/uninstall
    parser.add_argument(
        "--install",
        action="store_true",
        help="Global install (run once after cloning Mimir)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Uninstall Mimir from global config",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstall even if already installed",
    )
    
    # Per-project init
    parser.add_argument(
        "--code-dirs",
        help="Comma-separated list of code directories to index (e.g., 'src,tests')",
    )
    parser.add_argument(
        "--project-root",
        help="Project directory to initialize (default: current directory)",
    )

    args = parser.parse_args()

    mimir_root = find_mimir_root()
    if not mimir_root:
        print("❌ Could not detect Mimir installation directory.")
        print("   Set MIMIR_ROOT environment variable or run from Mimir directory.")
        return 1

    # Global install
    if args.install:
        return 0 if install_global(mimir_root, args.force) else 1

    # Uninstall
    if args.uninstall:
        return 0 if uninstall(mimir_root) else 1

    # Per-project init (default)
    project_root = detect_project_root(args.project_root)
    return 0 if init_project(project_root, mimir_root, args.code_dirs) else 1


if __name__ == "__main__":
    sys.exit(main())
