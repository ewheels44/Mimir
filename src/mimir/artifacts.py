"""Artifact dependency tracking system for Mimir.

Implements pre-compiled artifacts inspired by Pinecone Nexus's approach:
- Artifacts are pre-compiled knowledge (e.g., architectural summaries)
- Each artifact tracks which source files it depends on
- File watcher invalidates artifacts when dependencies change
- Lazy rebuild on query or eager rebuild via watcher

Storage:
  .knowledge/artifacts/manifest.json  - artifact metadata & dependencies
  .knowledge/artifacts/*.json        - actual artifact content
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.mimir.indexing import compute_file_hash

logger = logging.getLogger(__name__)

# Default artifact directory relative to project root
DEFAULT_ARTIFACT_DIR = Path(".knowledge/artifacts")
MANIFEST_PATH = DEFAULT_ARTIFACT_DIR / "manifest.json"

DEFAULT_TTL_SECONDS = 3600  # 1 hour


def _get_artifact_dir(project_root: Optional[Path] = None) -> Path:
    """Get the artifact directory path, resolving relative to project root if needed."""
    if project_root is None:
        # Auto-detect project root by looking for marker files
        current = Path.cwd()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists() or (parent / ".mimir").exists():
                project_root = parent
                break
        if project_root is None:
            project_root = current
    
    artifact_dir = DEFAULT_ARTIFACT_DIR
    if not artifact_dir.is_absolute():
        artifact_dir = project_root / artifact_dir
    
    return artifact_dir


def _get_manifest_path(project_root: Optional[Path] = None) -> Path:
    """Get the manifest file path."""
    return _get_artifact_dir(project_root) / "manifest.json"


def _ensure_artifact_dir(project_root: Optional[Path] = None):
    """Ensure artifact directory exists."""
    artifact_dir = _get_artifact_dir(project_root)
    artifact_dir.mkdir(parents=True, exist_ok=True)


def load_manifest(project_root: Optional[Path] = None) -> dict:
    """Load artifact manifest. Returns empty structure if not found."""
    manifest_path = _get_manifest_path(project_root)
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"artifacts": {}, "schema_version": "1.0"}


def save_manifest(manifest: dict, project_root: Optional[Path] = None) -> None:
    """Save artifact manifest."""
    _ensure_artifact_dir(project_root)
    manifest["last_updated"] = datetime.now().isoformat()
    manifest_path = _get_manifest_path(project_root)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def compute_source_hashes(depends_on: list[str]) -> dict:
    """Compute SHA-256 hashes for all dependency files."""
    hashes = {}
    for file_path in depends_on:
        path = Path(file_path)
        if path.exists():
            file_hash = compute_file_hash(path)
            if file_hash:
                hashes[file_path] = file_hash
    return hashes


def create_artifact(
    artifact_id: str,
    content: dict,
    depends_on: list[str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    eager_rebuild: bool = False,
) -> dict:
    """Create or update an artifact with dependency tracking.

    Args:
        artifact_id: Unique identifier (e.g., "rag_system_architectural_summary")
        content: The artifact content (will be serialized as JSON)
        depends_on: List of file paths this artifact depends on
        ttl_seconds: Time-to-live before artifact is considered stale
        eager_rebuild: If True, watcher will rebuild immediately on changes

    Returns:
        The artifact info dict
    """
    _ensure_artifact_dir()
    manifest = load_manifest()

    # Compute source hashes
    source_hashes = compute_source_hashes(depends_on)

    artifact_info = {
        "path": str(_get_artifact_dir() / f"{artifact_id}.json"),
        "version": "1.0.0",
        "depends_on": depends_on,
        "source_hashes": source_hashes,
        "last_built": datetime.now().isoformat(),
        "stale": False,
        "invalidated_at": None,
        "ttl_seconds": ttl_seconds,
        "eager_rebuild": eager_rebuild,
    }

    manifest["artifacts"][artifact_id] = artifact_info
    save_manifest(manifest)

    # Save artifact content
    artifact_path = Path(artifact_info["path"])
    with open(artifact_path, "w") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

    logger.info(f"Created artifact '{artifact_id}' with {len(depends_on)} dependencies")
    return artifact_info


def get_artifact(artifact_id: str, project_root: Optional[Path] = None) -> Optional[dict]:
    """Retrieve an artifact by ID. Returns None if not found.

    Also checks staleness and adds staleness warnings to the result.
    """
    manifest = load_manifest(project_root)
    artifact_info = manifest["artifacts"].get(artifact_id)

    if not artifact_info:
        return None

    # Check if stale due to source file changes
    is_stale = _check_staleness(artifact_info)

    # Resolve artifact path relative to project root if needed
    artifact_path = Path(artifact_info["path"])
    if not artifact_path.is_absolute() and project_root:
        artifact_path = project_root / artifact_path
    
    if not artifact_path.exists():
        logger.warning(f"Artifact '{artifact_id}' manifest exists but file missing")
        return None

    with open(artifact_path) as f:
        content = json.load(f)

    # Add metadata
    content["_metadata"] = {
        "artifact_id": artifact_id,
        "version": artifact_info.get("version", "1.0.0"),
        "last_built": artifact_info.get("last_built"),
        "stale": is_stale or artifact_info.get("stale", False),
        "invalidated_at": artifact_info.get("invalidated_at"),
    }

    return content


def _check_staleness(artifact_info: dict) -> bool:
    """Check if artifact is stale based on source file changes or TTL."""
    # Check TTL-based staleness
    last_built_str = artifact_info.get("last_built")
    ttl = artifact_info.get("ttl_seconds", DEFAULT_TTL_SECONDS)

    if last_built_str:
        try:
            last_built = datetime.fromisoformat(last_built_str)
            if datetime.now() - last_built > timedelta(seconds=ttl):
                return True
        except ValueError:
            pass

    # Check source file hash changes
    source_hashes = artifact_info.get("source_hashes", {})
    for file_path, expected_hash in source_hashes.items():
        path = Path(file_path)
        if path.exists():
            actual_hash = compute_file_hash(path)
            if actual_hash and actual_hash != expected_hash:
                return True
        else:
            # Source file deleted - consider stale
            return True

    return False


def invalidate_artifact(artifact_id: str, changed_file: Optional[str] = None) -> bool:
    """Mark an artifact as stale (invalidated).

    Args:
        artifact_id: The artifact to invalidate
        changed_file: Optional path of file that triggered invalidation

    Returns:
        True if artifact was found and invalidated
    """
    manifest = load_manifest()
    if artifact_id not in manifest["artifacts"]:
        return False

    info = manifest["artifacts"][artifact_id]
    info["stale"] = True
    info["invalidated_at"] = datetime.now().isoformat()
    if changed_file:
        info.setdefault("invalidation_history", [])
        info["invalidation_history"].append({
            "file": changed_file,
            "time": datetime.now().isoformat(),
        })
        # Keep only last 10 invalidation events
        info["invalidation_history"] = info["invalidation_history"][-10:]

    save_manifest(manifest)
    logger.info(f"Invalidated artifact '{artifact_id}' (triggered by: {changed_file or 'unknown'})")
    return True


def invalidate_artifacts_for_file(changed_file: str) -> list[str]:
    """Find and invalidate all artifacts that depend on a changed file.

    Args:
        changed_file: Path of the file that changed

    Returns:
        List of artifact IDs that were invalidated
    """
    manifest = load_manifest()
    invalidated = []

    for artifact_id, info in manifest["artifacts"].items():
        depends_on = info.get("depends_on", [])
        if changed_file in depends_on or any(changed_file == d for d in depends_on):
            if not info.get("stale", False):  # Only invalidate once
                invalidate_artifact(artifact_id, changed_file)
                invalidated.append(artifact_id)

    if invalidated:
        logger.info(f"File '{changed_file}' change invalidated {len(invalidated)} artifact(s): {invalidated}")

    return invalidated


def rebuild_artifact(artifact_id: str, project_root: Optional[Path] = None) -> bool:
    """Rebuild a stale artifact. This is a placeholder for the actual rebuild logic.

    In practice, this would:
    1. Read the artifact's original generation logic
    2. Re-run the compilation
    3. Update the artifact content and reset staleness

    For now, this just resets the staleness flag (actual rebuild would be
    implemented per-artifact-type with custom rebuild functions).

    Returns:
        True if rebuild was successful
    """
    manifest = load_manifest()
    if artifact_id not in manifest["artifacts"]:
        logger.warning(f"Cannot rebuild unknown artifact: '{artifact_id}'")
        return False

    info = manifest["artifacts"][artifact_id]

    # Recompute source hashes
    source_hashes = compute_source_hashes(info.get("depends_on", []))

    # Reset staleness
    info["source_hashes"] = source_hashes
    info["last_built"] = datetime.now().isoformat()
    info["stale"] = False
    info["invalidated_at"] = None

    save_manifest(manifest)
    logger.info(f"Rebuilt artifact '{artifact_id}' (hashes refreshed)")
    return True


def list_artifacts(project_root: Optional[Path] = None) -> dict:
    """List all artifacts with their status."""
    manifest = load_manifest(project_root)
    result = {}

    for artifact_id, info in manifest["artifacts"].items():
        is_stale = _check_staleness(info) or info.get("stale", False)
        result[artifact_id] = {
            "version": info.get("version", "1.0.0"),
            "stale": is_stale,
            "last_built": info.get("last_built"),
            "dependency_count": len(info.get("depends_on", [])),
            "eager_rebuild": info.get("eager_rebuild", False),
        }

    return result


def delete_artifact(artifact_id: str) -> bool:
    """Delete an artifact and its manifest entry."""
    manifest = load_manifest()
    if artifact_id not in manifest["artifacts"]:
        return False

    info = manifest["artifacts"][artifact_id]
    artifact_path = Path(info["path"])

    # Delete file
    if artifact_path.exists():
        artifact_path.unlink()

    # Remove from manifest
    del manifest["artifacts"][artifact_id]
    save_manifest(manifest)

    logger.info(f"Deleted artifact '{artifact_id}'")
    return True
