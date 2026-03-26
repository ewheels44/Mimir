# Three-Layer AI Context System — Implementation Plan

## TL;DR

> **Quick Summary**: Build a per-project AI context system (Memory Bank + Knowledge Graph + Context Manager) that wires into OpenCode/omo via a single MCP server. Eliminates Docker dependencies — everything runs as embedded Python libraries with data stored in `.mimir/` per project.
> 
> **Deliverables**:
> - `mimir` Python package (managed with `uv`): MCP server + memory client + graph client + context assembler + observer agent
> - `map-codebase` command: Bootstrap any project with full static analysis + doc ingestion
> - omo hooks: `chat.params` context injection + `chat.message` observer trigger
> - Per-project `.mimir/` data directory with Kuzu graph + Qdrant vectors + Mem0 memories
> - CLI review dashboard for memory/graph proposals
> - `uv` toolchain: Modern Python dependency management (replaces pip + venv)
> 
> **Estimated Effort**: Large (~9 weeks, 5 phases)
> **Parallel Execution**: YES — 6 waves, up to 7 parallel tasks per wave
> **Critical Path**: Bootstrap → Schema → Memory Client → Graph Client → MCP Server → omo Hooks → Observer → E2E Test

---

## Context

### Original Request
User provided a 667-line pre-implementation work plan (`three_layer_ai_context_system_workplan.md`) for a three-layer AI context system solving LLM context degradation and cross-session amnesia. The plan was thorough but had 21 identified gaps. User requested a gap analysis and executable implementation plan.

### Interview Summary
**Key Discussions**:
- **Mem0 deployment**: Library mode (not Docker). Mem0 imported directly in Python, no separate service.
- **Qdrant architecture**: Single instance, local on-disk mode via qdrant-client. No Docker needed. Separate collections for Mem0 memories and graph node embeddings.
- **Confidence scoring**: Hybrid approach — custom LLM-based confidence for Observer extraction, Mem0's relevance threshold for retrieval ranking.
- **Memory types**: Custom metadata layer on top of Mem0. Plan's 5 types (preference, decision, convention, episodic, correction) stored as metadata fields.
- **Per-project isolation**: Each project directory gets its own `.mimir/` data directory. Memories and graph are project-scoped.
- **Map-codebase command**: Full static analysis + embeddings + LLM doc extraction in one pass. Required bootstrap for each new project.
- **FastAPI eliminated**: Context assembly moved INTO the MCP server. One process, no HTTP overhead, no ops dependency.
- **Docker eliminated entirely**: Kuzu (embedded) + Qdrant (local mode) + Mem0 (library) = zero Docker for v1.
- **MCP auto-detection**: CWD-based. Server reads working directory, finds `.mimir/` data automatically.
- **Python toolchain**: `uv` for dependency management and virtual environments (fast, modern replacement for pip + venv).

**Research Findings**:
- **Kuzu**: `CREATE NODE TABLE` Cypher syntax confirmed correct. Python API: `kuzu.Database("path")` + `kuzu.Connection(db)`.
- **Mem0**: OSS is a Python library (`from mem0 import Memory`). NO built-in confidence scoring. Has own type system incompatible with plan's custom types. Uses Qdrant internally.
- **omo hooks**: `chat.params`, `chat.message`, `chat.headers` ALL confirmed. Factory pattern: `createMyHook(deps) → { 'event': handler }`. Hook cadence system exists.
- **MCP**: `type: "local"` confirmed correct for stdio transport in `opencode.json`.
- **AGENTS.md**: Auto-injected via `directory-agents-injector` hook. `/init-deep` generates hierarchical structure.

### Metis Review
**Identified Gaps** (addressed):
- No project bootstrapping → Added Wave 1 bootstrap tasks
- No error handling/degradation → Added explicit fallback strategy per component
- Conflicting chat.params hooks → Unified into single hook
- Observer dual identity → Clarified: Python module called by omo agent definition
- context_server.py ops dependency → Eliminated; logic moved into MCP server
- No schema migration → Added metadata JSON escape hatch + migration script task
- Decay scheduler no runtime → Added cron/launchctl task
- Hook code wrong signature → Corrected to factory pattern
- No performance criteria → Added latency targets per component
- No capacity limits → Added graph/memory size targets

---

## Work Objectives

### Core Objective
Build a zero-Docker, per-project AI context system that gives OpenCode/omo persistent memory across sessions and a queryable knowledge graph of codebase + business plan, assembled into lean context (<800 tokens) per message.

### Concrete Deliverables
- Python package `mimir/` with: memory client, graph client, context assembler, observer agent, MCP server, CLI tools
- omo hooks: `context_injector.ts`, `observer_trigger.ts`
- omo agent definition: `observer.md`
- Per-project `.mimir/` data directory structure
- `map-codebase` CLI command for project bootstrapping
- CLI review dashboard for proposals
- Schema files + validation tests
- E2E integration tests + regression suite

### Definition of Done
- [ ] Fresh project → run `map-codebase` → graph populated with nodes/edges
- [ ] Start OpenCode session → memories from past sessions injected automatically
- [ ] State a new preference → next session recalls it (after review approval)
- [ ] Query "what code implements goal X?" → accurate graph traversal result
- [ ] Turn 1 vs turn 30 latency stays flat (context assembly <200ms)
- [ ] Assembled context block stays under 800 tokens
- [ ] All proposals visible in review dashboard with full audit trail

### Must Have
- Per-project data isolation (`.mimir/` directory)
- `map-codebase` bootstrap command
- Memory injection via `chat.params` hook
- Observer extraction via post-session hook
- Human review gate before any permanent memory/graph commit
- Confidence scoring on all extractions
- Graceful degradation when any component fails
- Hallucination guard on Observer extractions

### Must NOT Have (Guardrails)
- No Docker dependency for v1 (all embedded/local)
- No separate FastAPI context server (assembly lives in MCP server)
- No web UI (CLI only for v1)
- No multi-project memory sharing or cross-project queries
- No ML-based relevance ranking (cosine similarity only)
- No caching layers (Redis, LRU) until latency is measured
- No memory export/import
- No graph visualization
- No authentication/authorization (local-only)
- No real-time sync or WebSocket push
- No memory versioning (single version per memory)
- No multi-format doc ingestion (markdown/text only for v1)
- Do NOT add excessive comments, JSDoc, or docstrings beyond what's needed
- Do NOT over-abstract — prefer inline logic over premature utility extraction
- Do NOT create wrapper classes around Kuzu/Mem0/Qdrant — use their APIs directly

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (greenfield — will be set up in Wave 1)
- **Automated tests**: YES (tests after implementation)
- **Framework**: pytest
- **Pattern**: Implement module → write tests → verify passing

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash (pytest, python -c) — import, call functions, assert output
- **MCP server**: Use Bash (python + stdio) — send JSON-RPC, assert response
- **omo hooks**: Use Bash (tsc --noEmit) — type-check, verify factory pattern
- **CLI tools**: Use interactive_bash (tmux) — run command, validate output
- **Integration**: Use Bash (pytest) — full flow tests

### Performance Targets
| Component | Target | How to Verify |
|-----------|--------|---------------|
| Memory retrieval | <100ms p95 | pytest benchmark |
| Graph query | <50ms p95 | pytest benchmark |
| Context assembly total | <200ms p95 | End-to-end timing |
| Hook execution overhead | <50ms | Measure hook duration |
| Memory extraction | <5s per session | Observer benchmark |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — project bootstrap, zero dependencies):
├── Task 1: Project bootstrap (git, uv, pyproject.toml) [quick]
├── Task 2: .mimir/ directory structure + config schema [quick]
├── Task 3: Kuzu graph schema definition [quick]
├── Task 4: Memory schema + metadata layer design [quick]
└── Task 5: Qdrant local mode setup + collection config [quick]

Wave 2 (After Wave 1 — core data clients, MAX PARALLEL):
├── Task 6: Memory client (Mem0 library integration) [deep]
├── Task 7: Graph client (Kuzu + Qdrant embeddings) [deep]
├── Task 8: Memory formatter (compact context block) [quick]
├── Task 9: Relevance ranker (scoring + top-K selection) [unspecified-high]
└── Task 10: Confidence scoring module [unspecified-high]

Wave 3 (After Wave 2 — MCP server + context assembly):
├── Task 11: MCP server core (stdio transport + project detection) [deep]
├── Task 12: Context assembler (memory + graph → lean block) [deep]
├── Task 13: Map-codebase: static analysis pipeline [deep]
├── Task 14: Map-codebase: doc/bizplan LLM extraction [deep]
└── Task 15: Map-codebase: embedding generation [unspecified-high]

Wave 4 (After Wave 3 — omo integration + Observer):
├── Task 16: MCP tool registration (graph + memory + context tools) [unspecified-high]
├── Task 17: omo chat.params hook (context injection) [unspecified-high]
├── Task 18: Observer agent: extraction + proposal logic [deep]
├── Task 19: Observer agent: hallucination guard [deep]
├── Task 20: Observer agent: memory reconciler + conflict resolver [deep]
└── Task 21: omo agent definition (observer.md) [quick]

Wave 5 (After Wave 4 — automation + tooling):
├── Task 22: omo post-session hook (observer trigger) [unspecified-high]
├── Task 23: Decay scheduler (time-based + manual trigger) [unspecified-high]
├── Task 24: CLI review dashboard [unspecified-high]
├── Task 25: AGENTS.md exporter (graph → markdown) [unspecified-high]
├── Task 26: History trimmer (conversation compression) [unspecified-high]
└── Task 27: Audit log + context inspector [unspecified-high]

Wave 6 (After Wave 5 — testing + hardening):
├── Task 28: Unit + integration tests for all modules [deep]
├── Task 29: E2E integration test (full message loop) [deep]
├── Task 30: Regression test suite (latency, retrieval, paths, tokens) [deep]
├── Task 31: Error handling + graceful degradation pass [unspecified-high]
└── Task 32: opencode.json config + setup documentation [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

Critical Path: T1 → T3 → T7 → T11 → T12 → T16 → T17 → T29 → F1-F4 → user okay
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 5 (Waves 1, 2, 5)

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2-32 | 1 |
| 2 | 1 | 6, 7, 11 | 1 |
| 3 | 1 | 7 | 1 |
| 4 | 1 | 6 | 1 |
| 5 | 1 | 6, 7 | 1 |
| 6 | 2, 4, 5 | 8, 10, 12, 18 | 2 |
| 7 | 2, 3, 5 | 12, 13, 14, 15 | 2 |
| 8 | 6 | 12 | 2 |
| 9 | — | 12 | 2 |
| 10 | 6 | 18 | 2 |
| 11 | 2 | 16, 17 | 3 |
| 12 | 6, 7, 8, 9 | 16, 17 | 3 |
| 13 | 7 | 29 | 3 |
| 14 | 7 | 29 | 3 |
| 15 | 7 | 29 | 3 |
| 16 | 11, 12 | 17, 22 | 4 |
| 17 | 11, 12, 16 | 29 | 4 |
| 18 | 6, 7, 10 | 20, 22 | 4 |
| 19 | 18 | 22 | 4 |
| 20 | 18 | 24 | 4 |
| 21 | — | 22 | 4 |
| 22 | 16, 18, 19, 21 | 29 | 5 |
| 23 | 6 | 30 | 5 |
| 24 | 20 | 29 | 5 |
| 25 | 7 | 32 | 5 |
| 26 | 12 | 30 | 5 |
| 27 | 6, 7, 12 | 30 | 5 |
| 28 | 6-27 | 30 | 6 |
| 29 | 17, 22, 24 | F1-F4 | 6 |
| 30 | 28, 29 | F1-F4 | 6 |
| 31 | 6-27 | F1-F4 | 6 |
| 32 | 11, 17, 22 | F1-F4 | 6 |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|------------|
| 1 | 5 | T1-T5 → `quick` |
| 2 | 5 | T6-T7 → `deep`, T8 → `quick`, T9-T10 → `unspecified-high` |
| 3 | 5 | T11-T14 → `deep`, T15 → `unspecified-high` |
| 4 | 6 | T16 → `unspecified-high`, T17 → `unspecified-high`, T18-T20 → `deep`, T21 → `quick` |
| 5 | 6 | T22-T27 → `unspecified-high` |
| 6 | 5 | T28-T30 → `deep`, T31 → `unspecified-high`, T32 → `quick` |
| FINAL | 4 | F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

### Wave 1: Bootstrap (All Parallel — Zero Dependencies)

- [x] **T1. Project Bootstrap**
  - What: Initialize git repo, create pyproject.toml with dependencies (kuzu, mem0ai, qdrant-client, fastapi, uvicorn, pytest, mcp), create .python-version, use `uv` for venv and dependency management
  - Depends: None
  - Blocks: T2-T32
  - Category: `quick`
  - Skills: [`git-master`]
  - QA: `git status` shows clean repo, `python --version` matches .python-version, `uv pip list` shows all dependencies

- [x] **T2. .mimir/ Directory Structure**
  - What: Create `.mimir/` directory structure: `graph/`, `qdrant/`, `memories/`, `config.yaml`. Add `.mimir/` to `.gitignore`
  - Depends: T1
  - Blocks: T6, T7, T11
  - Category: `quick`
  - Skills: []
  - QA: `ls -la .mimir/` shows all subdirs, `cat .gitignore | grep mimir` exists

- [x] **T3. Kuzu Graph Schema**
  - What: Create `schema/graph_schema.cypher` with all node tables (BusinessGoal, Feature, Module, DataModel, RevenueStream, Risk, CustomerSegment, ExternalDep) and edge tables (implements, depends_on, enables, blocks, serves, requires, measured_by, funded_by). Add `metadata JSON` field to all nodes.
  - Depends: T1
  - Blocks: T7
  - Category: `quick`
  - Skills: []
  - QA: `python -c "import kuzu; db = kuzu.Database(':memory:'); conn = kuzu.Connection(db); [conn.execute(stmt) for stmt in open('schema/graph_schema.cypher').read().split(';') if stmt.strip()]"` executes without error

- [x] **T4. Memory Schema + Metadata Layer**
  - What: Create `schema/memory_schema.yaml` with all memory types (preference, decision, convention, episodic, correction), fields (id, content, type, confidence, source_session, created_at, last_used_at, decay_weight, expires_at, status), and custom metadata layer design
  - Depends: T1
  - Blocks: T6
  - Category: `quick`
  - Skills: []
  - QA: `python -c "import yaml; yaml.safe_load(open('schema/memory_schema.yaml'))"` parses without error

- [x] **T5. Qdrant Local Mode Config**
  - What: Configure Qdrant for local on-disk mode (qdrant-client with `path` parameter). Create separate collections for Mem0 memories and graph node embeddings. Collection names: `{project_name}_memories`, `{project_name}_graph_nodes`
  - Depends: T1
  - Blocks: T6, T7
  - Category: `quick`
  - Skills: []
  - QA: `python -c "from qdrant_client import QdrantClient; client = QdrantClient(path='.mimir/qdrant'); print(client.get_collections())"` runs without error

### Wave 2: Core Clients (After Wave 1 — Max Parallel)

- [x] **T6. Memory Client (Mem0 Library)**
  - What: Create `mimir/memory/client.py` wrapping Mem0 OSS. Implement: `add(messages, user_id, metadata)`, `search(query, user_id, limit, threshold)`, `delete(memory_id)`. Store custom types as metadata on Mem0 memories. Integrate with local Qdrant for vector storage.
  - Depends: T2, T4, T5
  - Blocks: T8, T10, T12, T18
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_memory_client.py -v` passes

- [x] **T7. Graph Client (Kuzu + Qdrant Embeddings)**
  - What: Create `mimir/graph/client.py` with Kuzu embedded DB. Implement: `create_node(table, properties)`, `create_edge(from_id, to_id, rel_type, properties)`, `get_neighbors(node_id, depth)`, `find_path(from_id, to_id)`, `semantic_search(query, top_k)`. Sync embeddings to Qdrant collection `{project}_graph_nodes`.
  - Depends: T2, T3, T5
  - Blocks: T12, T13, T14, T15
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_graph_client.py -v` passes

- [x] **T8. Memory Formatter**
  - What: Create `mimir/memory/formatter.py`. Takes raw Mem0 memories, formats compact context block. Target: < 250 tokens. Handles different memory types with different formatting.
  - Depends: T6
  - Blocks: T12
  - Category: `quick`
  - Skills: []
  - QA: `python -c "from mimir.memory.formatter import format_memories; print(len(format_memories([...])) < 250)"` returns True

- [x] **T9. Relevance Ranker**
  - What: Create `mimir/context/ranker.py`. Scores retrieved memories and graph nodes by relevance to current message. Only top-K make it into context.
  - Depends: None
  - Blocks: T12
  - Category: `unspecified-high`
  - Skills: []
  - QA: `pytest tests/test_ranker.py -v` passes

- [x] **T10. Confidence Scoring Module**
  - What: Create `mimir/extraction/confidence.py`. LLM-based confidence scoring for extracted facts. Returns 0.0-1.0 score. < 0.70 → reject, 0.70-0.85 → review queue, > 0.85 → auto-stage.
  - Depends: T6
  - Blocks: T18
  - Category: `unspecified-high`
  - Skills: []
  - QA: `pytest tests/test_confidence.py -v` passes

### Wave 3: MCP Server + Context Assembly (After Wave 2)

- [x] **T11. MCP Server Core**
  - What: Create `mimir/mcp/server.py` with stdio transport. Implement JSON-RPC handling, tool registration framework, project detection (read CWD → find `.mimir/`), error handling with graceful degradation.
  - Depends: T2
  - Blocks: T16, T17
  - Category: `deep`
  - Skills: []
  - QA: `echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m mimir.mcp.server` returns valid tool list

- [x] **T12. Context Assembler**
  - What: Create `mimir/context/assembler.py`. Takes user message, queries Memory Bank (via T6) and Knowledge Graph (via T7), assembles single context block using formatter (T8) and ranker (T9). Target: < 800 tokens total.
  - Depends: T6, T7, T8, T9
  - Blocks: T16, T17
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_context_assembler.py -v` passes, token count < 800

- [x] **T13. Map-Codebase: Static Analysis**
  - What: Create `mimir/ingest/static.py`. Parse Python/JS/TS files. Extract: modules (file paths), imports (dependencies), data models (class definitions), external dependencies. Create corresponding graph nodes.
  - Depends: T7
  - Blocks: T29
  - Category: `deep`
  - Skills: []
  - QA: `python -m mimir.ingest.static /path/to/test-project` creates graph nodes for all modules

- [x] **T14. Map-Codebase: LLM Doc Extraction**
  - What: Create `mimir/ingest/docs.py`. Feed business plan docs to LLM (cheap model). Extract entities, classify as node types, propose edges. Output: draft node/edge list for review (not auto-commit).
  - Depends: T7
  - Blocks: T29
  - Category: `deep`
  - Skills: []
  - QA: `python -m mimir.ingest.docs business-plan.md` outputs structured extraction

- [x] **T15. Map-Codebase: Embedding Generation**
  - What: Create `mimir/ingest/embeddings.py`. Generate embeddings for all graph node content. Store in Qdrant `{project}_graph_nodes` collection. Link back to Kuzu via `embedding_id` field.
  - Depends: T7
  - Blocks: T29
  - Category: `unspecified-high`
  - Skills: []
  - QA: `python -m mimir.ingest.embeddings` populates Qdrant with embeddings

### Wave 4: omo Integration + Observer (After Wave 3)

- [x] **T16. MCP Tool Registration**
  - What: Register MCP tools: `mimir_assemble_context`, `mimir_graph_search`, `mimir_memory_search`, `mimir_add_node`, `mimir_add_edge`. All tools use project detection from T11.
  - Depends: T11, T12
  - Blocks: T17, T22
  - Category: `unspecified-high`
  - Skills: []
  - QA: MCP server responds to all tool calls with correct project scoping

- [x] **T17. omo chat.params Hook**
  - What: Create `omo_hooks/context_injector.ts`. Factory pattern hook that calls `mimir_assemble_context` MCP tool, injects result into system context via `chat.params`. Includes timeout (200ms) and graceful fallback.
  - Depends: T11, T12, T16
  - Blocks: T29
  - Category: `unspecified-high`
  - Skills: []
  - QA: TypeScript compiles, hook injects context in OpenCode session

- [x] **T18. Observer Agent: Extraction**
  - What: Create `mimir/observer/extraction.py`. Monitors completed sessions. Extracts: new preferences, decisions made, corrections to old info, new entities mentioned. Outputs structured JSON proposals with confidence scores (via T10).
  - Depends: T6, T7, T10
  - Blocks: T20, T22
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_observer_extraction.py -v` passes

- [x] **T19. Observer Agent: Hallucination Guard**
  - What: Create `mimir/observer/hallucination.py`. Validates that extracted facts are grounded in actual conversation transcript. Rejects extractions not traceable to source turn.
  - Depends: T18
  - Blocks: T22
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_hallucination.py -v` passes, fake facts rejected

- [x] **T20. Observer Agent: Reconciler + Conflict Resolver**
  - What: Create `mimir/observer/reconciler.py`. Compares new extractions against existing memory. Implements ADD/UPDATE/DELETE/NOOP logic. Logs conflicts with both versions for user resolution.
  - Depends: T18
  - Blocks: T24
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_reconciler.py -v` passes, conflicts surfaced correctly

- [x] **T21. omo Agent Definition (observer.md)**
  - What: Create `.opencode/agents/observer.md` with YAML frontmatter. Model category: fast (cheap). Permissions: write=false, propose=true. Never auto-commits.
  - Depends: None
  - Blocks: T22
  - Category: `quick`
  - Skills: []
  - QA: Agent loads in omo, appears in agent list

### Wave 5: Automation + Tooling (After Wave 4)

- [ ] **T22. omo Post-Session Hook**
  - What: Create `omo_hooks/post_session_observer.ts`. Triggers Observer Agent on full transcript after session ends. Feeds session content to extraction pipeline.
  - Depends: T16, T18, T19, T21
  - Blocks: T29
  - Category: `unspecified-high`
  - Skills: []
  - QA: Hook fires after session, Observer receives transcript

- [ ] **T23. Decay Scheduler**
  - What: Create `mimir/observer/decay.py`. Time-based decay for memory weights. Supports manual trigger via CLI. Configurable decay rates per memory type. Flags memories below threshold for review.
  - Depends: T6
  - Blocks: T30
  - Category: `unspecified-high`
  - Skills: []
  - QA: `python -m mimir.observer.decay --dry-run` executes, weights decrease correctly

- [ ] **T24. CLI Review Dashboard**
  - What: Create `mimir/observer/review.py`. CLI interface for all pending proposals (memory + graph). Commands: list, approve, reject, edit. Single interface for human review gate.
  - Depends: T20
  - Blocks: T29
  - Category: `unspecified-high`
  - Skills: []
  - QA: `python -m mimir.observer.review list` shows pending proposals

- [ ] **T25. AGENTS.md Exporter**
  - What: Create `mimir/export/agents_md.py`. Generates hierarchical AGENTS.md from graph subgraphs. Auto-includes: active business goals, in-progress features, architecture decisions. Runs on-demand or after graph updates.
  - Depends: T7
  - Blocks: T32
  - Category: `unspecified-high`
  - Skills: []
  - QA: Generated AGENTS.md contains graph content in proper format

- [ ] **T26. History Trimmer**
  - What: Create `mimir/context/trimmer.py`. Rolling window on conversation history. Summarizes older turns (via cheap LLM), compresses instead of hard-dropping. Keeps context lean.
  - Depends: T12
  - Blocks: T30
  - Category: `unspecified-high`
  - Skills: []
  - QA: Turn 30 history + summary fits in token budget

- [ ] **T27. Audit Log + Context Inspector**
  - What: Create `mimir/observability/audit.py` (logs all memory/graph changes with source) and `mimir/observability/inspector.py` (debug tool showing retrieved memories, relevance scores, token count for any message).
  - Depends: T6, T7, T12
  - Blocks: T30
  - Category: `unspecified-high`
  - Skills: []
  - QA: Audit log shows complete trail, inspector shows accurate context breakdown

### Wave 6: Testing + Hardening (After Wave 5)

- [ ] **T28. Unit + Integration Tests**
  - What: Comprehensive test suite for all modules. Each module has corresponding test file. Mock external dependencies. Test error handling paths.
  - Depends: T6-T27
  - Blocks: T30
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/ --cov=mimir` achieves >80% coverage

- [ ] **T29. E2E Integration Test**
  - What: Full flow test: message → context assembly → LLM response → observer extraction → proposal → approval → memory recall in next session. Uses real (but test) OpenCode session.
  - Depends: T17, T22, T24
  - Blocks: F1-F4
  - Category: `deep`
  - Skills: []
  - QA: `pytest tests/test_e2e.py -v` passes

- [ ] **T30. Regression Test Suite**
  - What: Performance tests: memory retrieval latency (<100ms), graph query latency (<50ms), context assembly (<200ms), token budget (<800). Load tests: 10k memories, 5k graph nodes.
  - Depends: T28, T29
  - Blocks: F1-F4
  - Category: `deep`
  - Skills: []
  - QA: All regression tests pass, latency flat at turn 30

- [ ] **T31. Error Handling + Graceful Degradation Pass**
  - What: Add explicit error handling to all external calls. Define fallback behavior: Mem0 down → empty memory, Qdrant down → graph-only search, Kuzu corrupted → error message but don't crash. Add retry with exponential backoff where appropriate.
  - Depends: T6-T27
  - Blocks: F1-F4
  - Category: `unspecified-high`
  - Skills: []
  - QA: Simulate failures (kill processes), system degrades gracefully

- [ ] **T32. opencode.json Config + Documentation**
  - What: Create `opencode.json` snippet for MCP server registration (type: local). Create comprehensive README.md with setup instructions, architecture diagram, usage guide, troubleshooting.
  - Depends: T11, T17, T22
  - Blocks: F1-F4
  - Category: `quick`
  - Skills: []
  - QA: README renders correctly, setup instructions reproducible by new user

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `pytest`. Review all files for: `as any`/type ignoring, empty catches, console.log/print in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify no Docker dependencies introduced.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Run `map-codebase` on a test project. Start OpenCode session. Verify memories inject. State a new preference. Run Observer. Check review dashboard. Approve proposal. Verify next session recalls it. Test graph queries. Capture all evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Wave | Commit Message | Files |
|------|---------------|-------|
| 1 | `chore(init): bootstrap project with uv, pyproject.toml, schemas, and .mimir structure` | pyproject.toml, .python-version, schema/*, .mimir config |
| 2 | `feat(core): add memory client, graph client, and scoring modules` | mimir/memory/*, mimir/graph/* |
| 3 | `feat(mcp): add MCP server with context assembly and map-codebase command` | mimir/mcp/*, mimir/context/*, mimir/ingest/* |
| 4 | `feat(integration): add omo hooks, observer agent, and MCP tool registration` | omo_hooks/*, .opencode/agents/*, mimir/observer/* |
| 5 | `feat(tooling): add review dashboard, decay scheduler, AGENTS.md exporter` | mimir/observer/*, mimir/export/* |
| 6 | `test(all): add unit, integration, regression tests and error handling` | tests/* |

---

## Success Criteria

### Verification Commands
```bash
# Project bootstrap
python --version  # Expected: 3.10+
uv pip list | grep -E "kuzu|mem0|qdrant"  # Expected: all three installed

# Schema validation
python -c "import kuzu; db = kuzu.Database(':memory:'); conn = kuzu.Connection(db); [conn.execute(line) for line in open('schema/graph_schema.cypher').read().split(';') if line.strip()]"
# Expected: no errors

# Map codebase
python -m mimir.ingest.map_codebase /path/to/test-project
# Expected: .mimir/ directory created with graph + qdrant data

# MCP server starts
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m mimir.mcp.server
# Expected: JSON response with tool list

# Memory recall across sessions
pytest tests/test_e2e.py -k "test_memory_persists_across_sessions"
# Expected: PASS

# Latency flat at turn 30
pytest tests/regression/test_latency_flat.py
# Expected: PASS (turn 30 latency within 20% of turn 1)

# Context under budget
pytest tests/regression/test_token_budget.py
# Expected: PASS (assembled context < 800 tokens)
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] `map-codebase` works on a real project
- [ ] omo hooks fire correctly in OpenCode
- [ ] Review dashboard shows proposals
- [ ] Latency targets met
