"""
Multi-Project Management for Mimir

Manages multiple Mimir projects with a central registry.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json
import logging

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = Path.home() / ".mimir" / "projects.json"


@dataclass
class ProjectEntry:
    """Represents a registered Mimir project."""

    name: str
    path: str
    added_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    description: str = ""

    @property
    def has_index(self) -> bool:
        """Check if project has a knowledge index."""
        return (Path(self.path) / ".knowledge" / "llamaindex").exists()

    @property
    def has_config(self) -> bool:
        """Check if project has Mimir configuration."""
        return (Path(self.path) / ".mimir" / "config.json").exists()

    @property
    def is_valid(self) -> bool:
        """Check if project path still exists."""
        return Path(self.path).exists()

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "path": self.path,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "last_accessed": self.last_accessed.isoformat()
            if self.last_accessed
            else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectEntry":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            path=data["path"],
            added_at=datetime.fromisoformat(data["added_at"])
            if data.get("added_at")
            else datetime.now(),
            last_accessed=datetime.fromisoformat(data["last_accessed"])
            if data.get("last_accessed")
            else None,
            description=data.get("description", ""),
        )


class ProjectManager:
    """Manages multiple Mimir projects."""

    def __init__(self, registry_path: Optional[Path | str] = None):
        """Initialize project manager with optional custom registry path."""
        self.registry_path = (
            Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
        )
        self._projects: dict[str, ProjectEntry] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load projects from registry file."""
        if not self.registry_path.exists():
            logger.debug(f"Registry not found at {self.registry_path}, starting fresh")
            return

        try:
            data = json.loads(self.registry_path.read_text())
            for proj_data in data.get("projects", []):
                entry = ProjectEntry.from_dict(proj_data)
                self._projects[entry.name] = entry
            logger.debug(f"Loaded {len(self._projects)} projects from registry")
        except Exception as e:
            logger.warning(f"Could not load registry: {e}")

    def _save_registry(self) -> None:
        """Save projects to registry file."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "projects": [p.to_dict() for p in self._projects.values()],
        }

        self.registry_path.write_text(json.dumps(data, indent=2))
        logger.debug(f"Saved registry to {self.registry_path}")

    def add(
        self, path: Path | str, name: Optional[str] = None, description: str = ""
    ) -> ProjectEntry:
        """Add a new project to the registry."""
        project_path = Path(path).resolve()

        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")

        # Auto-generate name from directory if not provided
        if not name:
            name = project_path.name

        # Check for existing project with same name
        if name in self._projects:
            raise ValueError(f"Project '{name}' already exists in registry")

        entry = ProjectEntry(
            name=name,
            path=str(project_path),
            description=description,
        )

        self._projects[name] = entry
        self._save_registry()

        logger.info(f"Added project '{name}' at {project_path}")
        return entry

    def remove(self, name: str) -> bool:
        """Remove a project from the registry."""
        if name not in self._projects:
            logger.warning(f"Project '{name}' not found in registry")
            return False

        del self._projects[name]
        self._save_registry()

        logger.info(f"Removed project '{name}'")
        return True

    def get(self, name: str) -> Optional[ProjectEntry]:
        """Get a project by name."""
        return self._projects.get(name)

    def list(self) -> List[ProjectEntry]:
        """List all registered projects."""
        return list(self._projects.values())

    def switch(self, name: str) -> Optional[ProjectEntry]:
        """Switch to a project (updates last_accessed)."""
        entry = self._projects.get(name)
        if not entry:
            logger.warning(f"Project '{name}' not found")
            return None

        if not entry.is_valid:
            logger.warning(f"Project path no longer exists: {entry.path}")
            return None

        entry.last_accessed = datetime.now()
        self._save_registry()

        logger.info(f"Switched to project '{name}'")
        return entry

    def discover(self, search_paths: Optional[List[Path | str]] = None) -> List[Path]:
        """Discover Mimir projects by searching for .mimir/config.json files."""
        if search_paths is None:
            search_paths = [
                Path.home(),
                Path.home() / "Projects",
                Path.home() / "workspace",
                Path.home() / "code",
                Path.home() / "src",
            ]

        discovered = []

        for search_path in search_paths:
            search_path = Path(search_path)
            if not search_path.exists():
                continue

            try:
                for config_file in search_path.rglob(".mimir/config.json"):
                    project_path = config_file.parent.parent
                    if project_path not in discovered:
                        discovered.append(project_path)
                        logger.debug(f"Found Mimir project at {project_path}")
            except PermissionError as e:
                logger.debug(f"Permission denied for {search_path}: {e}")
            except Exception as e:
                logger.debug(f"Error searching {search_path}: {e}")

        return discovered

    def status(self) -> dict:
        """Get registry status summary."""
        projects = self.list()

        valid_projects = [p for p in projects if p.is_valid]
        indexed_projects = [p for p in projects if p.has_index]
        configured_projects = [p for p in projects if p.has_config]

        return {
            "total_projects": len(projects),
            "valid_projects": len(valid_projects),
            "indexed_projects": len(indexed_projects),
            "configured_projects": len(configured_projects),
            "registry_path": str(self.registry_path),
            "projects": [
                {
                    "name": p.name,
                    "path": p.path,
                    "valid": p.is_valid,
                    "has_index": p.has_index,
                    "has_config": p.has_config,
                    "last_accessed": p.last_accessed.isoformat()
                    if p.last_accessed
                    else None,
                }
                for p in projects
            ],
        }
