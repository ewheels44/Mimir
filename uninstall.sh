#!/usr/bin/env bash
#
# uninstall.sh — Mimir Uninstallation Script
#
# Usage:
#   bash uninstall.sh              # Uninstall Mimir
#   bash uninstall.sh --help       # Show help
#   bash uninstall.sh --purge     # Remove all data (knowledge bases, etc.)
#
# This script:
#   1. Removes virtual environment
#   2. Removes built web components
#   3. Removes shell configuration
#   4. Optionally removes all Mimir data (with --purge)
#   5. Removes git hooks (if present)
#
# The script is safe — it won't delete your projects or indexed data
# unless you explicitly use --purge.
#

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────

MIMIR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${MIMIR_ROOT}/.venv"
BIN_DIR="${MIMIR_ROOT}/bin"

# Default options
PURGE=false
FORCE=false
VERBOSE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── Helper Functions ──────────────────────────────────────────────────────

print_header() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Mimir Uninstallation Script${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "  $1"
    fi
}

die() {
    print_error "$1"
    exit 1
}

prompt_confirm() {
    local prompt="${1:-Are you sure?}"
    local response

    if [ "$FORCE" = true ]; then
        return 0
    fi

    read -r -p "$prompt [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ─── Argument Parsing ─────────────────────────────────────────────────────

show_help() {
    cat << EOF
Mimir Uninstallation Script

Usage: bash uninstall.sh [OPTIONS]

Options:
  --purge         Remove ALL Mimir data (knowledge bases, indexes, etc.)
  --force         Skip confirmation prompts
  --verbose       Enable verbose output
  --help          Show this help message

Examples:
  bash uninstall.sh
  bash uninstall.sh --purge
  bash uninstall.sh --force

Note: By default, this script only removes Mimir installation files.
      Your projects and their .knowledge directories are NOT deleted.
      Use --purge to remove everything.

EOF
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --purge)
                PURGE=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                show_help
                ;;
            *)
                die "Unknown option: $1"
                ;;
        esac
    done
}

# ─── Uninstall Steps ─────────────────────────────────────────────────────

remove_virtual_env() {
    print_info "Removing Python virtual environment..."

    if [ -d "$VENV_DIR" ]; then
        rm -rf "$VENV_DIR"
        print_success "Virtual environment removed: $VENV_DIR"
    else
        print_warning "Virtual environment not found at $VENV_DIR"
    fi
}

remove_binaries() {
    print_info "Removing Mimir binaries..."

    if [ -d "$BIN_DIR" ]; then
        rm -rf "$BIN_DIR"
        print_success "Binaries removed: $BIN_DIR"
    else
        print_warning "Bin directory not found at $BIN_DIR"
    fi

    # Remove from shell config
    local shell_configs=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile")
    local mimir_path="$MIMIR_ROOT/bin"

    for config in "${shell_configs[@]}"; do
        if [ -f "$config" ] && grep -q "$mimir_path" "$config" 2>/dev/null; then
            if [ "$FORCE" = true ] || prompt_confirm "Remove Mimir PATH from $config?"; then
                # Remove lines containing Mimir path
                grep -v "$mimir_path" "$config" > "${config}.tmp" || true
                mv "${config}.tmp" "$config"
                print_success "Removed Mimir from $config"
            fi
        fi
    done
}

remove_web_components() {
    print_info "Removing web components..."

    # Remove Rust build artifacts
    if [ -d "$MIMIR_ROOT/web/server/target" ]; then
        rm -rf "$MIMIR_ROOT/web/server/target"
        print_success "Rust build artifacts removed"
    fi

    # Remove React build artifacts
    if [ -d "$MIMIR_ROOT/web/client/dist" ]; then
        rm -rf "$MIMIR_ROOT/web/client/dist"
        print_success "React build artifacts removed"
    fi

    # Remove node_modules
    if [ -d "$MIMIR_ROOT/web/client/node_modules" ]; then
        if [ "$FORCE" = true ] || prompt_confirm "Remove node_modules (fetched packages)?"; then
            rm -rf "$MIMIR_ROOT/web/client/node_modules"
            print_success "node_modules removed"
        fi
    fi
}

remove_git_hooks() {
    print_info "Checking for git hooks..."

    if [ -d "$MIMIR_ROOT/.git" ]; then
        local hooks_dir="$MIMIR_ROOT/.git/hooks"
        local post_commit="$hooks_dir/post-commit"

        if [ -f "$post_commit" ] && grep -q "mimir" "$post_commit" 2>/dev/null; then
            if [ "$FORCE" = true ] || prompt_confirm "Remove Mimir git hooks?"; then
                # Check if it's only Mimir hook or has other content
                if [ "$(grep -c '' "$post_commit")" -lt 10 ] && grep -q "mimir-reindex" "$post_commit"; then
                    rm -f "$post_commit"
                    print_success "Mimir git hooks removed"
                else
                    # Try to remove only Mimir parts
                    print_warning "Git hook has other content. Please remove Mimir lines manually."
                fi
            fi
        else
            print_verbose "No Mimir git hooks found"
        fi
    fi
}

purge_data() {
    if [ "$PURGE" != true ]; then
        return
    fi

    print_warning "PURGE MODE: This will remove ALL Mimir data!"

    if [ "$FORCE" = true ] || prompt_confirm "This will delete all knowledge bases, indexes, and cached data. Continue?"; then
        # Remove global Mimir data
        if [ -d "$HOME/.mimir" ]; then
            rm -rf "$HOME/.mimir"
            print_success "Global Mimir data removed: $HOME/.mimir"
        fi

        # Remove .knowledge directories in Mimir root (if it's a project too)
        if [ -d "$MIMIR_ROOT/.knowledge" ]; then
            rm -rf "$MIMIR_ROOT/.knowledge"
            print_success "Knowledge directory removed"
        fi

        if [ -d "$MIMIR_ROOT/.mimir" ]; then
            rm -rf "$MIMIR_ROOT/.mimir"
            print_success "Project Mimir config removed"
        fi

        print_warning "Note: Data in other projects was NOT removed."
        print_info "To remove data from specific projects, go to each project and run:"
        print_info "  rm -rf .knowledge .mimir"
    else
        print_info "Purge cancelled."
    fi
}

# ─── Main ────────────────────────────────────────────────────────────────

main() {
    parse_args "$@"

    print_header

    print_info "Mimir root: $MIMIR_ROOT"
    print_info "Purge mode: $PURGE"
    echo ""

    if [ "$FORCE" != true ]; then
        if ! prompt_confirm "Proceed with uninstallation?"; then
            print_info "Uninstallation cancelled."
            exit 0
        fi
    fi

    echo ""

    remove_virtual_env
    echo ""

    remove_binaries
    echo ""

    remove_web_components
    echo ""

    remove_git_hooks
    echo ""

    purge_data
    echo ""

    # Final message
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Mimir uninstallation complete!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ "$PURGE" != true ]; then
        print_info "Note: Your projects and their data were NOT deleted."
        print_info "To remove project data, go to each project and run:"
        print_info "  rm -rf .knowledge .mimir"
    fi

    print_info "Mimir has been uninstalled."
}

# Run main function
main "$@"
