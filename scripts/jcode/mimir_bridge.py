#!/usr/bin/env python3
"""
Mimir ↔ Jcode Bridge
====================
Detects Mimir-enabled projects and auto-registers Mimir's MCP tools
with the Jcode agent server so agents can use deep project knowledge
without manual configuration.

Usage:
    python mimir_bridge.py [--project-root /path/to/project]
    python mimir_bridge.py --register-skill
    python mimir_bridge.py --check
"""

import json
import os
import sys
from pathlib import Path


# ── Auto-detection ──────────────────────────────────────────────────────────

def find_project_root(cwd: Path | None = None) -> Path | None:
    """Walk up from cwd to find a directory containing .knowledge/llamaindex/."""
    cwd = cwd or Path.cwd()
    for d in [cwd, *cwd.parents]:
        if (d / ".knowledge" / "llamaindex").exists():
            return d
    return None


def find_mimir_root() -> Path | None:
    """Find the Mimir installation root."""
    # Try relative to this script
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "mcp_server_llamaindex.py").exists():
        return candidate

    # Try standard install path
    home_mimir = Path.home() / "Documents" / "Mimir"
    if (home_mimir / "mcp_server_llamaindex.py").exists():
        return home_mimir

    # Try adjacent to this script (dev layout)
    return None


def find_jcode_socket() -> Path | None:
    """Find the running Jcode server's Unix socket."""
    # Jcode uses a socket at /var/folders/.../jcode.sock on macOS
    env_sock = os.environ.get("JCODE_SOCKET")
    if env_sock and Path(env_sock).exists():
        return Path(env_sock)

    socket_dir = Path("/var/folders")
    if socket_dir.exists():
        for sock in socket_dir.rglob("jcode.sock"):
            if sock.exists():
                return sock
    return None


def is_jcode_running() -> bool:
    """Check if Jcode server is active."""
    return find_jcode_socket() is not None


# ── MCP Server management ────────────────────────────────────────────────────

def read_mcp_config(config_file: Path) -> dict:
    """Read a Jcode MCP config file."""
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}


def write_mcp_config(data: dict, config_file: Path) -> None:
    """Write a Jcode MCP config file."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(data, indent=2))


def get_config_file(local: bool, project_root: Path) -> tuple[Path, str]:
    """Get MCP config file path and description.
    
    Args:
        local: If True, use project-local .jcode/mcp.json. If False, use global.
        project_root: Project root for local config.
        
    Returns:
        (config_file_path, server_name_prefix)
    """
    if local:
        config_file = project_root / ".jcode" / "mcp.json"
        # For local configs, use simple "mimir" name since it's project-local anyway
        server_name = "mimir"
    else:
        config_file = Path.home() / ".jcode" / "mcp.json"
        server_name = f"mimir-{project_root.name}"
    return config_file, server_name


def register_mcp_server(
    project_root: Path,
    mimir_root: Path,
    local: bool = True,
) -> str:
    """Register Mimir's MCP server in Jcode's config.
    
    Args:
        project_root: Root of the project to register.
        mimir_root: Root of the Mimir installation.
        local: If True, use project-local .jcode/mcp.json (recommended).
               If False, use global ~/.jcode/mcp.json.
    """
    mcp_path = str(mimir_root / "mcp_server_llamaindex.py")
    config_file, server_name = get_config_file(local, project_root)

    config = read_mcp_config(config_file)

    if "servers" not in config:
        config["servers"] = {}

    if server_name in config["servers"]:
        mode = "local" if local else "global"
        return f"ℹ️  Mimir server '{server_name}' already registered ({mode})"

    config["servers"][server_name] = {
        "command": sys.executable,
        "args": [mcp_path],
        "env": {
            # NOTE: PROJECT_ROOT not needed - MCP server auto-detects from CWD
            # This is the key benefit of project-local config!
            "PYTHONPATH": str(mimir_root / "src"),
        },
    }

    write_mcp_config(config, config_file)
    mode = "local" if local else "global"
    return (
        f"✅ Registered Mimir MCP server '{server_name}' "
        f"for project {project_root.name} ({mode}) → {config_file}"
    )


def unregister_mcp_server(project_name: str, local: bool = True) -> str:
    """Remove a Mimir MCP server from Jcode config.
    
    Args:
        project_name: Name of the project to unregister.
        local: If True, use project-local .jcode/mcp.json.
    """
    project_root = find_project_root() or Path.cwd()
    config_file, server_name = get_config_file(local, project_root)

    config = read_mcp_config(config_file)

    if "servers" in config and server_name in config["servers"]:
        del config["servers"][server_name]
        write_mcp_config(config, config_file)
        mode = "local" if local else "global"
        return f"✅ Removed Mimir server '{server_name}' from config ({mode})"
    return f"ℹ️  Server '{server_name}' not found in config"


# ── Skill registration ─────────────────────────────────────────────────────

def get_mimir_skill(project_root: Path) -> dict:
    """Generate the Mimir skill content for a specific project."""
    return {
        "name": f"mimir-{project_root.name}",
        "description": (
            f"Deep project knowledge for {project_root.name}. "
            f"Uses semantic search, knowledge graph queries, and RAG "
            f"over the indexed codebase at {project_root}."
        ),
        "usage_when": [
            "User asks about project-specific code, architecture, or patterns",
            "User asks 'how does X work?' or 'where is Y used?'",
            "User needs to understand dependencies between modules",
            "User asks for documentation about internal libraries or APIs",
            "User starts a task and needs project context injected",
        ],
        "tools": [
            {
                "name": "mimir-knowledge_search",
                "description": "Semantic search across indexed project docs and code",
                "when": "Finding patterns, searching for code examples, looking up APIs",
            },
            {
                "name": "mimir-knowledge_query",
                "description": "Synthesized answers from the knowledge base using RAG",
                "when": "Answering complex questions about how the project works",
            },
            {
                "name": "mimir-knowledge_enrich_task",
                "description": "Get project-specific context before executing a task",
                "when": "Starting any task — provides conventions, patterns, and context",
            },
            {
                "name": "mimir-knowledge_graph_query",
                "description": "Find shortest path between two modules using weighted Dijkstra",
                "when": "Understanding how modules connect, tracing dependencies",
            },
            {
                "name": "mimir-knowledge_graph_neighbors",
                "description": "Find what connects to a given module or entity",
                "when": "Exploring a module's dependencies or finding related code",
            },
            {
                "name": "mimir-knowledge_sdk_cache_get",
                "description": "Get cached SDK/library documentation (7-day TTL)",
                "when": "Looking up external library APIs without burning tokens",
            },
            {
                "name": "mimir-knowledge_rag_workflow",
                "description": "Structured retrieve→generate pipeline for complex analysis",
                "when": "Deep analysis requiring multiple retrieval + reasoning steps",
            },
        ],
        "config": {
            "auto_activate": "smart",  # Uses should_use_mimir() classifier
            "priority": "high",
            "max_context_tokens": 8000,
            "activation": {
                "mode": "smart",  # Options: on|off|smart
                "skip_patterns": [
                    "git", "ls", "cd", "mkdir", "rm",
                    "readme", "license", "changelog"
                ],
                "require_keywords": [
                    "code", "function", "class", "bug", "feature",
                    "implement", "fix", "refactor", "test"
                ]
            }
        },
    }


def register_skill(project_root: Path) -> str:
    """Register the Mimir skill for a project."""
    skill = get_mimir_skill(project_root)

    # Skills directory in Jcode config
    skills_dir = Path.home() / ".jcode" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skill_file = skills_dir / f"mimir-{project_root.name}.json"
    skill_file.write_text(json.dumps(skill, indent=2))

    return (
        f"✅ Registered Mimir skill '{skill['name']}' "
        f"→ {skill_file}"
    )


# ── Jcode system prompt injection ───────────────────────────────────────────

def get_jcode_mimir_prompt(project_root: Path) -> str:
    """Generate the system prompt section for Mimir integration."""
    return f"""
## Mimir Knowledge Base (Auto-generated)

You have access to deep project knowledge for **{project_root.name}**.
The knowledge base is located at `{project_root / ".knowledge" / "llamaindex"}`
and includes semantic search, a code knowledge graph, and RAG workflows.

### Smart Auto-Activation (NEW)

Mimir now uses **smart activation** - it automatically decides when to use
project knowledge based on the task:

**ALWAYS use Mimir for:**
- Tasks with code keywords: "function", "class", "bug", "feature", "refactor", "implement", "fix"
- Questions: "how does X work?", "where is Y used?", "trace Z"
- Architecture tasks: "design", "pattern", "flow", "dependency"

**SKIP Mimir for:**
- Shell operations: `git`, `ls`, `cd`, `mkdir`, `rm`, `cp`, `mv`
- Documentation-only: editing README, LICENSE, CHANGELOG
- Non-project questions: weather, time, general knowledge

**Decision rule:**
If the task mentions code, functions, classes, bugs, features, or asks
"how/where/why" about the project → use Mimir.
If it's shell commands or docs → skip Mimir.

### When to use Mimir tools:
1. **Before starting any task**: Call `mimir-knowledge_enrich_task(task_description)`
   to get project-specific conventions, patterns, and context.

2. **Understanding code**: Use `mimir-knowledge_query(question)` for synthesized
   answers about how the codebase works.

3. **Finding code patterns**: Use `mimir-knowledge_search(query)` for semantic
   search across indexed docs and code.

4. **Tracing dependencies**: Use `mimir-knowledge_graph_query(source, target)`
   to find the shortest path between modules, or
   `mimir-knowledge_graph_neighbors(module)` to explore connections.

5. **External library docs**: Use `mimir-knowledge_sdk_cache_get(library, topic)`
   before searching the web — cached docs save tokens and are faster.

### Decision flow:
- Need to understand existing code? → `mimir-knowledge_query`
- Need to find a pattern or example? → `mimir-knowledge_search`
- Starting a task? → `mimir-knowledge_enrich_task` FIRST, then implement
- Need to trace how X connects to Y? → `mimir-knowledge_graph_query`
- External library question? → `mimir-knowledge_sdk_cache_get` → web fallback

### Programmatic check:
For automation, use the `should_use_mimir()` function from `mimir.activation`
to programmatically determine if Mimir should be used for a task.
"""


def inject_mimir_prompt(project_root: Path) -> str:
    """Add Mimir context to the Jcode system prompt if not already present."""
    prompt_dir = Path.home() / ".jcode" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    # Use project-specific prompt file
    prompt_file = prompt_dir / f"mimir-{project_root.name}.md"
    existing = ""
    if prompt_file.exists():
        existing = prompt_file.read_text()

    mimir_section = get_jcode_mimir_prompt(project_root)

    if "Mimir Knowledge Base" in existing:
        return f"ℹ️  Mimir prompt already in {prompt_file}"

    updated = existing.rstrip() + "\n" + mimir_section
    prompt_file.write_text(updated.strip() + "\n")

    return f"✅ Injected Mimir system prompt → {prompt_file}"


# ── Main ────────────────────────────────────────────────────────────────────

def print_usage():
    print(__doc__)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Bridge Mimir knowledge base with Jcode agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--project-root", "-p",
        type=Path,
        help="Project root directory (auto-detected if not specified)",
    )
    parser.add_argument(
        "--register-skill",
        action="store_true",
        help="Register Mimir as a Jcode skill",
    )
    parser.add_argument(
        "--inject-prompt",
        action="store_true",
        help="Inject Mimir system prompt into Jcode",
    )
    parser.add_argument(
        "--unregister",
        action="store_true",
        help="Remove Mimir from Jcode config",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check current integration status",
    )
    parser.add_argument(
        "--use-global",
        action="store_true",
        help="Use global ~/.jcode/mcp.json instead of project-local",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Full auto-setup: register skill + inject prompt + MCP server",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output",
    )

    args = parser.parse_args()

    # Auto-detect project root
    project_root = args.project_root or find_project_root()
    if not project_root:
        print("❌ No Mimir-enabled project found.")
        print("   Run this from within a Mimir project, or use --project-root /path/to/project")
        sys.exit(1)

    mimir_root = find_mimir_root()
    if not mimir_root:
        print("❌ Could not find Mimir installation.")
        sys.exit(1)

    # Determine local vs global mode (local is default)
    use_local = not args.use_global

    if args.check:
        print(f"📍 Project: {project_root}")
        print(f"📦 Mimir:   {mimir_root}")
        print(f"🧠 Index:   {project_root / '.knowledge' / 'llamaindex'}")

        jcode_running = is_jcode_running()
        print(f"🔧 Jcode:   {'Running' if jcode_running else 'Not running'}")

        if jcode_running:
            sock = find_jcode_socket()
            print(f"   Socket:   {sock}")

        skills_dir = Path.home() / ".jcode" / "skills"
        skill_file = skills_dir / f"mimir-{project_root.name}.json"
        print(f"🗂️  Skill:   {'Registered' if skill_file.exists() else 'Not registered'}")

        # Check both local and global MCP configs
        local_config_file = project_root / ".jcode" / "mcp.json"
        global_config_file = Path.home() / ".jcode" / "mcp.json"
        local_config = read_mcp_config(local_config_file)
        global_config = read_mcp_config(global_config_file)
        local_has = "servers" in local_config and "mimir" in local_config["servers"]
        global_has = "servers" in global_config and f"mimir-{project_root.name}" in global_config["servers"]
        print(f"🔗 MCP:     {'Local ✅' if local_has else 'Local ❌'} / {'Global ✅' if global_has else 'Global ❌'}")
        return

    if args.unregister:
        project_name = project_root.name
        msg1 = unregister_mcp_server(project_name, local=use_local)
        # Also remove skill file
        skill_file = Path.home() / ".jcode" / "skills" / f"mimir-{project_name}.json"
        if skill_file.exists():
            skill_file.unlink()
            msg2 = f"✅ Removed skill file {skill_file}"
        else:
            msg2 = "ℹ️  No skill file to remove"
        print(msg1)
        print(msg2)
        return

    results = []

    # Register skill
    if args.register_skill or args.auto:
        results.append(register_skill(project_root))

    # Inject system prompt
    if args.inject_prompt or args.auto:
        results.append(inject_mimir_prompt(project_root))

    # Register MCP server (local by default)
    if args.auto:
        results.append(register_mcp_server(project_root, mimir_root, local=use_local))

    if not args.quiet or not results:
        print(f"\n📍 Project: {project_root}")
        print(f"📦 Mimir:   {mimir_root}")
        print(f"📋 Mode:    {'Project-local' if use_local else 'Global'} .jcode/mcp.json")
        print()
        for r in results:
            print(f"  {r}")
        print()
        if use_local:
            print("💡 Project-local config - MCP server auto-detects project from CWD.")
            print("   No hardcoded PROJECT_ROOT needed. Works across all projects!")
        print("💡 Start Jcode to use Mimir tools. If Jcode is already running,")
        print("   run `/mcp reload` in the Jcode TUI to pick up the new server.")


if __name__ == "__main__":
    main()