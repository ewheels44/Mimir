#!/usr/bin/env python3
"""
Multi-project knowledge base initializer for OpenCode MCP.

Run this in ANY project directory to set up the raveneye-knowledge MCP server.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def find_server_script() -> Path:
    candidates = [
        Path.cwd() / "mcp_server_llamaindex.py",
        Path(__file__).parent / "mcp_server_llamaindex.py",
        Path.home() / "Documents" / "Mimir" / "mcp_server_llamaindex.py",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return None


def detect_project_root() -> Path:
    cwd = Path.cwd().resolve()
    markers = [".opencode", ".git", "pyproject.toml", "package.json", "Cargo.toml"]

    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


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


def create_project_setup_script(project_root: Path, server_script: Path) -> Path:
    opencode_dir = project_root / ".opencode"
    opencode_dir.mkdir(exist_ok=True)

    setup_script = opencode_dir / "setup.py"

    # Copy the template setup.py from the Mimir directory
    template_script = server_script.parent / ".opencode" / "setup.py"

    if template_script.exists():
        import shutil

        shutil.copy2(template_script, setup_script)
        setup_script.chmod(0o755)
    else:
        # Fallback: create a minimal script that references the central one
        script_content = f'''#!/usr/bin/env python3
"""
Project setup script for Mimir knowledge base.

This script delegates to the central Mimir installation.
For the full implementation, see: {server_script.parent / ".opencode" / "setup.py"}
"""

import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    central_script = Path("{server_script.parent / ".opencode" / "setup.py"}").resolve()
    if central_script.exists():
        subprocess.run([sys.executable, str(central_script)] + sys.argv[1:])
    else:
        print("❌ Central setup.py not found")
        sys.exit(1)
'''
        with open(setup_script, "w") as f:
            f.write(script_content)
        setup_script.chmod(0o755)

    return setup_script


def create_mimir_config(project_root: Path, code_dirs: list[str] = None) -> Path:
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
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return config_path


def create_agents_md(project_root: Path, mimir_root: Path) -> Path:
    import shutil

    mimir_dir = project_root / ".mimir"
    mimir_dir.mkdir(exist_ok=True)

    source_agents = mimir_root / "AGENTS.md"
    dest_agents = mimir_dir / "AGENTS.md"

    if source_agents.exists():
        shutil.copy2(source_agents, dest_agents)
    else:
        dest_agents.write_text("""# Project Knowledge Base (Mimir)

## Learn More

- Full documentation: https://github.com/ewheels44/Mimir

---

*Powered by Mimir - Knowledge that follows you*
""")

    return dest_agents


def create_opencode_json(project_root: Path, mimir_root: Path) -> Path:
    """Create opencode.json with instructions array for AGENTS.md chaining.

    This enables OpenCode to load multiple AGENTS.md files in order:
    1. Mimir system documentation (base)
    2. Project root AGENTS.md (project-specific)
    3. Any subdirectory AGENTS.md files (subsystem-specific)

    Users should customize this based on their project structure.
    """
    opencode_json = project_root / "opencode.json"

    config = {
        "$schema": "https://opencode.ai/config.json",
        "instructions": [f"{mimir_root}/AGENTS.md", "AGENTS.md"],
    }

    with open(opencode_json, "w") as f:
        json.dump(config, f, indent=2)

    return opencode_json


def init_project(project_root: Path, server_script: Path, args) -> bool:
    print(f"🎯 Project root: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    opencode_dir = project_root / ".opencode"
    mimir_dir = project_root / ".mimir"

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    opencode_dir.mkdir(exist_ok=True)
    mimir_dir.mkdir(exist_ok=True)

    print(f"📁 Created: {knowledge_dir}")
    print(f"📁 Created: {docs_dir}")
    print(f"📁 Created: {opencode_dir}")
    print(f"📁 Created: {mimir_dir}")

    setup_script = opencode_dir / "setup.py"
    if not setup_script.exists() or args.force:
        create_project_setup_script(project_root, server_script)
        print(f"📝 Created: {setup_script}")
    else:
        print(f"⏭️  Skipped: {setup_script} (exists, use --force to overwrite)")

    config_path = mimir_dir / "config.json"
    if not config_path.exists() or args.force:
        code_dirs = args.code_dirs.split(",") if args.code_dirs else None
        config_path = create_mimir_config(project_root, code_dirs)
        print(f"📝 Created: {config_path}")
        if code_dirs:
            print(f"   Code directories: {code_dirs}")
    else:
        print(f"⏭️  Skipped: {config_path} (exists, use --force to overwrite)")

    mimir_root = server_script.parent
    agents_path = mimir_dir / "AGENTS.md"
    if not agents_path.exists() or args.force:
        agents_path = create_agents_md(project_root, mimir_root)
        print(f"📝 Created: {agents_path}")
    else:
        print(f"⏭️  Skipped: {agents_path} (exists, use --force to overwrite)")

    opencode_json_path = project_root / "opencode.json"
    if not opencode_json_path.exists() or args.force:
        opencode_json_path = create_opencode_json(project_root, mimir_root)
        print(f"📝 Created: {opencode_json_path}")
        print(
            "   ⚠️  IMPORTANT: Customize 'instructions' array for your project structure"
        )
    else:
        print(f"⏭️  Skipped: {opencode_json_path} (exists, use --force to overwrite)")

    local_server = project_root / "mcp_server_llamaindex.py"
    if not local_server.exists() and not args.server_path:
        print(f"ℹ️  Server script at: {server_script}")
        print("   (referenced from central location)")

    api_key = get_openrouter_api_key()
    if not api_key:
        print("\n⚠️  Warning: OpenRouter API key not found")
        print("   Set OPENROUTER_API_KEY environment variable")
        print("   Or configure it in OpenCode settings")
    else:
        print("\n🔑 OpenRouter API key found")

    if not args.no_index and docs_dir.exists() and any(docs_dir.iterdir()):
        print("\n📚 Indexing documents...")
        env = {**os.environ, "OPENROUTER_API_KEY": api_key or ""}

        result = subprocess.run(
            [sys.executable, str(server_script), "--index"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.returncode == 0:
            print(result.stdout)
            print("\n✅ Indexing complete!")
        else:
            print(f"\n❌ Indexing error: {result.stderr}")
            return False
    elif not args.no_index:
        print("\n⚠️  No documents to index yet")
        print("   Add files to docs/ and run: python .opencode/setup.py")

    print("\n✅ Project initialized successfully!")
    print("\n📖 Next steps:")
    print("   1. Read AGENTS.md for complete usage guide")
    print("   2. Add documentation files to docs/")
    print("   3. Run: python .opencode/setup.py")
    print("   4. Or let OpenCode auto-index on first use")
    print("   5. Edit .mimir/config.json to index source code directories")
    print("   6. Customize opencode.json to chain multiple AGENTS.md files")
    print("\n💡 Quick start:")
    print("   echo '# My Project' > docs/README.md")
    print("   python .opencode/setup.py")
    print("\n📚 AGENTS.md Hierarchy:")
    print("   See README.md 'AGENTS.md Hierarchy' section for details")
    print("   on chaining multiple AGENTS.md files via opencode.json")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Initialize knowledge MCP for any project"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing setup files"
    )
    parser.add_argument(
        "--no-index", action="store_true", help="Skip initial document indexing"
    )
    parser.add_argument(
        "--server-path",
        help="Path to mcp_server_llamaindex.py (auto-detected if not provided)",
    )
    parser.add_argument(
        "--project-root", help="Project root directory (default: auto-detect)"
    )
    parser.add_argument(
        "--code-dirs",
        help="Comma-separated list of code directories to index (e.g., 'src,tests,lib')",
    )

    args = parser.parse_args()

    if args.server_path:
        server_script = Path(args.server_path).resolve()
        if not server_script.exists():
            print(f"❌ Server script not found: {server_script}")
            return 1
    else:
        server_script = find_server_script()
        if not server_script:
            print("❌ Could not find mcp_server_llamaindex.py")
            print("   Provide --server-path or run from the RavenEye project")
            return 1

    print(f"📜 Server script: {server_script}")

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = detect_project_root()

    success = init_project(project_root, server_script, args)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
