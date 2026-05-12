---
name: mimir-dev
description: Guide agents when developing Mimir itself, enforcing recursive knowledge base usage. This skill ensures the dogfooding pattern is followed - using Mimir to build Mimir.
---

# Mimir Development Skill

> **Purpose**: Enforce recursive knowledge base usage when developing Mimir itself.

## When to use

- **Any Mimir development task** — this skill is mandatory
- **Before implementing new features** — query Mimir first
- **After failures** — check if Mimir has the missing context
- **When unsure about patterns** — search before assuming

## When NOT to use

- Working on a different project (not Mimir)
- Purely generic tasks unrelated to Mimir's codebase

## Mandatory Pre-Flight Checklist

Before ANY code change to Mimir:

- [ ] Query `mimir-knowledge_enrich_task(task)` with the task description
- [ ] Search `mimir-knowledge_search(query)` for existing patterns
- [ ] Check `mimir-knowledge_sdk_cache_get(library, topic)` for external library questions
- [ ] Validate assumptions against indexed reality

## Why This Matters

Mimir is the validation layer for AI actions. If we don't use it to build itself, we're not testing the core loop.

**The Recursive Pattern:**
```
Task arrives → Query Mimir first
     ↓
Mimir returns context → Validate against code
     ↓
Implement → Index new patterns
     ↓
Next task benefits from richer knowledge
```

## Workflow

```
Mimir dev task received
     │
     ▼
Load this skill (mimir-dev)
     │
     ▼
Run pre-flight checklist:
  1. enrich_task(task)
  2. search("relevant patterns")
  3. sdk_cache_get(if external libs)
     │
     ├── no results → Proceed with caution, document gap
     │
     ▼
Validate returned context against actual code
     │
     ▼
Implement following discovered patterns
     │
     ▼
After success:
  └── Index new patterns (python mimir.py index)
  └── Document any gaps found
```

## Common Mistakes to Avoid

- ❌ Skipping Mimir queries because "I know the codebase"
- ❌ Using grep/read when Mimir search would be faster
- ❌ Assuming patterns without validating against indexed reality
- ❌ Not indexing new patterns after implementation
- ❌ Ignoring stale freshness tags — verify old patterns

## Success Criteria

- Every Mimir task starts with Mimir queries
- Failed queries reveal documentation gaps → fix them
- New patterns are indexed immediately after implementation
- Context from Mimir is validated against actual code

## Examples

### Example 1: Adding a new MCP tool

```
# WRONG:
→ Read existing tools
→ Implement new tool
→ Test

# RIGHT:
→ enrich_task("Add MCP tool for X")
→ search("MCP tool patterns")
→ Validate returned patterns against code
→ Implement following discovered patterns
→ Index new tool pattern
```

### Example 2: After a failure

```
# Generic approach failed
→ enrich_task("How does the knowledge agent workflow work?")
→ Found: knowledge_agent.py with detailed workflow
→ Found: workflow_analysis.md with performance notes
→ Retry with correct understanding
```

## Notes

- This skill is specific to Mimir development
- The recursive pattern validates Mimir's knowledge graph in real-time
- Every failed query is a documentation opportunity
- Freshness matters — verify stale patterns before relying on them
