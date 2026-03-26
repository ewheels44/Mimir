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

    script_content = f'''#!/usr/bin/env python3
import json
import os
import sys
import subprocess
from pathlib import Path


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


def main():
    project_root = Path("{project_root}").resolve()
    server_script = Path("{server_script}").resolve()
    
    print(f"🎯 Project root: {{project_root}}")
    print(f"📜 Server script: {{server_script}}")
    
    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    
    print(f"📁 Knowledge base: {{knowledge_dir}}")
    print(f"📁 Documents: {{docs_dir}}")
    
    api_key = get_openrouter_api_key()
    if not api_key:
        print("\\n⚠️  Warning: OpenRouter API key not found")
        print("   Set OPENROUTER_API_KEY environment variable")
        return 1
    
    os.environ["OPENROUTER_API_KEY"] = api_key
    print("\\n🔑 OpenRouter API key found")
    
    if (knowledge_dir / "index_store.json").exists():
        print("\\n✅ Knowledge base already exists")
        response = input("   Rebuild from docs/? [y/N]: ")
        if response.lower() != "y":
            print("   Skipping reindex")
            return 0
    
    if docs_dir.exists() and any(docs_dir.iterdir()):
        print("\\n📚 Indexing documents...")
        
        result = subprocess.run(
            [sys.executable, str(server_script), "--index"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={{**os.environ, "OPENROUTER_API_KEY": api_key}}
        )
        
        if result.returncode == 0:
            print(result.stdout)
            print("\\n✅ Setup complete!")
        else:
            print(f"\\n❌ Error: {{result.stderr}}")
            return 1
    else:
        print("\\n⚠️  No documents found in docs/")
        print("   Add documentation files and run: python .opencode/setup.py")
    
    print("\\n📖 Next steps:")
    print("   1. Add documents to docs/")
    print("   2. Run: python .opencode/setup.py")
    print("   3. Or let OpenCode auto-index on first use")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

    with open(setup_script, "w") as f:
        f.write(script_content)

    setup_script.chmod(0o755)
    return setup_script


def init_project(project_root: Path, server_script: Path, args) -> bool:
    print(f"🎯 Project root: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    opencode_dir = project_root / ".opencode"

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)
    opencode_dir.mkdir(exist_ok=True)

    print(f"📁 Created: {knowledge_dir}")
    print(f"📁 Created: {docs_dir}")
    print(f"📁 Created: {opencode_dir}")

    setup_script = opencode_dir / "setup.py"
    if not setup_script.exists() or args.force:
        create_project_setup_script(project_root, server_script)
        print(f"📝 Created: {setup_script}")
    else:
        print(f"⏭️  Skipped: {setup_script} (exists, use --force to overwrite)")

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
    print("   1. Add documentation files to docs/")
    print("   2. Run: python .opencode/setup.py")
    print("   3. Or let OpenCode auto-index on first use")
    print("   4. The MCP server will automatically use ${workspaceFolder} for paths")

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
