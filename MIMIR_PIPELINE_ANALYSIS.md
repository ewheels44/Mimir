# Mimir Pipeline — Failure Analysis & Remediation Plan

> Generated: 2026-05-11  
> Status: **Active investigation**  
> Method: Full source code review (manual — RAG workflow unavailable due to missing deps)

---

## How to Use This Document

Each section covers one stage of the Mimir pipeline. Problems are numbered (`P-XX`) and tagged by severity:

| Tag | Meaning |
|-----|---------|
| 🔴 | **Critical** — silent failure, data loss risk, or security issue |
| 🟠 | **High** — degraded UX, incorrect results, or high cost |
| 🟡 | **Medium** — edge case, surprising behavior, or missing observability |

Each problem has a proposed fix or investigation path. Check off as you go.

---

## Table of Contents

1. [Stage 1 — Configuration & Initialization](#stage-1--configuration--initialization)
2. [Stage 2 — Document Ingestion & Indexing](#stage-2--document-ingestion--indexing)
3. [Stage 3 — Knowledge Graph Construction](#stage-3--knowledge-graph-construction)
4. [Stage 4 — Semantic Vector Store](#stage-4--semantic-vector-store)
5. [Stage 5 — MCP Server & Tool Serving](#stage-5--mcp-server--tool-serving)
6. [Stage 6 — Jcode Skill Integration](#stage-6--jcode-skill-integration)
7. [Stage 7 — OpenSpace Bridge](#stage-7--openspace-bridge)
8. [Stage 8 — File Watcher (Auto-reindex)](#stage-8--file-watcher-auto-reindex)
9. [Critical Single Points of Failure](#critical-single-points-of-failure)
10. [Quick Wins](#quick-wins)

---

## Stage 1 — Configuration & Initialization

**Source:** `src/mimir/config.py`  
**Entry point:** `MimirConfig.load()` → env vars → `.mimir/config.json` → defaults

### P-01 🔴 No API key = silent degradation

**Problem:** If neither `OPENROUTER_API_KEY` nor `OPENAI_API_KEY` is set (and no auth file exists), `api_key` resolves to `""`. The system starts without error. The `health_check` tool reports `"status": "degraded"` but doesn't block anything.

**Risk:** Every embedding call and LLM query fails at the API level. Users see empty search results or cryptic errors with no clear root cause.

**Proposed fix:**
- [ ] Add startup validation in `KnowledgeServer.__init__()` — raise or warn loudly if `api_key` is empty
- [ ] Add a `--check` mode that validates all required deps and keys before serving

### P-02 🟡 Config singleton never refreshes

**Problem:** `get_config()` caches in module-level `_config_instance`. Changes to env vars or `.mimir/config.json` mid-session are invisible.

**Risk:** Hot-reloading config (e.g., switching API keys) requires process restart.

**Proposed fix:**
- [ ] Optional TTL on config cache, or watch `.mimir/config.json` for changes
- [ ] Or: document that config is immutable per process and restart is required

### P-03 🟡 Project root misdetection in monorepos

**Problem:** `_detect_project_root()` walks up from `cwd` looking for `.git`, `pyproject.toml`, etc. In a monorepo subproject with its own `.git`, detection is wrong.

**Risk:** Indexes the wrong files, looks for config in the wrong place.

**Proposed fix:**
- [ ] Accept `PROJECT_ROOT` env var as highest-priority override (already exists but is undocumented)
- [ ] Add a `.mimir` marker file option for explicit root declaration

---

## Stage 2 — Document Ingestion & Indexing

**Source:** `src/mimir/indexing.py`  
**Entry point:** `index_with_progress()` → LlamaIndex `SimpleDirectoryReader` → `VectorStoreIndex`

### P-04 🟠 Embedding one doc at a time (N API calls)

**Problem:** `VectorStoreIndex.from_documents([doc0])` then `index.insert(doc)` per remaining file. For 5000 source files = 5000 API calls.

**Cost impact:** At ~$0.0001/embedding (text-embedding-3-small), a 5000-file codebase costs ~$0.50 per full reindex. With larger models this multiplies.

**Proposed fix:**
- [ ] Batch insert: collect all docs, call `from_documents(docs)` once
- [ ] LlamaIndex `VectorStoreIndex.from_documents()` already supports lists — just pass all docs

### P-05 🟡 No deduplication of identical content

**Problem:** Two files with identical content (generated code, boilerplate) produce duplicate embeddings and search results.

**Proposed fix:**
- [ ] Hash document text before embedding, skip if hash already in index
- [ ] Or use LlamaIndex's `doc_id` dedup (already partially exists via stable doc IDs)

### P-06 🟡 No file size guard on document loading

**Problem:** `MAX_FILE_SIZE_FOR_HASHING = 50MB` only affects hashing, not loading. A 200MB JSON or minified JS file will be loaded and chunked, potentially OOMing.

**Proposed fix:**
- [ ] Add `MAX_FILE_SIZE_FOR_LOADING` (e.g., 10MB) with skip + warning
- [ ] Or configurable via `.mimir/config.json` → `max_file_size`

### P-07 🟡 Incremental indexing not available from CLI

**Problem:** `python mimir-index.py --index` always triggers a full reindex. The `detect_changed_files()` logic exists but is only wired into the watcher.

**Proposed fix:**
- [ ] Add `--incremental` flag to CLI that runs `detect_changed_files` → `_refresh_or_insert_doc`
- [ ] Keep `--reindex` for full rebuild

---

## Stage 3 — Knowledge Graph Construction

**Source:** `src/mimir/knowledge_graph.py`  
**Entry point:** `extract_code_relationships()` → `CombinedExtractor` or `PythonASTExtractor`

### P-08 🟠 Tree-sitter is optional but graph quality depends on it

**Problem:** Without `tree-sitter-languages`, the graph only covers Python. TypeScript, Rust, and Go code is invisible.

**Risk:** In a multi-language project (like Mimir itself — Python + TypeScript + Rust), >50% of the codebase has no graph representation.

**Proposed fix:**
- [ ] Make `tree-sitter-languages` a required/strongly-recommended dependency
- [ ] Add install hint in `_make_extractor()` output: `pip install tree-sitter-languages`
- [ ] Or: bundle a lightweight grammar for the most common languages

### P-09 🟠 Call detection is too shallow

**Problem:** `_calls()` in `PythonASTExtractor` only captures top-level function identifiers. Method calls (`self.client.get()`), chained calls, and qualified names (`module.function()`) are mostly invisible.

**Impact:** "Show me everything that calls `auth.check()`" returns incomplete results.

**Proposed fix:**
- [ ] Track `ast.Attribute` calls (e.g., `self.client.get` → target `client.get`)
- [ ] For qualified names, store the longest meaningful prefix
- [ ] Consider using `ast.Call` with `func` resolution instead of just top-level names

### P-10 🟡 No cross-file import resolution

**Problem:** Imports resolve to module names (`"utils"`, `"../api/client"`) but don't link to actual file paths. The graph says "A imports X" but not "X lives in `src/api/client.py`".

**Proposed fix:**
- [ ] Build an import resolver that maps module names → file paths using the index manifest
- [ ] Or: post-process the graph to resolve relative imports against `sys.path`

### P-11 🟡 No type alias / generic tracking

**Problem:** Only `class`, `struct`, `interface`, `trait` are tracked. Type aliases (`type Handler = func(...)` in Go, `type MyList = List[int]` in Python) are invisible.

**Proposed fix:**
- [ ] Add `type_alias` entity type to extractors
- [ ] Low priority unless type-system queries are needed

---

## Stage 4 — Semantic Vector Store

**Source:** `src/mimir/indexing.py` + LlamaIndex + embedding model  
**Storage:** ChromaDB (LlamaIndex default) in `.knowledge/llamaindex/`

### P-12 🟠 Default embedding model is low-dimensional

**Problem:** `text-embedding-3-small` → 1536 dims. Code semantics (imports, control flow, APIs) are dense and subtle. Low-dimensional embeddings miss fine-grained relationships.

**Proposed fix:**
- [ ] Default to `text-embedding-3-large` (3072 dims) or allow easy override
- [ ] Document the quality/cost tradeoff in the system prompt

### P-13 🟠 No hybrid search (vector only)

**Problem:** Pure cosine similarity. Keyword searches ("where is `rate_limit` defined?") may not match if the term wasn't prominent in the embedded text.

**Proposed fix:**
- [ ] Add BM25 keyword retrieval path alongside vector search
- [ ] Re-rank results with cross-encoder (more expensive but much better recall)
- [ ] Or: use LlamaIndex's built-in hybrid retrieval if available in current version

### P-14 🟡 No configurable chunking strategy

**Problem:** LlamaIndex default chunking can split functions mid-body. Search results may be incomplete snippets.

**Proposed fix:**
- [ ] Configure chunk size + overlap tuned for code (e.g., 512 tokens, 50-token overlap)
- [ ] Consider AST-aware chunking: split at function/method boundaries

### P-15 🟡 No namespace isolation

**Problem:** All files from `docs/`, `src/`, `tests/` live in one flat vector space. Queries can't scope to a specific area.

**Proposed fix:**
- [ ] Add metadata `source_type` (doc, source, test) to each node
- [ ] Allow `search()` to accept a metadata filter parameter
- [ ] Or: use separate LlamaIndex indices per source type

---

## Stage 5 — MCP Server & Tool Serving

**Source:** `mcp_server_llamaindex.py`  
**Server:** FastMCP via stdio

### P-16 🔴 No authentication on MCP server

**Problem:** The MCP server has zero auth. Any local process that can access the stdio pipe can call any tool (search, query, reindex, delete files).

**Risk:** Malicious or buggy tools can delete the index, extract sensitive code, or abuse the LLM.

**Proposed fix:**
- [ ] Token-based auth header in MCP handshake
- [ ] Or: Unix socket with restricted permissions (chmod 700)
- [ ] Minimum: document the risk and recommend socket-based isolation

### P-17 🟠 No request timeouts

**Problem:** `query()`, `rag_workflow()`, and `knowledge_agent()` have no timeout. A hung LLM call blocks the entire MCP event loop indefinitely.

**Risk:** Jcode hangs, user can't do anything until the process is killed.

**Proposed fix:**
- [ ] Add `asyncio.wait_for()` wrapper around all tool calls with a configurable timeout (e.g., 30s default)
- [ ] Return a timeout error instead of hanging

### P-18 🟡 Synchronous blocking under async facade

**Problem:** Tools are `async def` but LlamaIndex operations (index loading, retrieval) are synchronous I/O. This blocks the event loop.

**Proposed fix:**
- [ ] Run blocking calls in `asyncio.to_thread()` or `loop.run_in_executor()`
- [ ] Or: use LlamaIndex's async query engine if available

### P-19 🔴 `--reindex` is destructive with no confirmation

**Problem:** Running with `--reindex` deletes `.knowledge/llamaindex/` immediately. In a headless MCP server, there's no "are you sure?" prompt.

**Risk:** Accidental full reindex loses the current index. Backups exist but are only as recent as the last reindex.

**Proposed fix:**
- [ ] Add `--confirm` flag requirement for destructive operations
- [ ] Auto-backup before reindex (already exists via `backup_index()` — just ensure it always runs)

### P-20 🟡 `rag_workflow` and `knowledge_agent` are opaque

**Problem:** These tools delegate to LangGraph workflows (`langgraph/workflows/rag.py`, `knowledge_agent.py`). Errors inside those workflows are returned as plain strings, no structured error info.

**Risk:** Debugging failures requires reading LangGraph internals.

**Proposed fix:**
- [ ] Return structured JSON with `status`, `error`, `steps` fields instead of plain text
- [ ] Add logging within the LangGraph workflows for traceability

---

## Stage 6 — Jcode Skill Integration

**Source:** `scripts/jcode/mimir_bridge.py`  
**Config:** `~/.jcode/skills/mimir-Mimir.json`, `~/.jcode/mcp.json`

### P-21 🟠 Auto-activate is always-on (no granularity)

**Problem:** `auto_activate: true` means Mimir runs for every Jcode session, even when you're just editing a README.

**Impact:** Unnecessary latency on every message + token burn for trivial tasks.

**Proposed fix:**
- [ ] Change `auto_activate` to `false`; require explicit `/skills enable mimir-Mimir` per session
- [ ] Or: add a `context_aware` flag that only activates when query mentions project code/architecture

### P-22 🟡 `usage_when` hints are unenforced suggestions

**Problem:** The `usage_when` field in the skill JSON is advisory. The LLM can (and will) invoke tools for unrelated queries if the description loosely matches.

**Proposed fix:**
- [ ] Document expected vs. unexpected trigger patterns
- [ ] Add a lightweight classifier in `enrich_task()` that gates tool invocation

### P-23 🟡 `max_context_tokens: 8000` is aggressive

**Problem:** Up to 8000 tokens of context can be injected per query. Combined with system prompt + tool results, total context can exceed model limits → silent truncation.

**Proposed fix:**
- [ ] Reduce default to 4000 tokens
- [ ] Add dynamic budget calculation based on model context window

---

## Stage 7 — OpenSpace Bridge

**Source:** `src/mimir/openspace_bridge.py`  
**Guardrails:** Circuit breaker, LRU cache, content filter, kill switch, freshness scoring

### P-24 🟠 Circuit breaker too sensitive

**Problem:** 3 consecutive failures → 60-second blackout. API glitch or transient network error triggers full lockout.

**Proposed fix:**
- [ ] Increase threshold to 5–10 failures before opening
- [ ] Add half-open state with single probe request before full close
- [ ] Or: exponential backoff instead of fixed 60s window

### P-25 🟡 Freshness scoring is misleading

**Problem:** `_compute_freshness()` uses index build timestamp, not actual source file freshness. A reindexed index with 6-month-old source code reports 100% freshness.

**Proposed fix:**
- [ ] Track the newest file mtime across all indexed files as the freshness anchor
- [ ] Or: compare index timestamp against the most recently modified source file

### P-26 🟡 Cache key is exact task string (poor hit rate)

**Problem:** Cache uses `sha256(task + top_k)` as key. "Fix auth" and "Fix auth for CORS" are different keys despite being related queries likely hitting the same code.

**Proposed fix:**
- [ ] Use semantic similarity for cache lookup instead of exact match
- [ ] Or: simpler approach — normalize common prefixes and cache at a more general level

### P-27 🟡 Silent failure when OpenSpace auth changes

**Problem:** API key resolution reads `opencode_auth.json`. If OpenSpace changes its auth format, the bridge catches the exception and returns empty results with no clear error.

**Proposed fix:**
- [ ] Add explicit version/format checking in `_resolve_api_key()`
- [ ] Return a structured error with "auth format changed" message

---

## Stage 8 — File Watcher (Auto-reindex)

**Source:** `src/mimir/watcher.py`  
**Dependency:** `watchdog` (Python package)

### P-28 🔴 Watcher silently disabled without `watchdog`

**Problem:** If `watchdog` isn't installed, `WATCHER_AVAILABLE = False`. The MCP server starts, reports "watcher disabled" to stderr, and continues. No user-facing warning in the MCP tool responses.

**Risk:** Users think auto-reindex is working but it isn't. Index silently falls behind.

**Proposed fix:**
- [ ] Add a `health_check` / `status` tool response that includes watcher availability
- [ ] Print clear instructions: `pip install watchdog` to enable
- [ ] Block MCP startup with an error instead of silently continuing

### P-29 🟡 Debounce can lose rapid changes

**Problem:** 2-second debounce. Two file saves within 2s → only one reindex. The second state may introduce bugs not reflected in the index.

**Proposed fix:**
- [ ] After reindex, do a second change-detection pass to catch files modified during reindex
- [ ] Or: track version numbers and re-run if changes were detected during the previous run

### P-30 🟠 No error recovery in incremental reindex

**Problem:** If `incremental_reindex()` fails on file #47/100, it logs the error and stops. The index is now partially updated — some files reindexed, some not — with no way to detect this.

**Proposed fix:**
- [ ] Track which files succeeded/failed and retry failures
- [ ] Add a consistency check: compare file count in manifest vs. index after reindex
- [ ] Or: fail over to full reindex if incremental fails

### P-31 🟡 Race condition: vector index updated before graph

**Problem:** File changes trigger both a 2s reindex timer (vector store) and a 5s KG timer. Between those windows, search finds new code but graph queries don't see its relationships.

**Proposed fix:**
- [ ] Chain the KG update to run after reindex completes (sequential)
- [ ] Or: unify into a single "update all" step with a shared lock

---

## Critical Single Points of Failure

| SPOF | Component | What breaks | Mitigation |
|------|-----------|-------------|------------|
| 1 | **API keys** | All LLM + embedding calls fail | Startup validation (P-01) + health check |
| 2 | **LlamaIndex version** | Breaking API changes | Pin versions, test on upgrade |
| 3 | **`.knowledge/llamaindex/` dir** | No search, no queries | Auto-backup (P-19), restore script |
| 4 | **Rust web server** | Graph queries silently fail | Health check integration (P-20) |
| 5 | **File watcher** | Index silently stale | Explicit warning (P-28) |

---

## Quick Wins

These can be fixed with minimal effort and high impact:

| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| Q1 | Add `watchdog` install check to MCP server startup | 15 min | Prevents P-28 |
| Q2 | Add API key validation at server startup | 30 min | Prevents P-01 |
| Q3 | Batch document embedding (pass all docs to `from_documents()`) | 1 hour | Fixes P-04, major speedup |
| Q4 | Add request timeouts to all MCP tools | 1 hour | Prevents P-17 |
| Q5 | Auto-backup before every `--reindex` | 30 min | Mitigates P-19 |
| Q6 | Include watcher status in `health_check` response | 30 min | Addresses P-28 |
| Q7 | Increase circuit breaker threshold to 5 | 5 min | Addresses P-24 |

---

## Investigation Log

| Date | What was investigated | Finding | Status |
|------|----------------------|---------|--------|
| 2026-05-11 | Full pipeline source code review | 31 problems identified across 8 stages | ✅ Complete |
| | `rag_workflow` tool invocation | Failed — system Python missing `mcp` dependency | ⏳ Pending |
| | `knowledge_agent` tool invocation | Not tested — same dependency issue | ⏳ Pending |
| | LangGraph workflow internals | Not yet reviewed | ⏳ Pending |

---

*This document is a living artifact. Update as problems are resolved.*