"""Knowledge Graph Relationship Extraction

Multi-language support via tree-sitter with Python ast fallback.

Supported languages (requires tree-sitter-languages):
  Python, TypeScript, JavaScript, Rust, Go

Falls back to Python-only ast extraction if tree-sitter-languages
is not installed.
"""

import ast
import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict


# ---------------------------------------------------------------------------
# Shared data model
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Language → file extension mapping
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
}

EXCLUDE_DIRS = {
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".git",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    "target",  # Rust
}


# ---------------------------------------------------------------------------
# Tree-sitter extractor  (used when tree-sitter-languages is available)
# ---------------------------------------------------------------------------

# S-expression queries per language.
# Each query must only use node-type names that exist in that grammar.
_TS_QUERIES: Dict[str, Dict[str, str]] = {
    "python": {
        "imports": """
            (import_statement (dotted_name) @module)
            (import_from_statement
                module_name: (dotted_name)? @module
                name: (dotted_name) @name)
        """,
        "classes": """
            (class_definition
                name: (identifier) @class_name
                bases: (argument_list
                    [(identifier) @base
                     (attribute) @base])?)
        """,
        "calls": """
            (call function: (identifier) @func)
            (call function: (attribute attribute: (identifier) @method))
        """,
    },
    "typescript": {
        "imports": """
            (import_statement
                source: (string (string_fragment) @path))
            (import_declaration
                source: (string (string_fragment) @path))
        """,
        "classes": """
            (class_declaration
                name: (type_identifier) @class_name
                (class_heritage
                    (extends_clause value: (identifier) @base))?)
        """,
        "calls": """
            (call_expression function: (identifier) @func)
            (call_expression
                function: (member_expression
                    property: (property_identifier) @method))
        """,
    },
    "javascript": {
        "imports": """
            (import_statement
                source: (string (string_fragment) @path))
            (call_expression
                function: (identifier) @_req
                (#eq? @_req "require")
                arguments: (arguments (string (string_fragment) @path)))
        """,
        "classes": """
            (class_declaration
                name: (identifier) @class_name
                (class_heritage
                    (extends_clause value: (identifier) @base))?)
        """,
        "calls": """
            (call_expression function: (identifier) @func)
            (call_expression
                function: (member_expression
                    property: (property_identifier) @method))
        """,
    },
    "rust": {
        "imports": """
            (use_declaration
                argument: (scoped_identifier) @path)
            (use_declaration
                argument: (identifier) @path)
            (use_declaration
                argument: (scoped_use_list
                    path: (scoped_identifier)? @path))
        """,
        "classes": """
            (struct_item name: (type_identifier) @struct_name)
            (impl_item type: (type_identifier) @impl_type
                trait: (type_identifier)? @trait_name)
        """,
        "calls": """
            (call_expression
                function: (identifier) @func)
            (call_expression
                function: (scoped_identifier
                    name: (identifier) @func))
        """,
    },
    "go": {
        "imports": """
            (import_spec path: (interpreted_string_literal) @path)
        """,
        "classes": """
            (type_declaration
                (type_spec name: (type_identifier) @type_name))
        """,
        "calls": """
            (call_expression
                function: (identifier) @func)
            (call_expression
                function: (selector_expression
                    field: (field_identifier) @method))
        """,
    },
}


def _try_import_treesitter():
    """Return (get_parser, get_language) or (None, None) if not available."""
    try:
        from tree_sitter_languages import get_parser, get_language  # type: ignore

        return get_parser, get_language
    except ImportError:
        return None, None


class TreeSitterExtractor:
    """Multi-language relationship extractor using tree-sitter."""

    def __init__(self, project_root: Path):
        get_parser, get_language = _try_import_treesitter()
        if get_parser is None:
            raise ImportError(
                "tree-sitter-languages is not installed.\n"
                "Install it with: pip install tree-sitter-languages"
            )
        self._get_parser = get_parser
        self._get_language = get_language
        self.project_root = Path(project_root)
        self.relationships: List[Relationship] = []
        self.entities: Dict[str, CodeEntity] = {}
        self._parser_cache: Dict[str, object] = {}
        self._query_cache: Dict[str, object] = {}

    def _parser_for(self, lang: str):
        if lang not in self._parser_cache:
            self._parser_cache[lang] = self._get_parser(lang)
        return self._parser_cache[lang]

    def _query_for(self, lang: str, kind: str):
        key = f"{lang}:{kind}"
        if key not in self._query_cache:
            language_obj = self._get_language(lang)
            src = _TS_QUERIES.get(lang, {}).get(kind, "")
            if not src.strip():
                self._query_cache[key] = None
            else:
                try:
                    self._query_cache[key] = language_obj.query(src)
                except Exception:
                    self._query_cache[key] = None
        return self._query_cache[key]

    def extract_from_file(self, file_path: Path) -> List[Relationship]:
        suffix = file_path.suffix.lower()
        lang = EXTENSION_TO_LANGUAGE.get(suffix)
        if lang is None:
            return []

        try:
            source = file_path.read_bytes()
        except (OSError, PermissionError):
            return []

        try:
            parser = self._parser_for(lang)
            tree = parser.parse(source)
        except Exception as e:
            print(f"  tree-sitter parse error {file_path}: {e}")
            return []

        try:
            rel_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            rel_path = str(file_path)

        relationships: List[Relationship] = []
        source_str = source.decode("utf-8", errors="replace")

        relationships.extend(self._extract_imports(tree, rel_path, lang, source_str))
        relationships.extend(self._extract_classes(tree, rel_path, lang))
        relationships.extend(self._extract_calls(tree, rel_path, lang))

        return relationships

    def _node_text(self, node, source: str) -> str:
        return source[node.start_byte : node.end_byte]

    def _extract_imports(
        self, tree, rel_path: str, lang: str, source: str
    ) -> List[Relationship]:
        query = self._query_for(lang, "imports")
        if query is None:
            return []

        rels = []
        seen: Set[str] = set()
        for node, capture_name in query.captures(tree.root_node):
            if capture_name in ("module", "name", "path"):
                target = self._node_text(node, source).strip("\"'`")
                if not target or target in seen:
                    continue
                seen.add(target)
                rel_type = (
                    "imports_from" if capture_name == "name" else "imports_module"
                )
                rels.append(
                    Relationship(
                        source=rel_path,
                        target=target,
                        relation_type=rel_type,
                        metadata={"line": node.start_point[0] + 1, "lang": lang},
                    )
                )
        return rels

    def _extract_classes(self, tree, rel_path: str, lang: str) -> List[Relationship]:
        query = self._query_for(lang, "classes")
        if query is None:
            return []

        rels = []
        captures = query.captures(tree.root_node)
        # Group captures — class_name followed by optional base
        current_class: Optional[str] = None
        for node, capture_name in captures:
            text = node.start_byte  # used for ordering only

        # Re-iterate cleanly
        class_names: Dict[int, str] = {}
        for node, capture_name in query.captures(tree.root_node):
            if capture_name in ("class_name", "struct_name", "type_name", "impl_type"):
                class_names[node.start_byte] = node.start_point[0]

        for node, capture_name in query.captures(tree.root_node):
            if capture_name == "base":
                # Find the most recent class definition before this node
                earlier = {k: v for k, v in class_names.items() if k < node.start_byte}
                if earlier:
                    line = node.start_point[0] + 1
                    parent = node.start_byte  # crude text extraction
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=node.type,  # placeholder; overridden below
                            relation_type="inherits_from",
                            metadata={"line": line, "lang": lang},
                        )
                    )
                    # Fix target using raw source bytes — not available here.
                    # We'll re-run with source in a cleaner pass.
        return rels

    def _extract_classes_with_source(
        self, tree, rel_path: str, lang: str, source: str
    ) -> List[Relationship]:
        """Cleaner class extraction that has access to source text."""
        query = self._query_for(lang, "classes")
        if query is None:
            return []

        rels = []
        last_class_name: Optional[str] = None
        last_class_byte: int = -1

        for node, capture_name in query.captures(tree.root_node):
            raw = self._node_text(node, source)
            if capture_name in ("class_name", "struct_name", "type_name", "impl_type"):
                last_class_name = raw
                last_class_byte = node.start_byte
                self.entities[f"{rel_path}::{raw}"] = CodeEntity(
                    name=raw,
                    entity_type="class",
                    file_path=rel_path,
                    line_number=node.start_point[0] + 1,
                    metadata={"lang": lang},
                )
            elif capture_name in ("base", "trait_name") and last_class_name:
                rels.append(
                    Relationship(
                        source=rel_path,
                        target=raw,
                        relation_type="inherits_from",
                        metadata={
                            "line": node.start_point[0] + 1,
                            "class": last_class_name,
                            "lang": lang,
                        },
                    )
                )
        return rels

    def _extract_calls(self, tree, rel_path: str, lang: str) -> List[Relationship]:
        query = self._query_for(lang, "calls")
        if query is None:
            return []

        rels = []
        seen: Set[tuple] = set()
        # We need source to get text — skip if not available (called from extract_from_file)
        # This is a placeholder; real extraction happens inside extract_from_file
        return rels

    def extract_from_file(self, file_path: Path) -> List[Relationship]:  # noqa: F811
        """Full extraction with source access for all relationship types."""
        suffix = file_path.suffix.lower()
        lang = EXTENSION_TO_LANGUAGE.get(suffix)
        if lang is None:
            return []

        try:
            source_bytes = file_path.read_bytes()
            source = source_bytes.decode("utf-8", errors="replace")
        except (OSError, PermissionError):
            return []

        try:
            parser = self._parser_for(lang)
            tree = parser.parse(source_bytes)
        except Exception as e:
            print(f"  tree-sitter parse error {file_path}: {e}")
            return []

        try:
            rel_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            rel_path = str(file_path)

        relationships: List[Relationship] = []

        import re

        _VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        _PYTHON_KEYWORDS = {
            "True",
            "False",
            "None",
            "def",
            "class",
            "if",
            "else",
            "elif",
            "for",
            "while",
            "return",
            "import",
            "from",
            "as",
            "try",
            "except",
            "finally",
            "with",
            "pass",
            "break",
            "continue",
            "raise",
            "yield",
            "lambda",
            "and",
            "or",
            "not",
            "in",
            "is",
            "global",
            "nonlocal",
            "assert",
            "del",
            "async",
            "await",
        }

        def _clean_identifier(text: str) -> Optional[str]:
            if not text:
                return None
            text = text.strip().strip("\"'`")
            if not text or len(text) < 2:
                return None
            if "\n" in text or "\r" in text or "\t" in text:
                return None
            if any(
                c in text
                for c in [
                    "(",
                    ")",
                    ":",
                    "[",
                    "]",
                    "{",
                    "}",
                    ",",
                    "#",
                    "<",
                    ">",
                    "=",
                    "!",
                    "+",
                    "-",
                    "*",
                    "/",
                    "%",
                    "&",
                    "|",
                    "^",
                    "~",
                    "@",
                    "$",
                    "?",
                    ".",
                    " ",
                    '"',
                    "'",
                ]
            ):
                return None
            if not _VALID_IDENTIFIER.match(text):
                return None
            if text in _PYTHON_KEYWORDS:
                return None
            return text

        # Imports
        q = self._query_for(lang, "imports")
        if q:
            seen_imports: Set[str] = set()
            for node, capture_name in q.captures(tree.root_node):
                if capture_name.startswith("_"):
                    continue
                raw = source[node.start_byte : node.end_byte]
                target = _clean_identifier(raw)
                if not target or target in seen_imports:
                    continue
                seen_imports.add(target)
                rel_type = (
                    "imports_from" if capture_name == "name" else "imports_module"
                )
                relationships.append(
                    Relationship(
                        source=rel_path,
                        target=target,
                        relation_type=rel_type,
                        metadata={"line": node.start_point[0] + 1, "lang": lang},
                    )
                )

        # Classes / structs / impls
        relationships.extend(
            self._extract_classes_with_source(tree, rel_path, lang, source)
        )

        # Calls (deduplicated — only unique function names per file)
        q = self._query_for(lang, "calls")
        if q:
            seen_calls: Set[str] = set()
            for node, capture_name in q.captures(tree.root_node):
                if capture_name.startswith("_"):
                    continue
                raw = source[node.start_byte : node.end_byte]
                func = _clean_identifier(raw)
                if not func or func in seen_calls or len(func) > 64:
                    continue
                seen_calls.add(func)
                relationships.append(
                    Relationship(
                        source=rel_path,
                        target=func,
                        relation_type="calls",
                        metadata={"line": node.start_point[0] + 1, "lang": lang},
                    )
                )

        return relationships

    def extract_from_directory(self, directory: Path) -> List[Relationship]:
        all_rels: List[Relationship] = []
        for path in directory.rglob("*"):
            if path.is_dir():
                if path.name in EXCLUDE_DIRS:
                    continue
            if not path.is_file():
                continue
            if path.suffix.lower() not in EXTENSION_TO_LANGUAGE:
                continue
            # Skip excluded dirs in path
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            print(
                f"  [{path.suffix[1:].upper()}] {path.relative_to(self.project_root)}"
            )
            rels = self.extract_from_file(path)
            all_rels.extend(rels)

        self.relationships.extend(all_rels)
        return all_rels

    def save_to_file(self, output_path: Path):
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Saved {len(self.relationships)} relationships to {output_path}")

    def get_stats(self) -> Dict:
        type_counts = defaultdict(int)
        lang_counts = defaultdict(int)
        for rel in self.relationships:
            type_counts[rel.relation_type] += 1
            lang_counts[rel.metadata.get("lang", "unknown")] += 1
        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
            "by_language": dict(lang_counts),
        }


# ---------------------------------------------------------------------------
# Python-only AST extractor (original implementation, kept as fallback)
# ---------------------------------------------------------------------------


class ASTRelationshipExtractor:
    """Extract relationships from Python code using AST parsing (Python only)."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.relationships: List[Relationship] = []
        self.entities: Dict[str, CodeEntity] = {}

    def extract_from_file(self, file_path: Path) -> List[Relationship]:
        if file_path.suffix.lower() != ".py":
            return []
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

    def _extract_imports(self, tree, file_path) -> List[Relationship]:
        rels = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    rels.append(
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
                    rels.append(
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
        return rels

    def _extract_inheritance(self, tree, file_path) -> List[Relationship]:
        rels = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        rels.append(
                            Relationship(
                                source=str(file_path),
                                target=base.id,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.lineno,
                                    "class": node.name,
                                    "parent": base.id,
                                },
                            )
                        )
                    elif isinstance(base, ast.Attribute):
                        chain = self._get_attribute_chain(base)
                        rels.append(
                            Relationship(
                                source=str(file_path),
                                target=chain,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.lineno,
                                    "class": node.name,
                                    "parent": chain,
                                },
                            )
                        )
                self.entities[f"{file_path}::{node.name}"] = CodeEntity(
                    name=node.name,
                    entity_type="class",
                    file_path=str(file_path),
                    line_number=node.lineno,
                    metadata={"bases": [self._get_base_name(b) for b in node.bases]},
                )
        return rels

    def _extract_function_calls(self, tree, file_path) -> List[Relationship]:
        rels = []
        call_targets: Set[tuple] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node.func)
                if func_name:
                    call_targets.add((func_name, node.lineno))
        for target, line in call_targets:
            rels.append(
                Relationship(
                    source=str(file_path),
                    target=target,
                    relation_type="calls",
                    metadata={"line": line, "call_type": "function_call"},
                )
            )
        return rels

    def _extract_class_methods(self, tree, file_path) -> List[Relationship]:
        rels = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        rels.append(
                            Relationship(
                                source=f"{file_path}::{node.name}",
                                target=f"{file_path}::{node.name}.{item.name}",
                                relation_type="has_method",
                                metadata={
                                    "line": item.lineno,
                                    "class": node.name,
                                    "method": item.name,
                                },
                            )
                        )
                        self.entities[f"{file_path}::{node.name}.{item.name}"] = (
                            CodeEntity(
                                name=item.name,
                                entity_type="method",
                                file_path=str(file_path),
                                line_number=item.lineno,
                                metadata={
                                    "class": node.name,
                                    "args": [arg.arg for arg in item.args.args],
                                },
                            )
                        )
        return rels

    def _get_call_name(self, node) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        return None

    def _get_attribute_chain(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_attribute_chain(node.value)}.{node.attr}"
        return ""

    def _get_base_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        return ""

    def extract_from_directory(self, directory: Path) -> List[Relationship]:
        all_rels = []
        for py_file in directory.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in py_file.parts):
                continue
            print(f"  [PY ] {py_file.relative_to(self.project_root)}")
            rels = self.extract_from_file(py_file)
            all_rels.extend(rels)
        self.relationships.extend(all_rels)
        return all_rels

    def save_to_file(self, output_path: Path):
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Saved {len(self.relationships)} relationships to {output_path}")

    def get_stats(self) -> Dict:
        type_counts = defaultdict(int)
        for rel in self.relationships:
            type_counts[rel.relation_type] += 1
        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
            "by_language": {"python": len(self.relationships)},
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _make_extractor(project_root: Path):
    """Return a TreeSitterExtractor if available, otherwise ASTRelationshipExtractor."""
    get_parser, _ = _try_import_treesitter()
    if get_parser is not None:
        print("🌍 Multi-language extraction via tree-sitter")
        return TreeSitterExtractor(project_root)
    else:
        print(
            "🐍 Python-only extraction via ast (install tree-sitter-languages for multi-language)"
        )
        return ASTRelationshipExtractor(project_root)


def extract_code_relationships(
    project_root: Path,
    output_dir: Optional[Path] = None,
    code_dirs: Optional[List[str]] = None,
    from_index: bool = False,
) -> "ASTRelationshipExtractor | TreeSitterExtractor":
    """Extract code relationships from a project.

    Args:
        project_root:  Root directory of the project.
        output_dir:    Where to save code_relationships.json
                       (default: PROJECT/.knowledge).
        code_dirs:     Directory names to scan (default: ["src"]).
        from_index:    Use files from the index manifest instead of
                       scanning directories.
    """
    print(f"🔍 Extracting code relationships from {project_root}")
    print()

    extractor = _make_extractor(project_root)

    if from_index:
        indexed_files = load_indexed_files(project_root)
        supported_extensions = set(EXTENSION_TO_LANGUAGE.keys())
        indexed_files = [
            f for f in indexed_files if f.suffix.lower() in supported_extensions
        ]
        if indexed_files:
            print(f"📚 Using {len(indexed_files)} indexed source files from manifest")
            for file_path in indexed_files:
                if file_path.exists():
                    try:
                        rel = file_path.relative_to(project_root)
                    except ValueError:
                        rel = file_path
                    print(f"  {rel}")
                    rels = extractor.extract_from_file(file_path)
                    extractor.relationships.extend(rels)
        else:
            print(
                "⚠️  No indexed source files found in manifest. Run mimir-index.py first."
            )
    else:
        if code_dirs is None:
            code_dirs = ["src"]

        for dir_name in code_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                print(f"📁 Scanning {dir_name}/...")
                extractor.extract_from_directory(dir_path)
            else:
                print(f"⚠️  Directory not found: {dir_path}")

        print("📁 Scanning root-level source files...")
        for path in project_root.iterdir():
            if path.is_file() and path.suffix.lower() in EXTENSION_TO_LANGUAGE:
                print(f"  {path.name}")
                rels = extractor.extract_from_file(path)
                extractor.relationships.extend(rels)

    if output_dir is None:
        output_dir = project_root / ".knowledge"
    output_dir.mkdir(exist_ok=True)
    extractor.save_to_file(output_dir / "code_relationships.json")

    stats = extractor.get_stats()
    print(f"\n📊 Statistics:")
    print(f"  Total relationships: {stats['total_relationships']}")
    print(f"  Total entities:      {stats['total_entities']}")
    print(f"  By type:")
    for rel_type, count in stats["by_type"].items():
        print(f"    - {rel_type}: {count}")
    if stats.get("by_language"):
        print(f"  By language:")
        for lang, count in stats["by_language"].items():
            print(f"    - {lang}: {count}")

    return extractor


def load_project_config(project_root: Path) -> dict:
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
    for _, info in manifest.get("indexed_directories", {}).items():
        for file_path in info.get("files", []):
            path = Path(file_path)
            if not path.is_absolute():
                path = project_root / path
            if path.suffix.lower() in EXTENSION_TO_LANGUAGE:
                indexed_files.append(path)
    return indexed_files


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract code relationships from a project (multi-language via tree-sitter)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported languages (requires tree-sitter-languages):
  Python (.py), TypeScript (.ts/.tsx), JavaScript (.js/.jsx/.mjs),
  Rust (.rs), Go (.go)

Install multi-language support:
  pip install tree-sitter-languages

Examples:
  python knowledge_graph.py
  python knowledge_graph.py /path/to/project --dirs src,lib
  python knowledge_graph.py /path/to/project --from-index
        """,
    )
    parser.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--dirs", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--from-index", action="store_true", dest="from_index")
    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists() or not project_root.is_dir():
        print(f"❌ Error: {project_root} is not a directory")
        raise SystemExit(1)

    if args.from_index:
        extract_code_relationships(project_root, args.output, from_index=True)
    else:
        project_config = load_project_config(project_root)
        if args.dirs:
            code_dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
        elif "code_dirs" in project_config:
            code_dirs = project_config["code_dirs"]
        else:
            code_dirs = ["src"]
        extract_code_relationships(project_root, args.output, code_dirs)
