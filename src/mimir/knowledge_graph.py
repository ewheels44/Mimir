"""Knowledge Graph Relationship Extraction

Hybrid approach combining:
1. AST analysis for code structure (imports, calls, inheritance)
2. LLM extraction for semantic relationships
"""

import ast
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class Relationship:
    source: str
    target: str
    relation_type: str
    metadata: Dict

    def to_dict(self):
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "metadata": self.metadata,
        }


@dataclass
class CodeEntity:
    name: str
    entity_type: str
    file_path: str
    line_number: int
    metadata: Dict


class ASTRelationshipExtractor:
    """Extract relationships from Python code using AST parsing"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.relationships: List[Relationship] = []
        self.entities: Dict[str, CodeEntity] = {}

    def extract_from_file(self, file_path: Path) -> List[Relationship]:
        """Extract all relationships from a Python file"""
        relationships = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source)
            relative_path = file_path.relative_to(self.project_root)

            relationships.extend(self._extract_imports(tree, relative_path))
            relationships.extend(self._extract_inheritance(tree, relative_path))
            relationships.extend(self._extract_function_calls(tree, relative_path))
            relationships.extend(self._extract_class_methods(tree, relative_path))

        except SyntaxError as e:
            print(f"  Syntax error in {file_path}: {e}")
        except Exception as e:
            print(f"  Error processing {file_path}: {e}")

        return relationships

    def _extract_imports(self, tree: ast.AST, file_path: Path) -> List[Relationship]:
        """Extract import relationships"""
        relationships = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    relationships.append(
                        Relationship(
                            source=str(file_path),
                            target=alias.name,
                            relation_type="imports_module",
                            metadata={
                                "line": node.lineno,
                                "asname": alias.asname,
                                "import_type": "import",
                            },
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    target = f"{module}.{alias.name}" if module else alias.name
                    relationships.append(
                        Relationship(
                            source=str(file_path),
                            target=target,
                            relation_type="imports_from",
                            metadata={
                                "line": node.lineno,
                                "module": module,
                                "name": alias.name,
                                "asname": alias.asname,
                                "import_type": "from_import",
                            },
                        )
                    )

        return relationships

    def _extract_inheritance(
        self, tree: ast.AST, file_path: Path
    ) -> List[Relationship]:
        """Extract class inheritance relationships"""
        relationships = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name

                for base in node.bases:
                    if isinstance(base, ast.Name):
                        parent_class = base.id
                        relationships.append(
                            Relationship(
                                source=str(file_path),
                                target=parent_class,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.lineno,
                                    "class": class_name,
                                    "parent": parent_class,
                                },
                            )
                        )
                    elif isinstance(base, ast.Attribute):
                        parent_class = f"{self._get_attribute_chain(base)}"
                        relationships.append(
                            Relationship(
                                source=str(file_path),
                                target=parent_class,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.lineno,
                                    "class": class_name,
                                    "parent": parent_class,
                                },
                            )
                        )

                # Store entity
                self.entities[f"{file_path}::{class_name}"] = CodeEntity(
                    name=class_name,
                    entity_type="class",
                    file_path=str(file_path),
                    line_number=node.lineno,
                    metadata={"bases": [self._get_base_name(b) for b in node.bases]},
                )

        return relationships

    def _extract_function_calls(
        self, tree: ast.AST, file_path: Path
    ) -> List[Relationship]:
        """Extract function call relationships"""
        relationships = []
        call_targets = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node.func)
                if func_name:
                    call_targets.add((func_name, node.lineno))

        for target, line in call_targets:
            relationships.append(
                Relationship(
                    source=str(file_path),
                    target=target,
                    relation_type="calls",
                    metadata={"line": line, "call_type": "function_call"},
                )
            )

        return relationships

    def _extract_class_methods(
        self, tree: ast.AST, file_path: Path
    ) -> List[Relationship]:
        """Extract class-method relationships"""
        relationships = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name

                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name
                        relationships.append(
                            Relationship(
                                source=f"{file_path}::{class_name}",
                                target=f"{file_path}::{class_name}.{method_name}",
                                relation_type="has_method",
                                metadata={
                                    "line": item.lineno,
                                    "class": class_name,
                                    "method": method_name,
                                },
                            )
                        )

                        # Store entity
                        self.entities[f"{file_path}::{class_name}.{method_name}"] = (
                            CodeEntity(
                                name=method_name,
                                entity_type="method",
                                file_path=str(file_path),
                                line_number=item.lineno,
                                metadata={
                                    "class": class_name,
                                    "args": [arg.arg for arg in item.args.args],
                                },
                            )
                        )

        return relationships

    def _get_call_name(self, node) -> Optional[str]:
        """Extract function name from call node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        return None

    def _get_attribute_chain(self, node) -> str:
        """Get full attribute chain (e.g., 'os.path.join')"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_attribute_chain(node.value)}.{node.attr}"
        return ""

    def _get_base_name(self, node) -> str:
        """Get base class name"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        return ""

    def extract_from_directory(self, directory: Path) -> List[Relationship]:
        """Extract relationships from all Python files in directory"""
        all_relationships = []

        for py_file in directory.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            print(f"  Processing {py_file.relative_to(self.project_root)}...")
            relationships = self.extract_from_file(py_file)
            all_relationships.extend(relationships)

        self.relationships.extend(all_relationships)
        return all_relationships

    def save_to_file(self, output_path: Path):
        """Save relationships to JSON file"""
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"\n✅ Saved {len(self.relationships)} relationships to {output_path}")

    def get_stats(self) -> Dict:
        """Get statistics about extracted relationships"""
        type_counts = defaultdict(int)
        for rel in self.relationships:
            type_counts[rel.relation_type] += 1

        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
        }


def extract_code_relationships(
    project_root: Path,
    output_dir: Optional[Path] = None,
    code_dirs: Optional[List[str]] = None,
    from_index: bool = False,
) -> ASTRelationshipExtractor:
    """Main function to extract code relationships from project

    Args:
        project_root: Root directory of the project
        output_dir: Where to save code_relationships.json (default: PROJECT/.knowledge)
        code_dirs: List of directory names to scan (default: ["src"])
        from_index: If True, use files from the index manifest instead of scanning directories
    """
    print(f"🔍 Extracting code relationships from {project_root}")
    print()

    extractor = ASTRelationshipExtractor(project_root)

    if from_index:
        indexed_files = load_indexed_files(project_root)
        if indexed_files:
            print(f"📚 Using {len(indexed_files)} indexed Python files from manifest")
            for file_path in indexed_files:
                if file_path.exists():
                    rel_path = file_path.relative_to(project_root)
                    print(f"  Processing {rel_path}...")
                    relationships = extractor.extract_from_file(file_path)
                    extractor.relationships.extend(relationships)
        else:
            print("⚠️  No indexed files found in manifest. Run mimir-index.py first.")
    else:
        if code_dirs is None:
            code_dirs = ["src"]

        for dir_name in code_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                print(f"📁 Scanning {dir_name}/...")
                extractor.extract_from_directory(dir_path)

        print(f"📁 Scanning root-level Python files...")
        for py_file in project_root.glob("*.py"):
            print(f"  Processing {py_file.name}...")
            relationships = extractor.extract_from_file(py_file)
            extractor.relationships.extend(relationships)

    # Save results
    if output_dir is None:
        output_dir = project_root / ".knowledge"
    output_dir.mkdir(exist_ok=True)

    extractor.save_to_file(output_dir / "code_relationships.json")

    # Print stats
    stats = extractor.get_stats()
    print(f"\n📊 Statistics:")
    print(f"  Total relationships: {stats['total_relationships']}")
    print(f"  Total entities: {stats['total_entities']}")
    print(f"  By type:")
    for rel_type, count in stats["by_type"].items():
        print(f"    - {rel_type}: {count}")

    return extractor


def load_project_config(project_root: Path) -> dict:
    """Load configuration from .mimir/config.json"""
    config_path = project_root / ".mimir" / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def load_indexed_files(
    project_root: Path, knowledge_dir: Optional[Path] = None
) -> List[Path]:
    """Load list of indexed files from manifest.json

    Returns a list of Path objects for all files that have been indexed
    by mimir-index.py. Filters to only Python files (.py).
    """
    if knowledge_dir is None:
        knowledge_dir = project_root / ".knowledge" / "llamaindex"

    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    indexed_files = []
    for dir_key, info in manifest.get("indexed_directories", {}).items():
        for file_path in info.get("files", []):
            path = Path(file_path)
            # Resolve relative paths against project root
            if not path.is_absolute():
                path = project_root / path
            if path.suffix == ".py":
                indexed_files.append(path)

    return indexed_files


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract code relationships (imports, calls, inheritance) from a Python project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze current directory
  python knowledge_graph.py

  # Analyze specific project
  python knowledge_graph.py /path/to/my/project

  # Analyze with custom code directories
  python knowledge_graph.py /path/to/project --dirs src,lib,tests

  # Use indexed files from manifest (from mimir-index.py)
  python knowledge_graph.py /path/to/project --from-index

Configuration:
  You can also set 'code_dirs' in .mimir/config.json:
  {
    "code_dirs": ["src", "lib", "tests"]
  }

Output:
  Creates .knowledge/code_relationships.json in the project root.
  This file is used by the Mimir Web UI to visualize code relationships.
        """,
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Path to project directory (default: current directory)",
    )
    parser.add_argument(
        "--dirs",
        type=str,
        default=None,
        help="Comma-separated list of code directories to scan (overrides config.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for code_relationships.json (default: PROJECT/.knowledge)",
    )
    parser.add_argument(
        "--from-index",
        action="store_true",
        dest="from_index",
        help="Use indexed files from manifest instead of scanning directories",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"❌ Error: Project directory does not exist: {project_root}")
        exit(1)

    if not project_root.is_dir():
        print(f"❌ Error: Path is not a directory: {project_root}")
        exit(1)

    if args.from_index:
        # Use indexed files from manifest
        print(f"🔍 Analyzing project: {project_root}")
        print(f"📚 Using indexed files from manifest")
        print()
        extract_code_relationships(project_root, args.output, from_index=True)
    else:
        # Traditional directory scanning
        project_config = load_project_config(project_root)

        if args.dirs:
            code_dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
        elif "code_dirs" in project_config:
            code_dirs = project_config["code_dirs"]
            print(f"📋 Loaded code_dirs from .mimir/config.json")
        else:
            code_dirs = ["src"]

        print(f"🔍 Analyzing project: {project_root}")
        print(f"📁 Code directories: {', '.join(code_dirs)}")
        print()

        extract_code_relationships(project_root, args.output, code_dirs)
