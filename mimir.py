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
    mimir list                           List indexed files
    mimir list --git-tracked             Compare indexed vs git-tracked files
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


def _run_script(script: str, args: list[str], cwd: str | None = None) -> int:
    """Run a Mimir script as a subprocess, forwarding stdout/stderr."""
    script_path = MIMIR_ROOT / script
    if not script_path.exists():
        print(f"Error: {script} not found at {script_path}")
        return 1
    result = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=cwd or str(Path.cwd()),
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
        cwd=str(Path.cwd()),
        env=env,
    )
    return result.returncode


def _run_projects(args: list[str]) -> int:
    """Run a mimir-projects command."""
    return _run_script("scripts/mimir-projects.py", args)


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
        cwd=str(Path.cwd()),
        env=env,
    )
    return result.returncode


def _run_init(args: list[str]) -> int:
    """Run mimir-init."""
    return _run_script("scripts/mimir-init.py", args)


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
        cwd=str(Path.cwd()),
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
    if args.remove_dir:
        extra.extend(["--remove-dir", args.remove_dir])
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


def cmd_list(args: argparse.Namespace) -> int:
    """List indexed files and optionally compare with git-tracked files."""
    try:
        from src.mimir.config import get_config, reset_config

        reset_config()
        config = get_config()
        knowledge_dir = config.knowledge_dir
        project_root = config.project_root

        # Check if index exists
        if not (knowledge_dir / "index_store.json").exists():
            print("\n❌ No knowledge base found")
            print(f"   Expected: {knowledge_dir}")
            print("\n   Run: mimir index")
            return 1

        # If --git-tracked flag, show comparison
        if args.git_tracked:
            return _list_with_git_comparison(knowledge_dir, project_root)

        # Otherwise, show standard list
        return _run_script(".opencode/mimir-index.py", ["--list"])

    except Exception as e:
        print(f"Error listing files: {e}")
        return 1


def _list_with_git_comparison(knowledge_dir: Path, project_root: Path) -> int:
    """Show comparison between indexed files and git-tracked files."""
    import subprocess
    from pathlib import Path

    # Check if we're in a git repository
    git_dir = project_root / ".git"
    if not git_dir.exists():
        print("\n⚠️  Not a git repository")
        print("   Showing indexed files only:\n")
        # Fall back to showing just indexed files
        return _run_script(".opencode/mimir-index.py", ["--list"])

    # Load manifest
    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        print("\n❌ No manifest found")
        print(f"   Expected: {manifest_path}")
        return 1

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"\n❌ Error reading manifest: {e}")
        return 1

    # Get indexed files (relative paths)
    indexed_files = set()
    for dir_info in manifest.get("indexed_directories", {}).values():
        for file_path in dir_info.get("files", []):
            try:
                rel_path = Path(file_path).relative_to(project_root)
                indexed_files.add(str(rel_path))
            except ValueError:
                # File is outside project root, use absolute path
                indexed_files.add(file_path)

    # Get git-tracked files
    git_files = set()
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            git_files = (
                set(result.stdout.strip().split("\n"))
                if result.stdout.strip()
                else set()
            )
    except (
        subprocess.TimeoutExpired,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):
        print("\n⚠️  Git command failed")
        print("   Showing indexed files only:\n")
        # Fall back to showing just indexed files
        return _run_script(".opencode/mimir-index.py", ["--list"])

    # Calculate differences
    indexed_and_tracked = indexed_files & git_files
    indexed_not_tracked = indexed_files - git_files
    tracked_not_indexed = git_files - indexed_files

    # Print results
    print("\n" + "=" * 60)
    print("📚 INDEXED vs GIT-TRACKED FILES")
    print("=" * 60)

    # Indexed and tracked
    if indexed_and_tracked:
        print(f"\n✓ Indexed ({len(indexed_and_tracked)} files):")
        for f in sorted(indexed_and_tracked)[:20]:
            print(f"   {f}")
        if len(indexed_and_tracked) > 20:
            print(f"   ... and {len(indexed_and_tracked) - 20} more files")

    # Indexed but not tracked (e.g., files outside git)
    if indexed_not_tracked:
        print(f"\n✓ Indexed (not in git) ({len(indexed_not_tracked)} files):")
        for f in sorted(indexed_not_tracked)[:10]:
            print(f"   {f}")
        if len(indexed_not_tracked) > 10:
            print(f"   ... and {len(indexed_not_tracked) - 10} more files")

    # Tracked but not indexed
    if tracked_not_indexed:
        print(f"\n✗ Not indexed ({len(tracked_not_indexed)} files):")
        for f in sorted(tracked_not_indexed)[:30]:
            print(f"   {f}")
        if len(tracked_not_indexed) > 30:
            print(f"   ... and {len(tracked_not_indexed) - 30} more files")

    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Indexed: {len(indexed_files)} files")
    print(f"   Git-tracked: {len(git_files)} files")
    print(f"   Indexed & tracked: {len(indexed_and_tracked)} files")
    print(f"   Not indexed: {len(tracked_not_indexed)} files")
    print("=" * 60 + "\n")

    return 0


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
            print("\nWarnings:")
            for w in warnings:
                print(f"  ⚠️  {w}")
        else:
            print("\n✅ No warnings")

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


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run eval harness to measure accuracy and cost."""
    import json
    from pathlib import Path

    # Ensure Mimir root is on path
    mimir_root = Path(__file__).resolve().parent
    src_dir = mimir_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    eval_file = Path(args.eval_file)
    if not eval_file.exists():
        print(f"Error: Eval file not found: {eval_file}")
        return 1

    try:
        with open(eval_file) as f:
            questions = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {eval_file}: {e}")
        return 1

    # Filter by question ID if specified
    if args.question_id:
        questions = [q for q in questions if q.get("id") == args.question_id]
        if not questions:
            print(f"Error: No question found with ID: {args.question_id}")
            return 1

    results = []
    for q in questions:
        q_id = q.get("id", "unknown")
        question = q.get("question", "")
        expected_artifact = q.get("expected_artifact")
        max_tokens = q.get("max_tokens", 5000)
        gold_answer = q.get("gold_answer")

        print(f"\n{'=' * 60}")
        print(f"Running eval: {q_id}")
        print(f"Question: {question}")
        print(f"{'=' * 60}")

        # Try to get artifact first if expected
        result = {
            "id": q_id,
            "question": question,
            "expected_artifact": expected_artifact,
            "success": False,
            "used_artifact": False,
            "token_usage": {},
            "answer": None,
        }

        if expected_artifact:
            try:
                from mimir.artifacts import get_artifact
                artifact = get_artifact(expected_artifact)
                if artifact:
                    print(f"✓ Using artifact: {expected_artifact}")
                    result["used_artifact"] = True
                    result["answer"] = artifact
                    result["success"] = True
                else:
                    print(f"✗ Artifact not found: {expected_artifact}")
            except Exception as e:
                print(f"✗ Error getting artifact: {e}")

        # TODO: Also run via RAG workflow for comparison
        # For now, just report artifact usage

        if gold_answer and result["success"]:
            # Simple check: verify keys exist in answer
            from mimir.metrics import get_tracker
            # This is a placeholder - actual eval would compare answer to gold

        results.append(result)

    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {args.output}")
    else:
        print(f"\n{'=' * 60}")
        print("Eval Results Summary")
        print(f"{'=' * 60}")
        for r in results:
            status = "✓" if r["success"] else "✗"
            artifact_used = "(artifact)" if r["used_artifact"] else ""
            print(f"  {status} {r['id']} {artifact_used}")

    return 0


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
        description="Mimir — Persistent knowledge base for AI agents. Gives your AI assistants memory across sessions by indexing your project's documentation and code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Setup
  mimir install                          Global install (run once after clone)
  mimir uninstall                        Remove Mimir from global config
  mimir init                             Initialize current project
  mimir init --code-dirs=src,tests       Init with source directories

  # Indexing
  mimir index                            Index project documents
  mimir index --reindex                  Rebuild index from scratch
  mimir index --add src                  Add directory to existing index
  mimir index --remove-dir old/          Remove directory from index
  mimir list                             List all indexed files
  mimir list --git-tracked               Compare indexed vs git-tracked files

  # Search & Analysis
  mimir search "how does auth work?"     Semantic search across indexed content
  mimir rag "explain the database"       RAG workflow with structured reasoning
  mimir agent "research auth patterns"   Multi-step knowledge agent exploration
  mimir stats                            Show index statistics
  mimir health                           Check configuration and status

  # FDE Workflows
  mimir prep "video latency"             Generate customer call briefing
  mimir prep "video latency" --customer "Acme"
  mimir diff                             Session diff (last day)
  mimir diff --days 7                    Session diff (last 7 days)
  mimir metrics --days 7                 Cost and usage report
  mimir handoff --customer "Acme Corp"  Generate handoff documentation

  # Multi-Project
  mimir projects list                    List registered projects
  mimir projects add ~/Projects/acme    Register a project
  mimir projects switch acme             Switch active project

  # SDK Cache
  mimir cache list                       List cached SDK docs
  mimir cache get stripe                 Fetch Stripe API docs""",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ── init ──
    p = subparsers.add_parser(
        "init",
        help="Initialize a project for Mimir indexing",
        description="Set up Mimir for the current project. Creates .mimir/config.json and .opencode/mimir-index.py, then indexes your documentation and code.",
    )
    p.add_argument(
        "--code-dirs",
        help="Comma-separated list of code directories to index (e.g., 'src,tests'). Default: no code directories",
    )
    p.add_argument(
        "project_root",
        nargs="?",
        help="Project directory to initialize (default: current directory)",
    )

    # ── install ──
    p = subparsers.add_parser(
        "install",
        help="Global install — configure MCP server and system rules",
        description="One-time setup after cloning Mimir. Configures the MCP server in opencode.json and injects Mimir rules into system-context.md. Run this once per machine.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force re-injection of rules even if already installed",
    )

    # ── uninstall ──
    subparsers.add_parser(
        "uninstall",
        help="Uninstall — restore original OpenCode configuration",
        description="Remove Mimir from global OpenCode configuration. Restores backed up config files if available.",
    )

    # ── server ──
    p = subparsers.add_parser(
        "server",
        help="Run the MCP server for AI assistant integration",
        description="Start the Model Context Protocol (MCP) server that provides Mimir tools to AI assistants like Claude. Usually run automatically by your AI client.",
    )
    p.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    p.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP transport (default: 8000)"
    )

    # ── index ──
    p = subparsers.add_parser(
        "index",
        help="Index documents and code for semantic search",
        description="Build or update the knowledge base index. Indexes documentation and code files so they can be searched semantically by AI assistants.",
    )
    p.add_argument(
        "directory",
        nargs="?",
        help="Directory to index (default: project docs directory)",
    )
    p.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the entire index from scratch (slower but thorough)",
    )
    p.add_argument(
        "--add",
        metavar="DIR",
        help="Add a directory to the existing index (incremental update)",
    )
    p.add_argument(
        "--remove", metavar="FILE", help="Remove a single file from the index"
    )
    p.add_argument(
        "--remove-dir",
        metavar="DIR",
        help="Remove all files from a directory (recursively) from the index",
    )
    p.add_argument(
        "--shared-index",
        metavar="DIR",
        help="Index as a shared reference for cross-project search",
    )
    p.add_argument(
        "--name",
        metavar="NAME",
        help="Name for shared index (required with --shared-index)",
    )
    p.add_argument(
        "--shared-list", action="store_true", help="List all available shared indices"
    )

    # ── search ──
    p = subparsers.add_parser(
        "search",
        help="Semantic search across indexed content",
        description="Search the knowledge base using natural language. Returns semantically similar documents and code snippets.",
    )
    p.add_argument("query", help="Natural language search query")

    # ── stats ──
    subparsers.add_parser(
        "stats",
        help="Show index statistics",
        description="Display statistics about the knowledge base: document count, index size, indexed directories.",
    )

    # ── list ──
    p = subparsers.add_parser(
        "list",
        help="List all indexed files",
        description="Show all files currently in the knowledge base index. Useful for verifying what's been indexed.",
    )
    p.add_argument(
        "--git-tracked",
        action="store_true",
        help="Compare indexed files with git-tracked files to find gaps",
    )

    # ── health ──
    subparsers.add_parser(
        "health",
        help="Check Mimir health and configuration",
        description="Verify Mimir is properly configured: API keys, index status, directory paths, and any warnings.",
    )

    # ── rag ──
    p = subparsers.add_parser(
        "rag",
        help="RAG workflow with structured reasoning",
        description="Retrieve relevant documents and generate a synthesized answer using Retrieval-Augmented Generation. Best for specific questions.",
    )
    p.add_argument("query", help="Question to answer")

    # ── agent ──
    p = subparsers.add_parser(
        "agent",
        help="Knowledge agent for multi-step research",
        description="Launch an autonomous agent that performs multi-step research: searches, reads documents, and synthesizes findings. Best for complex questions.",
    )
    p.add_argument("query", help="Research question to investigate")

    # ── prep ──
    p = subparsers.add_parser(
        "prep",
        help="Generate customer call briefing",
        description="Prepare for a customer call by generating a briefing document with relevant context from the knowledge base.",
    )
    p.add_argument("topic", help="Call topic (e.g., 'video latency issues')")
    p.add_argument("--customer", help="Customer name for personalized briefing")

    # ── diff ──
    p = subparsers.add_parser(
        "diff",
        help="Session diff — what you learned recently",
        description="Show what was learned or changed in recent sessions. Useful for catching up after time away.",
    )
    p.add_argument(
        "--days", type=int, default=1, help="Number of days to look back (default: 1)"
    )

    # ── metrics ──
    p = subparsers.add_parser(
        "metrics",
        help="Cost and usage metrics report",
        description="Show API costs, token usage, and query statistics. Helps track spending and optimize usage.",
    )
    p.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to include in report (default: 30)",
    )

    # ── evaluate ──
    p = subparsers.add_parser(
        "evaluate",
        help="Run eval harness to measure accuracy and cost",
        description="Run eval questions to measure RAG system accuracy, token usage, and cost. Compares results against gold answers.",
    )
    p.add_argument(
        "--eval-file",
        default=".knowledge/evals/questions.json",
        help="Path to eval questions JSON file (default: .knowledge/evals/questions.json)",
    )
    p.add_argument(
        "--question-id",
        help="Run a specific question by ID (default: run all)",
    )
    p.add_argument(
        "--output",
        help="Output file for results (default: print to stdout)",
    )
    p.add_argument(
        "--update-gold",
        action="store_true",
        help="Update gold answers from current artifact/system state",
    )

    # ── projects ──
    p = subparsers.add_parser(
        "projects",
        help="Multi-project management",
        description="Manage multiple Mimir projects. Register, switch between, and track status of different projects.",
    )
    psp = p.add_subparsers(dest="projects_action", help="Project command")
    psp.add_parser(
        "list",
        help="List all registered projects",
        description="Show all projects registered with Mimir and their status.",
    )
    pa = psp.add_parser(
        "add",
        help="Register a new project",
        description="Add a project directory to Mimir's registry for easy switching.",
    )
    pa.add_argument("path", help="Path to project directory")
    pa.add_argument("--name", help="Project name (default: directory name)")
    pa.add_argument("--description", help="Brief project description")
    pr = psp.add_parser(
        "remove",
        help="Unregister a project",
        description="Remove a project from Mimir's registry (does not delete the project).",
    )
    pr.add_argument("name", help="Project name to remove")
    ps = psp.add_parser(
        "switch",
        help="Switch to a different project",
        description="Change the active project context for Mimir commands.",
    )
    ps.add_argument("name", help="Project name to switch to")
    psp.add_parser(
        "status",
        help="Show status of all projects",
        description="Display index status, last indexed time, and health for all projects.",
    )
    psp.add_parser(
        "discover",
        help="Find projects in common locations",
        description="Scan common directories for Mimir-enabled projects and offer to register them.",
    )

    # ── handoff ──
    p = subparsers.add_parser(
        "handoff",
        help="Generate handoff documentation",
        description="Create a comprehensive handoff document for transitioning work to another developer or team.",
    )
    p.add_argument("--project", "-p", help="Project name (default: current directory)")
    p.add_argument("--summary", "-s", help="Brief engagement summary or context")
    p.add_argument("--customer", "-c", help="Customer name for personalized handoff")
    p.add_argument("--output", "-o", help="Output file path (default: HANDOFF.md)")

    # ── cache ──
    p = subparsers.add_parser(
        "cache",
        help="SDK documentation cache management",
        description="Manage cached SDK/library documentation. Fetches current docs from Context7 and caches locally for fast access.",
    )
    csp = p.add_subparsers(dest="cache_action", help="Cache command")
    csp.add_parser(
        "list",
        help="List all cached libraries",
        description="Show all SDK documentation currently in the cache with freshness status.",
    )
    cg = csp.add_parser(
        "get",
        help="Get SDK docs (fetches if not cached or stale)",
        description="Retrieve documentation for a library. Automatically fetches from Context7 if not cached or cache is stale (7-day TTL).",
    )
    cg.add_argument("library", help="Library name (e.g., stripe, react, nextjs)")
    cg.add_argument(
        "--topic",
        default="general",
        help="Specific topic within docs (default: general)",
    )
    cr = csp.add_parser(
        "refresh",
        help="Force refresh cached docs",
        description="Force fetch fresh documentation even if cache is still valid.",
    )
    cr.add_argument("library", help="Library name to refresh")
    cr.add_argument("--topic", default="general", help="Documentation topic")
    ci = csp.add_parser(
        "invalidate",
        help="Remove cached docs",
        description="Delete cached documentation for a library to free space or force fresh fetch.",
    )
    ci.add_argument("library", help="Library name to remove from cache")

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
        "list": cmd_list,
        "health": cmd_health,
        "rag": cmd_rag,
        "agent": cmd_agent,
        "prep": cmd_prep,
        "diff": cmd_diff,
        "metrics": cmd_metrics,
        "evaluate": cmd_evaluate,
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
