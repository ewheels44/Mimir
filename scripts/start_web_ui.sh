#!/bin/bash
# Launch Mimir Web UI (React + Rust/Axum version)
# Usage: start_web_ui.sh [project_directory]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIMIR_DIR="$SCRIPT_DIR/.."

# Handle optional project directory argument
if [ $# -ge 1 ]; then
    PROJECT_ARG="$1"
    # Convert to absolute path and resolve .. components
    if [[ "$PROJECT_ARG" = /* ]]; then
        PROJECT_ROOT="$(cd "$PROJECT_ARG" 2>/dev/null && pwd || echo "$PROJECT_ARG")"
    else
        PROJECT_ROOT="$(cd "$(pwd)/$PROJECT_ARG" 2>/dev/null && pwd || echo "$(pwd)/$PROJECT_ARG")"
    fi
    echo "🌐 Starting Mimir Web UI..."
    echo ""
    echo "📁 Project root (from argument): $PROJECT_ROOT"
else
    echo "🌐 Starting Mimir Web UI..."
    echo ""
    # Check if we're in a project directory
    if [ -z "$PROJECT_ROOT" ]; then
        # If running from scripts directory, use Mimir root instead
        if [ "$(basename "$(pwd)")" = "scripts" ] && [ -f "$MIMIR_DIR/mcp_server_llamaindex.py" ]; then
            PROJECT_ROOT="$(cd "$MIMIR_DIR" && pwd)"
        else
            PROJECT_ROOT="$(pwd)"
        fi
        echo "📁 Project root (auto-detected): $PROJECT_ROOT"
    else
        echo "📁 Project root (from env): $PROJECT_ROOT"
    fi
fi

export PROJECT_ROOT

# Check for Rust toolchain
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust not found. Please install Rust: https://rustup.rs"
    exit 1
fi

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 20+: https://nodejs.org"
    exit 1
fi

cd "$MIMIR_DIR/web"

# Build if needed
if [ ! -f "$MIMIR_DIR/web/server/target/release/mimir-web" ]; then
    echo "🔨 Building Rust server (first time only)..."
    ./build.sh
fi

echo ""
echo "🚀 Starting Mimir Web UI..."
echo "   Project: $PROJECT_ROOT"
echo ""
echo "   Production: http://localhost:8000"
echo "   (Press Ctrl+C to stop)"
echo ""

# Run the production server
exec ./server/target/release/mimir-web --project "$PROJECT_ROOT"
