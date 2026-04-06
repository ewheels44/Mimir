---
name: unified-query
description: Single entry point for answering questions about SDKs, libraries, and project patterns. Automatically searches OpenSpace evolved skills, cached SDK docs, and Mimir knowledge base — then synthesizes the best answer. Use this instead of manually calling individual tools.
---

# Unified Query

One question hits all knowledge layers automatically. No need to know which tool to call.

## When to use

- **Any SDK/library question** — "How do I use Stripe checkout?"
- **Project pattern questions** — "How do we handle auth in this codebase?"
- **Integration questions** — "How do I add Redis to this app?"
- **Onboarding new developers** — "What's our API structure?"

## When NOT to use

- Simple file lookups (you know the exact path)
- Generic programming questions (no project/SDK context needed)
- Tasks that need code generation (use OpenCoder agent instead)

## How it works

```
Your question
    │
    ▼
Layer 1: OpenSpace Skills ─── "Do I already know the answer?"
    │
    ▼
Layer 2: SDK Doc Cache ────── "Do I have fresh docs for this?"
    │
    ▼
Layer 3: Mimir Knowledge ──── "What does the project codebase say?"
    │
    ▼
Layer 4: Synthesize ───────── Combine all sources into one answer
    │
    ▼
After execution: OpenSpace learns from the result
```

## Tools

### Step 1: Check OpenSpace for evolved skills

```
openspace_search_skills(query="<your question>", source="local", limit=3)
```

If a relevant skill exists with high confidence → use it directly, skip to Step 4.

### Step 2: Check SDK doc cache

Look for cached documentation:

```bash
ls .knowledge/sdk-cache/<library-name>/ 2>/dev/null
```

If cache exists and is fresh (< 7 days) → use it.
If stale or missing → fetch via ExternalScout and cache.

### Step 3: Search Mimir project knowledge

```
mimir-knowledge_enrich_task(task="<your question>", top_k=5)
```

This finds how YOUR project already uses the SDK/library.

### Step 4: Synthesize answer

Combine all sources:
- **OpenSpace skill**: Proven patterns from past tasks
- **SDK cache**: Current API reference
- **Mimir**: Your project's existing patterns

Present answer with source attribution so the user knows where each piece came from.

## SDK Doc Caching

When ExternalScout fetches docs for a library, cache them locally:

```
.knowledge/sdk-cache/
├── <library-name>/
│   ├── api-reference.md
│   ├── examples.md
│   └── meta.json          # { "fetched_at": "ISO", "version": "x.y.z", "ttl_days": 7 }
```

### Cache check logic

```python
import json
from pathlib import Path
from datetime import datetime, timedelta

def is_cache_fresh(cache_dir: Path, library: str) -> bool:
    meta = cache_dir / library / "meta.json"
    if not meta.exists():
        return False
    data = json.loads(meta.read_text())
    fetched = datetime.fromisoformat(data["fetched_at"])
    ttl = timedelta(days=data.get("ttl_days", 7))
    return datetime.now() - fetched < ttl
```

### Cache write

After ExternalScout returns docs:
1. Create `.knowledge/sdk-cache/<library>/`
2. Write `api-reference.md` with the fetched content
3. Write `meta.json` with timestamp and TTL

## Examples

### Example 1: SDK question (new developer)

```
Q: "How do I create a Stripe checkout session in this app?"

Layer 1 (OpenSpace): No Stripe skill yet → skip
Layer 2 (Cache): No cached Stripe docs → ExternalScout fetches → cache
Layer 3 (Mimir): Finds src/payments/stripe.ts with existing checkout code
Layer 4 (Synthesize):
  "This project uses Stripe v14. Here's how checkout sessions are created:
   [existing code from Mimir]
   The Stripe API reference for createCheckoutSession:
   [cached API docs]
   Recommended pattern based on project conventions:
   [synthesized guidance]"
```

### Example 2: Project pattern question

```
Q: "How do we handle API errors in this codebase?"

Layer 1 (OpenSpace): No error-handling skill → skip
Layer 2 (Cache): N/A (not an SDK question)
Layer 3 (Mimir): Finds error handling patterns across 8 files
Layer 4 (Synthesize):
  "This project uses a centralized error handler:
   [pattern from Mimir with file references]
   All API routes follow this pattern:
   [code examples]"
```

### Example 3: Repeat question (system has learned)

```
Q: "How do I add a new Stripe webhook handler?"

Layer 1 (OpenSpace): FINDS 'stripe-webhook-handler' skill (evolved from previous task)
Layer 2 (Cache): Stripe docs cached and fresh
Layer 3 (Mimir): Finds existing webhook handlers
Layer 4 (Synthesize):
  "Based on evolved skill + project patterns + current docs:
   [precise, project-specific answer]"
```

## Integration with task execution

When the unified query is used as part of a coding task:

1. **Before coding**: Run unified query to gather context
2. **During coding**: Use gathered context to write project-matching code
3. **After coding**: OpenSpace captures the pattern as a new skill

This creates a virtuous cycle:
```
Day 1:  No knowledge → fetch docs + search codebase → implement → learn
Day 7:  Some knowledge → use cached docs + evolved skill → implement faster
Day 30: Rich knowledge → skill handles most of it → near-instant answers
```

## Notes

- SDK cache TTL is 7 days by default (configurable in meta.json)
- Mimir searches are cached for 10 minutes by the MCP bridge
- OpenSpace skill search includes both local and cloud (if API key set)
- The synthesis step uses the agent's LLM — no extra API calls needed
- All sources are attributed so users can verify and dig deeper
