#!/usr/bin/env bash
# build.sh — production build
# Outputs: server/target/release/mimir-web (serves client/dist statically)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "→ Building React client..."
(cd "$SCRIPT_DIR/client" && npm install && npm run build)

echo "→ Building Rust server..."
(cd "$SCRIPT_DIR/server" && cargo build --release)

echo ""
echo "✓ Build complete."
echo "  Binary:  $SCRIPT_DIR/server/target/release/mimir-web"
echo ""
echo "Usage:"
echo "  ./server/target/release/mimir-web --project /path/to/project"
