#!/bin/bash
# Mimir Enrich - Simple context enrichment for Jcode
# Usage: mimir-enrich "your task description"

set -e

MIMIR_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$MIMIR_ROOT/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Mimir venv not found at $VENV_PYTHON"
    echo "   Run: cd $MIMIR_ROOT && uv venv && uv pip install -e ."
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: $0 'task description'"
    echo ""
    echo "Example:"
    echo "  $0 'implement a new feature for user authentication'"
    echo ""
    echo "This will:"
    echo "  1. Enrich the task with Mimir context"
    echo "  2. Save context to .jcode/prompts/01-mimir-enriched.md"
    echo "  3. Tell you to start Jcode"
    exit 1
fi

TASK="$1"
PROJECT_ROOT="${2:-$PWD}"

echo "🔍 Enriching task with Mimir context..."
echo "   Task: $TASK"
echo "   Project: $PROJECT_ROOT"
echo ""

# Run enrichment using the venv Python
"$VENV_PYTHON" - <<EOF
import sys
import json
from pathlib import Path

# Add Mimir to path
mimir_root = Path("$MIMIR_ROOT")
sys.path.insert(0, str(mimir_root / "src"))

try:
    from mimir.query_router import route_task
    
    task = """$TASK"""
    project_root = Path("$PROJECT_ROOT")
    
    print("⏳ Running Mimir enrichment...", file=sys.stderr)
    result = route_task(task, project_root=project_root)
    
    if not result.success:
        print("⚠️  Enrichment failed or no context available", file=sys.stderr)
        sys.exit(1)
    
    context = result.context
    print(f"✅ Enrichment successful", file=sys.stderr)
    print(f"   Routed to: {result.routed_to}", file=sys.stderr)
    print(f"   Context length: {len(context)} chars", file=sys.stderr)
    
    # Save to prompt file
    prompts_dir = project_root / ".jcode" / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    output_path = prompts_dir / "01-mimir-enriched.md"
    
    prompt_content = f"""## Mimir Auto-Enriched Context

**Task**: {task}
**Source**: Mimir ({result.routed_to}, {result.query_type})
**Cache**: {"hit" if result.cache_hit else "miss"}

### Project Context

{context}

---

**Instructions**: The above context was automatically injected by Mimir. Use it to inform your implementation.
"""
    
    output_path.write_text(prompt_content)
    print(f"", file=sys.stderr)
    print(f"✅ Context saved to: {output_path}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"🚀 Now start Jcode - the context will be loaded automatically!", file=sys.stderr)
    print(f"   jcode", file=sys.stderr)
    
except Exception as e:
    print(f"❌ Enrichment failed: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
