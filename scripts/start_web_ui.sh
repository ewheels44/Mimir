#!/bin/bash
# Launch Mimir Web UI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIMIR_DIR="$SCRIPT_DIR/.."

echo "🌐 Starting Mimir Web UI..."
echo ""

# Check if we're in a project directory
if [ -z "$PROJECT_ROOT" ]; then
    export PROJECT_ROOT="$(pwd)"
    echo "📁 Project root: $PROJECT_ROOT"
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
exec uv run --python '>=3.11' python web/server.py
