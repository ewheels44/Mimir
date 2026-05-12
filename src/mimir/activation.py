#!/usr/bin/env python3
"""
Smart Activation Logic for Mimir

Determines when Mimir should be used for a given task.
Implements a lightweight classifier that avoids expensive LLM calls for obvious cases.

Usage:
    from mimir.activation import should_use_mimir

    if should_use_mimir(task_description, project_root):
        # Call enrich_task(), search(), etc.
        pass
"""

import re
from pathlib import Path
from typing import Optional

# ─── Obvious non-code tasks (skip Mimir) ────────────────────────────

NON_CODE_PATTERNS = [
    # Shell/git operations (only match when it's JUST a shell command)
    r'^\s*(git\s+(status|log|diff|show|clone|pull|push|fetch|branch|checkout|stash|tag))\b',
    r'^\s*(cd|ls|pwd|mkdir|rm|cp|mv|chmod|chown)\s+',
    # Documentation-only edits
    r'^\s*edit\s+.*\b(readme|license|changelog|contributing)\b',
    # Non-project questions
    r'\b(weather|time|date|news|joke|story)\b',
    # Simple file operations without code context
    r'^\s*(open|view|cat|less)\s+[^/]*\.(txt|md|json|yml|yaml)$',
]

# ─── Code-related keywords (use Mimir) ──────────────────────────────────

CODE_KEYWORDS = [
    # Code elements
    'function', 'class', 'method', 'module', 'import', 'export', 'interface',
    'struct', 'enum', 'trait', 'type', 'variable', 'constant',
    'prototype', 'object', 'component', 'hook', 'middleware', 'handler',
    'route', 'endpoint', 'service', 'model', 'view', 'controller',

    # Actions (editing/updating)
    'update', 'modify', 'change', 'edit', 'patch', 'alter',
    'add', 'remove', 'delete', 'refactor', 'improve', 'migrate',
    'rename', 'move', 'extract', 'inline', 'optimize',

    # Bug/feature/issue work
    'bug', 'feature', 'issue', 'problem', 'error', 'crash', 'fix',
    'implement', 'build', 'create', 'develop', 'enhance', 'extend',
    'add support', 'integrate', 'launch', 'release',

    # Impact analysis
    'impact', 'affect', 'break', 'depends', 'require', 'relation',
    'side effect', 'consequence', 'ripple', 'cascade', 'regression',

    # Dependency analysis
    'dependency', 'call', 'invoke', 'return', 'throw', 'catch',
    'imports', 'uses', 'requires', 'references', 'links to',
    'coupled', 'tightly', 'loosely', 'depends on',

    # Questions about code
    'how does', 'why does', 'where is', 'what is', 'find', 'search',
    'trace', 'debug', 'understand', 'explain', 'analyze', 'investigate',
    'why is', 'how is', 'what does', 'where does', 'who calls',

    # Architecture/design
    'architecture', 'pattern', 'design', 'flow', 'diagram',
    'connect', 'relate', 'depend', 'structure', 'layering',
    'hierarchy', 'coupling', 'cohesion', 'abstraction',

    # Code review/quality
    'review', 'smell', 'clean', 'best practice', 'convention',
    'standard', 'style', 'lint', 'format', 'consistency',
    'readable', 'maintainable', 'technical debt',

    # Testing
    'test', 'tests', 'spec', 'mock', 'stub', 'assert', 'expect',
    'coverage', 'unit test', 'integration', 'e2e', 'regression',

    # Documentation
    'doc', 'documentation', 'comment', 'readme', 'changelog',
    'api doc', 'jsdoc', 'typedoc', 'swagger', 'openapi',

    # Performance
    'performance', 'slow', 'fast', 'optimize', 'bottleneck',
    'memory', 'cpu', 'latency', 'throughput', 'cache', 'lazy',
    'profiling', 'benchmark',

    # Security
    'security', 'vulnerability', 'auth', 'permission', 'role',
    'injection', 'csrf', 'xss', 'encrypt', 'hash', 'token',
    'authentication', 'authorization', 'cors', 'sanitize',

    # Search/discovery
    'find', 'search', 'locate', 'lookup', 'snippet', 'example',
    'usage', 'sample', 'similar', 'match', 'discover',

    # Workflow/process
    'deploy', 'build', 'compile', 'run', 'start', 'stop',
    'configure', 'config', 'setup', 'init', 'install', 'uninstall',
]

# ─── Project-specific triggers ────────────────────────────────────────

PROJECT_TRIGGERS = [
    'test', 'tests', 'spec', 'mock', 'stub',
    'config', 'configure', 'setup', 'init',
    'build', 'compile', 'deploy', 'run',
    'doc', 'documentation', 'comment',
]


def _match_patterns(text: str, patterns: list[str]) -> bool:
    """Check if text matches any pattern."""
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in patterns)


def _count_keywords(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in text."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def should_use_mimir(
    task: str,
    project_root: Optional[Path] = None,
    check_index: bool = True,
) -> dict:
    """
    Determine if Mimir should be used for a task.

    Args:
        task: Task description
        project_root: Project root directory (auto-detected if None)
        check_index: Whether to verify .knowledge/llamaindex/ exists

    Returns:
        dict with keys:
        - should_use: bool
        - reason: str (explanation)
        - confidence: float (0.0 to 1.0)
    """
    # Check if Mimir is set up for this project
    if check_index:
        if project_root is None:
            from .config import get_config
            project_root = get_config().project_root

        knowledge_dir = project_root / ".knowledge" / "llamaindex"
        if not knowledge_dir.exists():
            return {
                "should_use": False,
                "reason": f"No Mimir index found at {knowledge_dir}",
                "confidence": 1.0,
            }

    # Check obvious non-code patterns
    if _match_patterns(task, NON_CODE_PATTERNS):
        return {
            "should_use": False,
            "reason": "Task appears to be non-code (shell ops, docs, etc.)",
            "confidence": 0.9,
        }

    # Count code-related keywords
    code_score = _count_keywords(task, CODE_KEYWORDS)
    project_score = _count_keywords(task, PROJECT_TRIGGERS)

    total_score = code_score + project_score

    if total_score == 0:
        # No obvious code keywords - might still be relevant (e.g., "fix it")
        return {
            "should_use": True,  # Default to using Mimir for ambiguous cases
            "reason": "No clear indicators, defaulting to using Mimir",
            "confidence": 0.5,
        }

    if total_score >= 2:
        return {
            "should_use": True,
            "reason": f"Task has {total_score} code-related indicators",
            "confidence": min(0.5 + (total_score * 0.1), 1.0),
        }

    return {
        "should_use": True,
        "reason": "Task has some code-related keywords",
        "confidence": 0.6,
    }


def should_skip_mimir(task: str) -> bool:
    """
    Quick check for obvious cases where Mimir should NOT be used.
    Returns True if task should definitely skip Mimir.
    """
    return _match_patterns(task, NON_CODE_PATTERNS)


# ─── Enhanced enrich_task with gating ─────────────────────────────────

def enrich_task_with_gating(
    task: str,
    project_root: Optional[Path] = None,
    top_k: int = 5,
) -> dict:
    """
    Wrapper around enrich_task that gates on should_use_mimir().

    Returns early with empty results if Mimir shouldn't be used.
    """
    from .openspace_bridge import enrich_task_for_openspace

    # Quick gate check
    activation = should_use_mimir(task, project_root, check_index=True)

    if not activation["should_use"]:
        return {
            "success": True,
            "result_count": 0,
            "results": [],
            "should_use_mimir": False,
            "reason": activation["reason"],
            "confidence": activation["confidence"],
            "status": "skipped",
            "skipped_reason": activation["reason"],
        }

    # Proceed with normal enrich_task
    # Note: enrich_task_for_openspace doesn't support top_k parameter
    result = enrich_task_for_openspace(task, project_root)
    result["should_use_mimir"] = True
    result["activation_reason"] = activation["reason"]
    result["activation_confidence"] = activation["confidence"]

    return result
