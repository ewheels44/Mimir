# Mimir Knowledge Base

Deep project knowledge tools for Jcode agents.

## Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `mimir-knowledge_search` | Semantic search across indexed code/docs | Finding patterns, examples, API usage |
| `mimir-knowledge_query` | Synthesized RAG answers | "How does X work?" questions |
| `mimir-knowledge_enrich_task` | Pre-task context injection | **Always** before starting a task |
| `mimir-knowledge_graph_query` | Shortest path between modules (Dijkstra) | "How does X reach Y?" |
| `mimir-knowledge_graph_neighbors` | BFS neighbors of a module | Exploring dependencies |
| `mimir-knowledge_sdk_cache_get` | Cached SDK docs (7-day TTL) | Before hitting the web for lib docs |
| `mimir-knowledge_sdk_cache_list` | List cached libraries | Checking available docs |
| `mimir-knowledge_rag_workflow` | Structured retrieve→generate | Complex multi-hop analysis |
| `mimir-knowledge_knowledge_agent` | Agentic deep research | Multi-step exploration tasks |

## Decision Flow

```
Starting a task?
  → mimir-knowledge_enrich_task(description) FIRST

Need to understand code?
  → mimir-knowledge_query(question)

Looking for a pattern?
  → mimir-knowledge_search(query)

Tracing dependencies?
  → mimir-knowledge_graph_query(source, target)
  → mimir-knowledge_graph_neighbors(module)

External library docs?
  → mimir-knowledge_sdk_cache_get(library, topic)
  → ExternalScout (if not cached)
```

## Setup

Run during project init:
```bash
python ~/Documents/Mimir/mimir-init.py  # already includes jcode bridge setup
```

Or manually:
```bash
python ~/Documents/Mimir/mimir_bridge.py --auto
```