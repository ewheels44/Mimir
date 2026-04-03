#!/usr/bin/env bash
# dev.sh — start Mimir web UI in development mode
# Usage: ./dev.sh [--project /path/to/project] [--port 8000]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${PROJECT_ROOT:-$(pwd)}"
PORT="${PORT:-8000}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --project) PROJECT="$2"; shift 2 ;;
    --port)    PORT="$2";    shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# Resolve to absolute path (handles relative paths like "." or "../project")
PROJECT_ROOT="$(cd "$PROJECT" && pwd)"
export PROJECT_ROOT
export KNOWLEDGE_DIR="${KNOWLEDGE_DIR:-$PROJECT_ROOT/.knowledge/llamaindex}"

echo "▶ Mimir Dev"
echo "  project:  $PROJECT_ROOT"
echo "  knowledge: $KNOWLEDGE_DIR"
echo "  backend:  http://localhost:$PORT"
echo "  frontend: http://localhost:5173  (proxied)"
echo ""

# Build client deps if needed
if [ ! -d "$SCRIPT_DIR/client/node_modules" ]; then
  echo "→ Installing npm dependencies..."
  (cd "$SCRIPT_DIR/client" && npm install)
fi

# Trap to kill all children on Ctrl-C
cleanup() {
  echo ""
  echo "Shutting down..."
  # Kill entire process groups to ensure no zombies
  kill -- -"$RUST_PID" 2>/dev/null || true
  kill -- -"$VITE_PID" 2>/dev/null || true
  # Fallback: also kill by PID directly
  kill "$RUST_PID" 2>/dev/null || true
  kill "$VITE_PID" 2>/dev/null || true
  # Kill any remaining sidecar processes
  pkill -f "sidecar.py" 2>/dev/null || true
  pkill -f "mimir-web" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start Rust backend
echo "→ Starting Rust backend (cargo run)..."
(cd "$SCRIPT_DIR/server" && \
  RUST_LOG=mimir_web=info,warn \
  cargo run -- \
    --project "$PROJECT_ROOT" \
    --port "$PORT" \
) &
RUST_PID=$!

# Start Vite dev server
echo "→ Starting Vite dev server..."
(cd "$SCRIPT_DIR/client" && npm run dev) &
VITE_PID=$!

# Wait for either to exit (compatible with bash 3.2 on macOS)
wait "$RUST_PID" "$VITE_PID"
