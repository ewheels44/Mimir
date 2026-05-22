#!/usr/bin/env python3
"""
Mimir Auto-Enrich Setup for Jcode

This script sets up automatic context enrichment for Jcode.
It creates a prompt file that Jcode loads automatically.

Usage:
    python setup_auto_enrich.py [--project-root /path/to/project]
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("setup-auto-enrich")

MIMIR_ROOT = Path(__file__).resolve().parent.parent.parent
AUTO_ENRICH_SCRIPT = MIMIR_ROOT / "scripts" / "jcode" / "mimir_auto_enrich.py"


def setup_jcode_prompt(task: str, project_root: Path) -> bool:
    """Set up Jcode prompt with enriched context."""
    prompts_dir = project_root / ".jcode" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    
    # Output file - use low number to load early
    output_file = prompts_dir / "01-mimir-auto-enriched.md"
    
    # Run auto-enrich script
    try:
        result = subprocess.run(
            [sys.executable, str(AUTO_ENRICH_SCRIPT), task, "--output", str(output_file)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Created enriched prompt: {output_file}")
            return True
        else:
            logger.warning(f"Enrichment failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Enrichment timed out")
        return False
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        return False


def create_wrapper_script(project_root: Path) -> Path:
    """Create a wrapper script that auto-enriches before Jcode."""
    scripts_dir = project_root / ".jcode" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    wrapper_path = scripts_dir / "mimir-wrap"
    
    wrapper_content = f"""#!/bin/bash
# Mimir Jcode Wrapper - Auto-enriches context before Jcode

MIMIR_ROOT="{MIMIR_ROOT}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Get the task from command line
TASK="$*"

if [ -z "$TASK" ]; then
    echo "Usage: mimir-wrap 'task description'"
    exit 1
fi

# Generate enriched prompt
python3 "$MIMIR_ROOT/scripts/jcode/mimir_auto_enrich.py" \\
    "$TASK" \\
    --project-root "$PROJECT_ROOT" \\
    --output "$PROJECT_ROOT/.jcode/prompts/01-mimir-auto-enriched.md"

echo "✅ Context enriched. Start Jcode and type your task."
echo "   The enriched context is in: .jcode/prompts/01-mimir-auto-enriched.md"
"""
    
    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(0o755)
    
    logger.info(f"✅ Created wrapper script: {wrapper_path}")
    return wrapper_path


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Set up Mimir auto-enrichment for Jcode")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="implement a new feature",
        help="Sample task to generate initial enrichment",
    )
    parser.add_argument(
        "--wrapper",
        action="store_true",
        help="Also create a wrapper script",
    )
    
    args = parser.parse_args()
    
    # Check if Mimir project
    if not (args.project_root / ".knowledge" / "llamaindex").exists():
        logger.error(f"Not a Mimir project: {args.project_root}")
        logger.error("Run: python mimir.py init --code-dirs=src")
        sys.exit(1)
    
    # Setup auto-enrichment
    logger.info(f"Setting up auto-enrichment for: {args.project_root}")
    success = setup_jcode_prompt(args.task, args.project_root)
    
    if args.wrapper:
        wrapper = create_wrapper_script(args.project_root)
        print(f"\n📝 Wrapper script created: {wrapper}")
        print(f"   Usage: {wrapper} 'your task description'")
    
    print("\n" + "="*60)
    print("Mimir Auto-Enrichment Setup Complete")
    print("="*60)
    print("\nWhat happens now:")
    print("1. Jcode will load the enriched prompt automatically")
    print("2. The prompt is at: .jcode/prompts/01-mimir-auto-enriched.md")
    print("3. To re-enrich with a new task, run:")
    print(f"   python {AUTO_ENRICH_SCRIPT} 'your task' --output .jcode/prompts/01-mimir-auto-enriched.md")
    print("\n💡 Tip: The enrichment runs automatically when you start Jcode.")
    print("   The context is already there when the agent begins thinking.\n")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
