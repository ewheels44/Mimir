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

def read_mcp_config() -> dict:
    """Read the Jcode MCP config file (~/.jcode/mcp.json)."""
    config_dir = Path.home() / ".jcode"
    config_file = config_dir / "mcp.json"
    if config_file.exists():
        return json.loads(config_file.read_text())
    return {}


def write_mcp_config(data: dict) -> None:
    """Write the Jcode MCP config file (~/.jcode/mcp.json)."""
    config_dir = Path.home() / ".jcode"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "mcp.json"
    config_file.write_text(json.dumps(data, indent=2))


def register_mcp_server(project_root: Path, mimir_root: Path) -> str:
    """Register Mimir's MCP server in Jcode's config (~/.jcode/mcp.json)."""
    mcp_path = str(mimir_root / "mcp_server_llamaindex.py")
    server_name = f"mimir-{project_root.name}"

    config = read_mcp_config()

    if "servers" not in config:
        config["servers"] = {}

    if server_name in config["servers"]:
        return f"ℹ️  Mimir server '{server_name}' already registered"

    config["servers"][server_name] = {
        "command": sys.executable,
        "args": [mcp_path],
        "env": {
            "PROJECT_ROOT": str(project_root),
            "PYTHONPATH": str(mimir_root / "src"),
        },
    }

    write_mcp_config(config)
    return (
        f"✅ Registered Mimir MCP server '{server_name}' "
        f"for project {project_root.name} → {Path.home() / '.jcode' / 'mcp.json'}"
    )


def unregister_mcp_server(project_name: str) -> str:
    """Remove a Mimir MCP server from Jcode config."""
    config = read_mcp_config()
    server_name = f"mimir-{project_name}"

    if "servers" in config and server_name in config["servers"]:
        del config["servers"][server_name]
        write_mcp_config(config)
        return f"✅ Removed Mimir server '{server_name}' from config"
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
            "auto_activate": False,
            "priority": "high",
            "max_context_tokens": 8000,
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
        "--port",
        type=int,
        default=None,
        help="Port for the MCP server (auto-detected if not specified)",
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

        config = read_mcp_config()
        server_name = f"mimir-{project_root.name}"
        has_server = "servers" in config and server_name in config["servers"]
        print(f"🔗 MCP:     {'Configured' if has_server else 'Not configured'}")
        return

    if args.unregister:
        project_name = project_root.name
        msg1 = unregister_mcp_server(project_name)
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

    # Register MCP server
    if args.auto:
        results.append(register_mcp_server(project_root, mimir_root))

    if not args.quiet or not results:
        print(f"\n📍 Project: {project_root}")
        print(f"📦 Mimir:   {mimir_root}")
        print()
        for r in results:
            print(f"  {r}")
        print()
        print("💡 Start Jcode to use Mimir tools. If Jcode is already running,")
        print("   run `/mcp reload` in the Jcode TUI to pick up the new server.")


if __name__ == "__main__":
    main()