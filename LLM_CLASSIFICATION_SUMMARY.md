# LLM-Based Query Classification - Implementation Summary

## Overview

Implemented intelligent query routing in `openspace_bridge.py` to classify queries as **structural** (use graph tools) or **semantic** (use vector search).

## Architecture

```
enrich_task()
    ↓
_classify_query(query)
    ├─ Quick Check (keyword match)
    └─ LLM Classification (gpt-3.5-turbo)
         ↓
    Query Type?
    ├─ Structural → _search_graph() → graph_query/graph_neighbors
    └─ Semantic   → _search_raw() → vector search
```

## Files Modified

### 1. `src/mimir/openspace_bridge.py`

**New additions:**
- `BridgeConfig.classification_model` (default: `gpt-3.5-turbo`)
- `BridgeConfig.classification_enabled` (default: `True`)
- `_CLASSIFICATION_PROMPT` template for LLM
- `_STRUCTURAL_KEYWORDS` list for quick check
- `_quick_structural_check()` - fast keyword-based classification
- `_classify_query()` - LLM-based classification
- `_search_graph()` - graph search for structural queries
- `_parse_graph_response()` - helper to parse graph API responses
- `_format_graph_result()` - helper to format graph results

**Modified:**
- `enrich_task()` - now uses `_classify_query()` to route queries

### 2. `src/mimir/config.py`

**New additions:**
- `MimirConfig.bridge_classification_model`
- `MimirConfig.bridge_classification_enabled`
- Updated `load()` to read these from config/env

## Configuration

| Setting | Environment Variable | Default | Description |
|---------|-------------------|---------|-------------|
| `classification_model` | `MIMIR_BRIDGE_CLASSIFY_MODEL` | `gpt-3.5-turbo` | LLM model for classification |
| `classification_enabled` | `MIMIR_BRIDGE_CLASSIFY_ENABLED` | `True` | Enable/disable LLM classification |

## Usage Examples

**Structural queries** (routed to graph tools):
- "How does the MCP server connect to the indexing system?"
- "Show path from mcp_server to indexing"
- "What depends on the config module?"

**Semantic queries** (routed to vector search):
- "What is the purpose of the config module?"
- "How do I use the search function?"
- "Explain how indexing works"

## Key Features

✅ **Two-stage classification**: Fast keyword check → LLM for ambiguous cases  
✅ **Configurable**: Toggle LLM classification on/off via env var  
✅ **Smart routing**: Automatically selects best search method  
✅ **Graph integration**: Extracts source/target from queries like "between X and Y"  
✅ **Fallback handling**: Graph → vector search if graph fails  

## Testing

Quick test:
```bash
cd /Users/ethanwheeler/Documents/Mimir
python3 -c "
from src.mimir.openspace_bridge import _quick_structural_check
print(_quick_structural_check('How does X connect to Y?'))  # structural
print(_quick_structural_check('What is X?'))  # semantic
"
```

## How It Works

### Stage 1: Quick Keyword Check
- Checks for structural keywords: `connect`, `path`, `depends`, `between`, etc.
- Returns `structural` if 2+ keywords OR structural phrases like "how does"
- Returns `semantic` if 0 keywords
- Returns `None` for ambiguous cases (let LLM decide)

### Stage 2: LLM Classification
- Uses fast model (default: `gpt-3.5-turbo`)
- Sends classification prompt with query
- Returns "structural" or "semantic"
- Falls back to keyword check on error

### Graph Search
- Extracts source/target from queries using regex
- Patterns: "between X and Y", "from X to Y", "X to Y"
- Calls graph API at `localhost:8000/api/graph/path`
- Falls back to `graph_neighbors` for single-node queries

## Next Steps

1. **Test with real queries** using `enrich_task_for_openspace()`
2. **Start web server** (`cd web && ./dev.sh`) for graph API
3. **Monitor logs** to see classification decisions
4. **Tune keywords/patterns** based on real usage

---
*Implementation completed: 2026-05-14*  
*Commit changes with: `git add -A && git commit -m "feat: Add LLM-based query classification for smart routing"`*
