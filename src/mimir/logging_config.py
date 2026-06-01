"""Logging configuration for Mimir.

Provides a setup_logging() function that configures both file and console logging.

Usage:
    from src.mimir.logging_config import setup_logging
    setup_logging()  # Logs to ~/.mimir/mimir.log
"""

import logging
import os
from pathlib import Path


def setup_logging(
    log_file: str = None,
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
) -> None:
    """
    Configure logging for Mimir.

    Args:
        log_file: Path to log file. Defaults to ~/.mimir/mimir.log
        level: File logging level (default: DEBUG)
        console_level: Console logging level (default: INFO)
    """
    if log_file is None:
        # Default to ~/.mimir/mimir.log
        mimir_dir = Path.home() / ".mimir"
        mimir_dir.mkdir(exist_ok=True)
        log_file = str(mimir_dir / "mimir.log")

    # Create file handler with detailed formatting
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    # Create console handler with simpler formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_format = logging.Formatter("%(levelname)s - %(message)s")
    console_handler.setFormatter(console_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger(__name__).info("[LOGGING] Logging configured. File: %s", log_file)


if __name__ == "__main__":
    setup_logging()
    logging.info("Test log message")
    print(f"Log file: {Path.home() / '.mimir/mimir.log'}")
    print("Run: tail -f ~/.mimir/mimir.log")
