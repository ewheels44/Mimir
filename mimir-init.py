#!/usr/bin/env python3
"""
mimir-init.py - Initialize Mimir for any project or install globally.

Two modes:
  1. Global install (run once): Sets up MCP server and system rules
  2. Per-project init (run in each project): Creates directories and indexes

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


# ─── Constants ────────────────────────────────────────────────────────────────

MIMIR_RULES_START = "<!-- MIMIR_RULES_START -->"
MIMIR_RULES_END = "<!-- MIMIR_RULES_END -->"

MIMIR_RULES_BLOCK = f"""
{MIMIR_RULES_START}
## MIMIR RULES (4 ONLY)

### 1. MIMIR FIRST
Before any task, call `mimir-knowledge_enrich_task()`. This is my memory — without it I'm guessing. No exceptions.

### 2. CONTEXT BEFORE CODE
Before writing/editing:
- Code → read `~/.config/opencode/context/core/standards/code-quality.md`
- Docs → read `~/.config/opencode/context/core/standards/documentation.md`
- Tests → read `~/.config/opencode/context/core/standards/test-coverage.md`
- Review → read `~/.config/opencode/context/core/workflows/code-review.md`
- Delegation → read `~/.config/opencode/context/core/workflows/task-delegation-basics.md`

If it's bash-only, skip this.

### 3. ASK FIRST
Never run bash/write/edit/task without showing a plan and getting approval. Read/list/glob/grep are fine without asking.

### 4. CHECK SKILLS
Before executing, check if the task matches an available skill. If yes, load it with `skill()`. If no match, proceed with tools directly.

## Reference (read when needed)

Full reference is in the project's `AGENTS.md` if it exists. Key tool priority:

| Situation | Tool |
|-----------|------|
| SDK/library question | `sdk_cache_get` |
| Project context | `enrich_task` |
| Semantic search | `search` |
| Complex analysis | `rag_workflow` |
| Find skills | `openspace_search_skills` |
{MIMIR_RULES_END}
"""

BASE_SYSTEM_CONTEXT = """# System Context

This context is injected at the start of every session.

## Session Info
- **Date**: {{date}}
- **Git Branch**: {{git_branch}}
- **Working Directory**: {{cwd}}
- **Platform**: {{platform}}

## Instructions
<!-- Edit below this line to customize what gets injected -->

"""


# ─── Path Detection ───────────────────────────────────────────────────────────


def find_mimir_root() -> Path | None:
    """Detect where Mimir is installed.

    Checks:
    1. MIMIR_ROOT env var
    2. Location of this file (mimir-init.py → project root)
    3. ~/Documents/Mimir (legacy fallback)
    """
    if env := os.environ.get("MIMIR_ROOT"):
        p = Path(env).resolve()
        if p.exists():
            return p

    this_file = Path(__file__).resolve()
    if (this_file.parent / "mcp_server_llamaindex.py").exists():
        return this_file.parent

    legacy = Path.home() / "Documents" / "Mimir"
    if legacy.exists():
        return legacy

    return None


def find_opencode_config_dir() -> Path | None:
    """Detect the OpenCode global config directory."""
    candidates = [
        Path.home() / ".config" / "opencode",
        Path.home() / ".config" / "opencode-openagents",
        Path.home() / ".config" / "oh-my-opencode",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def detect_project_root() -> Path:
    """Detect project root by walking up from cwd."""
    cwd = Path.cwd().resolve()
    markers = [
        "opencode.json",
        ".opencode",
        ".git",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
    ]

    current = cwd
    while current != current.parent:
        if any((current / m).exists() for m in markers):
            return current
        current = current.parent

    return cwd


def get_openrouter_api_key() -> str | None:
    """Resolve API key from env or auth file."""
    if api_key := os.environ.get("OPENROUTER_API_KEY"):
        return api_key

    for auth_path in [
        Path.home() / ".local" / "share" / "opencode" / "auth.json",
        Path.home() / ".config" / "opencode" / "auth.json",
    ]:
        if auth_path.exists():
            try:
                data = json.loads(auth_path.read_text())
                if key := data.get("openrouter", {}).get("key"):
                    return key
            except (json.JSONDecodeError, KeyError):
                continue

    return None


# ─── Backup Helpers ───────────────────────────────────────────────────────────


def backup_file(src: Path, backup_dir: Path) -> Path | None:
    """Backup a file with timestamp. Returns backup path or None."""
    if not src.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{src.name}.{timestamp}.bak"
    shutil.copy2(src, backup)
    return backup


def restore_latest_backup(name: str, target: Path, backup_dir: Path) -> bool:
    """Restore the most recent backup of a file."""
    if not backup_dir.exists():
        return False

    backups = sorted(backup_dir.glob(f"{name}.*.bak"), reverse=True)
    if not backups:
        return False

    shutil.copy2(backups[0], target)
    return True


# ─── Global Install ───────────────────────────────────────────────────────────


def inject_system_rules(opencode_config_dir: Path, force: bool = False) -> dict:
    """Inject Mimir rules into system-context.md using markers.

    Returns status dict with actions taken.
    """
    result = {"backed_up": False, "injected": False, "skipped": False}

    prompts_dir = opencode_config_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    system_context = prompts_dir / "system-context.md"
    backup_dir = opencode_config_dir / "mimir-backups"

    # Backup existing
    if system_context.exists():
        backup = backup_file(system_context, backup_dir)
        if backup:
            result["backed_up"] = str(backup)

    # Create base if missing
    if not system_context.exists():
        system_context.write_text(BASE_SYSTEM_CONTEXT)

    # Read current content
    content = system_context.read_text()

    # Remove existing Mimir block (for re-installs)
    if MIMIR_RULES_START in content and MIMIR_RULES_END in content:
        if not force:
            result["skipped"] = True
            return result
        before = content.split(MIMIR_RULES_START)[0]
        after = content.split(MIMIR_RULES_END)[1]
        content = before.rstrip() + after

    # Append rules
    content = content.rstrip() + "\n" + MIMIR_RULES_BLOCK + "\n"
    system_context.write_text(content)
    result["injected"] = True

    return result


def install_mcp_config(opencode_config_dir: Path, mimir_root: Path) -> dict:
    """Merge Mimir MCP server config into global opencode.json.

    Preserves existing MCP entries. Returns status dict.
    """
    result = {"backed_up": False, "updated": False}

    config_path = opencode_config_dir / "opencode.json"
    backup_dir = opencode_config_dir / "mimir-backups"

    # Backup existing
    if config_path.exists():
        backup = backup_file(config_path, backup_dir)
        if backup:
            result["backed_up"] = str(backup)

    # Load existing or create new
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {"$schema": "https://opencode.ai/config.json"}

    if "mcp" not in config:
        config["mcp"] = {}

    # Add Mimir knowledge server
    mcp_server = mimir_root / "scripts" / "run_mcp_server.sh"
    config["mcp"]["mimir-knowledge"] = {
        "type": "local",
        "command": [str(mcp_server)],
        "enabled": True,
        "environment": {
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "LOG_LEVEL": "INFO",
        },
    }

    # Add OpenSpace server if available
    openspace_server = mimir_root / "scripts" / "run_openspace_mcp.sh"
    if openspace_server.exists():
        config["mcp"]["openspace"] = {
            "type": "local",
            "command": [str(openspace_server)],
            "environment": {
                "OPENSPACE_HOST_SKILL_DIRS": str(mimir_root / "skills"),
            },
            "enabled": True,
            "timeout": 600000,
        }

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    result["updated"] = True

    return result


def global_install(mimir_root: Path, opencode_config_dir: Path, force: bool) -> bool:
    """Run global installation: MCP config + system rules."""
    print(f"\n🔧 Global Mimir Install")
    print(f"   Mimir root: {mimir_root}")
    print(f"   OpenCode config: {opencode_config_dir}")

    # Check prerequisites
    mcp_server = mimir_root / "scripts" / "run_mcp_server.sh"
    if not mcp_server.exists():
        print(f"\n❌ MCP server not found at {mcp_server}")
        return False

    # 1. MCP config
    print("\n📦 MCP Server Config:")
    mcp_result = install_mcp_config(opencode_config_dir, mimir_root)
    if mcp_result["backed_up"]:
        print(f"   ✓ Backed up opencode.json → {mcp_result['backed_up']}")
    if mcp_result["updated"]:
        print(f"   ✓ Updated opencode.json with Mimir MCP server")

    # 2. System rules
    print("\n📋 System Rules:")
    rules_result = inject_system_rules(opencode_config_dir, force=force)
    if rules_result["backed_up"]:
        print(f"   ✓ Backed up system-context.md → {rules_result['backed_up']}")
    if rules_result["injected"]:
        print(f"   ✓ Injected Mimir rules into system-context.md")
    if rules_result["skipped"]:
        print(f"   ⏭️  Mimir rules already present (use --force to re-inject)")

    # 3. API key check
    api_key = get_openrouter_api_key()
    if api_key:
        print(f"\n🔑 OpenRouter API key found")
    else:
        print(f"\n⚠️  No OpenRouter API key found")
        print(f"   Set OPENROUTER_API_KEY or run: opencode auth openrouter")

    print(f"\n✅ Global install complete!")
    print(f"\nNext steps:")
    print(f"  1. Restart OpenCode to pick up the MCP server")
    mimir_cli = Path(__file__).resolve().parent / "mimir.py"
    print(f"  2. In any project, run: python {mimir_cli} init --code-dirs=src,tests")
    print(f"  3. Then use: mimir-knowledge_enrich_task()")
    print(f"\nTo uninstall: python {mimir_cli} uninstall")

    return True


# ─── Uninstall ────────────────────────────────────────────────────────────────


def global_uninstall(opencode_config_dir: Path) -> bool:
    """Remove Mimir from global config. Restores backups if available."""
    print(f"\n🗑️  Mimir Uninstall")
    backup_dir = opencode_config_dir / "mimir-backups"

    restored = False

    # Try to restore opencode.json from backup
    config_path = opencode_config_dir / "opencode.json"
    if restore_latest_backup("opencode.json", config_path, backup_dir):
        print(f"   ✓ Restored opencode.json from backup")
        restored = True
    elif config_path.exists():
        # Clean removal of Mimir entries
        config = json.loads(config_path.read_text())
        removed = []
        for key in ["mimir-knowledge", "openspace"]:
            if "mcp" in config and key in config.get("mcp", {}):
                del config["mcp"][key]
                removed.append(key)
        if removed:
            config_path.write_text(json.dumps(config, indent=2) + "\n")
            print(f"   ✓ Removed MCP entries: {', '.join(removed)}")
            restored = True

    # Try to restore system-context.md from backup
    system_context = opencode_config_dir / "prompts" / "system-context.md"
    if restore_latest_backup("system-context.md", system_context, backup_dir):
        print(f"   ✓ Restored system-context.md from backup")
        restored = True
    elif system_context.exists():
        # Clean removal using markers
        content = system_context.read_text()
        if MIMIR_RULES_START in content and MIMIR_RULES_END in content:
            before = content.split(MIMIR_RULES_START)[0]
            after = content.split(MIMIR_RULES_END)[1]
            system_context.write_text(before.rstrip() + after)
            print(f"   ✓ Removed Mimir rules from system-context.md")
            restored = True

    if not restored:
        print(f"   ℹ️  Nothing to uninstall")

    if backup_dir.exists():
        print(f"\n   Backups preserved at: {backup_dir}/")
        print(f"   To delete: rm -rf {backup_dir}")

    print(f"\n✅ Uninstall complete. Restart OpenCode to apply.")
    return True


# ─── Per-Project Init ─────────────────────────────────────────────────────────


def create_mimir_config(project_root: Path, code_dirs: list[str] = None) -> Path:
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


def create_project_setup_script(project_root: Path, mimir_root: Path) -> Path:
    """Create .opencode/mimir-index.py that delegates to central install."""
    opencode_dir = project_root / ".opencode"
    opencode_dir.mkdir(exist_ok=True)

    setup_script = opencode_dir / "mimir-index.py"
    template_script = mimir_root / ".opencode" / "mimir-index.py"

    if template_script.exists():
        shutil.copy2(template_script, setup_script)
        setup_script.chmod(0o755)
    else:
        script_content = f'''#!/usr/bin/env python3
"""Project indexing script — delegates to central Mimir installation."""
import subprocess, sys
from pathlib import Path

central = Path("{mimir_root / ".opencode" / "mimir-index.py"}").resolve()
if central.exists():
    subprocess.run([sys.executable, str(central)] + sys.argv[1:])
else:
    print("❌ Central mimir-index.py not found")
    sys.exit(1)
'''
        setup_script.write_text(script_content)
        setup_script.chmod(0o755)

    return setup_script


def create_agents_md(project_root: Path, mimir_root: Path) -> Path:
    """Copy AGENTS.md from Mimir to project's .mimir directory."""
    mimir_dir = project_root / ".mimir"
    mimir_dir.mkdir(exist_ok=True)

    source = mimir_root / "AGENTS.md"
    dest = mimir_dir / "AGENTS.md"

    if source.exists():
        shutil.copy2(source, dest)
    else:
        dest.write_text(
            "# Project Knowledge Base (Mimir)\n\nSee Mimir installation for docs.\n"
        )

    return dest


def init_project(project_root: Path, mimir_root: Path, args) -> bool:
    """Initialize a project for Mimir knowledge base."""
    try:
        from tqdm import tqdm
    except ImportError:
        # Fallback if tqdm not installed
        def tqdm(iterable, **kwargs):
            return iterable

        class tqdm:
            @staticmethod
            def write(msg):
                print(msg)

    print(f"\n🎯 Project init: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    opencode_dir = project_root / ".opencode"
    mimir_dir = project_root / ".mimir"

    # Create directories
    print("\n📁 Creating directories...")
    for d, desc in [
        (knowledge_dir, "Knowledge base"),
        (docs_dir, "Documents"),
        (opencode_dir, "OpenCode config"),
        (mimir_dir, "Mimir config"),
    ]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ {desc}: {d}")

    # Indexing script
    setup_script = opencode_dir / "mimir-index.py"
    if not setup_script.exists() or args.force:
        create_project_setup_script(project_root, mimir_root)
        print(f"   ✓ Created: {setup_script}")
    else:
        print(f"   ⏭️  Skipped: {setup_script} (exists)")

    # Mimir config
    config_path = mimir_dir / "config.json"
    if not config_path.exists() or args.force:
        code_dirs = args.code_dirs.split(",") if args.code_dirs else None
        create_mimir_config(project_root, code_dirs)
        print(f"   ✓ Created: {config_path}")
        if code_dirs:
            print(f"   Code directories: {code_dirs}")
    else:
        print(f"   ⏭️  Skipped: {config_path} (exists)")

    # AGENTS.md reference
    agents_path = mimir_dir / "AGENTS.md"
    if not agents_path.exists() or args.force:
        create_agents_md(project_root, mimir_root)
        print(f"   ✓ Created: {agents_path}")
    else:
        print(f"   ⏭️  Skipped: {agents_path} (exists)")

    # API key check
    api_key = get_openrouter_api_key()
    if api_key:
        print(f"\n🔑 OpenRouter API key found")
    else:
        print(f"\n⚠️  No OpenRouter API key found")
        print(f"   Set OPENROUTER_API_KEY or run: opencode auth openrouter")

    # Index documents
    if not args.no_index and docs_dir.exists() and any(docs_dir.iterdir()):
        print(f"\n📚 Indexing documents...")
        env = {**os.environ}
        if api_key:
            env["OPENROUTER_API_KEY"] = api_key

        index_script = opencode_dir / "mimir-index.py"
        result = subprocess.run(
            [sys.executable, str(index_script)],
            cwd=project_root,
            env=env,
        )

        if result.returncode != 0:
            print(f"\n❌ Indexing failed (exit code {result.returncode})")
            return False
    elif not args.no_index:
        print(f"\n⚠️  No documents to index yet")
        print(f"   Add files to docs/ then run: python .opencode/mimir-index.py")

    print(f"\n✅ Project initialized!")
    print(f"\nNext steps:")
    print(f"  1. Add docs to docs/ and code to your source dirs")
    print(f"  2. Index: python .opencode/mimir-index.py")
    print(f"  3. Query: mimir-knowledge_enrich_task('your question')")

    return True


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Mimir installer and project initializer"
    )

    # Mode selection
    parser.add_argument(
        "--install",
        action="store_true",
        help="Global install: set up MCP server and system rules (run once)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove Mimir from global config (restores backups)",
    )

    # Per-project options
    parser.add_argument(
        "--code-dirs",
        help="Comma-separated code directories to index (e.g., 'src,tests')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip initial document indexing",
    )

    # Override paths
    parser.add_argument(
        "--mimir-root",
        help="Path to Mimir installation (auto-detected if not provided)",
    )
    parser.add_argument(
        "--project-root",
        help="Project root directory (auto-detected if not provided)",
    )
    parser.add_argument(
        "--opencode-config",
        help="Path to OpenCode config directory (auto-detected if not provided)",
    )

    args = parser.parse_args()

    # Resolve Mimir root
    if args.mimir_root:
        mimir_root = Path(args.mimir_root).resolve()
    else:
        mimir_root = find_mimir_root()

    if not mimir_root or not mimir_root.exists():
        print("❌ Could not find Mimir installation")
        print("   Provide --mimir-root or run from the Mimir project")
        return 1

    # Resolve OpenCode config dir
    if args.opencode_config:
        opencode_config_dir = Path(args.opencode_config).resolve()
    else:
        opencode_config_dir = find_opencode_config_dir()

    # ─── Uninstall mode ───────────────────────────────────────────────────

    if args.uninstall:
        if not opencode_config_dir:
            print("❌ OpenCode config directory not found")
            return 1
        return 0 if global_uninstall(opencode_config_dir) else 1

    # ─── Global install mode ──────────────────────────────────────────────

    if args.install:
        if not opencode_config_dir:
            print("❌ OpenCode config directory not found")
            print("   Create it: mkdir -p ~/.config/opencode")
            return 1
        return 0 if global_install(mimir_root, opencode_config_dir, args.force) else 1

    # ─── Per-project init mode (default) ──────────────────────────────────

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = detect_project_root()

    return 0 if init_project(project_root, mimir_root, args) else 1


if __name__ == "__main__":
    sys.exit(main())
