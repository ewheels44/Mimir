#!/bin/bash
"""
Mimir Context Enrichment Script

This script:
1. Activates the Mimir venv
2. Runs enrichment using Mimir's query_router
3. Outputs enriched context as JSON or markdown

Usage:
    ./mimir-enrich.sh "task description" [--json|--markdown]
"""

set -e

MIMIR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PYTHON="$MIMIR_ROOT/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Mimir venv not found at $VENV_PYTHON"
    echo "   Run: cd $MIMIR_ROOT && uv venv && uv pip install -e ."
    exit 1
fi

TASK="$1"
OUTPUT_FORMAT="${2:---markdown}"

if [ -z "$TASK" ]; then
    echo "Usage: $0 'task description' [--json|--markdown]"
    exit 1
fi

# Create a Python script that does the enrichment
"$VENV_PYTHON" - <<EOF
import sys
import json
from pathlib import Path

# Add Mimir src to path
mimir_root = Path("$MIMIR_ROOT")
sys.path.insert(0, str(mimir_root / "src"))

try:
    from mimir.query_router import route_task
    
    task = """$TASK"""
    result = route_task(task, project_root=mimir_root)
    
    if "$OUTPUT_FORMAT" == "--json":
        output = {
            "success": result.success,
            "context": result.context,
            "routed_to": result.routed_to,
            "query_type": result.query_type,
            "cache_hit": result.cache_hit,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.success and result.context:
            print(f"## Mimir Enriched Context\n")
            print(f"**Task**: {task}")
            print(f"**Routed to**: {result.routed_to} ({result.query_type})\n")
            print(f"### Context\n")
            print(result.context)
            print("\n---")
        else:
            print(f"⚠️  Enrichment failed or no context available")
            if hasattr(result, 'error') and result.error:
                print(f"   Error: {result.error}")
            
except ImportError as e:
    print(f"❌ Failed to import Mimir: {e}", file=sys.stderr)
    print(f"   Make sure dependencies are installed in {mimir_root}/.venv", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"❌ Enrichment failed: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF
