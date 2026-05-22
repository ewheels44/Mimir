#!/usr/bin/env python3
"""
Mimir Jcode Hook - Automatic Context Enrichment

This hook automatically enriches tasks with Mimir context BEFORE the agent
processes them. It works by:
1. Intercepting task descriptions (via wrapper or prompt injection)
2. Running enrich_task() to get project context
3. Injecting context into the agent's prompt automatically

Usage:
    # As a wrapper (manual):
    python mimir_hook.py --task "implement feature X" --inject
    
    # As a daemon (automatic):
    python mimir_hook.py --daemon
    
    # Generate enriched prompt file:
    python mimir_hook.py --task "..." --output .jcode/prompts/01-enriched-context.md
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Mimir availability check
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent  # scripts/jcode/ → Mimir/
MIMIR_ROOT = SCRIPT_DIR

def check_mimir_available():
    """Check if Mimir is available and return (available, error_msg)."""
    # Add Mimir to path
    mimir_src = MIMIR_ROOT / "src"
    if str(mimir_src) not in sys.path:
        sys.path.insert(0, str(mimir_src))
    
    try:
        from mimir.query_router import route_task, RoutingResult
        from mimir.config import get_config
        return True, None
    except ImportError as e:
        return False, str(e)

MIMIR_AVAILABLE, MIMIR_ERROR = check_mimir_available()

if MIMIR_AVAILABLE:
    from mimir.query_router import route_task, RoutingResult
    from mimir.config import get_config
    print(f"✅ Mimir loaded from {MIMIR_ROOT}", file=sys.stderr)
else:
    print(f"⚠️  Mimir not available: {MIMIR_ERROR}", file=sys.stderr)

logger = logging.getLogger("mimir-hook")


def setup_logging():
    """Setup logging for the hook."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def is_mimir_project(project_root: Path) -> bool:
    """Check if directory is a Mimir-enabled project."""
    return (project_root / ".knowledge" / "llamaindex" / "index_store.json").exists()


def enrich_task(task_description: str, project_root: Optional[Path] = None) -> dict:
    """
    Enrich a task with Mimir context.
    
    Returns:
        dict with keys: context, success, routed_to, error (if any)
    """
    if not MIMIR_AVAILABLE:
        return {
            "success": False, 
            "error": f"Mimir not available: {MIMIR_ERROR}", 
            "context": "",
            "suggestion": "Run: python ~/Documents/Mimir/mimir.py install"
        }
    
    if project_root is None:
        project_root = Path.cwd()
    
    if not is_mimir_project(project_root):
        return {
            "success": False, 
            "error": "Not a Mimir project", 
            "context": "",
            "suggestion": "Run: python ~/Documents/Mimir/mimir.py init --code-dirs=src"
        }
    
    try:
        result: RoutingResult = route_task(task_description, project_root=project_root)
        
        return {
            "success": result.success,
            "context": result.context,
            "routed_to": result.routed_to,
            "query_type": result.query_type,
            "cache_hit": result.cache_hit,
            "elapsed_ms": result.elapsed_ms,
        }
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        return {"success": False, "error": str(e), "context": ""}


def format_context_for_prompt(enrichment: dict, task_description: str) -> str:
    """Format enriched context as a markdown prompt section."""
    if not enrichment.get("success") or not enrichment.get("context"):
        return ""
    
    context = enrichment["context"]
    routed_to = enrichment.get("routed_to", "unknown")
    query_type = enrichment.get("query_type", "unknown")
    cache_hit = enrichment.get("cache_hit", False)
    
    markdown = f"""## Mimir Auto-Enriched Context

**Task**: {task_description}
**Routed to**: {routed_to} ({query_type})
**Cache**: {"hit" if cache_hit else "miss"}

### Project Context

{context}

---
"""
    return markdown


def inject_prompt_file(task_description: str, project_root: Path, output_path: Optional[Path] = None) -> str:
    """
    Generate and inject a prompt file with enriched context.
    
    Returns:
        Path to the generated prompt file, or empty string on failure
    """
    enrichment = enrich_task(task_description, project_root)
    
    if not enrichment.get("success"):
        error = enrichment.get('error', 'Unknown error')
        suggestion = enrichment.get('suggestion', '')
        logger.warning(f"Enrichment failed: {error}")
        if suggestion:
            logger.warning(f"Suggestion: {suggestion}")
        return ""
    
    context_md = format_context_for_prompt(enrichment, task_description)
    
    if not context_md:
        logger.warning("No context to inject")
        return ""
    
    # Determine output path
    if output_path is None:
        prompts_dir = project_root / ".jcode" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        # Use a numbered prefix to ensure it loads early (after 00-global-*.md)
        output_path = prompts_dir / "01-mimir-enriched.md"
    
    output_path.write_text(context_md)
    logger.info(f"✅ Injected enriched context → {output_path}")
    
    return str(output_path)


def daemon_mode(project_root: Path, poll_interval: float = 1.0):
    """
    Run as a daemon that watches for new Jcode sessions and injects context.
    
    This is a simple implementation that watches the .jcode/sessions directory
    for new session files, and when detected, enriches the first user message.
    """
    logger.info(f"🔄 Starting Mimir enrichment daemon for {project_root}")
    
    sessions_dir = Path.home() / ".jcode" / "sessions"
    processed_sessions = set()
    
    if not sessions_dir.exists():
        logger.warning(f"Sessions directory not found: {sessions_dir}")
        return
    
    try:
        while True:
            for session_file in sessions_dir.glob("*.json"):
                if session_file.stem in processed_sessions:
                    continue
                
                # Check if this session is in our project
                try:
                    session_data = json.loads(session_file.read_text())
                    # Simple check: does the session have our project in cwd?
                    if session_data.get("cwd") == str(project_root):
                        # Extract first user message
                        messages = session_data.get("messages", [])
                        for msg in messages:
                            if msg.get("role") == "user":
                                task = msg.get("content", "")
                                if task:
                                    logger.info(f"📝 Enriching session {session_file.stem}")
                                    inject_prompt_file(task, project_root)
                                    processed_sessions.add(session_file.stem)
                                break
                except Exception as e:
                    logger.debug(f"Error processing {session_file}: {e}")
            
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logger.info("👋 Daemon stopped")


def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description="Mimir Jcode Hook - Automatic Context Enrichment"
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Task description to enrich",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root (auto-detected if not specified)",
    )
    parser.add_argument(
        "--inject",
        action="store_true",
        help="Inject enriched context into Jcode prompt file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for prompt file (default: .jcode/prompts/01-mimir-enriched.md)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run as daemon (watch for new sessions)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print enriched context to stdout (for testing)",
    )
    
    args = parser.parse_args()
    
    if args.daemon:
        daemon_mode(args.project_root)
        return
    
    if not args.task:
        parser.print_help()
        return
    
    # Enrich the task
    enrichment = enrich_task(args.task, args.project_root)
    
    if args.print:
        print(json.dumps(enrichment, indent=2))
        return
    
    if args.inject or args.output:
        output_path = Path(args.output) if args.output else None
        result = inject_prompt_file(args.task, args.project_root, output_path)
        if result:
            print(f"✅ Context injected: {result}")
        else:
            print("⚠️  No context injected (enrichment failed or empty)")
        return
    
    # Default: print summary
    if enrichment["success"]:
        print(f"✅ Enriched successfully (routed to {enrichment['routed_to']})")
        print(f"Context length: {len(enrichment['context'])} chars")
    else:
        print(f"❌ Enrichment failed: {enrichment.get('error')}")


if __name__ == "__main__":
    main()
