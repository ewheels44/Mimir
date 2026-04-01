#!/bin/bash
# Wrapper script for Mimir MCP server
# Auto-detects project root from CWD and sets environment variables

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Debug logging to stderr (goes to OpenCode logs)
log() {
    echo "[Mimir Wrapper] $1" >&2
}

# Detect project root by walking up from current directory
detect_project_root() {
    local cwd="$(pwd)"
    local markers=(".opencode" "opencode.json" ".git" "pyproject.toml" "package.json" "Cargo.toml")
    
    local current="$cwd"
    while [ "$current" != "$(dirname "$current")" ]; do
        for marker in "${markers[@]}"; do
            if [ -e "$current/$marker" ]; then
                echo "$current"
                return 0
            fi
        done
        current="$(dirname "$current")"
    done
    
    echo "$cwd"
}

# Set PROJECT_ROOT if not already set
if [ -z "$PROJECT_ROOT" ]; then
    export PROJECT_ROOT="$(detect_project_root)"
    log "Auto-detected PROJECT_ROOT: $PROJECT_ROOT"
else
    log "Using provided PROJECT_ROOT: $PROJECT_ROOT"
fi

# Set KNOWLEDGE_DIR and DOCS_DIR based on PROJECT_ROOT if not set
if [ -z "$KNOWLEDGE_DIR" ]; then
    export KNOWLEDGE_DIR="$PROJECT_ROOT/.knowledge/llamaindex"
    log "Set KNOWLEDGE_DIR: $KNOWLEDGE_DIR"
fi

if [ -z "$DOCS_DIR" ]; then
    export DOCS_DIR="$PROJECT_ROOT/docs"
    log "Set DOCS_DIR: $DOCS_DIR"
fi

# Check if OPENROUTER_API_KEY is already set
if [ -n "$OPENROUTER_API_KEY" ]; then
    log "OPENROUTER_API_KEY already set (length: ${#OPENROUTER_API_KEY})"
else
    log "OPENROUTER_API_KEY not set, trying to read from auth file"
    # Try multiple possible auth file locations
    AUTH_LOCATIONS=(
        "$HOME/.local/share/opencode/auth.json"
        "${HOME:-/Users/ethanwheeler}/.local/share/opencode/auth.json"
        "/Users/ethanwheeler/.local/share/opencode/auth.json"
    )
    
    for AUTH_FILE in "${AUTH_LOCATIONS[@]}"; do
        log "Checking auth file: $AUTH_FILE"
        if [ -f "$AUTH_FILE" ]; then
            log "Found auth file: $AUTH_FILE"
            # Extract the key using Python
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
                log "Successfully loaded OPENROUTER_API_KEY from $AUTH_FILE (length: ${#API_KEY})"
                break
            else
                log "Failed to extract key from $AUTH_FILE"
            fi
        fi
    done
fi

# Final check
if [ -z "$OPENROUTER_API_KEY" ]; then
    log "ERROR: OPENROUTER_API_KEY is still not set!"
else
    log "OPENROUTER_API_KEY is configured (length: ${#OPENROUTER_API_KEY})"
fi

# Set default base URL if using OpenRouter
if [ -n "$OPENROUTER_API_KEY" ] && [ -z "$OPENAI_BASE_URL" ]; then
    export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
    log "Set OPENAI_BASE_URL: $OPENAI_BASE_URL"
fi

# Find uv executable
UV_PATH=$(which uv 2>/dev/null || echo "/opt/homebrew/bin/uv")
if [ ! -x "$UV_PATH" ]; then
    log "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
log "Using uv: $UV_PATH"

# Run the MCP server from SCRIPT_DIR
cd "$SCRIPT_DIR"
log "Starting MCP server with uv..."
exec "$UV_PATH" run --python '>=3.11' "$SCRIPT_DIR/mcp_server_llamaindex.py" "$@"
