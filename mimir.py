#!/usr/bin/env python3
"""
mimir — Unified CLI for the Mimir knowledge base.

All commands in one place. No more remembering which script does what.

Usage:
    mimir install                        Global install (run once after clone)
    mimir uninstall                      Remove Mimir from global config
    mimir init                           Initialize a project
    mimir server                         Run the MCP server
    mimir index                          Index documents
    mimir index --reindex                Rebuild index
    mimir index --add src                Add directory to index
    mimir search "how does auth work?"   One-shot semantic search
    mimir stats                          Show index statistics
    mimir health                         Check server health
    mimir rag "question"                 RAG workflow
    mimir agent "question"               Knowledge agent
    mimir prep "topic"                   Customer call briefing
    mimir diff                           Session diff
    mimir metrics                        Cost report
    mimir projects list                  List projects
    mimir projects add /path             Register a project
    mimir projects switch NAME           Switch to a project
    mimir handoff                        Generate handoff doc
    mimir cache list                     List cached SDKs
    mimir cache get stripe               Get SDK docs
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure Mimir root is on sys.path
MIMIR_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MIMIR_ROOT))


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _run_script(script: str, args: list[str]) -> int:
    """Run a Mimir script as a subprocess, forwarding stdout/stderr."""
    script_path = MIMIR_ROOT / script
    if not script_path.exists():
        print(f"Error: {script} not found at {script_path}")
        return 1
    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=str(MIMIR_ROOT),
    )
    return result.returncode


def _run_langgraph(args: list[str]) -> int:
    """Run a langgraph CLI command."""
    script_path = MIMIR_ROOT / "langgraph/cli.py"
    if not script_path.exists():
        print(f"Error: langgraph/cli.py not found at {script_path}")
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = str(MIMIR_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=str(MIMIR_ROOT),
        env=env,
    )
    return result.returncode


def _run_projects(args: list[str]) -> int:
    """Run a mimir-projects command."""
    return _run_script("mimir-projects.py", args)


def _run_cache(args: list[str]) -> int:
    """Run an SDK cache command."""
    script_path = MIMIR_ROOT / "src/mimir/sdk_cache.py"
    if not script_path.exists():
        print(f"Error: src/mimir/sdk_cache.py not found at {script_path}")
        return 1

    env = os.environ.copy()
    env["PYTHONPATH"] = str(MIMIR_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=str(MIMIR_ROOT),
        env=env,
    )
    return result.returncode


def _run_init(args: list[str]) -> int:
    """Run mimir-init."""
    return _run_script("mimir-init.py", args)


def _run_indexing(args: list[str]) -> int:
    """Run the MCP server in indexing mode (not as a server)."""
    script_path = MIMIR_ROOT / "mcp_server_llamaindex.py"
    if not script_path.exists():
        print(f"Error: mcp_server_llamaindex.py not found at {script_path}")
        return 1

    env = os.environ.copy()
    # Put src first to avoid shadowing by mimir.py in root
    env["PYTHONPATH"] = str(MIMIR_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=str(MIMIR_ROOT),
        env=env,
    )
    return result.returncode


# ─── Commands ────────────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a project for Mimir."""
    extra = []
    if args.code_dirs:
        extra.extend(["--code-dirs", args.code_dirs])
    if args.project_root:
        extra.extend(["--project-root", args.project_root])
    return _run_init(extra)


def cmd_install(args: argparse.Namespace) -> int:
    """Global install — set up MCP server and system rules."""
    extra = ["--install"]
    if args.force:
        extra.append("--force")
    return _run_init(extra)


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall — restore backed up configs."""
    return _run_init(["--uninstall"])


def cmd_server(args: argparse.Namespace) -> int:
    """Run the MCP server."""
    extra = []
    if args.transport:
        extra.extend(["--transport", args.transport])
    if args.port:
        extra.extend(["--port", str(args.port)])
    return _run_indexing(extra)


def cmd_index(args: argparse.Namespace) -> int:
    """Index documents."""
    extra = []
    if args.reindex:
        extra.append("--reindex")
    if args.add:
        extra.extend(["--add", args.add])
    if args.remove:
        extra.extend(["--remove", args.remove])
    if args.shared_index:
        extra.extend(["--shared-index", args.shared_index])
        if args.name:
            extra.extend(["--name", args.name])
    if args.shared_list:
        extra.append("--shared-list")
    if args.directory:
        extra.extend(["--index", args.directory])
    if not extra:
        extra.append("--index")
    return _run_indexing(extra)


def cmd_search(args: argparse.Namespace) -> int:
    """One-shot semantic search."""
    return _run_indexing(["--query", args.query])


def cmd_stats(args: argparse.Namespace) -> int:
    """Show index statistics."""
    return _run_indexing(["--stats"])


def cmd_health(args: argparse.Namespace) -> int:
    """Check Mimir health and configuration."""
    try:
        from src.mimir.config import get_config, reset_config

        reset_config()
        config = get_config()
        warnings = config.validate()

        knowledge_dir = config.knowledge_dir
        has_index = (knowledge_dir / "index_store.json").exists()

        # Check manifest freshness
        index_timestamp = None
        manifest_path = knowledge_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                index_timestamp = manifest.get("last_updated")
            except (json.JSONDecodeError, OSError):
                pass

        status = "healthy" if (has_index and config.api_key) else "degraded"

        print(f"Status:         {status}")
        print(f"Project root:   {config.project_root}")
        print(f"Mimir root:     {config.mimir_root}")
        print(f"API key:        {'configured' if config.api_key else 'MISSING'}")
        print(f"Embedding:      {config.embedding_model}")
        print(f"LLM:            {config.llm_model}")
        print(f"Index:          {'exists' if has_index else 'NOT FOUND'}")
        if index_timestamp:
            print(f"Index updated:  {index_timestamp}")
        print(f"Docs dir:       {config.docs_dir}")
        print(f"Knowledge dir:  {config.knowledge_dir}")
        if config.code_dirs:
            print(f"Code dirs:      {', '.join(str(d) for d in config.code_dirs)}")
        if config.shared_indexes:
            print(f"Shared indices: {', '.join(config.shared_indexes.keys())}")

        if warnings:
            print(f"\nWarnings:")
            for w in warnings:
                print(f"  ⚠️  {w}")
        else:
            print(f"\n✅ No warnings")

        return 0 if status == "healthy" else 1

    except Exception as e:
        print(f"Error checking health: {e}")
        return 1


def cmd_rag(args: argparse.Namespace) -> int:
    """Run RAG workflow."""
    return _run_langgraph(["rag", args.query])


def cmd_agent(args: argparse.Namespace) -> int:
    """Run knowledge agent."""
    return _run_langgraph(["agent", args.query])


def cmd_prep(args: argparse.Namespace) -> int:
    """Generate customer call briefing."""
    extra = ["prep", args.topic]
    if args.customer:
        extra.extend(["--customer", args.customer])
    return _run_langgraph(extra)


def cmd_diff(args: argparse.Namespace) -> int:
    """Generate session diff."""
    extra = ["session-diff"]
    if args.days:
        extra.extend(["--days", str(args.days)])
    return _run_langgraph(extra)


def cmd_metrics(args: argparse.Namespace) -> int:
    """Show cost metrics."""
    extra = ["metrics"]
    if args.days:
        extra.extend(["--days", str(args.days)])
    return _run_langgraph(extra)


def cmd_projects(args: argparse.Namespace) -> int:
    """Multi-project management."""
    extra = [args.projects_action]
    if hasattr(args, "path") and args.path:
        extra.append(args.path)
    if hasattr(args, "name") and args.name:
        extra.extend(["--name", args.name])
    if hasattr(args, "description") and args.description:
        extra.extend(["--description", args.description])
    return _run_projects(extra)


def cmd_handoff(args: argparse.Namespace) -> int:
    """Generate handoff documentation."""
    extra = ["handoff"]
    if args.project:
        extra.append(args.project)
    if args.summary:
        extra.extend(["--summary", args.summary])
    if args.customer:
        extra.extend(["--customer", args.customer])
    if args.output:
        extra.extend(["--output", args.output])
    return _run_projects(extra)


def cmd_cache(args: argparse.Namespace) -> int:
    """SDK documentation cache management."""
    extra = [args.cache_action]
    if hasattr(args, "library") and args.library:
        extra.append(args.library)
    if hasattr(args, "topic") and args.topic:
        extra.extend(["--topic", args.topic])
    return _run_cache(extra)


# ─── Parser ──────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mimir",
        description="Mimir — Persistent knowledge base for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  mimir install                          Global install (run once after clone)
  mimir uninstall                        Remove Mimir from global config
  mimir init                             Initialize a project
  mimir init --code-dirs=src,tests       Init with source directories
  mimir server                           Start the MCP server
  mimir index                            Index documents
  mimir index --reindex                  Rebuild index from scratch
  mimir index --add src                  Add a directory to the index
  mimir search "how does auth work?"     Semantic search
  mimir stats                            Show index statistics
  mimir health                           Check configuration and status
  mimir rag "explain the database"       RAG workflow
  mimir prep "video latency"             Customer call briefing
  mimir diff                             Session diff (last day)
  mimir metrics --days 7                 Cost report
  mimir projects list                    List registered projects
  mimir projects add ~/Projects/acme     Register a project
  mimir handoff --customer "Acme Corp"   Generate handoff doc
  mimir cache list                       List cached SDK docs
  mimir cache get stripe                 Fetch Stripe docs""",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ── init ──
    p = subparsers.add_parser("init", help="Initialize a project for Mimir")
    p.add_argument(
        "--code-dirs", help="Comma-separated code directories (e.g., src,tests)"
    )
    p.add_argument(
        "project_root", nargs="?", help="Project directory (default: current)"
    )

    # ── install ──
    p = subparsers.add_parser(
        "install", help="Global install — set up MCP server and system rules (run once)"
    )
    p.add_argument("--force", action="store_true", help="Force re-injection of rules")

    # ── uninstall ──
    subparsers.add_parser("uninstall", help="Uninstall — restore backed up configs")

    # ── server ──
    p = subparsers.add_parser("server", help="Run the MCP server")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--port", type=int, default=8000)

    # ── index ──
    p = subparsers.add_parser("index", help="Index documents")
    p.add_argument(
        "directory", nargs="?", help="Directory to index (default: project docs)"
    )
    p.add_argument("--reindex", action="store_true", help="Rebuild index from scratch")
    p.add_argument("--add", metavar="DIR", help="Add directory to existing index")
    p.add_argument("--remove", metavar="FILE", help="Remove file from index")
    p.add_argument("--shared-index", metavar="DIR", help="Index as a shared reference")
    p.add_argument("--name", metavar="NAME", help="Name for shared index")
    p.add_argument("--shared-list", action="store_true", help="List shared indices")

    # ── search ──
    p = subparsers.add_parser("search", help="One-shot semantic search")
    p.add_argument("query", help="Search query")

    # ── stats ──
    subparsers.add_parser("stats", help="Show index statistics")

    # ── health ──
    subparsers.add_parser("health", help="Check Mimir health and configuration")

    # ── rag ──
    p = subparsers.add_parser("rag", help="RAG workflow")
    p.add_argument("query", help="Question to answer")

    # ── agent ──
    p = subparsers.add_parser("agent", help="Knowledge agent workflow")
    p.add_argument("query", help="Question to research")

    # ── prep ──
    p = subparsers.add_parser("prep", help="Generate customer call briefing")
    p.add_argument("topic", help="Call topic (e.g., 'video latency issues')")
    p.add_argument("--customer", help="Customer name")

    # ── diff ──
    p = subparsers.add_parser("diff", help="Session diff — what you learned recently")
    p.add_argument("--days", type=int, default=1, help="Days to look back (default: 1)")

    # ── metrics ──
    p = subparsers.add_parser("metrics", help="Cost metrics report")
    p.add_argument("--days", type=int, default=30, help="Days to include (default: 30)")

    # ── projects ──
    p = subparsers.add_parser("projects", help="Multi-project management")
    psp = p.add_subparsers(dest="projects_action", help="Project command")
    psp.add_parser("list", help="List registered projects")
    pa = psp.add_parser("add", help="Register a project")
    pa.add_argument("path", help="Path to project directory")
    pa.add_argument("--name", help="Project name (default: directory name)")
    pa.add_argument("--description", help="Project description")
    pr = psp.add_parser("remove", help="Unregister a project")
    pr.add_argument("name", help="Project name")
    ps = psp.add_parser("switch", help="Switch to a project")
    ps.add_argument("name", help="Project name")
    psp.add_parser("status", help="Show status of all projects")
    psp.add_parser("discover", help="Find projects in common locations")

    # ── handoff ──
    p = subparsers.add_parser("handoff", help="Generate handoff documentation")
    p.add_argument("--project", "-p", help="Project name (default: current directory)")
    p.add_argument("--summary", "-s", help="Engagement summary")
    p.add_argument("--customer", "-c", help="Customer name")
    p.add_argument("--output", "-o", help="Output file path (default: HANDOFF.md)")

    # ── cache ──
    p = subparsers.add_parser("cache", help="SDK documentation cache")
    csp = p.add_subparsers(dest="cache_action", help="Cache command")
    csp.add_parser("list", help="List cached libraries")
    cg = csp.add_parser("get", help="Get SDK docs (fetches + caches if stale)")
    cg.add_argument("library", help="Library name (e.g., stripe, react)")
    cg.add_argument("--topic", default="general", help="Documentation topic")
    cr = csp.add_parser("refresh", help="Force refresh cached docs")
    cr.add_argument("library", help="Library name")
    cr.add_argument("--topic", default="general", help="Documentation topic")
    ci = csp.add_parser("invalidate", help="Remove cached docs")
    ci.add_argument("library", help="Library name")

    return parser


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "init": cmd_init,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "server": cmd_server,
        "index": cmd_index,
        "search": cmd_search,
        "stats": cmd_stats,
        "health": cmd_health,
        "rag": cmd_rag,
        "agent": cmd_agent,
        "prep": cmd_prep,
        "diff": cmd_diff,
        "metrics": cmd_metrics,
        "projects": cmd_projects,
        "handoff": cmd_handoff,
        "cache": cmd_cache,
    }

    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
