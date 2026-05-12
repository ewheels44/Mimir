#!/usr/bin/env python3
"""
Mimir Projects CLI

Multi-project management and handoff documentation generation.
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mimir.handoff import HandoffGenerator
from mimir.projects import ProjectManager


def cmd_list(args):
    """List all registered projects."""
    manager = ProjectManager()
    projects = manager.list()

    if not projects:
        print("No projects registered.")
        return 0

    print(f"Registered Projects ({len(projects)}):\n")
    for p in projects:
        status_icons = []
        if not p.is_valid:
            status_icons.append("❌ invalid path")
        else:
            if p.has_index:
                status_icons.append("✓ indexed")
            if p.has_config:
                status_icons.append("✓ configured")

        status = " | ".join(status_icons) if status_icons else "no index/config"
        print(f"  {p.name}")
        print(f"    Path: {p.path}")
        print(f"    Status: {status}")
        if p.description:
            print(f"    Description: {p.description}")
        if p.last_accessed:
            print(f"    Last accessed: {p.last_accessed.strftime('%Y-%m-%d %H:%M')}")
        print()

    return 0


def cmd_add(args):
    """Add a new project."""
    manager = ProjectManager()

    try:
        entry = manager.add(
            path=args.path, name=args.name, description=args.description or ""
        )
        print(f"✓ Added project '{entry.name}'")
        print(f"  Path: {entry.path}")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_remove(args):
    """Remove a project."""
    manager = ProjectManager()

    if manager.remove(args.name):
        print(f"✓ Removed project '{args.name}'")
        return 0
    else:
        print(f"Error: Project '{args.name}' not found", file=sys.stderr)
        return 1


def cmd_switch(args):
    """Switch to a project."""
    manager = ProjectManager()
    entry = manager.switch(args.name)

    if entry:
        print(f"✓ Switched to project '{entry.name}'")
        print(f"  Path: {entry.path}")
        return 0
    else:
        print(f"Error: Could not switch to '{args.name}'", file=sys.stderr)
        return 1


def cmd_status(args):
    """Show registry status."""
    manager = ProjectManager()
    status = manager.status()

    print("Mimir Projects Status\n")
    print(f"Registry: {status['registry_path']}")
    print(f"Total projects: {status['total_projects']}")
    print(f"Valid paths: {status['valid_projects']}")
    print(f"Indexed: {status['indexed_projects']}")
    print(f"Configured: {status['configured_projects']}")

    if args.verbose and status["projects"]:
        print("\nProject Details:")
        for p in status["projects"]:
            print(f"\n  {p['name']}:")
            print(f"    Path: {p['path']}")
            print(f"    Valid: {p['valid']}")
            print(f"    Has Index: {p['has_index']}")
            print(f"    Has Config: {p['has_config']}")

    return 0


def cmd_discover(args):
    """Discover Mimir projects."""
    manager = ProjectManager()

    search_paths = None
    if args.paths:
        search_paths = [Path(p) for p in args.paths]

    discovered = manager.discover(search_paths)

    if not discovered:
        print("No Mimir projects discovered.")
        return 0

    print(f"Discovered {len(discovered)} Mimir project(s):\n")
    for path in discovered:
        print(f"  {path}")

    return 0


def cmd_handoff(args):
    """Generate handoff documentation."""
    manager = ProjectManager()

    # Get project path
    if args.project:
        entry = manager.get(args.project)
        if not entry:
            print(f"Error: Project '{args.project}' not found", file=sys.stderr)
            return 1
        project_path = Path(entry.path)
    else:
        project_path = Path.cwd()

    # Verify it's a Mimir project
    if not (project_path / ".mimir" / "config.json").exists():
        print(
            f"Warning: {project_path} does not appear to be a Mimir project",
            file=sys.stderr,
        )

    # Generate handoff document
    generator = HandoffGenerator(project_path)
    doc = generator.generate(
        engagement_summary=args.summary or "",
        customer_name=args.customer or "",
        fde_name=args.fde or "",
    )

    # Determine output path
    output_path = args.output if args.output else None

    # Save
    saved_path = generator.save(doc, output_path)
    print(f"✓ Handoff document generated: {saved_path}")

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="mimir-projects", description="Mimir multi-project management CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    subparsers.add_parser("list", help="List all registered projects")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new project")
    add_parser.add_argument("path", help="Path to the project directory")
    add_parser.add_argument(
        "--name", "-n", help="Project name (defaults to directory name)"
    )
    add_parser.add_argument(
        "--description", "-d", default="", help="Project description"
    )

    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove a project")
    remove_parser.add_argument("name", help="Name of the project to remove")

    # switch command
    switch_parser = subparsers.add_parser("switch", help="Switch to a project")
    switch_parser.add_argument("name", help="Name of the project to switch to")

    # status command
    status_parser = subparsers.add_parser("status", help="Show registry status")
    status_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed status"
    )

    # discover command
    discover_parser = subparsers.add_parser("discover", help="Discover Mimir projects")
    discover_parser.add_argument(
        "paths", nargs="*", help="Paths to search (defaults to common directories)"
    )

    # handoff command
    handoff_parser = subparsers.add_parser(
        "handoff", help="Generate handoff documentation"
    )
    handoff_parser.add_argument(
        "--project", "-p", help="Project name (defaults to current directory)"
    )
    handoff_parser.add_argument("--summary", "-s", help="Engagement summary")
    handoff_parser.add_argument("--customer", "-c", help="Customer name")
    handoff_parser.add_argument("--fde", "-f", help="FDE name")
    handoff_parser.add_argument(
        "--output", "-o", help="Output file path (defaults to HANDOFF.md)"
    )

    args = parser.parse_args()

    # Route to command handler
    commands = {
        "list": cmd_list,
        "add": cmd_add,
        "remove": cmd_remove,
        "switch": cmd_switch,
        "status": cmd_status,
        "discover": cmd_discover,
        "handoff": cmd_handoff,
    }

    if args.command is None:
        parser.print_help()
        return 0

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
