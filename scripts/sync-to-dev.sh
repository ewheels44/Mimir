#!/bin/bash
#
# sync-to-dev.sh - Sync clean source files from 'knowledge' branch to 'dev'
#
# This script copies non-generated files from the 'knowledge' branch
# to the 'dev' branch, ensuring dev stays clean and clone-ready.
#
# Usage:
#   ./scripts/sync-to-dev.sh                    # Interactive mode
#   ./scripts/sync-to-dev.sh --dry-run          # Preview what would sync
#   ./scripts/sync-to-dev.sh --message "feat: add new feature"
#   ./scripts/sync-to-dev.sh --auto             # Non-interactive mode
#
# Generated files excluded:
#   - .knowledge/ (vector index, code relationships)
#   - .mimir/ (project config and copied AGENTS.md)
#   - __pycache__/, *.pyc, .venv/, etc.
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=false
AUTO_MODE=false
COMMIT_MESSAGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --auto)
            AUTO_MODE=true
            shift
            ;;
        --message|-m)
            COMMIT_MESSAGE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run          Preview what would be synced (no changes)"
            echo "  --auto             Non-interactive mode (no prompts)"
            echo "  --message, -m      Commit message (required in auto mode)"
            echo "  --help, -h         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Interactive sync"
            echo "  $0 --dry-run                          # Preview changes"
            echo "  $0 --message 'feat: add feature X'    # Sync with commit message"
            echo "  $0 --auto --message 'docs: update'    # Non-interactive sync"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

log_info() { echo -e "${BLUE}ℹ${NC}  $1"; }
log_success() { echo -e "${GREEN}✓${NC}  $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
log_error() { echo -e "${RED}✗${NC}  $1"; }

cd "$REPO_ROOT"

if [ ! -d ".git" ]; then
    log_error "Not a git repository!"
    exit 1
fi

if ! git diff-index --quiet HEAD --; then
    log_warn "You have uncommitted changes in the current branch"
    
    if [ "$AUTO_MODE" = false ]; then
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Aborted"
            exit 0
        fi
    else
        log_error "Uncommitted changes detected. Stash or commit them first."
        exit 1
    fi
fi

CURRENT_BRANCH=$(git branch --show-current)
log_info "Current branch: $CURRENT_BRANCH"

if ! git show-ref --verify --quiet refs/heads/knowledge; then
    log_error "Branch 'knowledge' not found"
    exit 1
fi

SYNC_PATTERNS=(
    "README.md"
    "AGENTS.md"
    "BLOG_POST.md"
    "pyproject.toml"
    "requirements.txt"
    "mimir-init.py"
    "mcp_server_llamaindex.py"
    "langgraph.json"
    "opencode.json"
    "src/"
    "tests/"
    "scripts/"
    "langgraph/"
    "web/"
    "examples/"
    "docs/"
    ".opencode/"
    ".gitignore"
)

EXCLUDE_PATTERNS=(
    ".knowledge/"
    ".mimir/"
    "__pycache__/"
    "*.pyc"
    ".venv/"
    "venv/"
    ".ruff_cache/"
    ".pytest_cache/"
    ".DS_Store"
    "*.egg-info/"
    "dist/"
    "build/"
)

log_info "Analyzing changes between 'knowledge' and 'dev'..."

DIFF_FILES=$(git diff --name-only dev..knowledge 2>/dev/null || true)

if [ -z "$DIFF_FILES" ]; then
    log_success "No differences between 'knowledge' and 'dev'"
    exit 0
fi

FILES_TO_SYNC=""
for file in $DIFF_FILES; do
    EXCLUDED=false
    for exclude in "${EXCLUDE_PATTERNS[@]}"; do
        if [[ "$file" == $exclude* ]] || [[ "$file" == *$exclude* ]]; then
            EXCLUDED=true
            break
        fi
    done
    
    if [ "$EXCLUDED" = true ]; then
        continue
    fi
    
    INCLUDED=false
    for pattern in "${SYNC_PATTERNS[@]}"; do
        pattern_base="${pattern%/}"
        if [[ "$file" == $pattern* ]] || [[ "$file" == "$pattern_base" ]]; then
            INCLUDED=true
            break
        fi
    done
    
    if [ "$INCLUDED" = true ]; then
        FILES_TO_SYNC="$FILES_TO_SYNC$file "
    fi
done

if [ -z "$FILES_TO_SYNC" ]; then
    log_success "No syncable files found (all differences are in excluded directories)"
    log_info "Excluded: .knowledge/, .mimir/, cache files, etc."
    exit 0
fi

echo ""
echo "Files to sync from 'knowledge' → 'dev':"
echo "───────────────────────────────────────"
for file in $FILES_TO_SYNC; do
    if git show-ref --verify --quiet refs/heads/dev; then
        if git diff --quiet dev..knowledge -- "$file" 2>/dev/null; then
            echo "  [same]  $file"
        else
            echo -e "  ${YELLOW}[modified]${NC} $file"
        fi
    else
        echo "  [new]   $file"
    fi
done
echo ""

NUM_FILES=$(echo "$FILES_TO_SYNC" | wc -w | tr -d ' ')
log_info "$NUM_FILES file(s) ready to sync"

if [ "$DRY_RUN" = true ]; then
    echo ""
    log_info "Dry run complete. No changes made."
    exit 0
fi

if [ "$AUTO_MODE" = false ]; then
    echo ""
    read -p "Proceed with sync? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Aborted"
        exit 0
    fi
fi

echo ""
log_info "Switching to 'dev' branch..."

ORIGINAL_BRANCH=$CURRENT_BRANCH
git checkout dev --quiet

log_info "Copying files from 'knowledge'..."

for file in $FILES_TO_SYNC; do
    dir=$(dirname "$file")
    if [ "$dir" != "." ]; then
        mkdir -p "$dir"
    fi
    
    git checkout knowledge -- "$file" 2>/dev/null || true
    log_success "Copied: $file"
done

CHANGED_FILES=$(git diff --name-only HEAD)

if [ -z "$CHANGED_FILES" ]; then
    log_warn "No files were actually changed"
    git checkout "$ORIGINAL_BRANCH" --quiet
    exit 0
fi

git add -A

echo ""
echo "Changes staged:"
echo "───────────────────────────────────────"
git diff --cached --stat
echo ""

if [ -z "$COMMIT_MESSAGE" ]; then
    if [ "$AUTO_MODE" = false ]; then
        echo ""
        read -p "Enter commit message (or press Enter for default): " COMMIT_MESSAGE
    fi
    
    if [ -z "$COMMIT_MESSAGE" ]; then
        COMMIT_MESSAGE="Sync: Update from knowledge branch ($(date '+%Y-%m-%d'))"
    fi
fi

git commit -m "$COMMIT_MESSAGE"
log_success "Committed: $COMMIT_MESSAGE"

log_info "Returning to '$ORIGINAL_BRANCH' branch..."
git checkout "$ORIGINAL_BRANCH" --quiet

echo ""
echo "═══════════════════════════════════════════════════════"
log_success "Sync complete!"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Summary:"
echo "  • Copied $NUM_FILES file(s) from 'knowledge'"
echo "  • Committed to 'dev' with message:"
echo "    \"$COMMIT_MESSAGE\""
echo "  • Returned to '$ORIGINAL_BRANCH'"
echo ""
echo "Your 'dev' branch is now clean and up to date!"
echo ""
