#!/bin/bash
# Wrapper script for Mimir MCP server
# Auto-detects project root from CWD and sets environment variables
# Includes robust cleanup to prevent stale processes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Debug logging to stderr (goes to OpenCode logs)
log() {
    echo "[Mimir Wrapper] $1" >&2
}

# Create a unique identifier for this project instance
get_project_id() {
    echo "$PROJECT_ROOT" | tr '/' '_'
}

# Get the PID file path
get_pid_file() {
    local project_id=$(get_project_id)
    echo "/tmp/mimir-mcp-${project_id}.pid"
}

# Cleanup function - kill stale processes and remove PID file
cleanup_stale() {
    local pid_file=$(get_pid_file)
    
    # Check if there's a PID file from a previous run
    if [ -f "$pid_file" ]; then
        local old_pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            log "Found stale MCP server process (PID: $old_pid), terminating..."
            kill -TERM "$old_pid" 2>/dev/null || true
            sleep 1
            # Force kill if still running
            if kill -0 "$old_pid" 2>/dev/null; then
                log "Force killing stale process..."
                kill -9 "$old_pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
    
    # Also kill any other MCP servers for this project that might be orphaned
    local project_pattern=$(echo "$PROJECT_ROOT" | sed 's/\//\\\//g')
    local stale_pids=$(ps aux | grep "mcp_server_llamaindex.py" | grep "$PROJECT_ROOT" | grep -v grep | awk '{print $2}')
    if [ -n "$stale_pids" ]; then
        log "Cleaning up additional orphaned MCP processes..."
        echo "$stale_pids" | while read -r pid; do
            if [ "$pid" != "$$" ] && [ "$pid" != "$MCP_PID" ]; then
                kill -TERM "$pid" 2>/dev/null || true
                sleep 0.5
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    fi
}

# Cleanup on exit - remove PID file
on_exit() {
    local exit_code=$?
    local pid_file=$(get_pid_file)
    
    if [ -f "$pid_file" ]; then
        local saved_pid=$(cat "$pid_file" 2>/dev/null)
        # Only remove if it's our PID
        if [ "$saved_pid" = "$$" ] || [ "$saved_pid" = "$MCP_PID" ]; then
            rm -f "$pid_file"
            log "Cleaned up PID file"
        fi
    fi
    
    # If the MCP server is still running, kill it
    if [ -n "$MCP_PID" ] && kill -0 "$MCP_PID" 2>/dev/null; then
        log "Terminating MCP server (PID: $MCP_PID)..."
        kill -TERM "$MCP_PID" 2>/dev/null || true
        wait "$MCP_PID" 2>/dev/null || true
    fi
    
    exit $exit_code
}

# Signal handlers
cleanup_on_signal() {
    log "Received signal, cleaning up..."
    on_exit
}

# Register cleanup handlers
trap on_exit EXIT
trap cleanup_on_signal INT TERM HUP

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

# Clean up any stale processes before starting
cleanup_stale

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
    # Try auth file locations
    AUTH_LOCATIONS=(
        "$HOME/.local/share/opencode/auth.json"
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

# Find uv or python executable
UV_PATH=$(which uv 2>/dev/null || echo "")
PYTHON_PATH=$(which python3 2>/dev/null || echo "")
if [ -z "$UV_PATH" ] && [ -z "$PYTHON_PATH" ]; then
    log "ERROR: Neither uv nor python3 found. Install Python 3.11+ or uv."
    exit 1
fi
log "Using uv: ${UV_PATH:-not found}, python3: ${PYTHON_PATH:-not found}"

# Set PYTHONPATH to include src directory for mimir imports
export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
log "Set PYTHONPATH: $PYTHONPATH"

# Run the MCP server from SCRIPT_DIR
cd "$SCRIPT_DIR"
log "Starting MCP server with uv..."

# Create PID file before starting
PID_FILE=$(get_pid_file)
echo $$ > "$PID_FILE"
log "Created PID file: $PID_FILE (wrapper PID: $$)"

# Start the MCP server - exec replaces this shell with the Python process
# The trap handlers will still work because exec preserves signal handlers
if [ -n "$UV_PATH" ]; then
    log "Starting MCP server with uv..."
    exec env PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH" "$UV_PATH" run --python '>=3.11' "$SCRIPT_DIR/mcp_server_llamaindex.py" "$@"
else
    log "Starting MCP server with python3..."
    exec env PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH" "$PYTHON_PATH" "$SCRIPT_DIR/mcp_server_llamaindex.py" "$@"
fi
