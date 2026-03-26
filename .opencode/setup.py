#!/usr/bin/env python3
import json
import os
import subprocess
import sys
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


def detect_project_root() -> Path:
    cwd = Path.cwd().resolve()
    markers = [".opencode", ".git"]

    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


def main():
    project_root = detect_project_root()
    print(f"🎯 Project root: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(exist_ok=True)

    print(f"📁 Knowledge base: {knowledge_dir}")
    print(f"📁 Documents: {docs_dir}")

    api_key = get_openrouter_api_key()
    if not api_key:
        print("\n⚠️  Warning: OpenRouter API key not found")
        print("   Set OPENROUTER_API_KEY environment variable")
        return 1

    os.environ["OPENROUTER_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
    print("\n🔑 OpenRouter API key found")

    if (knowledge_dir / "index_store.json").exists():
        print("\n✅ Knowledge base already exists")
        response = input("   Rebuild from docs/? [y/N]: ")
        if response.lower() != "y":
            print("   Skipping reindex")
            return 0

    if docs_dir.exists() and any(docs_dir.iterdir()):
        print("\n📚 Indexing documents...")

        server_script = Path(__file__).parent.parent / "mcp_server_llamaindex.py"
        if not server_script.exists():
            server_script = (
                Path.home() / "Documents" / "Mimir" / "mcp_server_llamaindex.py"
            )

        result = subprocess.run(
            [sys.executable, str(server_script), "--index"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "OPENROUTER_API_KEY": api_key,
                "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            },
        )

        if result.returncode == 0:
            print(result.stdout)
            print("\n✅ Setup complete!")
        else:
            print(f"\n❌ Error: {result.stderr}")
            return 1
    else:
        print("\n⚠️  No documents found in docs/")
        print("   Add documentation files and run: python .opencode/setup.py")

    print("\n📖 Next steps:")
    print("   1. Add documents to docs/")
    print("   2. Run: python .opencode/setup.py")
    print("   3. Or let OpenCode auto-index on first use")

    return 0


if __name__ == "__main__":
    sys.exit(main())
