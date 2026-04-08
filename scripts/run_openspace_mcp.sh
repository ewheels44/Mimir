#!/bin/bash
# Wrapper script for OpenSpace MCP server
# Reads OpenRouter API key from OpenCode's auth file to share with Mimir

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
    echo "[OpenSpace Wrapper] $1" >&2
}

# Read OpenRouter API key from OpenCode auth file
AUTH_FILE="$HOME/.local/share/opencode/auth.json"

if [ -z "$OPENROUTER_API_KEY" ] && [ -f "$AUTH_FILE" ]; then
    log "Reading OPENROUTER_API_KEY from $AUTH_FILE"
    API_KEY=$(python3 -c "
import json
import sys
try:
    with open('$AUTH_FILE') as f:
        data = json.load(f)
    key = data.get('openrouter', {}).get('key', '')
    if key:
        print(key)
        sys.exit(0)
except Exception as e:
    pass
sys.exit(1)
" 2>&1)
    
    if [ $? -eq 0 ] && [ -n "$API_KEY" ]; then
        export OPENROUTER_API_KEY="$API_KEY"
        log "Successfully loaded OPENROUTER_API_KEY (length: ${#API_KEY})"
    else
        log "Failed to extract key from $AUTH_FILE"
    fi
elif [ -n "$OPENROUTER_API_KEY" ]; then
    log "OPENROUTER_API_KEY already set"
else
    log "No auth file found at $AUTH_FILE"
fi

# Pass through skill dirs from environment if not set
if [ -z "$OPENSPACE_HOST_SKILL_DIRS" ]; then
    export OPENSPACE_HOST_SKILL_DIRS="$SCRIPT_DIR/skills"
    log "Set default OPENSPACE_HOST_SKILL_DIRS: $OPENSPACE_HOST_SKILL_DIRS"
fi

if [ -z "$OPENSPACE_WORKSPACE" ]; then
    export OPENSPACE_WORKSPACE="$HOME/Documents/OpenSpace"
    log "Set default OPENSPACE_WORKSPACE: $OPENSPACE_WORKSPACE"
fi

# Find openspace-mcp binary
if [ -n "$OPENSPACE_VENV" ] && [ -x "$OPENSPACE_VENV/bin/openspace-mcp" ]; then
    OPENSPACE_BIN="$OPENSPACE_VENV/bin/openspace-mcp"
elif [ -x "$OPENSPACE_WORKSPACE/.venv/bin/openspace-mcp" ]; then
    OPENSPACE_BIN="$OPENSPACE_WORKSPACE/.venv/bin/openspace-mcp"
elif command -v openspace-mcp &> /dev/null; then
    OPENSPACE_BIN="$(command -v openspace-mcp)"
else
    log "ERROR: openspace-mcp not found. Install OpenSpace or set OPENSPACE_VENV."
    exit 1
fi

log "Using openspace-mcp: $OPENSPACE_BIN"

# Run the OpenSpace MCP server
cd "$SCRIPT_DIR"
exec "$OPENSPACE_BIN" "$@"
