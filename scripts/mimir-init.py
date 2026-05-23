#!/usr/bin/env python3
"""
mimir-init.py - Initialize Mimir for any project or install globally.

Two modes:
  1. Global install (run once): Sets up MCP server and system rules
  2. Per-project init (run in each project): Creates directories and indexes

Per-project setup creates:
  - .mimir/config.json     - Project-specific Mimir settings
  - .opencode/mimir-index.py - Delegates to central Mimir install

The .jcode/mcp.json uses a unique server name (mimir-{project-name}) to avoid
conflicts when working on multiple projects. It also sets PROJECT_ROOT so the
MCP server knows which project it's serving.

Usage:
    # Global install (run once after cloning Mimir)
    python ~/Documents/Mimir/mimir.py install

    # Per-project init (run in each project you want to index)
    cd /path/to/your/project
    python ~/Documents/Mimir/mimir.py init
    python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests

    # Uninstall (restores backed up configs)
    python ~/Documents/Mimir/mimir.py uninstall
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Mimir root directory
MIMIR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MIMIR_ROOT / "src"))
