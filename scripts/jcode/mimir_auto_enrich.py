#!/usr/bin/env python3
"""
Mimir Auto-Enrich for Jcode

This script automatically enriches tasks with Mimir context.
It outputs enriched context that can be:
1. Prepended to the agent's prompt
2. Saved as a Jcode prompt file
3. Used as context for any LLM agent

Usage:
    # Generate enriched context for a task
    python mimir_auto_enrich.py "implement feature X" --output .jcode/prompts/01-enriched.md
    
    # Just print the context
    python mimir_auto_enrich.py "how does auth work?" --print
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mimir-auto-enrich")

MIMIR_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = MIMIR_ROOT / ".venv" / "bin" / "python"


def enrich_task(task: str, project_root: Optional[Path] = None) -> dict:
    """Run enrichment using Mimir's query_router via the venv Python."""
    if project_root is None:
        project_root = MIMIR_ROOT
    
    # Use the venv Python to run enrichment
    escaped_task = task.replace('"', '\\"').replace("'", "\\'")
    escaped_mimir_root = str(MIMIR_ROOT).replace('"', '\\"')
    escaped_project_root = str(project_root).replace('"', '\\"')
    
    script = f'''
import sys
import json
from pathlib import Path

# Add Mimir to path
mimir_root = Path("{escaped_mimir_root}")
sys.path.insert(0, str(mimir_root / "src"))

try:
    from mimir.query_router import route_task
    
    task = "{escaped_task}"
    result = route_task(task, project_root=Path("{escaped_project_root}"))
    
    output = {{
        "success": result.success,
        "context": result.context,
        "routed_to": result.routed_to,
        "query_type": result.query_type,
        "cache_hit": result.cache_hit,
        "elapsed_ms": result.elapsed_ms,
    }}
    print(json.dumps(output))
    
except Exception as e:
    import traceback
    error_output = {{
        "success": False,
        "error": str(e),
        "traceback": traceback.format_exc(),
        "context": "",
    }}
    print(json.dumps(error_output))
'''
    
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            logger.error(f"Enrichment script failed: {result.stderr}")
            return {"success": False, "error": result.stderr, "context": ""}
        
        output = json.loads(result.stdout)
        return output
        
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Enrichment timed out", "context": ""}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse enrichment output: {e}")
        logger.error(f"stdout: {result.stdout[:500]}")
        return {"success": False, "error": "Invalid output from enrichment", "context": ""}


def format_for_prompt(task: str, enrichment: dict) -> str:
    """Format enriched context as a prompt section."""
    if not enrichment.get("success"):
        error = enrichment.get("error", "Unknown error")
        return f"<!-- Mimir enrichment failed: {error} -->\n"
    
    context = enrichment.get("context", "")
    if not context:
        return "<!-- No Mimir context available -->\n"
    
    routed_to = enrichment.get("routed_to", "unknown")
    query_type = enrichment.get("query_type", "unknown")
    cache_hit = enrichment.get("cache_hit", False)
    
    return f"""## Mimir Auto-Enriched Context

**Task**: {task}
**Source**: Mimir ({routed_to}, {query_type})
**Cache**: {"hit" if cache_hit else "miss"}

### Project Context

{context}

---

**Instructions**: The above context was automatically injected by Mimir. Use it to inform your implementation.

"""


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Mimir Auto-Enrich: Automatic context enrichment for Jcode"
    )
    parser.add_argument("task", help="Task description to enrich")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for prompt file (default: print to stdout)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=MIMIR_ROOT,
        help="Project root directory",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print enriched context to stdout",
    )
    
    args = parser.parse_args()
    
    # Check venv exists
    if not VENV_PYTHON.exists():
        logger.error(f"Mimir venv not found at {VENV_PYTHON}")
        logger.error("Run: cd " + str(MIMIR_ROOT) + " && uv venv && uv pip install -e .")
        sys.exit(1)
    
    # Enrich task
    logger.info(f"Enriching task: {args.task[:50]}...")
    enrichment = enrich_task(args.task, args.project_root)
    
    if not enrichment.get("success") and not args.print:
        logger.warning(f"Enrichment failed: {enrichment.get('error')}")
    
    # Format output
    prompt_content = format_for_prompt(args.task, enrichment)
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(prompt_content)
        logger.info(f"✅ Enriched context written to: {args.output}")
        logger.info(f"   Context length: {len(enrichment.get('context', ''))} chars")
    else:
        print(prompt_content)
    
    sys.exit(0 if enrichment.get("success") else 1)


if __name__ == "__main__":
    main()
