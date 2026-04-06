---
name: mimir-knowledge
description: Search the project's Mimir knowledge base before executing tasks. Mimir provides semantic search over project docs and code, giving you project-specific context (conventions, APIs, patterns) that generic skills lack. Use this to avoid reasoning from scratch and burning tokens.
---

# Mimir Knowledge Base

Mimir is a semantic knowledge base indexed from this project's documentation and source code. It gives you project-specific context that generic skills don't have.

## When to use

- **Before any task** — search Mimir first to understand project conventions, APIs, and patterns
- **When you're unsure** — if the task mentions project-specific files, functions, or concepts
- **After a failure** — your generic approach failed; Mimir may have the missing context
- **Complex tasks** — multi-file changes, architecture decisions, integration work

## When NOT to use

- Purely generic tasks (rename a variable, fix a typo)
- When you already have the exact file path and know what to do
- When Mimir's `openspace_health` tool reports `has_index: false`

## Tools

### enrich_task

Search Mimir for project context relevant to your task. Call this BEFORE executing.

```
enrich_task(task="Build authentication middleware for the FastAPI router")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `task` | yes | — | Your task description (natural language) |
| `top_k` | no | `5` | Number of context chunks to retrieve |

**Response:**
```json
{
  "success": true,
  "context": "[src/auth.py (fresh, score=0.89)]\ndef verify_token(...)\n\n[docs/api.md (recent, score=0.72)]\n## Authentication\n...",
  "result_count": 3,
  "cache_hit": false,
  "elapsed_ms": 245
}
```

**How to use the context:**
1. Call `enrich_task` with your task description
2. If `success: true` and `result_count > 0`, inject `context` into your prompt
3. Use the context to understand project patterns, avoid mistakes, and follow conventions
4. If `success: false` or `result_count: 0`, proceed without project context

**Freshness tags:**
- `fresh` — indexed recently, high confidence
- `recent` — indexed this week, likely accurate
- `stale` — older index, verify before relying on it

### openspace_health

Check if Mimir is available before depending on it.

```
openspace_health()
```

**Response:**
```json
{
  "enabled": true,
  "circuit_open": false,
  "has_index": true,
  "index_timestamp": "2026-04-05T10:30:00",
  "cache_size": 12
}
```

**Decision logic:**
- `enabled: false` → Mimir is disabled, skip all searches
- `circuit_open: true` → Mimir is failing, skip and retry later
- `has_index: false` → No knowledge base exists, skip
- All clear → Use `enrich_task` freely

## Workflow

```
Task received
    │
    ▼
Call openspace_health()
    │
    ├── disabled/error → Skip Mimir, execute with generic skills
    │
    ▼
Call enrich_task(task)
    │
    ├── no results → Execute with generic skills
    │
    ▼
Inject context into skill prompt
    │
    ▼
Execute task with project-aware context
    │
    ▼
If execution fails:
    └── Try enrich_task with rephrased query
    └── Check if context was stale (verify patterns)
```

## Examples

### Example 1: Before building a feature

```
enrich_task(task="Add rate limiting to API endpoints")

# Result: Found auth middleware patterns, existing middleware stack,
#         and rate limiting config in docs/architecture.md

# Now execute with context:
# "This project uses Starlette middleware stack. Rate limiting
#  should be added as a new middleware class following the pattern
#  in src/middleware/auth.py..."
```

### Example 2: After a failure

```
# Generic approach failed — couldn't find the right import path
enrich_task(task="import database connection pool")

# Result: Found src/db/pool.py with the actual connection pool class
#         and docs/setup.md with environment variable names

# Retry with correct imports and config
```

### Example 3: Health check before batch tasks

```
openspace_health()
# If healthy, batch-enrich multiple tasks
enrich_task(task="task 1")
enrich_task(task="task 2")
# If unhealthy, skip enrichment for all tasks
```

## Notes

- Mimir searches are cached for 10 minutes — repeated queries are instant
- A circuit breaker stops calls after 3 consecutive failures (auto-resets after 60s)
- Sensitive content (API keys, internal URLs) is automatically redacted
- The bridge has a kill switch: set `MIMIR_OPENSPACE_ENABLED=false` to disable
- Context is capped at ~2500 tokens to avoid bloating your context window
