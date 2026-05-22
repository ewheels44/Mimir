#!/usr/bin/env python3
"""
Mimir Context Enricher for Jcode

This script automatically enriches tasks with Mimir context.
It can be used in two ways:

1. WRAPPER MODE: Wrap Jcode to intercept tasks
   Usage: mimir-enrich wrap jcode "your task here"

2. PROMPT MODE: Generate enriched prompt files (recommended)
   Usage: mimir-enrich prompt "your task" --output .jcode/prompts/01-enriched.md

3. CHECK MODE: Test if enrichment works
   Usage: mimir-enrich test "your task"

The recommended approach is PROMPT MODE because:
- It works with Jcode's existing prompt system
- No wrapper/Hook needed
- Context is injected before the agent thinks
"""

import json
import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mimir-enrich")

# Mimir imports
SCRIPT_DIR = Path(__file__).resolve().parent
MIMIR_ROOT = SCRIPT_DIR.parent.parent  # scripts/jcode/ → Mimir/

# Add Mimir src to path
mimir_src = MIMIR_ROOT / "src"
if str(mimir_src) not in sys.path:
    sys.path.insert(0, str(mimir_src))

try:
    from mimir.query_router import route_task, RoutingResult
    from mimir.config import get_config
    MIMIR_AVAILABLE = True
    print(f"✅ Mimir loaded from {MIMIR_ROOT}", file=sys.stderr)
except ImportError as e:
    MIMIR_AVAILABLE = False
    print(f"⚠️  Mimir not available: {e}", file=sys.stderr)


def is_mimir_project(project_root: Path) -> bool:
    """Check if directory is a Mimir-enabled project."""
    return (project_root / ".knowledge" / "llamaindex" / "index_store.json").exists()


def enrich_task(task_description: str, project_root: Optional[Path] = None) -> dict:
    """Enrich a task with Mimir context."""
    if not MIMIR_AVAILABLE:
        return {"success": False, "error": "Mimir not available", "context": ""}
    
    if project_root is None:
        project_root = Path.cwd()
    
    if not is_mimir_project(project_root):
        return {"success": False, "error": "Not a Mimir project", "context": ""}
    
    try:
        result: RoutingResult = route_task(task_description, project_root=project_root)
        return {
            "success": result.success,
            "context": result.context,
            "routed_to": result.routed_to,
            "query_type": result.query_type,
            "cache_hit": result.cache_hit,
        }
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        return {"success": False, "error": str(e), "context": ""}


def format_prompt(task: str, enrichment: dict) -> str:
    """Format enriched context as a Jcode prompt file."""
    if not enrichment.get("success") or not enrichment.get("context"):
        return ""
    
    context = enrichment["context"]
    routed = enrichment.get("routed_to", "unknown")
    query_type = enrichment.get("query_type", "unknown")
    
    return f"""## Mimir Auto-Enriched Context

**Task**: {task}
**Source**: Mimir ({routed}, {query_type})

### Project Context

{context}

---

**Instructions to Agent**: Use the context above to inform your implementation.
This context was auto-injected by Mimir before you started thinking.

"""


def generate_prompt_file(task: str, output_path: Path, project_root: Optional[Path] = None):
    """Generate a prompt file with enriched context."""
    if project_root is None:
        project_root = Path.cwd()
    
    logger.info(f"Enriching task: {task[:50]}...")
    enrichment = enrich_task(task, project_root)
    
    if not enrichment.get("success"):
        logger.warning(f"Enrichment failed: {enrichment.get('error')}")
        # Create empty file to avoid repeated attempts
        output_path.write_text(f"<!-- Mimir enrichment failed: {enrichment.get('error')} -->\n")
        return False
    
    prompt_content = format_prompt(task, enrichment)
    if not prompt_content:
        logger.warning("No context to inject")
        return False
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt_content)
    logger.info(f"✅ Generated enriched prompt: {output_path}")
    return True


def wrap_jcode(task: str, extra_args: list = None):
    """Wrap Jcode by enriching task first, then launching Jcode."""
    # Generate enriched prompt
    project_root = Path.cwd()
    prompts_dir = project_root / ".jcode" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompts_dir / "01-mimir-enriched.md"
    
    generate_prompt_file(task, prompt_file, project_root)
    
    # Launch Jcode with the task
    # Note: Jcode doesn't have a CLI flag for initial task, so we rely on prompt injection
    logger.info("Launching Jcode...")
    logger.info("The enriched context is in: " + str(prompt_file))
    logger.info("Start Jcode and type your task - context will be available.")
    
    # Alternatively, we could use Jcode's socket API if available
    # But for now, just inform the user
    print("\n" + "="*60)
    print("Mimir Context Enrichment Complete")
    print("="*60)
    print(f"Enriched context written to: {prompt_file}")
    print("\nStart Jcode and your task context will be available.")
    print("The agent will see the enriched context automatically.\n")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Mimir Context Enricher for Jcode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate enriched prompt file
  %(prog)s prompt "implement feature X"
  
  # Wrap Jcode (not fully implemented yet)
  %(prog)s wrap --task "implement feature X"
  
  # Test enrichment
  %(prog)s test "how does auth work?"
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Prompt command
    prompt_parser = subparsers.add_parser("prompt", help="Generate enriched prompt file")
    prompt_parser.add_argument("task", help="Task description")
    prompt_parser.add_argument("--output", type=Path, help="Output path (default: .jcode/prompts/01-mimir-enriched.md)")
    prompt_parser.add_argument("--project-root", type=Path, default=Path.cwd())
    
    # Wrap command  
    wrap_parser = subparsers.add_parser("wrap", help="Wrap Jcode with enrichment")
    wrap_parser.add_argument("task", help="Task description")
    wrap_parser.add_argument("--jcode-path", default="jcode", help="Path to Jcode binary")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Test enrichment")
    test_parser.add_argument("task", help="Task to test")
    test_parser.add_argument("--print-context", action="store_true", help="Print full context")
    
    args = parser.parse_args()
    
    if args.command == "prompt":
        output = args.output or (args.project_root / ".jcode" / "prompts" / "01-mimir-enriched.md")
        success = generate_prompt_file(args.task, output, args.project_root)
        sys.exit(0 if success else 1)
    
    elif args.command == "wrap":
        wrap_jcode(args.task)
    
    elif args.command == "test":
        enrichment = enrich_task(args.task)
        print(json.dumps(enrichment, indent=2))
        if args.print_context and enrichment.get("context"):
            print("\n" + "="*60)
            print("ENRICHED CONTEXT:")
            print("="*60)
            print(enrichment["context"])
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
