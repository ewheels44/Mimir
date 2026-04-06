#!/usr/bin/env python3
"""
mimir-reindex-hook.py — Lightweight incremental reindex triggered by git hooks.

Detects changed files since last index and updates the Mimir knowledge base.
Designed to run in background after git commits with minimal overhead.

Usage:
    python mimir-reindex-hook.py [--project-root /path/to/project]
"""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime

MIMIR_DIR = Path.home() / "Documents" / "Mimir"


def setup_logging(log_file: Path) -> logging.Logger:
    """Configure file-based logging (no stdout pollution)."""
    logger = logging.getLogger("mimir-hook")
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(str(log_file))
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    return logger


def detect_project_root() -> Path:
    """Find project root by looking for .git directory."""
    cwd = Path.cwd().resolve()
    current = cwd
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return cwd


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Mimir post-commit auto-reindex")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args()

    project_root = args.project_root or detect_project_root()

    # Guard: Mimir installed?
    if not MIMIR_DIR.exists():
        sys.exit(0)

    # Guard: Mimir project?
    config_path = project_root / ".mimir" / "config.json"
    if not config_path.exists():
        sys.exit(0)

    knowledge_dir = project_root / ".knowledge" / "llamaindex"
    if not (knowledge_dir / "index_store.json").exists():
        sys.exit(0)

    # Setup logging
    log_file = project_root / ".mimir" / "reindex.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(log_file)

    # Load config
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(0)

    # Add Mimir to path
    sys.path.insert(0, str(MIMIR_DIR))
    sys.path.insert(0, str(MIMIR_DIR / "src"))

    # Build watched directories
    docs_dir = project_root / config.get("docs_dir", "docs")
    code_dirs = [project_root / d for d in config.get("code_dirs", [])]
    watched_dirs = [d for d in [docs_dir] + code_dirs if d.exists()]

    if not watched_dirs:
        logger.info("No watched directories found")
        sys.exit(0)

    # Run incremental reindex
    try:
        from mimir.indexing import incremental_reindex

        result = incremental_reindex(
            project_root=project_root,
            watched_dirs=watched_dirs,
            knowledge_dir=knowledge_dir,
            verbose=False,
        )

        if result["success"]:
            total = (
                result["added_count"]
                + result["modified_count"]
                + result["deleted_count"]
            )
            if total > 0:
                logger.info(
                    f"Auto-indexed: +{result['added_count']} ~{result['modified_count']} -{result['deleted_count']}"
                )
            else:
                logger.debug("No changes detected")
        else:
            logger.warning("Incremental reindex reported failure")

    except ImportError as e:
        logger.error(f"Mimir indexing module not available: {e}")
    except Exception as e:
        logger.error(f"Reindex failed: {e}")


if __name__ == "__main__":
    main()
