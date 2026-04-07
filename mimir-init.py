#!/usr/bin/env python3
"""
mimir-init.py - Initialize a new project for Mimir knowledge base.

Run this in ANY project directory to set up Mimir integration.
This creates the necessary directories and configuration files.

Usage:
    python ~/Documents/Mimir/mimir-init.py
    python ~/Documents/Mimir/mimir-init.py --code-dirs=src,tests

The --code-dirs flag pre-configures source code directories for indexing.
If not specified, you can later add code_dirs to .mimir/config.json
or use --add with mimir-index.py for incremental indexing.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_opencode_config_dir() -> Path | None:
    """Detect the OpenCode global config directory.

    Checks common locations:
    - ~/.config/opencode-openagents/
    - ~/.config/opencode/
    - ~/.config/oh-my-opencode/

    Returns the first existing directory, or None if not found.
    """
    candidates = [
        Path.home() / ".config" / "opencode-openagents",
        Path.home() / ".config" / "opencode",
        Path.home() / ".config" / "oh-my-opencode",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def install_opencode_plugin(
    mimir_root: Path, config_dir: Path, force: bool = False
) -> list[Path]:
    """Install the Mimir system-prompt plugin into OpenCode's config directory.

    Copies:
    - opencode-plugin/plugin/system-prompt.ts -> {config_dir}/plugin/
    - opencode-plugin/prompts/system-context.md -> {config_dir}/prompts/

    Returns list of installed file paths.
    """
    plugin_source = mimir_root / "opencode-plugin" / "plugin" / "system-prompt.ts"
    prompt_source = mimir_root / "opencode-plugin" / "prompts" / "system-context.md"

    if not plugin_source.exists():
        print(f"   ⚠️  Plugin source not found: {plugin_source}")
        return []

    installed = []

    plugin_dir = config_dir / "plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_dest = plugin_dir / "system-prompt.ts"

    if not plugin_dest.exists() or force:
        shutil.copy2(plugin_source, plugin_dest)
        installed.append(plugin_dest)

    prompt_dir = config_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_dest = prompt_dir / "system-context.md"

    if not prompt_dest.exists() or force:
        shutil.copy2(prompt_source, prompt_dest)
        installed.append(prompt_dest)

    return installed


def install_opencode_agents(
    mimir_root: Path, config_dir: Path, force: bool = False
) -> list[Path]:
    """Install Mimir-enhanced agent definitions into OpenCode's config directory.

    These agent definitions include Mimir MCP tool permissions, ensuring subagents
    can use mimir-knowledge_* tools for project-specific queries.

    Copies:
    - opencode-config/agent/subagents/core/*.md -> {config_dir}/agent/subagents/core/
    - opencode-config/agent/subagents/code/*.md -> {config_dir}/agent/subagents/code/

    Backs up existing files before overwriting.

    Returns list of installed file paths.
    """
    agent_source_dir = mimir_root / "opencode-config" / "agent"

    if not agent_source_dir.exists():
        print(f"   ⚠️  Agent source directory not found: {agent_source_dir}")
        return []

    installed = []
    agent_dest_dir = config_dir / "agent"

    # Define which agent files to install
    agent_files = [
        ("subagents/core/contextscout.md", "ContextScout"),
        ("subagents/core/task-manager.md", "TaskManager"),
        ("subagents/code/coder-agent.md", "CoderAgent"),
    ]

    for rel_path, agent_name in agent_files:
        source_file = agent_source_dir / rel_path
        dest_file = agent_dest_dir / rel_path

        if not source_file.exists():
            print(f"   ⚠️  Agent source not found: {source_file}")
            continue

        # Create parent directories
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file if it exists and we're forcing
        if dest_file.exists() and force:
            backup_file = dest_file.with_suffix(f".md.backup-{int(time.time())}")
            shutil.copy2(dest_file, backup_file)
            print(f"   📦 Backed up: {backup_file.name}")

        if not dest_file.exists() or force:
            shutil.copy2(source_file, dest_file)
            installed.append(dest_file)
            print(f"   ✓ Installed agent: {agent_name}")
        else:
            print(f"   ⏭️  Skipped: {agent_name} (exists, use --force to overwrite)")

    return installed


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

    setup_script = opencode_dir / "mimir-index.py"
    template_script = server_script.parent / ".opencode" / "mimir-index.py"

    if template_script.exists():
        shutil.copy2(template_script, setup_script)
        setup_script.chmod(0o755)
    else:
        script_content = f'''#!/usr/bin/env python3
"""
Project indexing script for Mimir knowledge base.

This script delegates to the central Mimir installation.
"""

import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    central_script = Path("{server_script.parent / ".opencode" / "mimir-index.py"}").resolve()
    if central_script.exists():
        subprocess.run([sys.executable, str(central_script)] + sys.argv[1:])
    else:
        print("❌ Central mimir-index.py not found")
        sys.exit(1)
'''
        with open(setup_script, "w") as f:
            f.write(script_content)
        setup_script.chmod(0o755)

    return setup_script


def create_agents_md(project_root: Path, mimir_root: Path) -> Path:
    """Copy AGENTS.md from Mimir installation to project's .mimir directory.

    This provides a local copy of the Mimir documentation that can be
    referenced in opencode.json for AGENTS.md chaining.
    """
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
- See AGENTS.md in the Mimir installation directory for complete guide

---

*Powered by Mimir - Knowledge that follows you*
""")

    return dest_agents


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


def create_mimir_skill(project_root: Path, mimir_root: Path) -> Path:
    """Create a Mimir skill file for subagent context inheritance.

    NOTE: The load_skills parameter does NOT exist in the task tool.
    Instead, subagents now have Mimir tool permissions built-in.

    This skill file is kept for reference and can be used to embed
    Mimir instructions directly in prompts for subagents that don't
    have built-in Mimir permissions (explore, librarian).

    Usage for subagents with built-in Mimir permissions (ContextScout, CoderAgent, TaskManager):
        task(
            subagent_type="ContextScout",
            prompt="Find patterns. Use mimir-knowledge_search for project queries."
        )

    Usage for other subagents (explore, librarian):
        task(
            subagent_type="explore",
            prompt="Find patterns. IMPORTANT: Use mimir-knowledge_search instead of grep."
        )
    """
    skills_dir = project_root / ".opencode" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    source_agents = mimir_root / "AGENTS.md"
    agents_content = source_agents.read_text() if source_agents.exists() else ""

    skill_content = f"""---
name: mimir
description: Mimir knowledge base directives for subagent context inheritance. Subagents now have Mimir tool permissions built-in - just include instructions in your prompt to use them.
---

# Mimir Knowledge Base — Subagent Context

This skill ensures that spawned subagents receive the full Mimir context
that would otherwise be missing when they are created via task().

## Why This Skill Is Needed

When you spawn a subagent using:
```
task(subagent_type="explore", prompt="...")
```

The subagent starts with a clean context containing only:
- Base agent configuration from ~/.config/opencode/oh-my-opencode.json
- The task prompt you provide
- NOT the project-specific opencode.json instructions
- NOT the full AGENTS.md directives

## How to Use

**Note**: The `load_skills` parameter does NOT exist in the task tool. Instead, subagents now have Mimir tool permissions built-in.

For subagents with built-in Mimir permissions (ContextScout, CoderAgent, TaskManager), just include instructions:

```
task(
    subagent_type="ContextScout",
    prompt="Find authentication patterns. Use mimir-knowledge_search for project-specific queries."
)
```

For other subagents (explore, librarian), embed Mimir instructions in the prompt:

```
task(
    subagent_type="explore",
    run_in_background=true,
    prompt="Find auth implementations. IMPORTANT: Use mimir-knowledge_search for project-specific queries instead of grep when available."
)
```

---

{agents_content}
"""

    skill_path = skills_dir / "mimir.md"
    with open(skill_path, "w") as f:
        f.write(skill_content)

    return skill_path


def init_project(project_root: Path, server_script: Path, args) -> bool:
    from tqdm import tqdm
    import time

    print(f"🎯 Project root: {project_root}")

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    docs_dir = project_root / "docs"
    opencode_dir = project_root / ".opencode"
    mimir_dir = project_root / ".mimir"

    directories = [
        (knowledge_dir, "Knowledge base"),
        (docs_dir, "Documents"),
        (opencode_dir, "OpenCode config"),
        (mimir_dir, "Mimir config"),
    ]

    print("\n📁 Creating directories...")
    for dir_path, desc in tqdm(directories, desc="   Creating", unit="dir", ncols=80):
        dir_path.mkdir(parents=True, exist_ok=True)
        tqdm.write(f"   ✓ {desc}: {dir_path}")

    setup_script = opencode_dir / "mimir-index.py"
    if not setup_script.exists() or args.force:
        create_project_setup_script(project_root, server_script)
        tqdm.write(f"   ✓ Created: {setup_script}")
    else:
        tqdm.write(f"   ⏭️  Skipped: {setup_script} (exists, use --force to overwrite)")

    config_path = mimir_dir / "config.json"
    if not config_path.exists() or args.force:
        code_dirs = args.code_dirs.split(",") if args.code_dirs else None
        config_path = create_mimir_config(project_root, code_dirs)
        tqdm.write(f"   ✓ Created: {config_path}")
        if code_dirs:
            tqdm.write(f"   Code directories: {code_dirs}")
    else:
        tqdm.write(f"   ⏭️  Skipped: {config_path} (exists, use --force to overwrite)")

    mimir_root = server_script.parent

    agents_path = mimir_dir / "AGENTS.md"
    if not agents_path.exists() or args.force:
        agents_path = create_agents_md(project_root, mimir_root)
        tqdm.write(f"   ✓ Created: {agents_path}")
    else:
        tqdm.write(f"   ⏭️  Skipped: {agents_path} (exists, use --force to overwrite)")

    opencode_json_path = project_root / "opencode.json"
    if not opencode_json_path.exists() or args.force:
        opencode_json_path = create_opencode_json(project_root, mimir_root)
        tqdm.write(f"   ✓ Created: {opencode_json_path}")
        tqdm.write(
            "   ⚠️  IMPORTANT: Customize 'instructions' array for your project structure"
        )
    else:
        tqdm.write(
            f"   ⏭️  Skipped: {opencode_json_path} (exists, use --force to overwrite)"
        )

    mimir_skill_path = project_root / ".opencode" / "skills" / "mimir.md"
    if not mimir_skill_path.exists() or args.force:
        mimir_skill_path = create_mimir_skill(project_root, mimir_root)
        tqdm.write(f"   ✓ Created: {mimir_skill_path}")
        tqdm.write(
            "   ⚠️  IMPORTANT: Subagents now have Mimir tool permissions built-in."
        )
        tqdm.write(
            "      Just include instructions: 'Use mimir-knowledge_search for project queries.'"
        )
    else:
        tqdm.write(
            f"   ⏭️  Skipped: {mimir_skill_path} (exists, use --force to overwrite)"
        )

    if args.opencode_config:
        opencode_config_dir = Path(args.opencode_config).resolve()
    else:
        opencode_config_dir = find_opencode_config_dir()

    if opencode_config_dir and opencode_config_dir.exists():
        installed = install_opencode_plugin(mimir_root, opencode_config_dir, args.force)
        if installed:
            for f in installed:
                tqdm.write(f"   ✓ Installed plugin: {f}")
            tqdm.write("   ⚠️  Restart OpenCode for plugin changes to take effect")
        else:
            tqdm.write(
                f"   ⏭️  Plugin already installed in {opencode_config_dir}/plugin/ (use --force to overwrite)"
            )

        # Install Mimir-enhanced agent definitions
        tqdm.write("\n🤖 Installing Mimir-enhanced agent definitions...")
        installed_agents = install_opencode_agents(
            mimir_root, opencode_config_dir, args.force
        )
        if installed_agents:
            tqdm.write(f"   ✓ Installed {len(installed_agents)} agent definitions")
            tqdm.write("   ⚠️  Restart OpenCode for agent changes to take effect")
    else:
        tqdm.write("   ⚠️  OpenCode config dir not found — plugin not installed")
        tqdm.write(
            "      Use --opencode-config=/path/to/config or create ~/.config/opencode-openagents/"
        )

    local_server = project_root / "mcp_server_llamaindex.py"
    if not local_server.exists() and not args.server_path:
        tqdm.write(f"ℹ️  Server script at: {server_script}")
        tqdm.write("   (referenced from central location)")

    api_key = get_openrouter_api_key()
    if not api_key:
        print("\n⚠️  Warning: OpenRouter API key not found")
        print("   Set OPENROUTER_API_KEY environment variable")
        print("   Or configure it in OpenCode settings")
    else:
        print("\n🔑 OpenRouter API key found")

    if not args.no_index and docs_dir.exists() and any(docs_dir.iterdir()):
        print("\n📚 Starting document indexing...")
        print("   (This may take a few minutes for large projects)")
        print()
        env = {**os.environ, "OPENROUTER_API_KEY": api_key or ""}

        index_script = project_root / ".opencode" / "mimir-index.py"
        result = subprocess.run(
            [sys.executable, str(index_script)],
            cwd=project_root,
            env=env,
        )

        if result.returncode != 0:
            print(f"\n❌ Indexing failed with exit code: {result.returncode}")
            return False
    elif not args.no_index:
        print("\n⚠️  No documents to index yet")
        print("   Add files to docs/ and run: python .opencode/mimir-index.py")

    print("\n✅ Project initialized successfully!")
    print("\n📖 Next steps:")
    print("   1. Add documentation files to docs/")
    print("      Example: echo '# My Project' > docs/README.md")
    print("\n   2. Index your documents:")
    print("      python .opencode/mimir-index.py")
    print("\n   3. Include source code in indexing (optional):")
    print("      A. Edit .mimir/config.json and add:")
    print('         "code_dirs": ["src", "tests", "lib"]')
    print("      B. Then reindex:")
    print("         python .opencode/mimir-index.py --reindex")
    print("      C. Or use incremental adds:")
    print("         python .opencode/mimir-index.py --add src")
    print("\n   4. Query your knowledge base:")
    print(
        "      Via CLI: python ~/Documents/Mimir/mcp_server_llamaindex.py --query 'your question'"
    )
    print(
        "      Via OpenCode: Just ask questions and Mimir tools will search automatically"
    )
    print("\n   5. OpenCode MCP Integration:")
    print("      The MCP server is configured in ~/.config/opencode/opencode.json")
    print("      and will automatically provide search/query tools to OpenCode agents.")
    print(
        "      Customize opencode.json to chain AGENTS.md files for multi-module projects."
    )
    print("\n   6. Using with Subagents:")
    print("      Subagents (ContextScout, CoderAgent, TaskManager) now have Mimir")
    print("      tool permissions built-in. Just include instructions in your prompt:")
    print("         task(")
    print("             subagent_type='ContextScout',")
    print(
        "             prompt='Find patterns. Use mimir-knowledge_search for project queries.'"
    )
    print("         )")
    print("      For other subagents (explore, librarian), embed Mimir instructions:")
    print("         task(")
    print("             subagent_type='explore',")
    print(
        "             prompt='Find patterns. IMPORTANT: Use mimir-knowledge_search instead of grep.'"
    )
    print("         )")
    print("\n🌐 Web UI:")
    print("   ./ ~/Documents/Mimir/scripts/start_web_ui.sh")
    print("   Then open http://localhost:8000")
    print("\n📚 Documentation:")
    print("   See README.md for complete user guide and usage examples")

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
    parser.add_argument(
        "--opencode-config",
        help="Path to OpenCode config directory (auto-detected if not provided)",
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
            print("   Provide --server-path or run from the Mimir project")
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
