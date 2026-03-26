# T2: Create .mimir/ Directory Structure

## Completed
- Created `.mimir/` directory with subdirectories: `graph/`, `qdrant/`, `memories/`
- Created `config.yaml` with project configuration schema
- Updated `.gitignore` to exclude `.mimir/`

## Config Schema
- project_name (string)
- version (string, default "1.0")
- embedding_model (string, default "text-embedding-3-small")
- memory_types (list)
- decay_config (object with rates per type)

## Notes
- No Docker files created (as per requirements)
- Only structure created, no actual data files

---

# T5: Configure Qdrant for Local On-Disk Mode

## Completed
- Created `schema/qdrant_config.yaml` with local mode configuration
- Collection templates: `{project_name}_memories`, `{project_name}_graph_nodes`
- Vector size: 1536 (OpenAI text-embedding-3-small)
- Distance metric: Cosine
- HNSW config: m=16, ef_construct=100
- Created test script `test_qdrant_local.py`
- QA verification passed: Qdrant initializes at `.mimir/qdrant`

## Notes
- Local mode requires no authentication
- Collections not created yet (config only)
- qdrant-client installed with `--break-system-packages` flag

---

## T4: Memory Schema Design

### Completed
- Created `schema/memory_schema.yaml` with complete memory type definitions
- Memory types defined: preference, decision, convention, episodic, correction
- All 10 fields defined with proper types, required status, defaults, and validation constraints
- YAML validates successfully with Python yaml.safe_load()

### Schema Structure
- version: "1.0"
- memory_types: array of 5 memory categories
- fields: object defining each field's type, required, default, and constraints

### Fields Defined
1. id (string, required, uuid format)
2. content (string, required)
3. type (enum: preference|decision|convention|episodic|correction, required)
4. confidence (number, 0.0-1.0, required)
5. source_session (string, required)
6. created_at (datetime, required)
7. last_used_at (datetime, required)
8. decay_weight (number, default 1.0)
9. expires_at (datetime, optional)
10. status (enum: active|decayed|archived, default "active")

---

# T1: Initialize Mimir Python Project

## Completed
- Initialized git repository in `/Users/ethanwheeler/Documents/Mimir`
- Created `.python-version` with "3.10"
- Created `pyproject.toml` with all required dependencies
- Created `.gitignore` with Python + uv entries
- Created virtual environment with `uv venv`
- Installed all dependencies via `uv pip install`

## Dependencies Installed
- kuzu: 0.11.3
- mem0ai: 1.0.7
- qdrant-client: 1.17.1
- fastapi: 0.135.1
- uvicorn: 0.42.0
- pytest: 9.0.2
- mcp: 1.26.0

## QA Verification
- `git status` shows clean repo (untracked files only)
- `python --version` shows 3.10.19 (matches .python-version)
- `uv pip list` shows all 62 packages installed

## Notes
- Used uv for all dependency management (not pip)
- No requirements.txt created (uv manages this)
- No Docker files created (as per requirements)
- pyproject.toml includes pytest config and ruff linting config
---

# T9: Relevance Ranker

## Completed
- Created `mimir/context/__init__.py` exporting `Ranker`
- Created `mimir/context/ranker.py` with `Ranker` class and `ScoredItem` dataclass
- Created `tests/test_ranker.py` with 31 tests (all passing)
- Fixed `pyproject.toml` to add `[tool.setuptools.packages.find]` with `include = ["mimir*"]` to resolve multi-top-level-package discovery error

## Implementation
- `_cosine_similarity(vec_a, vec_b)` — pure Python, no numpy; handles zero vectors (returns 0.0), raises ValueError on length mismatch
- `Ranker.score_memory(memory, query_embedding)` — reads `memory["embedding"]`, delegates to cosine similarity
- `Ranker.score_graph_node(node, query_embedding)` — reads `node["embedding"]`, delegates to cosine similarity
- `Ranker.rank_items(items, query_embedding, top_k, item_type)` — scores all items, sorts descending, slices top_k; validates item_type ("memory" | "graph_node")
- `ScoredItem` dataclass holds `item: Any` and `score: float`

## Notes
- No numpy/scipy dependency — stdlib `math` only
- `pyproject.toml` needed `[tool.setuptools.packages.find]` because `schema/` directory was being picked up as a top-level package
- `asyncio_mode = "auto"` in pytest config causes a warning (pytest-asyncio not installed), but tests pass fine

---

# T10: Confidence Scoring Module

## Completed
- Created `mimir/extraction/` package with `__init__.py` and `confidence.py`
- `ConfidenceScorer` class uses OpenAI chat completions API (gpt-4o-mini by default)
- `score_extraction(fact, context)` returns `ScoredFact` dataclass with score, threshold, reasoning
- `ConfidenceThreshold` enum: REJECT / REVIEW / AUTO_STAGE
- Threshold logic: < 0.70 → REJECT, 0.70–0.85 → REVIEW, > 0.85 → AUTO_STAGE
- Score clamped to [0.0, 1.0] regardless of LLM output
- Markdown code fence stripping in response parser (LLMs sometimes wrap JSON in ```json)
- 39 tests, all passing — fully mocked (no real API calls)

## Design Decisions
- `openai.OpenAI` client injected via constructor for testability (no global state)
- `temperature=0.0` default for deterministic scoring
- `classify()` public helper for re-classifying a score without LLM call
- `ScoredFact` is a dataclass (not TypedDict) to match `ScoredItem` pattern in ranker.py

## Notes
- openai package is installed (v2.29.0) but Pyright reports false-positive import error (venv not on Pyright path)
- Pre-existing LSP errors in graph/client.py and memory/__init__.py are unrelated to this task

---

# T15: Map-Codebase Embedding Generation

## Completed
- Created `mimir/ingest/embeddings.py` with `EmbeddingGenerator` class
- Created `tests/test_embeddings.py` with 25 tests (all passing)
- Updated `mimir/ingest/__init__.py` with lazy `__getattr__` export

## Implementation
- `EmbeddingGenerator.__init__()` — takes kuzu.Database, QdrantClient, OpenAI, project_name, batch_size
- `_ensure_collection()` — idempotent Qdrant collection creation
- `_fetch_all_nodes()` — queries all 8 node types from Kuzu, returns list of dicts
- `_build_text(node)` — joins node_type, name, description with ": " separator
- `_embed_batch(texts)` — calls OpenAI text-embedding-3-small, returns list of vectors
- `generate_embeddings(nodes=None)` — main entry point; batches, embeds, upserts to Qdrant, writes embedding_id back to Kuzu metadata
- `_update_node_embedding_id()` — SET n.metadata with embedding_id merged into existing metadata
- `main()` / `_build_clients_from_config()` — CLI entry point reads .mimir/config.yaml

## Design Decisions
- embedding_id stored in Kuzu node's metadata JSON field (not a separate column — schema has no embedding_id column)
- Qdrant point ID = UUID (not the Kuzu node ID) to avoid type conflicts
- Qdrant payload includes: node_id, node_type, name, description
- Batch failures are logged and skipped (other batches continue)
- `__init__.py` uses lazy `__getattr__` to avoid RuntimeWarning when running as `__main__`

## Gotchas
- Kuzu parameterized queries require parameter names to match column names exactly (e.g., `$description` not `$desc`)
- Kuzu `description` is NOT a reserved word — the issue was parameter name mismatch
- `set.count()` doesn't exist in Python — use `in` operator instead
- Running `python -m mimir.ingest.embeddings` when `__init__.py` eagerly imports the module causes `RuntimeWarning: found in sys.modules` — fixed with lazy `__getattr__`

---

# T14: Map-Codebase: LLM Doc Extraction

## Completed
- Created `mimir/ingest/__init__.py` package init
- Created `mimir/ingest/docs.py` with `DocExtractor` class
- Created `tests/test_doc_extraction.py` with 18 tests (all passing)
- Added `openai>=1.0.0` to `pyproject.toml` dependencies
- Created sample `business-plan.md` for testing

## Implementation
- `DocExtractor` class uses OpenAI chat completions API (gpt-4o-mini by default)
- `extract_from_file(file_path)` - reads markdown/text files, extracts entities via LLM
- `extract_from_text(text, source_file)` - extracts from raw text content
- `to_dict(result)` / `to_json(result)` - converts ExtractionResult to JSON output
- CLI entry point: `python -m mimir.ingest.docs <file>`

## Node Types Supported
- BusinessGoal, Feature, Module, DataModel
- RevenueStream, Risk, CustomerSegment, ExternalDep

## Edge Types Supported
- implements, depends_on, depends_on_feature, depends_on_data
- enables, enables_feature, blocks, blocks_module
- serves, serves_segment, requires, requires_data, requires_external
- measured_by, funded_by

## Output Format
```json
{
  "nodes": [{"type": "BusinessGoal", "name": "...", "description": "...", "source_evidence": "..."}],
  "edges": [{"from": "...", "to": "...", "type": "implements", "reasoning": "..."}]
}
```

## Design Decisions
- Output is for REVIEW only (not auto-committed to graph)
- Uses cheap model (gpt-4o-mini) for cost efficiency
- Validates node/edge types against schema (skips invalid ones)
- Supports markdown code fence stripping in LLM responses

## Notes
- Tests use mocked OpenAI client (no real API calls)
- QA with real document requires OPENAI_API_KEY environment variable
- LSP errors about openai/pytest imports are false positives (venv not on Pyright path)

---

# T13: Map-Codebase Static Analysis Pipeline

## Completed
- Created `mimir/ingest/static.py` with `StaticAnalyzer` class
- Created `tests/test_static_analysis.py` with 31 tests (all passing)
- Updated `mimir/ingest/__init__.py` with lazy `__getattr__` export for StaticAnalyzer

## Implementation
- `PythonParser` class — uses Python's `ast` module to parse `.py` files
  - Extracts imports (both `import X` and `from X import Y`)
  - Extracts class definitions with inheritance (base_classes)
  - Extracts functions (including async functions)
  - Counts lines for each node
- `JSTSParser` class — uses regex-based parsing for `.js`, `.jsx`, `.ts`, `.tsx` files
  - Extracts ES6 imports and CommonJS require() statements
  - Extracts class definitions with extends/implements
  - Extracts function declarations and arrow functions
  - Handles exported functions/classes
- `StaticAnalyzer` class — orchestrates parsing and graph node creation
  - `analyze_file(path)` — dispatches to appropriate parser based on extension
  - `analyze_directory(path, recursive, exclude_patterns)` — batch analysis
  - `create_graph_nodes(module, commit)` — creates Module, DataModel, Feature nodes
  - Significant function detection: >10 lines OR has docstring OR is exported
- CLI entry point: `python -m mimir.ingest.static <path>`

## Node Types Created
- Module — each source file becomes a Module node
- DataModel — class definitions become DataModel nodes
- Feature — significant functions become Feature nodes

## Edge Types Created
- depends_on — from module to imported modules
- implements — from class to parent class (inheritance)

## Design Decisions
- Regex patterns for JS/TS avoid external dependencies (no tree-sitter)
- GraphClient is optional in constructor (created lazily if not provided)
- Output is for REVIEW only (commit=False by default)
- Exclusion patterns: node_modules, __pycache__, .git, .venv, venv, dist, build, *.pyc, .mimir

## Gotchas
- JS/TS regex patterns need to handle both indented and non-indented code
- Python AST `lineno` and `end_lineno` attributes may be None for some nodes
- YAML import is conditional (fallback to defaults if yaml not installed)
- The `^` anchor in MULTILINE regex only matches at line start, not after newline

## Notes
- Tests use mocked GraphClient (no real graph commits)
- QA with real code requires valid .mimir/config.yaml
- LSP errors about ast.lineno are false positives (Pyright doesn't know about dynamic attributes)

---

# T21: omo Agent Definition (observer.md)

## Completed
- Created `.opencode/agents/observer.md` with YAML frontmatter
- Agent name: "observer"
- Model category: "fast" (cheap)
- Permissions: write=false, propose=true
- Never auto-commits (all proposals go to review dashboard)

## YAML Frontmatter
```yaml
---
name: observer
description: Monitors completed sessions and proposes memory/graph updates
model: fast
permissions:
  write: false
  propose: true
---
```

## Markdown Body Contents
- **Purpose**: Analyze completed sessions, propose memory/graph updates for review
- **What to Extract**: 5 types (preferences, decisions, corrections, entities, conventions)
- **Instructions**: Step-by-step workflow for extraction pipeline
- **When to Propose vs Skip**: Confidence score thresholds, conflict detection
- **Workflow**: Session ends → Load transcript → Extract → Validate → Check conflicts → Generate proposals → Review dashboard
- **Example**: Sample extraction from session excerpt showing JSON proposal format
- **Important Notes**: No write permissions, cite source evidence, low-confidence skipped

## Notes
- Directory `.opencode/agents/` created (didn't exist before)
- Agent follows omo agent definition format with YAML frontmatter + markdown body
- References T18 (Observer Extraction) pipeline modules
- Pre-existing LSP errors in other files are unrelated to this task

---

# T16: MCP Tool Registration

## Completed
- Modified `mimir/mcp/server.py` to register 5 Mimir tools via `_register_mimir_tools()`
- Added `tools/call` dispatch handler to `_dispatch()` method
- Added 43 new tests in `tests/test_mcp_server.py` (71 total, all passing)

## Tools Registered
1. `mimir_assemble_context` — calls ContextAssembler.assemble_context(user_message, user_id)
2. `mimir_graph_search` — calls GraphClient.get_neighbors() or semantic_search() based on params
3. `mimir_memory_search` — calls MemoryClient.search(query, user_id, limit, threshold)
4. `mimir_add_node` — calls GraphClient.create_node(table, properties)
5. `mimir_add_edge` — calls GraphClient.create_edge(from_id, to_id, rel_type, properties)

## Design Decisions
- All imports are lazy (inside handler functions) to avoid circular imports and startup cost
- `project_name` param overrides ProjectDetector auto-detection; falls back to "default" if neither available
- `_get_project_name(params)` helper centralizes project name resolution
- `_get_mimir_path(project_name, *parts)` builds paths relative to detected .mimir dir
- Validation errors (missing required params) raise `ValueError` directly before the try/except block
- Errors from client calls are wrapped in `RuntimeError` with tool name prefix for traceability
- `_process_message` return type changed to `Any` to accommodate both dict and list (batch) responses

## Patch Target Gotcha
- Handler functions use local imports (`from mimir.graph.client import GraphClient`)
- Tests must patch the source module (`mimir.graph.client.GraphClient`), NOT `mimir.mcp.server.GraphClient`
- Patching the server module namespace won't work for locally-imported names

## Notes
- `tools/call` method added to `_dispatch()` handlers dict alongside existing methods
- All 5 tools have JSON Schema `inputSchema` with proper `enum` constraints for node/edge types
- Pre-existing LSP errors in test file (lines 78-215) are Pyright false positives from original code

---

# T18: Observer Agent Extraction

## Completed
- Created `mimir/observer/__init__.py` package init
- Created `mimir/observer/extraction.py` with `SessionExtractor` class
- Created `tests/test_observer_extraction.py` with 15 tests (all passing)
- Integrated with `ConfidenceScorer` from `mimir.extraction.confidence`

## Implementation
- `SessionExtractor` class uses OpenAI chat completions API (gpt-4o-mini by default)
- `extract_from_transcript(transcript, source_session)` — main entry point
- `_extract_preferences(parsed, transcript)` — extracts user preferences
- `_extract_decisions(parsed, transcript)` — extracts decisions made
- `_extract_corrections(parsed, transcript)` — extracts corrections to previous info
- `_extract_entities(parsed, transcript)` — extracts new business entities
- `to_dict(result)` / `to_json(result)` — converts to JSON output
- CLI entry point: `python -m mimir.observer.extraction <transcript.json>`

## Extraction Types
- **Preferences**: UI preferences, workflow preferences, communication preferences
- **Decisions**: Architectural decisions, feature decisions, priority decisions
- **Corrections**: Facts that were wrong and are now corrected (includes `corrects_fact` field)
- **Entities**: Business entities (BusinessGoal, Feature, Module, DataModel, RevenueStream, Risk, CustomerSegment, ExternalDep, Person)

## Dataclasses
- `ExtractedPreference` — content, confidence, source_turn, evidence
- `ExtractedDecision` — content, confidence, source_turn, evidence
- `ExtractedCorrection` — content, confidence, source_turn, evidence, corrects_fact
- `ExtractedEntity` — name, entity_type, description, confidence, source_turn, evidence
- `ExtractionResult` — preferences, decisions, corrections, entities, source_session

## Confidence Scoring
- Each extraction is scored using `ConfidenceScorer.score_extraction()`
- Only extractions with threshold "review" or "auto_stage" are included
- Low-confidence extractions (< 0.70) are filtered out

## Design Decisions
- Output is for REVIEW only (not auto-committed to memory/graph)
- Uses cheap model (gpt-4o-mini) for cost efficiency
- ConfidenceScorer is injected via constructor for testability
- Transcript format: `[{"role": "user", "content": "...", "turn": 1}, ...]`

## Notes
- Tests use mocked OpenAI client and ConfidenceScorer (no real API calls)
- QA with real transcript requires OPENAI_API_KEY environment variable
- Pre-existing LSP errors in other files are unrelated to this task

---

# T19: Observer Agent Hallucination Guard

## Completed
- Created `mimir/observer/hallucination.py` with `HallucinationGuard` class
- Created `tests/test_hallucination.py` with 33 tests (all passing)
- Integrated with `mimir.observer.extraction` types

## Implementation
- `HallucinationGuard` class validates extractions against transcripts
- `validate(extraction, transcript)` — main entry point, returns ValidationResult
- `_check_grounding(evidence, source_turn, transcript_texts, transcript)` — verifies evidence exists
- `_calculate_similarity(text1, text2)` — fuzzy matching using SequenceMatcher
- `_check_contradiction(evidence, source_text)` — detects negation-based contradictions

## Dataclasses
- `ValidatedItem` — extraction that passed validation with similarity_score and adjusted_confidence
- `RejectedItem` — extraction that failed with reason and similarity_score
- `ValidationResult` — contains validated and rejected lists

## Validation Logic
- Exact match in source turn → valid (score 1.0)
- Fuzzy match above threshold (default 0.75) → valid with adjusted confidence
- Source turn doesn't exist → rejected with "source_turn_invalid"
- Evidence not found → rejected with "evidence_not_found"
- Contradiction detected → rejected with "contradicts_transcript"

## Confidence Adjustment
- Exact matches preserve original confidence
- Partial matches reduce confidence: `adjusted = confidence - penalty * (1 - score)`
- Default penalty: 0.15

## CLI Entry Point
- `python -m mimir.observer.hallucination <extraction.json> <transcript.json>`
- Supports `--threshold` flag for custom similarity threshold
- Supports `--output` flag for JSON output file

## Design Decisions
- No LLM used — pure string matching (difflib.SequenceMatcher)
- Default threshold 0.75 balances strictness vs paraphrased evidence
- Confidence adjustment penalizes fuzzy matches proportionally
- Transcript format: `[{"role": "user", "content": "...", "turn": 1}, ...]`

## Notes
- Tests verify fake facts are rejected when not traceable to transcript
- Fuzzy matching handles paraphrased evidence (e.g., "dark theme" vs "dark mode")
- Pre-existing LSP errors in other files are unrelated to this task

---

# T17: omo chat.params Hook (context_injector.ts)

## Completed
- Created `omo_hooks/context_injector.ts` with factory pattern
- Created `omo_hooks/package.json` with `@opencode-ai/plugin` dependency
- Created `omo_hooks/tsconfig.json` for TypeScript compilation
- TypeScript compiles cleanly (`tsc --noEmit` exits 0)

## Implementation
- `createContextInjector(deps)` returns `Pick<Hooks, "chat.params">`
- `chat.params` handler: extracts user message text → calls `mimir_assemble_context` with 200ms timeout → injects context into `output.options["system"]`
- Graceful fallback: on timeout or any error, logs warning and returns without modifying params
- Appends to existing `output.options["system"]` rather than replacing it

## Key Findings: @opencode-ai/plugin SDK Types
- `chat.params` output has: `{ temperature, topP, topK, options: Record<string, any> }`
- **No direct system field** — context injected via `output.options["system"]`
- `experimental.chat.system.transform` is the dedicated system-prompt hook (separate from `chat.params`)
- `UserMessage.parts` is an array of `{ type: string, text?: string }` — text parts joined with space
- MCP tool result: `{ content: [{ type: "text", text: string }], metadata: {...} }`

## Design Decisions
- `McpClient` interface is minimal (only `callTool`) — decoupled from full SDK client
- `withTimeout` uses `Promise` + `setTimeout` (no AbortController needed for this use case)
- `extractUserMessageText` joins all text parts — handles multi-part messages
- Logger is injectable for testability; defaults to `console.warn/error` with `[mimir:context_injector]` prefix
- `userId` defaults to `"default"` matching MCP server convention

## Gotchas
- `tsc` via `npx tsc` installs wrong package (npm `tsc@2.0.4`); must use `./node_modules/.bin/tsc`
- `@opencode-ai/plugin` v1.3.0 imports from `@opencode-ai/sdk` — `skipLibCheck: true` needed to avoid transitive type errors
- `module: "NodeNext"` + `moduleResolution: "NodeNext"` required for ESM compatibility with the plugin package

---

# T20: Observer Agent Reconciler + Conflict Resolver

## Completed
- Created `mimir/observer/reconciler.py` with `MemoryReconciler` class
- Created `tests/test_reconciler.py` with 29 tests (all passing)
- Integrated with `MemoryClient` from `mimir.memory.client`
- Integrated with `ExtractionResult` from `mimir.observer.extraction`

## Implementation
- `MemoryReconciler.__init__(memory_client, similarity_threshold)` — takes optional MemoryClient, threshold defaults to 0.85
- `reconcile(extractions, user_id)` — main entry point, returns ReconciliationResult
- `_reconcile_item(item, user_id, memory_type)` — reconciles single extracted item
- `_reconcile_correction(correction, user_id)` — handles corrections specially (may indicate UPDATE)
- `_find_existing_memory(content, user_id, memory_type)` — searches for similar memory using threshold
- `_determine_operation(new_item, existing)` — returns ADD/UPDATE/DELETE/NOOP
- `_detect_conflict(item, all_items, user_id)` — detects duplicates and contradictions
- `_extract_content(item)` — extracts content string from any extracted item type
- `_is_identical(content_a, content_b)` — case-insensitive comparison with strip()
- `_build_summary(operations)` — counts operations by type
- `to_dict(result)` / `to_json(result)` — serialization methods
- CLI entry point: `python -m mimir.observer.reconciler <extractions.json> <user_id>`

## Dataclasses
- `MemoryItem` — id, content, memory_type, metadata, score
- `Operation` — type, new_memory, existing_memory, reason
- `Conflict` — type, items, existing_items, resolution_required
- `ReconciliationResult` — operations, conflicts, summary

## Operations
- **ADD**: New memory not existing yet
- **UPDATE**: Similar memory exists but content changed
- **DELETE**: User explicitly removed/corrected previous memory (via corrections)
- **NOOP**: Identical memory already exists

## Conflict Detection
- **duplicate**: Same content extracted multiple times
- **contradiction**: Similar but different from existing memory
- **ambiguous**: Multiple corrections to the same fact

## Design Decisions
- Does NOT auto-apply operations (proposes only)
- Does NOT delete without explicit user confirmation
- Uses MemoryClient.search() with similarity threshold
- Gracefully handles search errors (falls back to ADD)
- All extraction types processed: preferences, decisions, corrections, entities

## Notes
- Tests use mocked MemoryClient (no real API calls)
- QA with real memory requires OPENAI_API_KEY and configured .mimir/
- Pre-existing LSP errors in other files are unrelated to this task
