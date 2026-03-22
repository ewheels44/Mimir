# Three-Layer AI Context System — Implementation Work Plan
> Stack: OpenCode + oh-my-opencode (omo) + OpenRouter  
> Last updated: 2026-03-22  
> Status: Pre-implementation — ready for agent handoff

---

## Purpose

This document is the authoritative implementation plan for a three-layer AI context system designed to solve two core problems:

1. **Latency growth** — conversation quality degrades and response time increases as message count grows
2. **Context amnesia** — the LLM loses preferences, decisions, and project context across sessions

The solution is a three-layer architecture where the LLM only ever receives a small, dynamically assembled context block — never the full conversation history.

---

## Stack Context (Read This First)

This plan is written specifically for the following toolchain. Architecture decisions below are derived from this stack — do not generalize to other setups without re-evaluating.

| Tool | Role | Notes |
|---|---|---|
| **OpenCode** | Terminal-based AI coding agent | MCP host; reads `opencode.json` for MCP server config |
| **oh-my-opencode (omo)** | OpenCode plugin | Provides Sisyphus orchestrator, 11 specialized agents, 48 lifecycle hooks, and hook-based context injection |
| **OpenRouter** | LLM resolution layer | Routes model requests; omo uses category-based delegation through it |
| **Mem0** | Memory bank (self-hosted) | Persistent facts, preferences, decisions |
| **Kuzu** | Graph store | Embedded, no-server, Cypher-compatible — codebase + business plan nodes/edges |
| **Qdrant** | Vector store | Semantic search on graph node content |

### Critical Stack Constraints

- **MCP transport**: OpenCode has known bugs with SSE-based MCP servers. Always use `type: "local"` (stdio) or HTTP streamable transport. Never SSE.
- **MCP token budget**: Every enabled MCP server adds to context on every message. Design graph MCP tools to be on-demand, not always-on.
- **Observer Agent**: Do NOT build from scratch. Wire into omo's existing hook system (`chat.message`, post-session hooks). omo's `chat.params` hook is the injection point for memory.
- **AGENTS.md is context injection**: omo reads AGENTS.md natively. This is the format for injecting graph context into agents — not a custom system prompt wrapper.
- **Model routing**: Observer and retrieval agents should use a cheap/fast category via OpenRouter. Reserve Opus-class models for Sisyphus and Prometheus only.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    You (Human in the Loop)                    │
│              review gate · conflict resolution                │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                    Observer Agent                             │
│         (custom omo agent + post-session hooks)               │
│   monitors conversations · extracts facts · scores confidence │
│   proposes ADD / UPDATE / DELETE / NOOP                       │
└───────────────┬──────────────────────────┬───────────────────┘
                │                          │
┌───────────────▼──────────┐  ┌────────────▼──────────────────┐
│      Layer 1             │  │      Layer 2                   │
│      Memory Bank         │  │      Knowledge Graph           │
│      (Mem0 self-hosted)  │  │      (Kuzu + Qdrant)           │
│  personal facts          │  │  codebase + business plan      │
│  preferences             │  │  nodes + typed edges           │
│  decisions               │  │  recursive updates             │
│  temporal decay          │  │  AGENTS.md export              │
└───────────────┬──────────┘  └────────────┬──────────────────┘
                └──────────────┬────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Layer 3                                     │
│                    Context Manager                             │
│          (omo hooks: chat.params + chat.headers)              │
│   retrieves relevant memories + graph nodes per message       │
│   assembles lean context block (target: <800 tokens)          │
│   keeps conversation history trimmed                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    OpenCode + omo                              │
│              Sisyphus · Prometheus · agents                    │
│         small context · accurate · consistent                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Graph Node Types

```cypher
// Node type definitions for Kuzu schema

CREATE NODE TABLE BusinessGoal (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  status STRING,  -- active | achieved | deprecated
  created_at TIMESTAMP,
  embedding_id STRING  -- pointer to Qdrant
);

CREATE NODE TABLE Feature (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  status STRING,  -- planned | in-progress | shipped | deprecated
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE Module (
  id STRING PRIMARY KEY,
  name STRING,
  file_path STRING,
  language STRING,
  description STRING,
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE DataModel (
  id STRING PRIMARY KEY,
  name STRING,
  schema_description STRING,
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE RevenueStream (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  tier STRING,
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE Risk (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  severity STRING,  -- low | medium | high | critical
  status STRING,    -- open | mitigated | resolved
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE CustomerSegment (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  created_at TIMESTAMP,
  embedding_id STRING
);

CREATE NODE TABLE ExternalDep (
  id STRING PRIMARY KEY,
  name STRING,
  description STRING,
  dep_type STRING,  -- api | library | service | hardware
  created_at TIMESTAMP,
  embedding_id STRING
);
```

### Graph Edge Types

```cypher
CREATE REL TABLE implements (FROM Feature TO Module, confidence DOUBLE);
CREATE REL TABLE depends_on (FROM Module TO Module, strength STRING);
CREATE REL TABLE enables (FROM Feature TO BusinessGoal, weight DOUBLE);
CREATE REL TABLE blocks (FROM Risk TO Feature, severity STRING);
CREATE REL TABLE serves (FROM Feature TO CustomerSegment);
CREATE REL TABLE requires (FROM Feature TO ExternalDep);
CREATE REL TABLE measured_by (FROM BusinessGoal TO DataModel);
CREATE REL TABLE funded_by (FROM Feature TO RevenueStream);
```

### Memory Schema

```yaml
# memory_schema.yaml
memory:
  fields:
    id: uuid
    content: string          # compressed natural language fact
    type: enum               # preference | decision | convention | episodic | correction
    confidence: float        # 0.0 - 1.0
    source_session: string   # session ID where extracted
    created_at: timestamp
    last_used_at: timestamp
    decay_weight: float      # decreases over time, affects retrieval ranking
    expires_at: timestamp    # optional — ephemeral decisions
    status: enum             # active | pending_review | rejected | expired

memory_types:
  preference:
    description: "How the user likes things done — UI, style, tone, tooling"
    example: "Prefers blue color palettes for UI work"
    decay_rate: slow
  decision:
    description: "Architecture or product decisions already made"
    example: "Decided to use Rust for the API layer, not Go"
    decay_rate: medium
  convention:
    description: "Agreed project conventions — naming, structure, formatting"
    example: "File naming convention is snake_case throughout"
    decay_rate: slow
  episodic:
    description: "Compressed summary of a past work session"
    example: "Session 2026-03-10: Finalized data model for RaceResult entity"
    decay_rate: fast
  correction:
    description: "Explicit corrections to previously held beliefs"
    example: "Previously thought X; corrected to Y on 2026-03-15"
    decay_rate: never  # corrections persist
```

---

## Phase 0 — Foundation & Schema Design
**Timeline: Week 1**  
**Goal: Define the shape of the data before writing any code. Everything downstream depends on getting schema right.**

### Tasks

- [ ] **Define memory schema** — finalize `memory_schema.yaml`. Identify all memory types needed. Define all fields including confidence, decay, expiry.
- [ ] **Define graph node types** — enumerate all entity types from the business plan. Map codebase concepts onto node types. Write Kuzu schema from the definitions above.
- [ ] **Define graph edge types** — enumerate all relationship types. Define directionality and cardinality for each edge.
- [ ] **Set up dev environment** — install Kuzu (embedded, no server needed). Spin up Qdrant via Docker. Spin up Mem0 via Docker (self-hosted). Write `docker-compose.yaml` for Qdrant + Mem0.
- [ ] **Write schema validation tests** — unit tests that reject malformed nodes/edges at write time. Add a `metadata: JSON` escape hatch field to all node types for unanticipated properties.
- [ ] **Audit existing business plan** — read through existing business plan docs and manually enumerate the first batch of node candidates. Do not ingest yet — just list them.

### Outputs
```
schema/
  memory_schema.yaml
  graph_schema.cypher
  graph_schema_test.py
docker/
  docker-compose.yaml   # Qdrant + Mem0
```

### Decision Gate
> Do not proceed to Phase 1 until the schema has been reviewed and signed off. Schema refactors after data is ingested are expensive.

---

## Phase 1 — Memory Bank
**Timeline: Weeks 2–3**  
**Goal: Persistent memory working end-to-end. The LLM recalls facts from previous sessions without any manual re-feeding.**

### Tasks

- [ ] **Deploy Mem0 self-hosted** — Docker container, local network only. Configure extraction model (use a cheap/fast model via OpenRouter — not Opus).
- [ ] **Seed initial memories** — manually write the first batch. Include: preferences already known, tech stack conventions, key architectural decisions already made. This is Day 1 state.
- [ ] **Build memory retrieval client** (`memory_client.py`) — takes incoming user message, queries Mem0 for top-K relevant memories, returns compact structured block.
- [ ] **Add confidence scoring** — extraction confidence < 0.70 goes to review queue, not auto-committed. Confidence >= 0.85 can be auto-staged (not auto-committed).
- [ ] **Build review queue** — simple CLI or file-based queue for inspecting, approving, editing, or rejecting proposed memory updates before commit.
- [ ] **Build injection formatter** (`memory_formatter.py`) — takes raw memories, formats them into a compact block. Target: < 250 tokens for memory context.
- [ ] **Wire into omo's `chat.params` hook** — memory retrieval fires before every message. Inject formatted memory block into system context via hook. Do NOT add a wrapper layer around OpenCode.
- [ ] **End-to-end test** — start fresh session. Verify memories are injected. State a new preference. Verify it gets extracted, goes to review queue, and after approval is recalled in the next session.

### Outputs
```
memory/
  memory_client.py       # retrieval + injection
  memory_formatter.py    # compact context block formatter
  memory_review.py       # CLI review queue
  seed_memories.py       # one-time seeding script
  test_e2e_memory.py
omo_hooks/
  chat_params_memory.ts  # omo hook — injects memory before each message
```

### Memory Types Priority Order
1. `correction` — always injected (never decay)
2. `convention` — always injected (project-wide)
3. `decision` — injected if related to current topic
4. `preference` — injected if related to current task type
5. `episodic` — injected only if directly relevant

---

## Phase 2 — Knowledge Graph
**Timeline: Weeks 3–5**  
**Goal: Codebase and business plan correlated into a traversable graph. Query: "what code is at risk if this business assumption changes?" — get a real answer.**

### Tasks

- [ ] **Initialize Kuzu schema** — create node and edge tables from Phase 0 schema. Validate with synthetic test data. Confirm Cypher queries work.
- [ ] **Build business plan ingestion** (`ingest_bizplan.py`) — LLM-assisted extraction. Feed business plan docs to a mid-tier model. Extract entities, classify as node types, propose edges. Output: draft node/edge list for human review. Do NOT auto-commit.
- [ ] **Build codebase ingestion** (`ingest_codebase.py`) — static analysis pass. Parse imports, function calls, file/module boundaries. Auto-classify as Module, DataModel, ExternalDep nodes. This pipeline is deterministic — no LLM needed here.
- [ ] **Add vector embeddings** (`embed_nodes.py`) — for each node, generate embedding of its content description. Store in Qdrant with `node_id` as the key. Link back to Kuzu via `embedding_id` field.
- [ ] **Build graph query client** (`graph_client.py`):
  - `get_neighbors(node_id, depth=1, rel_filter=None)`
  - `find_path(from_id, to_id)` — what connects business goal X to module Y?
  - `get_subgraph(node_id, depth=2)` — Roam-style graph view
  - `semantic_search(query, top_k=10)` — falls through to Qdrant
- [ ] **Validate correlations** — manually audit: do feature nodes connect to the right business goals? Are module dependencies accurate? Log discrepancies.
- [ ] **Build AGENTS.md exporter** (`export_agents_md.py`) — generates a hierarchical AGENTS.md from graph subgraphs relevant to each directory in the codebase. This is the primary context injection format for omo — not a custom format.
- [ ] **Build graph update pipeline** (`graph_updater.py`) — incremental updates when new code or docs are added. Never rebuild from scratch.
- [ ] **Expose as MCP server** — local stdio MCP server (NOT SSE). Register in `opencode.json` under `mcp`. Keep always-on tools minimal to avoid context bloat. Make retrieval tools on-demand only.

### MCP Server Tool Surface

```typescript
// opencode.json MCP registration
{
  "mcp": {
    "knowledge-graph": {
      "type": "local",
      "command": "python mcp/graph_mcp_server.py",
      "enabled": true
    }
  }
}

// Tools exposed (keep this list lean — each tool adds to context)
tools = [
  "graph_semantic_search",      // query → relevant nodes via Qdrant
  "graph_get_subgraph",         // node_id + depth → subgraph
  "graph_find_path",            // from_id + to_id → path
  "graph_get_neighbors",        // node_id → adjacent nodes
  "graph_add_node",             // write — requires confidence score
  "graph_add_edge",             // write — requires confidence score
]
```

### Outputs
```
graph/
  init_graph.py
  ingest_bizplan.py
  ingest_codebase.py
  embed_nodes.py
  graph_client.py
  graph_updater.py
  export_agents_md.py
mcp/
  graph_mcp_server.py    # stdio transport — NOT SSE
```

### Note on Two Ingestion Strategies
Keep pipelines strictly separate:
- **Static analysis** for code — deterministic, no LLM, auto-commit with review
- **LLM extraction** for business docs — semantic, requires human review gate before commit

---

## Phase 3 — Context Manager (omo Hook Integration)
**Timeline: Weeks 5–6**  
**Goal: Lean context assembled per message. Latency stays flat. No separate wrapper layer needed — wires directly into omo's hook system.**

### Architecture Note
Unlike the generic version of this plan, you do NOT build a standalone context manager service. omo's hook system already provides the injection points. The Context Manager is implemented as a set of omo hooks.

### omo Hook Mapping

| Hook | Purpose |
|---|---|
| `chat.params` | Inject memory block + relevant graph nodes before each message |
| `chat.message` | Feed message to Observer Agent for fact extraction |
| `chat.headers` | (Optional) Pass session metadata for episodic memory |
| Post-session | Trigger Observer Agent to process full session and propose updates |

### Tasks

- [ ] **Build context assembler** (`context_assembler.py`) — takes user message, queries Memory Bank and Knowledge Graph, assembles single context block. Target: < 800 tokens total including memories + graph nodes.
- [ ] **Build relevance ranker** (`relevance_ranker.py`) — scores retrieved memories and graph nodes by relevance to current message. Only top-K make it into context.
- [ ] **Implement history trimmer** — rolling window on conversation history. Older turns get summarized and compressed, not hard-dropped. Use a cheap model via OpenRouter for summarization.
- [ ] **Wire `chat.params` hook** — fires context assembler before every message. Injects result into system context. This replaces any need for a wrapper service.
- [ ] **Wire `chat.message` hook** — passes message to Observer Agent pipeline for background fact extraction.
- [ ] **Latency benchmark** — measure context retrieval time. Target: < 200ms per message. Kuzu is embedded so graph queries should be fast. Profile and optimize if needed.
- [ ] **Integration test** — full loop: message in → context assembled → omo processes → LLM responds → observer extracts → memory/graph updated.

### omo Hook Implementation

```typescript
// omo hook — fires before every message
// File: .opencode/hooks/context-injector.ts

export const chatParamsHook = {
  name: "context-injector",
  event: "chat.params",
  handler: async (ctx) => {
    const message = ctx.params.messages.at(-1)?.content;
    if (!message) return ctx;

    // Retrieve from both layers
    const contextBlock = await fetch("http://localhost:8765/assemble", {
      method: "POST",
      body: JSON.stringify({ message }),
    }).then(r => r.json());

    // Inject as system context — prepend to existing system prompt
    ctx.params.system = [contextBlock.formatted, ctx.params.system]
      .filter(Boolean)
      .join("\n\n---\n\n");

    return ctx;
  }
};
```

### Outputs
```
context/
  context_assembler.py
  relevance_ranker.py
  history_trimmer.py
  context_server.py      # lightweight FastAPI — called by omo hook
omo_hooks/
  context_injector.ts    # chat.params hook
  observer_trigger.ts    # chat.message hook
```

---

## Phase 4 — Observer Agent & Recursive Learning
**Timeline: Weeks 6–8**  
**Goal: Close the loop. System monitors conversations, extracts new facts, proposes updates to both layers. Human review gate before permanent commit.**

### Observer Agent Design

The Observer is a custom omo agent — lightweight, uses a cheap/fast model category via OpenRouter. It does not use Opus. It runs in the background after sessions, not inline during them.

```yaml
# omo agent config — observer
name: observer
description: "Monitors completed sessions. Extracts facts, decisions, preferences. Proposes memory and graph updates. Never makes commits — proposals only."
model_category: fast          # routes to cheap model via OpenRouter
tools:
  - read                      # read session transcript
  - memory_propose            # propose memory update (no auto-commit)
  - graph_add_node            # propose new node (no auto-commit)
  - graph_add_edge            # propose new edge (no auto-commit)
permissions:
  write: false                # Observer never writes directly
  propose: true
```

### Tasks

- [ ] **Register Observer as omo custom agent** — create agent definition in `.opencode/agents/observer.md`. Wire to cheap model category. Disable write permissions — proposals only.
- [ ] **Build extraction prompt** — engineered to extract: new preferences stated, decisions made, corrections to old info, new entities mentioned, relationships implied. Output must be structured JSON.
- [ ] **Implement ADD/UPDATE/DELETE/NOOP logic** (`memory_reconciler.py`) — compare new extractions against existing memory. Surface conflicts explicitly. Never silently overwrite.
- [ ] **Build conflict resolver** (`conflict_resolver.py`) — when new fact contradicts existing one, log the conflict with both versions. Present to user for resolution. The user decides, not the system.
- [ ] **Add temporal decay scheduler** (`decay_scheduler.py`) — nightly job. Decreases `decay_weight` on memories based on type and age. Flags memories that have decayed below threshold for review.
- [ ] **Build graph auto-update pipeline** (`graph_proposer.py`) — Observer also proposes new graph nodes and edges based on conversation. Code module mentioned that doesn't exist? Propose node. Feature linked to goal in conversation? Propose edge.
- [ ] **Add hallucination guard** (`hallucination_guard.py`) — before any proposal is staged, validate that extracted facts are grounded in the actual conversation transcript. Reject extractions not traceable to a source turn.
- [ ] **Build review dashboard** — single interface for all pending proposals. Memory proposals + graph proposals in one view. Approve / Reject / Edit before commit. Can be CLI or simple web UI.
- [ ] **Wire post-session hook** — after session ends, trigger Observer Agent on full transcript. Route through omo's session end lifecycle hook.

### Outputs
```
observer/
  observer_agent.py          # core extraction logic
  memory_reconciler.py
  conflict_resolver.py
  decay_scheduler.py
  graph_proposer.py
  hallucination_guard.py
  review_dashboard.py        # CLI or web UI
.opencode/agents/
  observer.md                # omo agent definition
omo_hooks/
  post_session_observer.ts   # triggers Observer after session ends
```

### Critical Rule
> The Observer NEVER auto-commits to permanent storage. Confident extractions (>0.85) can be auto-staged in the review queue. Commit to Mem0 or Kuzu requires explicit human approval. This prevents compounding errors.

---

## Phase 5 — Observability & Hardening
**Timeline: Weeks 8–9**  
**Goal: The system is fully inspectable. You can see exactly what it knows, why it knows it, and where it came from.**

### Tasks

- [ ] **Memory audit log** — every memory add/update/delete logged with: source session ID, source turn, timestamp, confidence score, who approved.
- [ ] **Graph diff viewer** (`graph_diff.py`) — after each Observer run, show what changed in the graph. Which nodes were added? Which edges updated? Diffs committed to git.
- [ ] **Context inspector** — debug tool: for any given message, show exactly which memories and graph nodes were retrieved, their relevance scores, and total token count of assembled context.
- [ ] **Manual memory editor** — direct UI to view, edit, or delete any memory entry. Full control. The system serves you — not the other way around.
- [ ] **Performance dashboard** — track: context assembly latency (p50, p95), memory bank size, graph node/edge counts, Observer hit rate (proposals per session), approval/rejection ratio.
- [ ] **Regression tests** — key memories should always be retrievable. Latency should stay flat at turn 30 vs turn 1. Critical graph paths should always resolve.
- [ ] **omo token audit** — verify that the MCP server and hook injections are not bloating context. Check that total injected context stays under budget per message.

### Outputs
```
observability/
  audit_log.db
  graph_diff.py
  context_inspector.py
  memory_editor.py
  metrics/
    dashboard.py
tests/
  regression/
    test_memory_retrieval.py
    test_latency_flat.py
    test_graph_paths.py
    test_token_budget.py
```

---

## Milestones & Success Criteria

| # | Phase | Timeframe | Pass Condition |
|---|---|---|---|
| M1 | End of Phase 1 | Week 3 | Start fresh session. LLM recalls a preference set in a previous session with zero manual re-feeding. |
| M2 | End of Phase 2 | Week 5 | Query: "what code implements goal X?" Returns accurate path from business goal node to module node via graph traversal. |
| M3 | End of Phase 3 | Week 6 | Latency per message is flat at turn 1 vs turn 30. Assembled context block stays under 800 tokens. omo hooks confirmed firing. |
| M4 | End of Phase 4 | Week 8 | State something new in a session. Next session, system recalls it unprompted. Review dashboard shows full extraction trail. |
| M5 | End of Phase 5 | Week 9 | Full audit trail visible. Any memory traceable to source conversation. Token budget verified under threshold. Regression suite passing. |

---

## Risks & Mitigations

### Risk: Observer hallucinates memory extractions
**Impact:** System learns wrong facts. Errors compound over time.  
**Mitigation:** Hallucination guard validates all extractions against source turns. Human review gate before any commit. Confidence threshold enforced. Low-confidence proposals auto-rejected, not queued.

### Risk: MCP server bloats context
**Impact:** Every tool registration adds tokens. Many tools = context blown before the conversation starts.  
**Mitigation:** Keep always-on MCP tools minimal (< 5 tools registered). Make retrieval tools invocable on-demand via omo agent mentions, not always-on. Audit token budget in Phase 5.

### Risk: Graph schema too rigid
**Impact:** New entity types discovered mid-project don't fit cleanly. Painful migrations.  
**Mitigation:** Phase 0 schema design is the most critical week. Add `metadata: JSON` escape hatch to all node types. Document the extension process in schema validation tests.

### Risk: omo context management conflicts with custom hooks
**Impact:** omo's built-in context management and custom memory injection hooks collide. Context is duplicated or overwritten.  
**Mitigation:** Read omo hook documentation before implementing. Use omo's hook priority system to ensure correct ordering. Test hook ordering explicitly in Phase 3 integration tests.

### Risk: OpenRouter routing sends expensive model to Observer tasks
**Impact:** Observer should use cheap/fast model. Mis-routing to Opus wastes budget.  
**Mitigation:** Define Observer as an explicit omo agent category mapped to a cheap model. Never allow category inheritance to pull it up to Opus. Document model assignment in agent config.

---

## OpenCode Config Reference

```json
// opencode.json additions for this system
{
  "mcp": {
    "knowledge-graph": {
      "type": "local",
      "command": "python mcp/graph_mcp_server.py",
      "enabled": true
    }
  },
  "agents": {
    "observer": {
      "model_category": "fast",
      "permissions": {
        "write": false
      }
    }
  }
}
```

```markdown
<!-- AGENTS.md additions — auto-generated by export_agents_md.py -->

## Knowledge Graph Context
<!-- This section is auto-generated. Do not edit manually. -->
<!-- Last updated: {timestamp} -->

### Active Business Goals
{graph_export: BusinessGoal, depth=1}

### Current Sprint Features
{graph_export: Feature[status=in-progress], depth=2}

### Architecture Decisions
{memory_export: type=decision, top_k=5}
```

---

## File Structure (Full)

```
project-root/
├── schema/
│   ├── memory_schema.yaml
│   ├── graph_schema.cypher
│   └── graph_schema_test.py
├── docker/
│   └── docker-compose.yaml          # Qdrant + Mem0
├── memory/
│   ├── memory_client.py
│   ├── memory_formatter.py
│   ├── memory_review.py
│   ├── seed_memories.py
│   └── test_e2e_memory.py
├── graph/
│   ├── init_graph.py
│   ├── ingest_bizplan.py
│   ├── ingest_codebase.py
│   ├── embed_nodes.py
│   ├── graph_client.py
│   ├── graph_updater.py
│   └── export_agents_md.py
├── mcp/
│   └── graph_mcp_server.py          # stdio transport — NOT SSE
├── context/
│   ├── context_assembler.py
│   ├── relevance_ranker.py
│   ├── history_trimmer.py
│   └── context_server.py
├── observer/
│   ├── observer_agent.py
│   ├── memory_reconciler.py
│   ├── conflict_resolver.py
│   ├── decay_scheduler.py
│   ├── graph_proposer.py
│   ├── hallucination_guard.py
│   └── review_dashboard.py
├── observability/
│   ├── audit_log.db
│   ├── graph_diff.py
│   ├── context_inspector.py
│   ├── memory_editor.py
│   └── metrics/
│       └── dashboard.py
├── omo_hooks/
│   ├── chat_params_memory.ts        # memory injection hook
│   ├── context_injector.ts          # graph context injection hook
│   ├── observer_trigger.ts          # post-message observer trigger
│   └── post_session_observer.ts     # post-session full observer run
├── .opencode/
│   └── agents/
│       └── observer.md              # omo Observer agent definition
└── tests/
    ├── schema/
    └── regression/
        ├── test_memory_retrieval.py
        ├── test_latency_flat.py
        ├── test_graph_paths.py
        └── test_token_budget.py
```

---

## Agent Handoff Instructions

If you are an agent receiving this document:

1. **Start with Phase 0.** Do not skip schema design. All downstream work depends on it.
2. **Read omo documentation** before implementing any hooks. Hook ordering and priority matter. Do not assume.
3. **Never auto-commit** to Mem0 or Kuzu from the Observer. All writes go through the review queue.
4. **MCP server must use stdio transport.** SSE is broken in OpenCode. Use `type: "local"` in `opencode.json`.
5. **Check the token budget** after each MCP tool registration. The goal is lean context, not comprehensive context.
6. **One pipeline at a time.** Static analysis ingestion and LLM extraction ingestion are separate scripts. Do not mix.
7. **The AGENTS.md export is the primary context injection format.** omo reads it natively. Do not invent a custom format.
8. **Test end-to-end at each milestone** before moving to the next phase. Do not stack phases without validation.

---

*This is a living document. Update it as architectural decisions are made and phases complete. Commit changes to the plans repo with timestamps.*
