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
