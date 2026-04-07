"""
FDE Handoff Documentation Generator

Generates comprehensive handoff documentation from the Mimir knowledge base.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class HandoffSection:
    """A section in the handoff document."""

    title: str
    content: str
    priority: int = 5  # 1 = highest, 10 = lowest

    def to_markdown(self) -> str:
        """Render section as markdown."""
        return f"## {self.title}\n\n{self.content}\n"


@dataclass
class HandoffDocument:
    """Complete handoff document with multiple sections."""

    title: str
    generated_at: datetime = field(default_factory=datetime.now)
    sections: list[HandoffSection] = field(default_factory=list)

    def add_section(self, section: HandoffSection) -> None:
        """Add a section to the document."""
        self.sections.append(section)

    def to_markdown(self) -> str:
        """Render full document as markdown with table of contents."""
        lines = [
            f"# {self.title}",
            "",
            f"*Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M')}*",
            "",
            "## Table of Contents",
            "",
        ]

        # Sort sections by priority
        sorted_sections = sorted(self.sections, key=lambda s: s.priority)

        # Add TOC entries
        for section in sorted_sections:
            anchor = section.title.lower().replace(" ", "-").replace("/", "-")
            lines.append(f"- [{section.title}](#{anchor})")

        lines.append("")

        # Add section content
        for section in sorted_sections:
            lines.append(section.to_markdown())

        return "\n".join(lines)


class HandoffGenerator:
    """Generates handoff documentation from knowledge base."""

    TECH_STACK_FILES = [
        ("pyproject.toml", "Python (pyproject.toml)"),
        ("setup.py", "Python (setup.py)"),
        ("requirements.txt", "Python (requirements.txt)"),
        ("package.json", "Node.js"),
        ("Cargo.toml", "Rust"),
        ("go.mod", "Go"),
        ("Dockerfile", "Docker"),
        ("docker-compose.yml", "Docker Compose"),
        ("docker-compose.yaml", "Docker Compose"),
    ]

    ENTRY_POINT_FILES = [
        "main.py",
        "app.py",
        "server.py",
        "cli.py",
        "run.py",
        "wsgi.py",
        "asgi.py",
    ]

    SKIP_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }

    def __init__(self, project_root: Path | str):
        """Initialize generator with project root."""
        self.project_root = Path(project_root).resolve()
        self.config_path = self.project_root / ".mimir" / "config.json"

    def generate(
        self, engagement_summary: str = "", customer_name: str = "", fde_name: str = ""
    ) -> HandoffDocument:
        """Generate a complete handoff document."""
        title_parts = ["Handoff Document"]
        if customer_name:
            title_parts.append(f"- {customer_name}")
        title = " ".join(title_parts)

        doc = HandoffDocument(title=title)

        # Add all sections
        doc.add_section(
            self._project_overview(engagement_summary, customer_name, fde_name)
        )
        doc.add_section(self._tech_stack())
        doc.add_section(self._architecture())
        doc.add_section(self._key_files())
        doc.add_section(self._what_was_built())
        doc.add_section(self._integration_points())
        doc.add_section(self._how_to_extend())
        doc.add_section(self._knowledge_base())
        doc.add_section(self._next_steps())

        return doc

    def save(
        self, doc: HandoffDocument, output_path: Optional[Path | str] = None
    ) -> Path:
        """Save handoff document to file."""
        if output_path is None:
            output_path = self.project_root / "HANDOFF.md"
        else:
            output_path = Path(output_path)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = doc.to_markdown()
        output_path.write_text(content)
        logger.info(f"Handoff document saved to {output_path}")

        return output_path

    def _project_overview(
        self, summary: str, customer: str, fde: str
    ) -> HandoffSection:
        """Generate project overview section."""
        content_lines = []

        if summary:
            content_lines.append(summary)
            content_lines.append("")

        if customer:
            content_lines.append(f"**Customer:** {customer}")

        if fde:
            content_lines.append(f"**FDE:** {fde}")

        if not content_lines:
            content_lines.append(
                "This document provides a comprehensive handoff of the project."
            )

        return HandoffSection("Project Overview", "\n".join(content_lines), priority=1)

    def _tech_stack(self) -> HandoffSection:
        """Detect and document tech stack."""
        detected = []

        for filename, label in self.TECH_STACK_FILES:
            if (self.project_root / filename).exists():
                detected.append(f"- {label}")

        if not detected:
            detected.append("- No standard tech stack files detected")

        # Try to read package details
        content = "### Detected Technologies\n\n" + "\n".join(detected)

        # Add Python version if available
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                import tomllib

                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                    if "project" in data:
                        content += f"\n\n### Python Project\n\n"
                        if "name" in data["project"]:
                            content += f"- **Name:** {data['project']['name']}\n"
                        if "version" in data["project"]:
                            content += f"- **Version:** {data['project']['version']}\n"
                        if "requires-python" in data["project"]:
                            content += (
                                f"- **Python:** {data['project']['requires-python']}\n"
                            )
            except Exception as e:
                logger.debug(f"Could not parse pyproject.toml: {e}")

        return HandoffSection("Tech Stack", content, priority=2)

    def _architecture(self) -> HandoffSection:
        """Document project architecture."""
        lines = ["### Directory Structure", "", "```"]

        def should_skip(name: str) -> bool:
            return name in self.SKIP_DIRS or name.startswith(".")

        try:
            # Top level
            for item in sorted(self.project_root.iterdir()):
                if should_skip(item.name):
                    continue

                if item.is_dir():
                    lines.append(f"{item.name}/")
                    # Second level
                    try:
                        for subitem in sorted(item.iterdir())[:10]:  # Limit to 10 items
                            if should_skip(subitem.name):
                                continue
                            prefix = (
                                "└──"
                                if subitem == sorted(item.iterdir())[-1]
                                else "├──"
                            )
                            if subitem.is_dir():
                                lines.append(f"    {prefix} {subitem.name}/")
                            else:
                                lines.append(f"    {prefix} {subitem.name}")
                    except PermissionError:
                        pass
                else:
                    lines.append(item.name)
        except PermissionError as e:
            logger.warning(f"Permission error reading directory: {e}")

        lines.append("```")

        return HandoffSection("Architecture", "\n".join(lines), priority=3)

    def _key_files(self) -> HandoffSection:
        """Document key files."""
        lines = ["### Entry Points", ""]

        # Find entry points
        entry_points = []
        for filename in self.ENTRY_POINT_FILES:
            path = self.project_root / filename
            if path.exists():
                entry_points.append(f"- `{filename}`")

        if entry_points:
            lines.extend(entry_points)
        else:
            lines.append("- No standard entry points found")

        lines.extend(["", "### Configuration", ""])

        # Config files
        config_files = [
            ".mimir/config.json",
            "opencode.json",
            ".opencode.json",
            "pyproject.toml",
        ]

        for config in config_files:
            path = self.project_root / config
            if path.exists():
                lines.append(f"- `{config}`")

        lines.extend(["", "### Documentation", ""])

        # Docs directory
        docs_dir = self.project_root / "docs"
        if docs_dir.exists() and docs_dir.is_dir():
            for doc in sorted(docs_dir.iterdir())[:15]:
                if doc.is_file() and doc.suffix in (".md", ".rst", ".txt"):
                    lines.append(f"- `docs/{doc.name}`")
        else:
            lines.append("- No docs directory found")

        return HandoffSection("Key Files", "\n".join(lines), priority=4)

    def _what_was_built(self) -> HandoffSection:
        """Document what was built."""
        content = """This section should be customized with details about what was built during the engagement.

Key components:
- [List main features/components built]
- [Describe any custom integrations]
- [Note any workarounds or special solutions]

Consider including:
- Screenshots or diagrams
- API endpoints created
- Database schemas
- Configuration changes"""

        return HandoffSection("What Was Built", content, priority=5)

    def _integration_points(self) -> HandoffSection:
        """Document integration points."""
        lines = []

        # Check for MCP configuration
        opencode_json = self.project_root / "opencode.json"
        if opencode_json.exists():
            lines.append("### MCP Integration (opencode.json)")
            lines.append("")
            try:
                data = json.loads(opencode_json.read_text())
                if "mcpServers" in data:
                    lines.append("MCP servers configured:")
                    for name in data["mcpServers"]:
                        lines.append(f"- `{name}`")
            except Exception as e:
                logger.debug(f"Could not parse opencode.json: {e}")

        # Check for API routes
        api_dirs = ["api", "routes", "endpoints", "src/api", "src/routes"]
        for api_dir in api_dirs:
            path = self.project_root / api_dir
            if path.exists() and path.is_dir():
                lines.append(f"\n### API Routes (`{api_dir}/`)\n")
                for f in sorted(path.iterdir())[:10]:
                    if f.is_file():
                        lines.append(f"- `{f.name}`")

        # Check for database migrations
        migration_dirs = ["migrations", "alembic", "db/migrations"]
        for mig_dir in migration_dirs:
            path = self.project_root / mig_dir
            if path.exists() and path.is_dir():
                lines.append(f"\n### Database Migrations (`{mig_dir}/`)\n")
                count = len(list(path.glob("*.py"))) + len(list(path.glob("*.sql")))
                lines.append(f"- {count} migration files")

        # Check for shared indexes in config
        if self.config_path.exists():
            try:
                config = json.loads(self.config_path.read_text())
                if "shared_indexes" in config:
                    lines.append("\n### Shared Indexes\n")
                    for idx in config["shared_indexes"]:
                        lines.append(f"- `{idx}`")
            except Exception:
                pass

        if not lines:
            lines.append("No standard integration points detected.")

        return HandoffSection("Integration Points", "\n".join(lines), priority=6)

    def _how_to_extend(self) -> HandoffSection:
        """Document how to extend the project."""
        content = """### Adding New Features

1. **Create a new module** in the appropriate directory
2. **Add tests** in the corresponding test directory
3. **Update documentation** in the docs folder
4. **Register any new CLI commands** in the main entry point

### Modifying Existing Code

1. **Check for existing tests** before modifying
2. **Run the test suite** to ensure nothing breaks
3. **Update inline documentation** as needed
4. **Consider backwards compatibility**

### Knowledge Base Updates

After making changes:
```bash
python .opencode/mimir-index.py
```

This reindexes the documentation to keep the knowledge base current."""

        return HandoffSection("How to Extend", content, priority=7)

    def _knowledge_base(self) -> HandoffSection:
        """Document the knowledge base."""
        lines = ["### Mimir Knowledge Base", ""]

        if self.config_path.exists():
            lines.append(f"Configuration: `.mimir/config.json`")
            lines.append("")

            try:
                config = json.loads(self.config_path.read_text())
                if "docs_dir" in config:
                    lines.append(f"- **Docs Directory:** `{config['docs_dir']}`")
                if "code_dirs" in config:
                    lines.append(
                        f"- **Indexed Code:** `{', '.join(config['code_dirs'])}`"
                    )
                if "embedding_model" in config:
                    lines.append(
                        f"- **Embedding Model:** `{config['embedding_model']}`"
                    )
            except Exception:
                pass

        index_path = self.project_root / ".knowledge" / "llamaindex"
        if index_path.exists():
            lines.append(f"\nIndex location: `.knowledge/llamaindex/`")
            docstore = index_path / "docstore.json"
            if docstore.exists():
                try:
                    data = json.loads(docstore.read_text())
                    lines.append(
                        f"- **Documents indexed:** {len(data) if isinstance(data, list) else 'N/A'}"
                    )
                except Exception:
                    pass

        lines.extend(
            [
                "",
                "### Querying the Knowledge Base",
                "",
                "```bash",
                "# Search via CLI",
                'python -m mimir.cli query "your question"',
                "",
                "# Or use the MCP tools",
                'mimir_search(query="your question")',
                "```",
            ]
        )

        return HandoffSection("Knowledge Base", "\n".join(lines), priority=8)

    def _next_steps(self) -> HandoffSection:
        """Document next steps."""
        content = """### Immediate Actions

- [ ] Review this handoff document
- [ ] Verify access to all repositories and services
- [ ] Test the knowledge base queries
- [ ] Review any open issues or tickets

### Recommended Follow-ups

- [ ] Update documentation with any missing details
- [ ] Add monitoring/alerting if not present
- [ ] Schedule knowledge transfer session
- [ ] Document any workarounds in detail

### Known Issues / Technical Debt

*Document any known issues or technical debt here:*

- [Issue 1: Description and recommended fix]
- [Issue 2: Description and recommended fix]"""

        return HandoffSection("Next Steps", content, priority=9)
