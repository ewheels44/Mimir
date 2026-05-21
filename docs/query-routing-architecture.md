# Mimir Query Routing Architecture

> Replaces the OpenSpace bridge with a standalone query router.

## Overview

```
User Query
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      MCP Server (mcp_server_llamaindex.py)           │
│                                                                      │
│  ┌─────────────────────┐  ┌──────────────────────┐                  │
│  │  KnowledgeServer     │  │  KnowledgeServer      │                  │
│  │  .query()            │  │  .enrich_task()       │                  │
│  │  (synthesized Q&A)   │  │  (context injection)  │                  │
│  └──────────┬──────────┘  └──────────┬───────────┘                  │
│             │                        │                               │
│             ▼                        ▼                               │
│  ┌──────────────────────┐  ┌─────────────────────────────┐          │
│  │ LlamaIndex QueryEngine│  │ query_router.route_task()   │          │
│  │ (hybrid BM25+vector)  │  │ (standalone, no OpenSpace)  │          │
│  │ + OpenRouter LLM      │  │                             │          │
│  └──────────────────────┘  └──────────┬──────────────────┘          │
│                                        │                            │
│                                        ▼                            │
│                          ┌───────────────────────────┐              │
│                          │   Query Router             │              │
│                          │                            │              │
│                          │  ① _classify_query()       │              │
│                          │     ├─ keyword pre-check   │              │
│                          │     ├─ neural 10→8→2 NN    │              │
│                          │     └─ keyword fallback    │              │
│                          │                            │              │
│                          │  ② Route based on type:    │              │
│                          │     ├─ "structural" → graph │              │
│                          │     └─ "semantic"  → vector │              │
│                          │                            │              │
│                          │  ③ Guardrails:             │              │
│                          │     ├─ Circuit breaker      │              │
│                          │     ├─ LRU cache (TTL)      │              │
│                          │     ├─ Content filter       │              │
│                          │     └─ Freshness scoring    │              │
│                          └─────────────┬───────────────┘              │
│                                        │                             │
└────────────────────────────────────────┼─────────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
          ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
          │  Knowledge    │    │  Vector Search   │    │  Graph API   │
          │  Graph (Rust) │    │  (LlamaIndex)    │    │  (localhost) │
          │  Dijkstra     │    │  FAISS + docs    │    │  /api/graph  │
          │  path-finding │    │  OpenAI embed    │    │  /api/nbors  │
          └──────────────┘    └──────────────────┘    └──────────────┘
```

## Request Paths

### Path A: Synthesized Q&A (`mimir-knowledge_query`)

The direct Q&A path — user asks "What is our auth strategy?" and gets a synthesized answer.

```
User question
    │
    ▼
MCP → KnowledgeServer.query()
    │
    ▼
LlamaIndex QueryEngine (hybrid BM25 + vector retrieval)
    │
    ▼
OpenRouter API (o3-mini) — LLM synthesis
    │
    ▼
Synthesized answer
```

**Note:** This path does NOT use the query router or neural classifier.

### Path B: Context Enrichment (`mimir-knowledge_enrich_task`)

The pre-task context path — injects project-specific knowledge before executing a skill.

```
User task (e.g., "Build auth middleware")
    │
    ▼
MCP → KnowledgeServer.enrich_task()
    │
    ▼
query_router.route_task()
    │
    ├─ _classify_query(task)
    │   ├─ ① Keyword check (free, instant)
    │   ├─ ② Neural 10→8→2 NN (~$0.000001)
    │   └─ ③ Keyword fallback (free)
    │
    ├─ If "structural" → _search_graph()
    │   ├─ HTTP → localhost:8000 /api/graph/path
    │   └─ Dijkstra shortest weighted path
    │
    └─ If "semantic" → _search_raw()
        └─ LlamaIndex vector retrieval (top_k)
    │
    ▼
RoutingResult.to_dict() → JSON {context, routed_to, query_type, ...}
    │
    ▼
Injected into LLM prompt as system context
```

### Path C: LangGraph Workflows (unchanged)

Multi-step reasoning via `rag_workflow` or `knowledge_agent`. Not affected by the refactor.

```
User complex question
    │
    ▼
MCP → LangGraph workflow
    │
    ├─ Multiple retrieve → reason → retrieve cycles
    └─ Final synthesized answer
```

## Classification Decision Chain

```
Query text
    │
    ▼
① _quick_structural_check() — free keyword pre-filter
    │
    ├─ ≥2 structural keywords          → "structural" (return)
    ├─ 0 structural keywords           → "semantic"  (return)
    └─ 1 keyword (uncertain)           → continue ↓
    │
    ▼
② SimpleQueryClassifier.predict() — 10→8→2 neural net (NumPy)
    │   Cost: ~$0.000001/inference
    │   Confidence threshold: 0.6
    │
    ├─ Confidence ≥ 0.6  → return label
    └─ Confidence < 0.6  → continue ↓
    │
    ▼
③ _keyword_fallback() — deterministic final fallback (free)
```

## Guardrails

All guardrails are self-contained in `src/mimir/query_router.py` with zero external dependencies:

| Guardrail | Implementation | Location |
|-----------|---------------|----------|
| Circuit breaker | `_CircuitBreakerState` — 3 failures → 60s cooldown | query_router.py:61 |
| LRU cache | `_TimedCache` — 128 entries, 10min TTL, SHA-256 keys | query_router.py:97 |
| Content filter | `_is_sensitive` / `_filter_sensitive` — regex patterns | query_router.py:146 |
| Freshness | `_compute_freshness` — exponential decay over 168h | query_router.py:194 |
| Classification | `_quick_structural_check` + neural net | query_router.py:222 |

## Migration from OpenSpace Bridge

```
# OLD (OpenSpace-coupled):
from src.mimir.openspace_bridge import MimirOpenSpaceBridge
bridge = MimirOpenSpaceBridge(project_root=Path("."))
result = bridge.enrich_task("Build auth middleware")

# NEW (standalone):
from src.mimir.query_router import route_task
result = route_task("Build auth middleware")

# Backward compatibility:
# - openspace_bridge.py still exists as a thin wrapper
# - EnrichmentResult is an alias for RoutingResult
# - MimirOpenSpaceBridge delegates to query_router
# - All existing imports and MCP tool names still work
```