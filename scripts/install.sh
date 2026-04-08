#!/bin/bash
# Mimir Installer — thin wrapper around mimir-init.py
# Run: bash scripts/install.sh

set -e

MIMIR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec python3 "$MIMIR_DIR/mimir-init.py" --install "$@"
