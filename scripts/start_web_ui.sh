#!/bin/bash
# Launch Mimir Web UI
# Usage: start_web_ui.sh [project_directory]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIMIR_DIR="$SCRIPT_DIR/.."

# Handle optional project directory argument
if [ $# -ge 1 ]; then
    PROJECT_ARG="$1"
    # Convert to absolute path and resolve .. components
    if [[ "$PROJECT_ARG" = /* ]]; then
        export PROJECT_ROOT="$(cd "$PROJECT_ARG" 2>/dev/null && pwd || echo "$PROJECT_ARG")"
    else
        export PROJECT_ROOT="$(cd "$(pwd)/$PROJECT_ARG" 2>/dev/null && pwd || echo "$(pwd)/$PROJECT_ARG")"
    fi
    echo "🌐 Starting Mimir Web UI..."
    echo ""
    echo "📁 Project root (from argument): $PROJECT_ROOT"
else
    echo "🌐 Starting Mimir Web UI..."
    echo ""
    # Check if we're in a project directory
    if [ -z "$PROJECT_ROOT" ]; then
        export PROJECT_ROOT="$(pwd)"
        echo "📁 Project root (auto-detected): $PROJECT_ROOT"
    else
        echo "📁 Project root (from env): $PROJECT_ROOT"
    fi
fi

# Set knowledge directory
if [ -z "$KNOWLEDGE_DIR" ]; then
    export KNOWLEDGE_DIR="$PROJECT_ROOT/.knowledge/llamaindex"
    echo "📚 Knowledge dir: $KNOWLEDGE_DIR"
fi

# Check for OpenRouter API key
if [ -z "$OPENROUTER_API_KEY" ]; then
    AUTH_FILE="$HOME/.local/share/opencode/auth.json"
    if [ -f "$AUTH_FILE" ]; then
        export OPENROUTER_API_KEY=$(python3 -c "
import json
with open('$AUTH_FILE') as f:
    data = json.load(f)
print(data.get('openrouter', {}).get('key', ''))
" 2>/dev/null)
        echo "🔑 Loaded API key from auth file"
    fi
fi

echo ""
echo "🚀 Starting server on http://localhost:8000"
echo ""

cd "$MIMIR_DIR"

# Pass through any arguments to the server
if [ $# -ge 1 ]; then
    # Use resolved PROJECT_ROOT, not raw $1, since we've cd'd to MIMIR_DIR
    echo "Args for server"
    echo $PROJECT_ROOT
    exec uv run --python '>=3.11' python web/server.py --project "$PROJECT_ROOT"
else
    echo "No Server Args"
    exec uv run --python '>=3.11' python web/server.py
fi
