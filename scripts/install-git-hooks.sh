#!/usr/bin/env bash
#
# install-git-hooks.sh — Install Mimir auto-index git hooks
#
# Usage:
#   bash ~/Documents/Mimir/scripts/install-git-hooks.sh              # current repo
#   bash ~/Documents/Mimir/scripts/install-git-hooks.sh /path/to/repo # specific repo
#   bash ~/Documents/Mimir/scripts/install-git-hooks.sh --all         # all Mimir projects
#

set -euo pipefail

MIMIR_DIR="${MIMIR_HOME:-$HOME/Documents/Mimir}"
HOOK_SOURCE="$MIMIR_DIR/scripts/git-hooks/post-commit"

install_hook() {
    local repo_dir="$1"
    local git_dir="$repo_dir/.git"
    local hooks_dir="$git_dir/hooks"
    local target="$hooks_dir/post-commit"

    if [ ! -d "$git_dir" ]; then
        echo "  ⚠️  Not a git repo: $repo_dir"
        return 1
    fi

    # Create hooks dir if missing
    mkdir -p "$hooks_dir"

    # Check for existing hook
    if [ -f "$target" ]; then
        # Check if it's already our hook
        if grep -q "mimir-reindex-hook.py" "$target" 2>/dev/null; then
            echo "  ✅ Already installed: $repo_dir"
            return 0
        fi

        # Existing non-Mimir hook — append ours
        echo "  ⚠️  Existing post-commit hook found. Appending Mimir hook."
        echo "" >> "$target"
        echo "# ── Mimir auto-index (appended by install-git-hooks.sh) ──" >> "$target"
        cat "$HOOK_SOURCE" | grep -v '^#!' | grep -v '^#' | grep -v '^$' >> "$target"
        chmod +x "$target"
        echo "  ✅ Appended to: $target"
        return 0
    fi

    # Fresh install
    cp "$HOOK_SOURCE" "$target"
    chmod +x "$target"
    echo "  ✅ Installed: $target"
    return 0
}

# ── Main ───────────────────────────────────────────────────────────
echo "🔗 Mimir Git Hook Installer"
echo ""

if [ ! -f "$HOOK_SOURCE" ]; then
    echo "❌ Hook source not found: $HOOK_SOURCE"
    exit 1
fi

if [ "${1:-}" = "--all" ]; then
    # Find all Mimir projects (have .mimir/config.json)
    echo "Scanning for Mimir projects..."
    count=0
    while IFS= read -r config; do
        repo_dir="$(dirname "$(dirname "$config")")"
        echo ""
        echo "📁 $repo_dir"
        install_hook "$repo_dir" && count=$((count + 1))
    done < <(find "$HOME/Documents" -maxdepth 4 -name "config.json" -path "*/.mimir/*" 2>/dev/null)
    echo ""
    echo "✅ Installed in $count project(s)"
else
    repo_dir="${1:-$(pwd)}"
    repo_dir="$(cd "$repo_dir" && pwd)"

    echo "📁 Target: $repo_dir"
    echo ""

    if install_hook "$repo_dir"; then
        echo ""
        echo "Done. Commits will now auto-index the Mimir knowledge base."
        echo "Logs: $repo_dir/.mimir/reindex.log"
    else
        exit 1
    fi
fi
