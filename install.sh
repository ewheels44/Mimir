#!/usr/bin/env bash
#
# install.sh — Mimir Installation Script
#
# Usage:
#   bash install.sh                  # Install with defaults
#   bash install.sh --help           # Show help
#   bash install.sh --prefix /usr/local  # Install to custom location
#   bash install.sh --skip-web       # Skip web UI build
#   bash install.sh --skip-hooks     # Skip git hooks installation
#
# This script:
#   1. Checks prerequisites (Python, uv, Node.js, Rust)
#   2. Sets up Python environment with uv
#   3. Installs Python dependencies
#   4. Optionally builds web components (Rust server + React client)
#   5. Installs git hooks for auto-indexing
#   6. Configures shell environment
#
# The script is idempotent — safe to run multiple times.
#

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

MIMIR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${MIMIR_ROOT}/.venv"
BIN_DIR="${MIMIR_ROOT}/bin"

# Default options
PREFIX="${PREFIX:-}"
SKIP_WEB=false
SKIP_HOOKS=false
SKIP_SHELL=false
FORCE=false
VERBOSE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── Validation ────────────────────────────────────────────────────────

validate_mimir_root() {
    print_info "Validating Mimir installation directory..."

    local required_files=("pyproject.toml" "src/mimir" "README.md")
    local missing_files=()

    for file in "${required_files[@]}"; do
        if [ ! -e "$MIMIR_ROOT/$file" ]; then
            missing_files+=("$file")
        fi
    done

    if [ ${#missing_files[@]} -gt 0 ]; then
        print_error "Invalid Mimir root directory: $MIMIR_ROOT"
        print_error "Missing files: ${missing_files[*]}"
        die "Please run this script from the Mimir directory or check MIMIR_ROOT"
    fi

    print_success "Mimir root directory validated: $MIMIR_ROOT"
}

# ─── Helper Functions ──────────────────────────────────────────────────────────

print_header() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Mimir Installation Script${NC}"
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

check_command() {
    command -v "$1" >/dev/null 2>&1
}

# ─── Argument Parsing ─────────────────────────────────────────────────────────

show_help() {
    cat << EOF
Mimir Installation Script

Usage: bash install.sh [OPTIONS]

Options:
  --prefix PATH     Install prefix (default: Mimir root)
  --skip-web       Skip building web UI components (Rust + React)
  --skip-hooks     Skip git hooks installation
  --skip-shell     Skip shell configuration
  --force          Force reinstallation even if already installed
  --verbose        Enable verbose output
  --help           Show this help message

Examples:
  bash install.sh
  bash install.sh --skip-web
  bash install.sh --prefix /usr/local

EOF
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --prefix)
                PREFIX="$2"
                shift 2
                ;;
            --skip-web)
                SKIP_WEB=true
                shift
                ;;
            --skip-hooks)
                SKIP_HOOKS=true
                shift
                ;;
            --skip-shell)
                SKIP_SHELL=true
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

    # Set prefix to Mimir root if not specified
    if [ -z "$PREFIX" ]; then
        PREFIX="$MIMIR_ROOT"
    fi
}

# ─── Prerequisite Checks ─────────────────────────────────────────────────────

check_prerequisites() {
    print_info "Checking prerequisites..."
    local all_good=true

    # Check Python version (3.12+ required per pyproject.toml)
    if check_command python3; then
        PYTHON_CMD="python3"
    elif check_command python; then
        PYTHON_CMD="python"
    else
        print_error "Python not found. Please install Python 3.12 or later."
        all_good=false
    fi

    if [ -n "${PYTHON_CMD:-}" ]; then
        local python_version
        python_version=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        local major minor
        major=$(echo "$python_version" | cut -d. -f1)
        minor=$(echo "$python_version" | cut -d. -f2)

        if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
            print_success "Python $python_version found"
        else
            print_error "Python 3.12+ required, found $python_version"
            all_good=false
        fi
    fi

    # Check uv package manager
    if check_command uv; then
        print_success "uv package manager found: $(uv --version)"
    else
        print_warning "uv not found. Installing uv..."
        install_uv
    fi

    # Check Node.js (for web client)
    if check_command node; then
        local node_version
        node_version=$(node --version)
        print_success "Node.js found: $node_version"
    else
        print_warning "Node.js not found. Web client will not be built."
        SKIP_WEB=true
    fi

    # Check npm (for web client)
    if check_command npm; then
        local npm_version
        npm_version=$(npm --version)
        print_success "npm found: $npm_version"
    else
        print_warning "npm not found. Web client will not be built."
        SKIP_WEB=true
    fi

    # Check Rust/Cargo (for web server)
    if check_command cargo; then
        local rust_version
        rust_version=$(rustc --version)
        print_success "Rust found: $rust_version"
    else
        print_warning "Rust/Cargo not found. Web server will not be built."
        SKIP_WEB=true
    fi

    # Check git
    if check_command git; then
        print_success "git found: $(git --version)"
    else
        print_warning "git not found. Git hooks will not be installed."
        SKIP_HOOKS=true
    fi

    if [ "$all_good" = false ]; then
        die "Prerequisite check failed. Please install missing dependencies."
    fi
}

install_uv() {
    print_info "Installing uv package manager..."
    if check_command curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Add uv to PATH for this session
        export PATH="$HOME/.local/bin:$PATH"
        print_success "uv installed successfully"
    elif check_command brew; then
        brew install uv
        print_success "uv installed via Homebrew"
    else
        die "Cannot install uv. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
}

# ─── Python Environment Setup ────────────────────────────────────────────────

setup_python_env() {
    print_info "Setting up Python environment..."

    # Create virtual environment if it doesn't exist or force reinstall
    if [ -d "$VENV_DIR" ] && [ "$FORCE" = false ]; then
        print_success "Virtual environment already exists at $VENV_DIR"
    else
        if [ "$FORCE" = true ] && [ -d "$VENV_DIR" ]; then
            print_info "Force reinstall: removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        fi

        print_info "Creating virtual environment with uv..."
        uv venv "$VENV_DIR" --python 3.12
        print_success "Virtual environment created at $VENV_DIR"
    fi

    # Activate virtual environment
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"

    # Install Python dependencies with uv
    print_info "Installing Python dependencies (this may take a few minutes)..."

    if [ "$VERBOSE" = true ]; then
        uv pip install -e "$MIMIR_ROOT[dev]"
    else
        uv pip install -e "$MIMIR_ROOT[dev]" > /dev/null 2>&1
    fi

    print_success "Python dependencies installed"
}

# ─── Web Components Build ───────────────────────────────────────────────────

build_web_components() {
    if [ "$SKIP_WEB" = true ]; then
        print_warning "Skipping web components build (--skip-web specified or dependencies missing)"
        return
    fi

    print_info "Building web components..."

    # Build Rust web server
    print_info "Building Rust web server..."
    if [ -d "$MIMIR_ROOT/web/server" ]; then
        cd "$MIMIR_ROOT/web/server"
        if [ "$VERBOSE" = true ]; then
            cargo build --release
        else
            cargo build --release 2>&1 | grep -E "(Compiling|Finished|error)" || true
        fi
        print_success "Rust web server built"
    else
        print_warning "Rust server directory not found, skipping..."
    fi

    # Build React web client
    print_info "Building React web client..."
    if [ -d "$MIMIR_ROOT/web/client" ]; then
        cd "$MIMIR_ROOT/web/client"

        # Install npm dependencies
        print_verbose "Installing npm dependencies..."
        if [ "$VERBOSE" = true ]; then
            npm install
        else
            npm install --silent 2>/dev/null
        fi

        # Build for production
        print_verbose "Building React app..."
        if [ "$VERBOSE" = true ]; then
            npm run build
        else
            npm run build --silent 2>/dev/null
        fi

        print_success "React web client built"
    else
        print_warning "React client directory not found, skipping..."
    fi

    # Return to Mimir root
    cd "$MIMIR_ROOT"
}

# ─── Git Hooks Installation ──────────────────────────────────────────────────

install_git_hooks() {
    if [ "$SKIP_HOOKS" = true ]; then
        print_warning "Skipping git hooks installation (--skip-hooks specified)"
        return
    fi

    # Only install hooks if we're in a git repository
    if [ ! -d "$MIMIR_ROOT/.git" ]; then
        print_warning "Not a git repository. Skipping git hooks installation."
        return
    fi

    print_info "Installing git hooks..."

    local hooks_dir="$MIMIR_ROOT/.git/hooks"
    local post_commit_source="$MIMIR_ROOT/scripts/git-hooks/post-commit"
    local post_commit_target="$hooks_dir/post-commit"

    # Check if hook source exists
    if [ ! -f "$post_commit_source" ]; then
        print_warning "Post-commit hook source not found at $post_commit_source"
        return
    fi

    # Install post-commit hook
    if [ -f "$post_commit_target" ]; then
        if grep -q "mimir" "$post_commit_target" 2>/dev/null; then
            print_success "Git hooks already installed"
        else
            print_warning "Existing post-commit hook found. Appending Mimir hook..."
            # Backup existing hook
            cp "$post_commit_target" "$post_commit_target.backup"
            # Append our hook
            cat "$post_commit_source" >> "$post_commit_target"
            print_success "Mimir hook appended to existing post-commit hook"
        fi
    else
        cp "$post_commit_source" "$post_commit_target"
        chmod +x "$post_commit_target"
        print_success "Git post-commit hook installed"
    fi
}

# ─── Shell Configuration ────────────────────────────────────────────────────

setup_shell() {
    if [ "$SKIP_SHELL" = true ]; then
        print_warning "Skipping shell configuration (--skip-shell specified)"
        return
    fi

    print_info "Setting up shell environment..."

    # Create bin directory for symlinks
    mkdir -p "$BIN_DIR"

    # Create mimir CLI symlink
    local cli_script="$MIMIR_ROOT/scripts/mimir_bridge.py"
    if [ -f "$cli_script" ]; then
        # Create a wrapper script that activates the venv
        cat > "$BIN_DIR/mimir" << 'EOF'
#!/usr/bin/env bash
# Mimir CLI wrapper
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIMIR_ROOT="$(dirname "$SCRIPT_DIR")"
source "$MIMIR_ROOT/.venv/bin/activate"
exec python "$MIMIR_ROOT/scripts/mimir_bridge.py" "$@"
EOF
        chmod +x "$BIN_DIR/mimir"
        print_success "Mimir CLI installed to $BIN_DIR/mimir"
    fi

    # Detect shell and update PATH
    local shell_config=""
    if [ -n "${ZSH_VERSION:-}" ] || [[ "${SHELL:-}" == *"zsh"* ]]; then
        shell_config="$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [[ "${SHELL:-}" == *"bash"* ]]; then
        shell_config="$HOME/.bashrc"
    fi

    if [ -n "$shell_config" ]; then
        local path_export="export PATH=\"$BIN_DIR:\$PATH\""

        if grep -q "$BIN_DIR" "$shell_config" 2>/dev/null; then
            print_success "PATH already configured in $shell_config"
        else
            echo "" >> "$shell_config"
            echo "# Mimir" >> "$shell_config"
            echo "$path_export" >> "$shell_config"
            print_success "Added $BIN_DIR to PATH in $shell_config"
            print_info "Restart your shell or run: source $shell_config"
        fi
    fi
}

# ─── API Key Configuration ─────────────────────────────────────────────────

configure_api_key() {
    print_info "Checking API key configuration..."

    if [ -n "${OPENROUTER_API_KEY:-}" ]; then
        print_success "OPENROUTER_API_KEY is set"
        return
    fi

    # Check if auth file exists
    local auth_file="$HOME/.local/share/opencode/auth.json"
    if [ -f "$auth_file" ]; then
        print_success "Found auth file at $auth_file"
        return
    fi

    print_warning "No API key found."
    print_info "To use Mimir, you need an OpenRouter API key."
    print_info "Get one at: https://openrouter.ai/settings/keys"
    print_info ""
    print_info "Set it via environment variable:"
    print_info "  export OPENROUTER_API_KEY=\"sk-or-v1-your-key-here\""
    print_info ""
    print_info "Or configure via opencode:"
    print_info "  opencode auth openrouter"
}

# ─── Verification ───────────────────────────────────────────────────────────

verify_installation() {
    print_info "Verifying installation..."

    # Check virtual environment
    if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
        print_success "Virtual environment is ready"
    else
        print_error "Virtual environment verification failed"
        return 1
    fi

    # Check if we can import key modules
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"

    local modules=("mimir" "llama_index" "langchain" "mcp")
    for module in "${modules[@]}"; do
        if python -c "import $module" 2>/dev/null; then
            print_verbose "Module $module is importable"
        else
            print_warning "Module $module may not be installed correctly"
        fi
    done

    print_success "Installation verified"
}

# ─── Main ──────────────────────────────────────────────────────────────────

main() {
    parse_args "$@"

    validate_mimir_root

    print_header

    print_info "Mimir root: $MIMIR_ROOT"
    print_info "Install prefix: $PREFIX"
    echo ""

    # Run installation steps
    check_prerequisites
    echo ""

    setup_python_env
    echo ""

    build_web_components
    echo ""

    install_git_hooks
    echo ""

    setup_shell
    echo ""

    configure_api_key
    echo ""

    verify_installation
    echo ""

    # Final message
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Mimir installation complete!${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    print_info "Next steps:"
    echo "  1. If this is your first time, set your API key:"
    echo "     export OPENROUTER_API_KEY=\"sk-or-v1-your-key-here\""
    echo ""
    echo "  2. Initialize a project for indexing:"
    echo "     cd /path/to/your/project"
    echo "     mimir init --code-dirs=src,tests"
    echo ""
    echo "  3. Index your project:"
    echo "     mimir index"
    echo ""
    echo "  4. Start using Mimir with ecode"
    echo ""
    print_info "For help: mimir --help"
    print_info "Documentation: cat $MIMIR_ROOT/README.md"
}

# Run main function
main "$@"
