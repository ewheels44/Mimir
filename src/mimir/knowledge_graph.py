"""Knowledge Graph Relationship Extraction

Two complementary extractors, used together when tree-sitter-languages is
available, or Python-only as a reliable fallback:

  PythonASTExtractor   — .py files via Python's built-in `ast` module.
                         Always available, semantically accurate, fast.

  TreeSitterExtractor  — .ts/.tsx/.js/.jsx/.rs/.go files via tree-sitter.
                         Requires: pip install tree-sitter-languages
                         Walks the concrete syntax tree directly — no
                         fragile S-expression queries.

  CombinedExtractor    — Routes .py to AST, everything else to TreeSitter.
                         This is the preferred path when tree-sitter is
                         available.

Public API
----------
    extract_code_relationships(project_root, output_dir, code_dirs, from_index)
        → extractor with .relationships, .entities, .get_stats(), .save_to_file()
"""

import ast
import contextlib
import json
import keyword
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from src.mimir.utils import should_exclude as _should_exclude_files

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS: set[str] = {
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".git",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    "out",
    ".output",
}

EXTENSION_TO_LANGUAGE: dict[str, str] = {
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

# Per-language keywords — used to filter noise out of extracted identifiers.
_PYTHON_KW: frozenset[str] = frozenset(keyword.kwlist) | {
    "True",
    "False",
    "None",
    "self",
    "cls",
}
_JS_KW: frozenset[str] = frozenset(
    {
        "var",
        "let",
        "const",
        "function",
        "class",
        "if",
        "else",
        "for",
        "while",
        "do",
        "return",
        "import",
        "export",
        "from",
        "as",
        "try",
        "catch",
        "finally",
        "throw",
        "new",
        "delete",
        "typeof",
        "instanceof",
        "in",
        "of",
        "switch",
        "case",
        "break",
        "continue",
        "default",
        "async",
        "await",
        "yield",
        "static",
        "extends",
        "super",
        "this",
        "true",
        "false",
        "null",
        "undefined",
        "void",
    }
)
_RUST_KW: frozenset[str] = frozenset(
    {
        "fn",
        "let",
        "mut",
        "pub",
        "use",
        "mod",
        "struct",
        "enum",
        "impl",
        "trait",
        "for",
        "while",
        "loop",
        "if",
        "else",
        "match",
        "return",
        "self",
        "Self",
        "super",
        "crate",
        "type",
        "where",
        "async",
        "await",
        "move",
        "ref",
        "in",
        "as",
        "true",
        "false",
        "dyn",
        "box",
    }
)
_GO_KW: frozenset[str] = frozenset(
    {
        "func",
        "var",
        "const",
        "type",
        "struct",
        "interface",
        "map",
        "chan",
        "for",
        "range",
        "if",
        "else",
        "switch",
        "case",
        "default",
        "return",
        "break",
        "continue",
        "goto",
        "defer",
        "go",
        "select",
        "package",
        "import",
        "true",
        "false",
        "nil",
        "make",
        "new",
        "len",
        "cap",
        "append",
        "copy",
        "delete",
        "close",
        "panic",
        "recover",
    }
)

_LANG_KEYWORDS: dict[str, frozenset[str]] = {
    "python": _PYTHON_KW,
    "typescript": _JS_KW,
    "javascript": _JS_KW,
    "rust": _RUST_KW,
    "go": _GO_KW,
}

# Valid identifier pattern (covers Python, JS/TS, Rust, Go, with $ for JS)
_VALID_NAME_RE = re.compile(r"^[a-zA-Z_$][a-zA-Z0-9_$.:]*$")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Relationship:
    source: str  # relative file path
    target: str  # relative file path OR module/symbol name
    relation_type: (
        str  # imports_module | imports_from | inherits_from | calls | has_method
    )
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "metadata": self.metadata,
        }


@dataclass
class CodeEntity:
    name: str
    entity_type: str  # class | method | function | struct | interface
    file_path: str
    line_number: int
    metadata: dict


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_valid_identifier(text: str, lang: str = "python") -> bool:
    """Return True iff *text* looks like a real, keepable identifier."""
    if not text or len(text) < 2 or len(text) > 128:
        return False
    if not _VALID_NAME_RE.match(text):
        return False
    return text not in _LANG_KEYWORDS.get(lang, _PYTHON_KW)


def _strip_quotes(text: str) -> str:
    """Remove surrounding quote characters from a string literal token."""
    return text.strip().strip('"').strip("'").strip("`")


def _should_exclude(path: Path) -> bool:
    """True if path should be excluded (directory or file pattern)."""
    # Check directory components
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True
    # Also check file-level patterns from shared utils
    return _should_exclude_files(path)


def _walk_ts_tree(node):
    """Depth-first generator over a tree-sitter CST."""
    yield node
    for child in node.children:
        yield from _walk_ts_tree(child)


def _ts_node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Python AST extractor  (always available, very accurate)
# ---------------------------------------------------------------------------


class PythonASTExtractor:
    """Extract relationships from Python source using the built-in ast module."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.relationships: list[Relationship] = []
        self.entities: dict[str, CodeEntity] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract_from_file(self, file_path: Path) -> list[Relationship]:
        if file_path.suffix.lower() != ".py":
            return []
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            print(f"  [WARN] syntax error in {file_path}: {exc}")
            return []
        except Exception as exc:
            print(f"  [WARN] cannot parse {file_path}: {exc}")
            return []

        rel_path = self._rel(file_path)
        rels: list[Relationship] = []
        rels.extend(self._imports(tree, rel_path))
        rels.extend(self._classes(tree, rel_path))
        rels.extend(self._calls(tree, rel_path))
        return rels

    def extract_from_directory(self, directory: Path) -> list[Relationship]:
        found: list[Relationship] = []
        for py_file in sorted(directory.rglob("*.py")):
            if _should_exclude(py_file):
                continue
            try:
                rel = py_file.relative_to(self.project_root)
            except ValueError:
                rel = py_file
            print(f"  [PY ] {rel}")
            rels = self.extract_from_file(py_file)
            self.relationships.extend(rels)
            found.extend(rels)
        return found

    def save_to_file(self, output_path: Path) -> None:
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Saved {len(self.relationships)} relationships → {output_path}")

    def get_stats(self) -> dict:
        type_counts: dict[str, int] = defaultdict(int)
        for r in self.relationships:
            type_counts[r.relation_type] += 1
        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
            "by_language": {"python": len(self.relationships)},
        }

    # ------------------------------------------------------------------
    # Private extraction helpers
    # ------------------------------------------------------------------

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    def _imports(self, tree: ast.Module, rel_path: str) -> list[Relationship]:
        rels: list[Relationship] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=alias.name,
                            relation_type="imports_module",
                            metadata={"line": node.lineno, "asname": alias.asname},
                        )
                    )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    target = f"{module}.{alias.name}" if module else alias.name
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=target,
                            relation_type="imports_from",
                            metadata={
                                "line": node.lineno,
                                "module": module,
                                "name": alias.name,
                            },
                        )
                    )
        return rels

    def _classes(self, tree: ast.Module, rel_path: str) -> list[Relationship]:
        rels: list[Relationship] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            self.entities[f"{rel_path}::{node.name}"] = CodeEntity(
                name=node.name,
                entity_type="class",
                file_path=rel_path,
                line_number=node.lineno,
                metadata={"bases": [self._base_name(b) for b in node.bases]},
            )

            for base in node.bases:
                name = self._base_name(base)
                if name and _is_valid_identifier(name.split(".")[-1], "python"):
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=name,
                            relation_type="inherits_from",
                            metadata={"line": node.lineno, "class": node.name},
                        )
                    )

            # Methods
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_key = f"{rel_path}::{node.name}.{item.name}"
                    self.entities[method_key] = CodeEntity(
                        name=item.name,
                        entity_type="method",
                        file_path=rel_path,
                        line_number=item.lineno,
                        metadata={"class": node.name},
                    )
                    rels.append(
                        Relationship(
                            source=f"{rel_path}::{node.name}",
                            target=method_key,
                            relation_type="has_method",
                            metadata={
                                "line": item.lineno,
                                "class": node.name,
                                "method": item.name,
                            },
                        )
                    )
        return rels

    def _calls(self, tree: ast.Module, rel_path: str) -> list[Relationship]:
        """Function / method calls — deduplicated per file.

        Now captures:
          - bare calls:     foo()
          - method calls:   self.client.get()
          - attr calls:     module.func()
          - chained calls:  self.builder().configure().run()
        """
        rels: list[Relationship] = []
        seen_local: set[str] = set()

        # Also track calls at deeper levels (self.x.y())
        seen_qualified: set[str] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = self._call_name(node.func)
            if not name:
                continue

            # For simple top-level names (foo), keep just the identifier
            top = name.split(".")[0]
            if top and _is_valid_identifier(top, "python") and top not in seen_local:
                    seen_local.add(top)
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=top,
                            relation_type="calls",
                            metadata={"line": node.lineno},
                        )
                    )

            # Also record qualified chains (self.client.get) for richer graph
            if "." in name and name not in seen_qualified:
                seen_qualified.add(name)
                rels.append(
                    Relationship(
                        source=rel_path,
                        target=name,
                        relation_type="calls",
                        metadata={"line": node.lineno, "qualified": True},
                    )
                )

        return rels

    @staticmethod
    def _call_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = PythonASTExtractor._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    @staticmethod
    def _base_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = PythonASTExtractor._base_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""


# ---------------------------------------------------------------------------
# Tree-sitter extractor  (multi-language)
# ---------------------------------------------------------------------------

# Node type sets per language — what we look for when walking the tree.
# These match the actual grammar node types produced by tree-sitter-languages.

_TS_IMPORT_NODES: dict[str, set[str]] = {
    "typescript": {"import_statement", "import_declaration"},
    "javascript": {"import_statement", "import_declaration"},
    "rust": {"use_declaration"},
    "go": {"import_declaration", "import_spec"},
}

_TS_CLASS_NODES: dict[str, set[str]] = {
    "typescript": {"class_declaration", "abstract_class_declaration", "class_body"},
    "javascript": {"class_declaration", "class_expression"},
    "rust": {"struct_item", "impl_item", "trait_item", "enum_item"},
    "go": {"type_spec"},
}

_TS_CALL_NAME_NODES: dict[str, set[str]] = {
    "typescript": {"identifier"},
    "javascript": {"identifier"},
    "rust": {"identifier"},
    "go": {"identifier"},
}


def _try_import_treesitter() -> tuple[Optional[object], Optional[object]]:
    try:
        from tree_sitter_languages import get_language, get_parser  # type: ignore

        return get_parser, get_language
    except ImportError:
        print(
            "⚠️  tree-sitter-languages not installed — knowledge graph will only cover Python. "
            "Run: pip install tree-sitter-languages   # adds TS/JS/Rust/Go support",
            flush=True,
        )
        return None, None


class TreeSitterExtractor:
    """
    Multi-language extractor that walks tree-sitter CSTs directly.
    No S-expression queries — just typed node matching, which is stable
    across grammar versions.

    Only handles non-Python files. Use CombinedExtractor to get both.
    """

    SUPPORTED: set[str] = {"typescript", "javascript", "rust", "go"}

    def __init__(self, project_root: Path):
        get_parser, get_language = _try_import_treesitter()
        if get_parser is None:
            raise ImportError(
                "tree-sitter-languages is not installed.\n"
                "  pip install tree-sitter-languages"
            )
        self._get_parser = get_parser
        self._get_language = get_language
        self.project_root = Path(project_root)
        self.relationships: list[Relationship] = []
        self.entities: dict[str, CodeEntity] = {}
        self._parser_cache: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract_from_file(self, file_path: Path) -> list[Relationship]:
        lang = EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower())
        if lang not in self.SUPPORTED:
            return []

        try:
            source_bytes = file_path.read_bytes()
        except (OSError, PermissionError) as exc:
            print(f"  [WARN] cannot read {file_path}: {exc}")
            return []

        try:
            parser = self._parser_for(lang)
            tree = parser.parse(source_bytes)
        except Exception as exc:
            print(f"  [WARN] tree-sitter parse failed {file_path}: {exc}")
            return []

        rel_path = self._rel(file_path)
        dispatch = {
            "typescript": self._extract_ts_js,
            "javascript": self._extract_ts_js,
            "rust": self._extract_rust,
            "go": self._extract_go,
        }
        extractor_fn = dispatch.get(lang)
        if extractor_fn is None:
            return []

        rels = extractor_fn(tree.root_node, source_bytes, rel_path, lang)
        return rels

    def extract_from_directory(self, directory: Path) -> list[Relationship]:
        found: list[Relationship] = []
        supported_exts = {
            ext for ext, lang in EXTENSION_TO_LANGUAGE.items() if lang in self.SUPPORTED
        }
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in supported_exts:
                continue
            if _should_exclude(path):
                continue
            try:
                rel = path.relative_to(self.project_root)
            except ValueError:
                rel = path
            lang = EXTENSION_TO_LANGUAGE[path.suffix.lower()]
            print(f"  [{lang.upper()[:2]}] {rel}")
            rels = self.extract_from_file(path)
            self.relationships.extend(rels)
            found.extend(rels)
        return found

    def save_to_file(self, output_path: Path) -> None:
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Saved {len(self.relationships)} relationships → {output_path}")

    def get_stats(self) -> dict:
        type_counts: dict[str, int] = defaultdict(int)
        lang_counts: dict[str, int] = defaultdict(int)
        for r in self.relationships:
            type_counts[r.relation_type] += 1
            lang_counts[r.metadata.get("lang", "unknown")] += 1
        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
            "by_language": dict(lang_counts),
        }

    # ------------------------------------------------------------------
    # Private: parser cache
    # ------------------------------------------------------------------

    def _parser_for(self, lang: str):
        if lang not in self._parser_cache:
            self._parser_cache[lang] = self._get_parser(lang)
        return self._parser_cache[lang]

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root))
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------
    # TypeScript / JavaScript extraction
    # ------------------------------------------------------------------

    def _extract_ts_js(
        self, root, source: bytes, rel_path: str, lang: str
    ) -> list[Relationship]:
        rels: list[Relationship] = []
        seen_imports: set[str] = set()
        seen_calls: set[str] = set()

        for node in _walk_ts_tree(root):
            ntype = node.type

            # ── Imports ────────────────────────────────────────────────
            if ntype in ("import_statement", "import_declaration"):
                # Find the string source: "from './foo'" or "import './bar'"
                for child in _walk_ts_tree(node):
                    if child.type == "string":
                        raw = _strip_quotes(_ts_node_text(child, source))
                        if raw and raw not in seen_imports:
                            seen_imports.add(raw)
                            rels.append(
                                Relationship(
                                    source=rel_path,
                                    target=raw,
                                    relation_type="imports_module",
                                    metadata={
                                        "line": node.start_point[0] + 1,
                                        "lang": lang,
                                    },
                                )
                            )
                        break  # one string per import statement

            # ── Class declarations ──────────────────────────────────────
            elif ntype in (
                "class_declaration",
                "abstract_class_declaration",
                "class_expression",
            ):
                class_name = None
                bases: list[str] = []

                for child in node.children:
                    if child.type in ("identifier", "type_identifier"):
                        if class_name is None:
                            class_name = _ts_node_text(child, source)
                    elif child.type == "class_heritage":
                        # Grab what comes after `extends`
                        past_extends = False
                        for hchild in child.children:
                            if hchild.type == "extends":
                                past_extends = True
                                continue
                            if past_extends and hchild.type in (
                                "identifier",
                                "type_identifier",
                                "member_expression",
                            ):
                                base = _ts_node_text(hchild, source).split("<")[
                                    0
                                ]  # strip generics
                                if _is_valid_identifier(base.split(".")[-1], lang):
                                    bases.append(base)

                if class_name:
                    self.entities[f"{rel_path}::{class_name}"] = CodeEntity(
                        name=class_name,
                        entity_type="class",
                        file_path=rel_path,
                        line_number=node.start_point[0] + 1,
                        metadata={"lang": lang},
                    )
                    for base in bases:
                        rels.append(
                            Relationship(
                                source=rel_path,
                                target=base,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.start_point[0] + 1,
                                    "class": class_name,
                                    "lang": lang,
                                },
                            )
                        )

            # ── Call expressions ────────────────────────────────────────
            elif ntype == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is None:
                    continue
                if func_node.type == "identifier":
                    name = _ts_node_text(func_node, source)
                elif func_node.type in ("member_expression", "subscript_expression"):
                    # Full qualified name: foo.bar() → "foo.bar"
                    name = _ts_node_text(func_node, source)
                else:
                    continue

                if name not in seen_calls and _is_valid_identifier(name, lang):
                    seen_calls.add(name)
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=name,
                            relation_type="calls",
                            metadata={"line": node.start_point[0] + 1, "lang": lang},
                        )
                    )

        return rels

    # ------------------------------------------------------------------
    # Rust extraction
    # ------------------------------------------------------------------

    def _extract_rust(
        self, root, source: bytes, rel_path: str, lang: str
    ) -> list[Relationship]:
        rels: list[Relationship] = []
        seen_uses: set[str] = set()
        seen_calls: set[str] = set()

        for node in _walk_ts_tree(root):
            ntype = node.type

            # ── use declarations ────────────────────────────────────────
            if ntype == "use_declaration":
                # Walk children to collect scoped_identifier / identifier text
                for child in _walk_ts_tree(node):
                    if child.type in (
                        "scoped_identifier",
                        "identifier",
                        "scoped_use_list",
                    ):
                        text = _ts_node_text(child, source).strip("{}")
                        # Take just the first segment as the crate/module name
                        top = text.split("::")[0].strip()
                        if (
                            top
                            and top not in seen_uses
                            and _is_valid_identifier(top, lang)
                        ):
                            seen_uses.add(top)
                            rels.append(
                                Relationship(
                                    source=rel_path,
                                    target=text,
                                    relation_type="imports_module",
                                    metadata={
                                        "line": node.start_point[0] + 1,
                                        "lang": lang,
                                    },
                                )
                            )
                        break

            # ── struct / enum / trait definitions ───────────────────────
            elif ntype in ("struct_item", "enum_item", "trait_item"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _ts_node_text(name_node, source)
                    etype = ntype.replace("_item", "")
                    self.entities[f"{rel_path}::{name}"] = CodeEntity(
                        name=name,
                        entity_type=etype,
                        file_path=rel_path,
                        line_number=node.start_point[0] + 1,
                        metadata={"lang": lang},
                    )

            # ── impl blocks — track what trait is being implemented ─────
            elif ntype == "impl_item":
                type_node = node.child_by_field_name("type")
                trait_node = node.child_by_field_name("trait")
                if type_node and trait_node:
                    impl_type = _ts_node_text(type_node, source)
                    trait_name = _ts_node_text(trait_node, source)
                    if _is_valid_identifier(trait_name.split("<")[0], lang):
                        rels.append(
                            Relationship(
                                source=rel_path,
                                target=trait_name,
                                relation_type="inherits_from",
                                metadata={
                                    "line": node.start_point[0] + 1,
                                    "impl_type": impl_type,
                                    "lang": lang,
                                },
                            )
                        )

            # ── call expressions ────────────────────────────────────────
            elif ntype == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is None:
                    continue
                # Rust calls: identifier, field_expression, scoped_identifier
                if func_node.type == "identifier" or func_node.type == "scoped_identifier":
                    name = _ts_node_text(func_node, source)
                elif func_node.type == "field_expression":
                    # Full qualified name: receiver.method → "receiver.method"
                    name = _ts_node_text(func_node, source)
                else:
                    continue

                if name and name not in seen_calls and _is_valid_identifier(name, lang):
                    seen_calls.add(name)
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=name,
                            relation_type="calls",
                            metadata={"line": node.start_point[0] + 1, "lang": lang},
                        )
                    )

        return rels

    # ------------------------------------------------------------------
    # Go extraction
    # ------------------------------------------------------------------

    def _extract_go(
        self, root, source: bytes, rel_path: str, lang: str
    ) -> list[Relationship]:
        rels: list[Relationship] = []
        seen_imports: set[str] = set()
        seen_calls: set[str] = set()

        for node in _walk_ts_tree(root):
            ntype = node.type

            # ── import paths ────────────────────────────────────────────
            if ntype == "import_spec":
                for child in node.children:
                    if child.type == "interpreted_string_literal":
                        raw = _strip_quotes(_ts_node_text(child, source))
                        # Keep the final path segment as the short name
                        short = raw.split("/")[-1]
                        if short and short not in seen_imports:
                            seen_imports.add(short)
                            rels.append(
                                Relationship(
                                    source=rel_path,
                                    target=raw,
                                    relation_type="imports_module",
                                    metadata={
                                        "line": node.start_point[0] + 1,
                                        "lang": lang,
                                    },
                                )
                            )

            # ── type declarations (struct / interface) ──────────────────
            elif ntype == "type_spec":
                name_node = node.child_by_field_name("name")
                type_node = node.child_by_field_name("type")
                if name_node:
                    name = _ts_node_text(name_node, source)
                    etype = "struct"
                    if type_node and type_node.type == "interface_type":
                        etype = "interface"
                    self.entities[f"{rel_path}::{name}"] = CodeEntity(
                        name=name,
                        entity_type=etype,
                        file_path=rel_path,
                        line_number=node.start_point[0] + 1,
                        metadata={"lang": lang},
                    )

            # ── call expressions ────────────────────────────────────────
            elif ntype == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node is None:
                    continue
                if func_node.type == "identifier":
                    name = _ts_node_text(func_node, source)
                elif func_node.type == "selector_expression":
                    # Full qualified name: fmt.Sprintf → "fmt.Sprintf"
                    name = _ts_node_text(func_node, source)
                else:
                    continue

                if name and name not in seen_calls and _is_valid_identifier(name, lang):
                    seen_calls.add(name)
                    rels.append(
                        Relationship(
                            source=rel_path,
                            target=name,
                            relation_type="calls",
                            metadata={"line": node.start_point[0] + 1, "lang": lang},
                        )
                    )

        return rels


# ---------------------------------------------------------------------------
# Combined extractor — Python via AST, everything else via tree-sitter
# ---------------------------------------------------------------------------


class CombinedExtractor:
    """Routes .py to PythonASTExtractor, other languages to TreeSitterExtractor."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self._py = PythonASTExtractor(project_root)
        self._ts = TreeSitterExtractor(project_root)

    @property
    def relationships(self) -> list[Relationship]:
        return self._py.relationships + self._ts.relationships

    @property
    def entities(self) -> dict[str, CodeEntity]:
        return {**self._py.entities, **self._ts.entities}

    def extract_from_file(self, file_path: Path) -> list[Relationship]:
        if file_path.suffix.lower() == ".py":
            rels = self._py.extract_from_file(file_path)
            self._py.relationships.extend(rels)
        else:
            rels = self._ts.extract_from_file(file_path)
            self._ts.relationships.extend(rels)
        return rels

    def extract_from_directory(self, directory: Path) -> list[Relationship]:
        """Walk directory, routing each file to the right extractor."""
        found: list[Relationship] = []
        supported_exts = set(EXTENSION_TO_LANGUAGE.keys())

        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in supported_exts:
                continue
            if _should_exclude(path):
                continue
            try:
                rel = path.relative_to(self.project_root)
            except ValueError:
                rel = path
            lang = EXTENSION_TO_LANGUAGE[path.suffix.lower()]
            tag = "PY " if lang == "python" else lang.upper()[:3]
            print(f"  [{tag}] {rel}")
            rels = self.extract_from_file(path)
            found.extend(rels)
        return found

    def save_to_file(self, output_path: Path) -> None:
        data = {
            "relationships": [r.to_dict() for r in self.relationships],
            "entities": {k: asdict(v) for k, v in self.entities.items()},
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n✅ Saved {len(self.relationships)} relationships → {output_path}")

    def get_stats(self) -> dict:
        type_counts: dict[str, int] = defaultdict(int)
        lang_counts: dict[str, int] = defaultdict(int)
        for r in self.relationships:
            type_counts[r.relation_type] += 1
            lang_counts[r.metadata.get("lang", "python")] += 1
        return {
            "total_relationships": len(self.relationships),
            "total_entities": len(self.entities),
            "by_type": dict(type_counts),
            "by_language": dict(lang_counts),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _make_extractor(
    project_root: Path,
) -> "CombinedExtractor | PythonASTExtractor":
    get_parser, _ = _try_import_treesitter()
    if get_parser is not None:
        print("🌍  Multi-language extraction (Python AST + tree-sitter)")
        return CombinedExtractor(project_root)
    else:
        print(
            "🐍  Python-only extraction via ast\n"
            "    Install tree-sitter-languages for TS/JS/Rust/Go support."
        )
        return PythonASTExtractor(project_root)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_code_relationships(
    project_root: Path,
    output_dir: Optional[Path] = None,
    code_dirs: Optional[list[str]] = None,
    from_index: bool = False,
) -> "CombinedExtractor | PythonASTExtractor":
    """
    Extract code relationships from *project_root*.

    Parameters
    ----------
    project_root : Path
        Root of the project to analyse.
    output_dir : Path, optional
        Where to write code_relationships.json.
        Defaults to ``project_root/.knowledge``.
    code_dirs : list of str, optional
        Sub-directory names to scan (default: ``["src"]``).
        Ignored when *from_index* is True.
    from_index : bool
        If True, read the list of files from the Mimir manifest instead of
        scanning directories. Useful to stay in sync with what was indexed.

    Returns
    -------
    The extractor instance — inspect `.relationships` and `.entities`
    or call `.get_stats()` for a summary.
    """
    print(f"🔍  Extracting code relationships from {project_root}\n")

    extractor = _make_extractor(project_root)

    if from_index:
        indexed_files = load_indexed_files(project_root)
        supported = set(EXTENSION_TO_LANGUAGE.keys())
        indexed_files = [f for f in indexed_files if f.suffix.lower() in supported]
        if not indexed_files:
            print(
                "⚠️   No indexed source files found in manifest. Run mimir-index.py first."
            )
        else:
            print(f"📚  Using {len(indexed_files)} files from manifest\n")
            for fp in indexed_files:
                if fp.exists():
                    try:
                        rel = fp.relative_to(project_root)
                    except ValueError:
                        rel = fp
                    lang = EXTENSION_TO_LANGUAGE.get(fp.suffix.lower(), "?")
                    tag = "PY " if lang == "python" else lang.upper()[:3]
                    print(f"  [{tag}] {rel}")
                    rels = extractor.extract_from_file(fp)
                    # For non-combined extractor, we need to extend relationships manually
                    if isinstance(extractor, PythonASTExtractor):
                        extractor.relationships.extend(rels)
                    elif isinstance(extractor, CombinedExtractor):
                        # CombinedExtractor routes to internal extractors, but we need to
                        # ensure relationships are stored based on file type
                        if fp.suffix.lower() == ".py":
                            extractor._py.relationships.extend(rels)
                        else:
                            extractor._ts.relationships.extend(rels)
    else:
        if code_dirs is None:
            code_dirs = ["src"]

        for dir_name in code_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                print(f"📁  Scanning {dir_name}/…")
                extractor.extract_from_directory(dir_path)
            else:
                print(f"⚠️   Directory not found: {dir_path}")

        # Also scan root-level source files
        print("\n📁  Scanning project root source files…")
        supported_exts = set(EXTENSION_TO_LANGUAGE.keys())
        for path in sorted(project_root.iterdir()):
            if path.is_file() and path.suffix.lower() in supported_exts:
                lang = EXTENSION_TO_LANGUAGE[path.suffix.lower()]
                tag = "PY " if lang == "python" else lang.upper()[:3]
                print(f"  [{tag}] {path.name}")
                rels = extractor.extract_from_file(path)
                if isinstance(extractor, PythonASTExtractor):
                    extractor.relationships.extend(rels)
                elif isinstance(extractor, CombinedExtractor):
                    # CombinedExtractor routes to internal extractors, but we need to
                    # ensure relationships are stored based on file type
                    if path.suffix.lower() == ".py":
                        extractor._py.relationships.extend(rels)
                    else:
                        extractor._ts.relationships.extend(rels)

    # Save
    if output_dir is None:
        output_dir = project_root / ".knowledge"
    output_dir.mkdir(exist_ok=True)
    extractor.save_to_file(output_dir / "code_relationships.json")

    stats = extractor.get_stats()
    print("\n📊  Statistics:")
    print(f"    Total relationships : {stats['total_relationships']}")
    print(f"    Total entities      : {stats['total_entities']}")
    print("    By relationship type:")
    for rel_type, count in sorted(stats["by_type"].items()):
        print(f"      {rel_type:<20} {count}")
    print("    By language:")
    for lang, count in sorted(stats["by_language"].items()):
        print(f"      {lang:<20} {count}")

    return extractor


# ---------------------------------------------------------------------------
# Supporting helpers (used by extract_code_relationships and mimir-index.py)
# ---------------------------------------------------------------------------


def load_project_config(project_root: Path) -> dict:
    config_path = project_root / ".mimir" / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def load_indexed_files(
    project_root: Path,
    knowledge_dir: Optional[Path] = None,
) -> list[Path]:
    if knowledge_dir is None:
        knowledge_dir = project_root / ".knowledge" / "llamaindex"
    manifest_path = knowledge_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    supported = set(EXTENSION_TO_LANGUAGE.keys())
    files: list[Path] = []
    for _, info in manifest.get("indexed_directories", {}).items():
        for file_path_str in info.get("files", []):
            path = Path(file_path_str)
            if not path.is_absolute():
                path = project_root / path
            if path.suffix.lower() in supported:
                files.append(path)
    return files


# ---------------------------------------------------------------------------
# Incremental graph update
# ---------------------------------------------------------------------------


def incremental_graph_update(
    project_root: Path,
    changed_files: dict[str, list[str]],
    output_dir: Optional[Path] = None,
) -> tuple[int, int, int]:
    """
    Apply incremental changes to the existing knowledge graph without a full rebuild.

    Parameters
    ----------
    project_root : Path
        Root of the project.
    changed_files : dict
        Keys are change types: ``"added"``, ``"modified"``, ``"deleted"``.
        Values are lists of file paths (relative or absolute).
        Example::

            {
                "added":    ["src/new_module.py"],
                "modified": ["src/existing.py"],
                "deleted":  ["src/old_module.py"],
            }

    output_dir : Path, optional
        Directory containing ``code_relationships.json``.
        Defaults to ``project_root/.knowledge``.

    Returns
    -------
    tuple of (added_count, removed_count, modified_count)
        ``added_count``    – net new entities added
        ``removed_count``  – entities removed (deleted + old versions of modified)
        ``modified_count`` – relationships changed (re-extracted for modified files)
    """
    project_root = Path(project_root)
    if output_dir is None:
        output_dir = project_root / ".knowledge"
    graph_path = output_dir / "code_relationships.json"

    # ── Load existing graph ────────────────────────────────────────────────
    existing_entities: dict[str, dict] = {}
    existing_relationships: list[dict] = []

    if graph_path.exists():
        try:
            with open(graph_path) as f:
                data = json.load(f)
            existing_entities = data.get("entities", {})
            existing_relationships = data.get("relationships", [])
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [WARN] Could not load existing graph: {exc}. Starting fresh.")

    # ── Normalise file paths to relative strings ───────────────────────────
    def _to_rel(fp: str) -> str:
        p = Path(fp)
        if p.is_absolute():
            try:
                return str(p.relative_to(project_root))
            except ValueError:
                return str(p)
        return str(p)

    deleted_files: set[str] = {_to_rel(f) for f in changed_files.get("deleted", [])}
    modified_files: set[str] = {_to_rel(f) for f in changed_files.get("modified", [])}
    added_files: list[str] = [_to_rel(f) for f in changed_files.get("added", [])]

    # Files whose old data must be purged (deleted + modified old versions)
    files_to_purge: set[str] = deleted_files | modified_files

    # ── Remove entities/relationships for purged files ─────────────────────
    removed_entity_keys: set[str] = {
        key
        for key, ent in existing_entities.items()
        if ent.get("file_path") in files_to_purge
    }
    removed_count = len(removed_entity_keys)

    surviving_entities: dict[str, dict] = {
        k: v for k, v in existing_entities.items() if k not in removed_entity_keys
    }
    surviving_relationships: list[dict] = [
        r for r in existing_relationships if r.get("source") not in files_to_purge
    ]

    # ── Re-extract modified + added files ─────────────────────────────────
    files_to_extract: list[str] = list(modified_files) + added_files
    added_count = 0
    modified_rel_count = 0

    if files_to_extract:
        extractor = _make_extractor(project_root)

        for rel_path_str in files_to_extract:
            abs_path = project_root / rel_path_str
            if not abs_path.exists():
                print(f"  [WARN] File not found, skipping: {abs_path}")
                continue

            lang = EXTENSION_TO_LANGUAGE.get(abs_path.suffix.lower())
            if lang is None:
                print(f"  [SKIP] Unsupported extension: {rel_path_str}")
                continue

            tag = "PY " if lang == "python" else lang.upper()[:3]
            print(f"  [{tag}] {rel_path_str}")

            new_rels = extractor.extract_from_file(abs_path)

            # Collect new entities from the extractor (populated as side-effect)
            new_entity_keys = {
                k
                for k, ent in extractor.entities.items()
                if ent.file_path == rel_path_str
            }
            for key in new_entity_keys:
                surviving_entities[key] = asdict(extractor.entities[key])
                added_count += 1

            # Merge new relationships
            new_rel_dicts = [r.to_dict() for r in new_rels]
            surviving_relationships.extend(new_rel_dicts)
            modified_rel_count += len(new_rel_dicts)

    # ── Build final graph data ─────────────────────────────────────────────
    final_data = {
        "relationships": surviving_relationships,
        "entities": surviving_entities,
    }

    # ── Atomic write via temp file + rename ───────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(output_dir), prefix=".code_relationships_", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(final_data, f, indent=2)
        os.rename(tmp_path, str(graph_path))
    except Exception:
        # Clean up temp file on failure
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    print(
        f"\n✅ Knowledge graph updated: "
        f"+{added_count} entities, -{removed_count} entities, "
        f"~{modified_rel_count} relationships changed"
    )
    return added_count, removed_count, modified_rel_count


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Extract code relationships from a project.\n"
            "Uses Python AST for .py and tree-sitter for TS/JS/Rust/Go.\n\n"
            "  pip install tree-sitter-languages   # optional multi-lang support"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--dirs",
        type=str,
        default=None,
        help="Comma-separated list of sub-directories to scan (default: src)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for code_relationships.json",
    )
    parser.add_argument(
        "--from-index",
        action="store_true",
        dest="from_index",
        help="Use files listed in the Mimir index manifest",
    )
    parser.add_argument(
        "--incremental",
        type=str,
        default=None,
        metavar="JSON",
        help=(
            "JSON object of changed files, e.g. "
            '\'{"added":["src/new.py"],"modified":["src/x.py"],"deleted":["src/old.py"]}\''
        ),
    )
    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.is_dir():
        print(f"❌  Not a directory: {project_root}")
        raise SystemExit(1)

    project_config = load_project_config(project_root)

    if args.incremental is not None:
        try:
            changed_files = json.loads(args.incremental)
        except json.JSONDecodeError as exc:
            print(f"❌  Invalid JSON for --incremental: {exc}")
            raise SystemExit(1) from exc
        if not isinstance(changed_files, dict):
            print("❌  --incremental must be a JSON object")
            raise SystemExit(1)
        incremental_graph_update(project_root, changed_files, args.output)
    elif args.from_index:
        extract_code_relationships(project_root, args.output, from_index=True)
    else:
        if args.dirs:
            code_dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
        elif "code_dirs" in project_config:
            code_dirs = project_config["code_dirs"]
        else:
            code_dirs = ["src"]
        extract_code_relationships(project_root, args.output, code_dirs=code_dirs)
