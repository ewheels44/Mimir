# MIMIR RULES (5 ONLY)

> **Canonical source**: `~/.config/opencode/prompts/system-context.md` (installed globally)
> This file is a reference copy. Run `scripts/install.sh` to install the rules globally.

## 1. MIMIR FIRST
Before any task, call `mimir-knowledge_enrich_task()`. This is my memory — without it I'm guessing. No exceptions.

## 2. CONTEXT BEFORE CODE
Before writing/editing:
- Code → read `~/.config/opencode/context/core/standards/code-quality.md`
- Docs → read `~/.config/opencode/context/core/standards/documentation.md`
- Tests → read `~/.config/opencode/context/core/standards/test-coverage.md`
- Review → read `~/.config/opencode/context/core/workflows/code-review.md`
- Delegation → read `~/.config/opencode/context/core/workflows/task-delegation-basics.md`

If it's bash-only, skip this.

## 3. ASK FIRST
Never run bash/write/edit/task without showing a plan and getting approval. Read/list/glob/grep are fine without asking.

## 4. CHECK SKILLS
Before executing, check if the task matches an available skill. If yes, load it with `skill()`. If no match, proceed with tools directly.

## 5. GRAPH FIRST
For structural questions ("how does X connect to Y?", "what calls this?", "what does this import?"), use `graph_query` or `graph_neighbors` before reading files. The graph has weighted Dijkstra path-finding — it finds the strongest coupling path, not just the shortest.

- "How does auth reach the database?" → `graph_query(source="auth", target="database")`
- "What depends on this module?" → `graph_neighbors(node_id="module", depth=2)`
- "What are the most connected files?" → `graph_stats()`

Use semantic search (`enrich_task`, `search`) for meaning-based questions. Use graph tools for topology-based questions.
