"""AST-aware code chunking for Mimir.

Provides syntax-aware chunking that splits code at logical boundaries
(functions, classes, methods) rather than arbitrary token limits.

Two strategies:
  - PythonASTChunker: Uses Python's ast module for .py files
  - TreeSitterChunker: Uses tree-sitter for .ts/.js/.rs/.go files
  - IntelligentChunker: Routes to appropriate chunker based on file type
"""

import ast
import hashlib
import re
from pathlib import Path
from typing import Optional

from mimir.utils import should_exclude as _should_exclude


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CHUNK_SIZE = 1500  # tokens (approximate)
MIN_CHUNK_SIZE = 100   # tokens (approximate)

# Rough tokens per character (for estimation)
CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Python AST Chunker
# ---------------------------------------------------------------------------

class PythonASTChunker:
    """Chunk Python files using AST to preserve function/class boundaries."""

    def __init__(self, max_chunk_size: int = MAX_CHUNK_SIZE):
        self.max_chunk_size = max_chunk_size

    def chunk_file(self, file_path: Path) -> list[dict]:
        """Chunk a Python file into logical pieces.

        Returns list of dicts with keys:
          - content: str (code chunk)
          - start_line: int
          - end_line: int
          - type: str (module/function/class/method)
          - name: str (function/class name)
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except Exception:
            return [{"content": "", "start_line": 0, "end_line": 0, "type": "error", "name": "error"}]

        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Fallback: return whole file as one chunk
            return [{
                "content": source,
                "start_line": 1,
                "end_line": len(source.splitlines()),
                "type": "module",
                "name": file_path.stem,
            }]

        chunks = []
        lines = source.splitlines(keepends=True)

        # Process top-level items
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_function_chunk(node, lines, file_path)
                if chunk:
                    chunks.append(chunk)
            elif isinstance(node, ast.ClassDef):
                class_chunks = self._extract_class_chunks(node, lines, file_path)
                chunks.extend(class_chunks)
            elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.Expr)):
                # Module-level statements - collect into module chunk
                pass  # Handle below

        # If no structured chunks, return whole module
        if not chunks:
            return [{
                "content": source,
                "start_line": 1,
                "end_line": len(lines),
                "type": "module",
                "name": file_path.stem,
            }]

        return chunks

    def _extract_function_chunk(self, node, lines, file_path) -> Optional[dict]:
        """Extract a function/method as a chunk."""
        start = node.lineno - 1  # 0-based
        end = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
        content = "".join(lines[start:end])

        # Check size - if too large, try to split
        if len(content) > self.max_chunk_size * CHARS_PER_TOKEN:
            # For now, keep as-is (future: split by logic blocks)
            pass

        return {
            "content": content,
            "start_line": node.lineno,
            "end_line": end,
            "type": "function",
            "name": node.name,
        }

    def _extract_class_chunks(self, node, lines, file_path) -> list[dict]:
        """Extract class with methods as separate chunks."""
        chunks = []
        class_start = node.lineno - 1
        class_end = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno

        # Class definition as a chunk (includes decorators, docstring)
        class_header = "".join(lines[class_start:class_start + 10])  # First ~10 lines
        chunks.append({
            "content": class_header,
            "start_line": node.lineno,
            "end_line": min(node.lineno + 10, class_end),
            "type": "class",
            "name": node.name,
        })

        # Each method as separate chunk
        for item in ast.iter_child_nodes(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_function_chunk(item, lines, file_path)
                if chunk:
                    chunk["type"] = "method"
                    chunks.append(chunk)

        return chunks


# ---------------------------------------------------------------------------
# TreeSitter Chunker (for TypeScript, JavaScript, Rust, Go)
# ---------------------------------------------------------------------------

class TreeSitterChunker:
    """Chunk code files using tree-sitter for syntax-aware splitting."""

    def __init__(self, max_chunk_size: int = MAX_CHUNK_SIZE):
        self.max_chunk_size = max_chunk_size
        self._parser = None
        self._language = None

    def _get_parser(self, language: str):
        """Lazy-load tree-sitter parser."""
        if self._parser is not None:
            return self._parser

        try:
            from tree_sitter_languages import get_language, get_parser

            lang_map = {
                "typescript": "typescript",
                "tsx": "tsx",
                "javascript": "javascript",
                "jsx": "jsx",
                "rust": "rust",
                "go": "go",
            }

            ts_lang = lang_map.get(language)
            if not ts_lang:
                return None

            self._parser = get_parser(ts_lang)
            return self._parser
        except ImportError:
            return None

    def chunk_file(self, file_path: Path) -> list[dict]:
        """Chunk a file using tree-sitter."""
        suffix = file_path.suffix.lstrip(".")
        parser = self._get_parser(suffix)
        if parser is None:
            # Fallback: whole file
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                return [{
                    "content": content,
                    "start_line": 1,
                    "end_line": len(content.splitlines()),
                    "type": "module",
                    "name": file_path.stem,
                }]
            except Exception:
                return []

        try:
            with open(file_path, "rb") as f:
                source_bytes = f.read()
            tree = parser.parse(source_bytes)
            lines = source_bytes.decode("utf-8", errors="ignore").splitlines(keepends=True)
        except Exception:
            return []

        chunks = []
        root = tree.root_node

        # Extract functions and classes
        for child in root.children:
            if child.type in ("function_definition", "method_definition"):
                chunk = self._extract_node_chunk(child, lines, file_path, "function")
                if chunk:
                    chunks.append(chunk)
            elif child.type == "struct_definition":
                chunk = self._extract_node_chunk(child, lines, file_path, "class")
                if chunk:
                    chunks.append(chunk)
            elif child.type in ("impl_item", "trait_item"):
                # Rust impl blocks
                for subchild in child.children:
                    if subchild.type == "function_item":
                        chunk = self._extract_node_chunk(subchild, lines, file_path, "method")
                        if chunk:
                            chunks.append(chunk)

        if not chunks:
            # Return whole file
            content = source_bytes.decode("utf-8", errors="ignore")
            return [{
                "content": content,
                "start_line": 1,
                "end_line": len(lines),
                "type": "module",
                "name": file_path.stem,
            }]

        return chunks

    def _extract_node_chunk(self, node, lines, file_path, chunk_type) -> Optional[dict]:
        """Extract a node as a chunk."""
        start = node.start_point[0]
        end = node.end_point[0] + 1
        content = "".join(lines[start:end])

        # Try to get name
        name = file_path.stem
        for child in node.children:
            if child.type == "identifier":
                name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="ignore")
                break

        return {
            "content": content,
            "start_line": start + 1,
            "end_line": end,
            "type": chunk_type,
            "name": name,
        }


# ---------------------------------------------------------------------------
# Intelligent Chunker (routes to appropriate chunker)
# ---------------------------------------------------------------------------

class IntelligentChunker:
    """Routes to appropriate chunker based on file type."""

    def __init__(self, max_chunk_size: int = MAX_CHUNK_SIZE):
        self.max_chunk_size = max_chunk_size
        self._python_chunker = None
        self._treesitter_chunker = None

        self.extension_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".jsx": "jsx",
            ".rs": "rust",
            ".go": "go",
        }

    def chunk_file(self, file_path: Path) -> list[dict]:
        """Chunk a file using the appropriate strategy."""
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            if self._python_chunker is None:
                self._python_chunker = PythonASTChunker(self.max_chunk_size)
            return self._python_chunker.chunk_file(file_path)

        if suffix in (".ts", ".tsx", ".js", ".jsx", ".rs", ".go"):
            if self._treesitter_chunker is None:
                self._treesitter_chunker = TreeSitterChunker(self.max_chunk_size)
            return self._treesitter_chunker.chunk_file(file_path)

        # Fallback: treat as plain text
        return self._chunk_plain_text(file_path)

    def _chunk_plain_text(self, file_path: Path) -> list[dict]:
        """Fallback chunking for plain text / markdown."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return []

        # Simple split by size
        if len(content) <= self.max_chunk_size * CHARS_PER_TOKEN:
            return [{
                "content": content,
                "start_line": 1,
                "end_line": len(content.splitlines()),
                "type": "text",
                "name": file_path.stem,
            }]

        # Split into overlapping chunks
        chunks = []
        lines = content.splitlines(keepends=True)
        current_chunk = []
        current_size = 0
        start_line = 1

        for i, line in enumerate(lines):
            line_size = len(line)
            if current_size + line_size > self.max_chunk_size * CHARS_PER_TOKEN and current_chunk:
                chunks.append({
                    "content": "".join(current_chunk),
                    "start_line": start_line,
                    "end_line": i,
                    "type": "text",
                    "name": f"{file_path.stem}_part{len(chunks) + 1}",
                })
                current_chunk = [line]
                current_size = line_size
                start_line = i + 1
            else:
                current_chunk.append(line)
                current_size += line_size

        if current_chunk:
            chunks.append({
                "content": "".join(current_chunk),
                "start_line": start_line,
                "end_line": len(lines),
                "type": "text",
                "name": f"{file_path.stem}_part{len(chunks) + 1}",
            })

        return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_code_file(file_path: Path, max_chunk_size: int = MAX_CHUNK_SIZE) -> list[dict]:
    """Chunk a code file using AST-aware strategies.

    Args:
        file_path: Path to the code file
        max_chunk_size: Maximum chunk size in tokens

    Returns:
        List of chunk dicts with content, line numbers, and metadata
    """
    chunker = IntelligentChunker(max_chunk_size)
    return chunker.chunk_file(file_path)


def get_file_hash(content: str) -> str:
    """Get SHA-256 hash of file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
