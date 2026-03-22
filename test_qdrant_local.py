#!/usr/bin/env python3
"""Test Qdrant local mode initialization."""

import sys
from pathlib import Path

try:
    from qdrant_client import QdrantClient
except ImportError:
    print("ERROR: qdrant-client not installed. Run: pip install qdrant-client")
    sys.exit(1)


def test_qdrant_local():
    qdrant_path = Path(".mimir/qdrant")
    qdrant_path.mkdir(parents=True, exist_ok=True)

    client = QdrantClient(path=str(qdrant_path))
    collections = client.get_collections()
    print(f"SUCCESS: Qdrant local mode initialized at {qdrant_path}")
    print(f"Collections: {collections}")
    return True


if __name__ == "__main__":
    test_qdrant_local()
