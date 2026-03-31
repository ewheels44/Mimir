"""Mimir Web UI - FastAPI Backend

Changes vs original:
  - _graph_cache: in-memory cache keyed on file mtimes (eliminates rebuild on every request)
  - _build_graph_data(): extracted graph-building logic with O(1) suffix-index matching
  - GET /api/graph now accepts ?mode=summary|full and ?min_degree=N
  - GET /api/graph/edges  — edge-only endpoint for lazy client loading
  - GET /api/metrics/components — per-component (embedding/llm_in/llm_out) spend totals
  - GET /api/metrics/breakdown   — now includes component costs
  - Inline graph HTML: two-phase load (nodes first, then edges in background)
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))

from mcp_server_llamaindex import ServerConfig, KnowledgeServer
from src.mimir.metrics import get_tracker, MetricsTracker

app = FastAPI(title="Mimir Web UI", version="2.0.0")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryRequest(BaseModel):
    question: str


class Node(BaseModel):
    id: str
    label: str
    type: str
    metadata: Dict[str, Any]


class Edge(BaseModel):
    source: str
    target: str
    label: str
    type: str


class GraphData(BaseModel):
    nodes: List[Node]
    edges: List[Edge]


# ---------------------------------------------------------------------------
# Module-level graph cache
#
# Structure: _graph_cache = {
#   "cache_key": str,          # mtime-based fingerprint
#   "nodes": List[dict],
#   "edges": List[dict],
#   "degree": Dict[str, int],  # node_id -> edge count
# }
# ---------------------------------------------------------------------------

_graph_cache: Dict[str, Any] = {}
_server_config: Optional[ServerConfig] = None


def _graph_cache_key(config: ServerConfig) -> str:
    """Build a cheap cache key from the mtimes of the two source files."""
    parts = []
    index_file = config.knowledge_dir / "index_store.json"
    rel_file = config.knowledge_dir.parent / "code_relationships.json"
    for p in (index_file, rel_file):
        try:
            parts.append(f"{p}:{p.stat().st_mtime_ns}")
        except OSError:
            parts.append(f"{p}:missing")
    return "|".join(parts)


def _build_suffix_index(
    file_path_to_id: Dict[str, str],
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Build a multi-level suffix index so relationship source/target matching
    is O(1) instead of O(n).

    Returns: { suffix_segment: [(full_path, node_id), ...] }
    The suffix_segment is every contiguous tail of the path components.
    E.g. "src/mimir/indexing.py" registers under:
      "indexing.py", "mimir/indexing.py", "src/mimir/indexing.py"
    """
    idx: Dict[str, List[Tuple[str, str]]] = {}
    for fp, did in file_path_to_id.items():
        parts = Path(fp).parts
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            idx.setdefault(suffix, []).append((fp, did))
    return idx


def _lookup_in_suffix_index(
    target: str,
    suffix_idx: Dict[str, List[Tuple[str, str]]],
) -> Optional[str]:
    """Return node_id for the best match of *target* in the suffix index, or None."""
    # Try exact suffix first, then stem (without extension), then basename
    candidates = [
        target,
        target if target.endswith(".py") else target + ".py",
        Path(target).name,
        Path(target).stem + ".py",
        Path(target).stem,
    ]
    for key in candidates:
        matches = suffix_idx.get(key)
        if matches:
            return matches[0][1]  # take first match
    return None


def _build_graph_data(config: ServerConfig) -> Dict[str, Any]:
    """
    Build the full node+edge payload and cache it.
    Returns a dict with keys: nodes, edges, degree, cache_key.
    """
    cache_key = _graph_cache_key(config)
    if _graph_cache.get("cache_key") == cache_key:
        return _graph_cache

    server = KnowledgeServer(config)
    index = server.get_index()
    if index is None:
        result = {"cache_key": cache_key, "nodes": [], "edges": [], "degree": {}}
        _graph_cache.update(result)
        return result

    # --- Build nodes --------------------------------------------------------
    nodes: List[dict] = []
    file_path_to_id: Dict[str, str] = {}

    for doc_id, doc in index.storage_context.docstore.docs.items():
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        file_path = metadata.get("file_path", metadata.get("file_name", "unknown"))
        file_name = metadata.get("file_name", "unknown")

        if file_path in file_path_to_id:
            continue
        file_path_to_id[file_path] = doc_id

        node_type = (
            "code"
            if file_name.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"))
            else "document"
        )

        nodes.append(
            {
                "id": doc_id,
                "label": file_name,
                "type": node_type,
                "metadata": metadata,
            }
        )

    # Build O(1) suffix index
    suffix_idx = _build_suffix_index(file_path_to_id)

    # --- Build edges --------------------------------------------------------
    edges: List[dict] = []
    relationships_path = config.knowledge_dir.parent / "code_relationships.json"

    if relationships_path.exists():
        try:
            with open(relationships_path) as f:
                rel_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            rel_data = {}

        for rel in rel_data.get("relationships", []):
            source_file = rel.get("source", "")
            target = rel.get("target", "")
            rel_type = rel.get("relation_type", "unknown")

            source_id = _lookup_in_suffix_index(source_file, suffix_idx)
            if source_id is None:
                continue

            target_id = _lookup_in_suffix_index(target, suffix_idx)

            # External module node (not in the index)
            if target_id is None:
                target_id = f"external:{target}"
                ext_label = (
                    Path(target).name
                    if "/" in target or "\\" in target
                    else target.split(".")[-1]
                )
                if not any(n["id"] == target_id for n in nodes):
                    nodes.append(
                        {
                            "id": target_id,
                            "label": ext_label,
                            "type": "module",
                            "metadata": {"module_path": target, "external": True},
                        }
                    )

            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "label": rel_type.replace("_", " "),
                    "type": rel_type,
                    "id": f"e-{source_id[:8]}-{target_id[:8]}-{rel_type[:4]}",
                }
            )

    # --- Compute degree map (for min_degree filtering) ----------------------
    degree: Dict[str, int] = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1

    result = {
        "cache_key": cache_key,
        "nodes": nodes,
        "edges": edges,
        "degree": degree,
    }
    _graph_cache.clear()
    _graph_cache.update(result)
    return result


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    global _server_config

    if not os.environ.get("PROJECT_ROOT"):
        os.environ["PROJECT_ROOT"] = str(Path.cwd())
    if not os.environ.get("KNOWLEDGE_DIR"):
        pr = Path(os.environ["PROJECT_ROOT"])
        os.environ["KNOWLEDGE_DIR"] = str(pr / ".knowledge" / "llamaindex")

    _server_config = ServerConfig.from_env()
    print(f"[Startup] project={_server_config.project_root}", file=sys.stderr)


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTMLResponse(content=_GRAPH_HTML)


@app.get("/metrics", response_class=HTMLResponse)
async def read_metrics():
    metrics_path = Path(__file__).parent / "templates" / "metrics.html"
    return HTMLResponse(content=metrics_path.read_text())


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------


@app.get("/api/graph", response_model=GraphData)
async def get_graph(
    mode: str = Query(
        "full", description="'summary' = nodes only, 'full' = nodes+edges"
    ),
    min_degree: int = Query(0, description="Exclude nodes with fewer connections"),
):
    """Return the knowledge graph. Use mode=summary for fast initial render,
    then fetch /api/graph/edges to progressively add edges."""
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()

        data = _build_graph_data(_server_config)
        degree = data["degree"]

        if min_degree > 0:
            keep_ids = {nid for nid, deg in degree.items() if deg >= min_degree}
            nodes = [
                n
                for n in data["nodes"]
                if n["id"] in keep_ids or n.get("type") != "module"
            ]
        else:
            nodes = data["nodes"]

        if mode == "summary":
            return GraphData(nodes=[Node(**n) for n in nodes], edges=[])

        # Apply min_degree to edges too
        node_ids = {n["id"] for n in nodes}
        edges = [
            e
            for e in data["edges"]
            if e["source"] in node_ids and e["target"] in node_ids
        ]
        return GraphData(
            nodes=[Node(**n) for n in nodes],
            edges=[Edge(**e) for e in edges],
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/edges")
async def get_graph_edges(
    min_degree: int = Query(0),
):
    """Return edges only. Call after /api/graph?mode=summary to lazy-load
    relationships without blocking the initial render."""
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()

        data = _build_graph_data(_server_config)
        degree = data["degree"]

        if min_degree > 0:
            keep_ids = {nid for nid, deg in degree.items() if deg >= min_degree}
            edges = [
                e
                for e in data["edges"]
                if e["source"] in keep_ids and e["target"] in keep_ids
            ]
        else:
            edges = data["edges"]

        return {"edges": edges, "count": len(edges)}

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/graph/invalidate")
async def invalidate_graph_cache():
    """Force graph cache rebuild on next request (call after reindex)."""
    _graph_cache.clear()
    return {"status": "cache cleared"}


# ---------------------------------------------------------------------------
# Metrics API
# ---------------------------------------------------------------------------


@app.get("/api/metrics/summary")
async def get_metrics_summary(days: int = Query(30, ge=1, le=365)):
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        tracker = MetricsTracker(_server_config.project_root)
        return tracker.get_summary(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/daily")
async def get_metrics_daily(days: int = Query(30, ge=1, le=365)):
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        tracker = MetricsTracker(_server_config.project_root)
        return tracker.get_daily_stats(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/breakdown")
async def get_metrics_breakdown(days: int = Query(30, ge=1, le=365)):
    """Per-query-type breakdown including component cost split."""
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        tracker = MetricsTracker(_server_config.project_root)
        summary = tracker.get_summary(days)
        if not summary.get("by_type"):
            raise HTTPException(status_code=404, detail="No metrics found")
        return [{"query_type": qt, **data} for qt, data in summary["by_type"].items()]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/components")
async def get_metrics_components(days: int = Query(30, ge=1, le=365)):
    """Return aggregate embedding / llm_input / llm_output spend totals."""
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        tracker = MetricsTracker(_server_config.project_root)
        return tracker.get_component_totals(days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Search & query API
# ---------------------------------------------------------------------------


@app.post("/api/search")
async def search(request: SearchRequest):
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        server = KnowledgeServer(_server_config)
        results_text = server.search(request.query, request.top_k)

        if (
            "No relevant documents found" in results_text
            or "No knowledge base found" in results_text
        ):
            return [{"title": "No Results", "snippet": results_text, "source": ""}]

        import re

        results = []
        for entry in results_text.split("\n\n"):
            if not entry.strip():
                continue
            lines = entry.strip().split("\n")
            header = lines[0]
            content = "\n".join(lines[1:]) if len(lines) > 1 else ""
            match = re.match(r"\[\d+\]\s+(.+?)\s+\(score:", header)
            fname = match.group(1) if match else "Unknown"
            results.append(
                {"title": fname, "snippet": content.strip() or header, "source": fname}
            )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query")
async def query(request: QueryRequest):
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        server = KnowledgeServer(_server_config)
        answer = server.query(request.question)
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        return KnowledgeServer(_server_config).get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Inline graph HTML  (two-phase load: nodes → edges)
# ---------------------------------------------------------------------------

_GRAPH_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mimir Knowledge Base</title>
    <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
    <script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
    <script src="https://unpkg.com/marked@9.1.6/marked.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; overflow: hidden; }
        .container { display: flex; height: 100vh; }
        .sidebar { width: 320px; background: #1e293b; border-right: 1px solid #334155; display: flex; flex-direction: column; padding: 20px; overflow-y: auto; }
        .logo { font-size: 24px; font-weight: bold; color: #60a5fa; margin-bottom: 20px; }
        .search-box { margin-bottom: 20px; }
        .search-box input { width: 100%; padding: 12px; border: 1px solid #475569; border-radius: 8px; background: #334155; color: #e2e8f0; font-size: 14px; outline: none; }
        .search-box input:focus { border-color: #60a5fa; }
        .search-box button { width: 100%; padding: 12px; margin-top: 8px; border: none; border-radius: 8px; background: #3b82f6; color: white; font-size: 14px; cursor: pointer; }
        .search-box button:hover { background: #2563eb; }
        .query-box { margin-bottom: 20px; }
        .query-box textarea { width: 100%; padding: 12px; border: 1px solid #475569; border-radius: 8px; background: #334155; color: #e2e8f0; font-size: 14px; outline: none; resize: vertical; min-height: 80px; font-family: inherit; }
        .query-box textarea:focus { border-color: #60a5fa; }
        .query-box button { width: 100%; padding: 12px; margin-top: 8px; border: none; border-radius: 8px; background: #8b5cf6; color: white; font-size: 14px; cursor: pointer; }
        .query-box button:hover { background: #7c3aed; }
        .query-box button:disabled { background: #475569; cursor: not-allowed; }
        .controls { margin-top: auto; padding-top: 20px; border-top: 1px solid #334155; }
        .controls h3 { font-size: 14px; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        .control-btn { width: 100%; padding: 10px; margin-bottom: 8px; border: 1px solid #475569; border-radius: 6px; background: transparent; color: #cbd5e1; font-size: 13px; cursor: pointer; }
        .control-btn:hover { background: #334155; border-color: #60a5fa; }
        .toggle-label { display: flex; align-items: center; padding: 8px 0; cursor: pointer; font-size: 13px; color: #cbd5e1; }
        .toggle-label input[type="checkbox"] { margin-right: 10px; width: 16px; height: 16px; cursor: pointer; accent-color: #3b82f6; }
        .toggle-color { width: 12px; height: 12px; border-radius: 2px; margin-left: 8px; }
        .main-content { flex: 1; display: flex; flex-direction: column; position: relative; }
        .toolbar { height: 50px; background: #1e293b; border-bottom: 1px solid #334155; display: flex; align-items: center; padding: 0 20px; gap: 10px; }
        .toolbar button { padding: 8px 16px; border: 1px solid #475569; border-radius: 6px; background: transparent; color: #cbd5e1; font-size: 13px; cursor: pointer; }
        .toolbar button:hover { background: #334155; }
        .toolbar button.active { background: #3b82f6; border-color: #3b82f6; }
        #graph-container { flex: 1; position: relative; background: #0f172a; }
        #cy { width: 100%; height: 100%; }
        .loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 18px; color: #60a5fa; text-align: center; }
        .loading-sub { font-size: 13px; color: #94a3b8; margin-top: 8px; }
        .edge-loading-badge { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid #334155; border-radius: 20px; padding: 6px 14px; font-size: 12px; color: #94a3b8; display: none; z-index: 10; }
        .detail-panel { position: absolute; right: 20px; top: 20px; width: 300px; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.5); display: none; max-height: 60vh; overflow-y: auto; z-index: 1000; }
        .detail-panel.visible { display: block; }
        .detail-panel h3 { font-size: 16px; color: #60a5fa; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #334155; }
        .detail-row { margin-bottom: 12px; }
        .detail-row label { display: block; font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .detail-row .value { display: block; font-size: 14px; color: #e2e8f0; word-break: break-word; }
        .results-panel { position: fixed; right: 0; top: 0; width: 450px; height: 100vh; background: #1e293b; border-left: 1px solid #334155; padding: 20px; box-shadow: -5px 0 30px rgba(0,0,0,0.5); display: none; overflow-y: auto; z-index: 2000; transition: transform 0.3s ease; }
        .results-panel.visible { display: block; }
        .results-panel h3 { font-size: 16px; color: #60a5fa; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #334155; }
        .results-panel .collapse-btn { position: absolute; top: 20px; right: 20px; background: transparent; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 6px; z-index: 2001; }
        .results-panel.collapsed { transform: translateX(calc(100% - 40px)); }
        .results-panel.collapsed .collapse-btn { left: 8px; right: auto; background: #1e293b; border: 1px solid #334155; }
        .results-panel .collapse-btn #collapseIcon { display: inline-block; transition: transform 0.3s ease; }
        .results-panel.collapsed .collapse-btn #collapseIcon { transform: rotate(180deg); }
        .markdown-content { color: #e2e8f0; line-height: 1.6; }
        .markdown-content h1,.markdown-content h2,.markdown-content h3 { color: #60a5fa; margin-top: 16px; margin-bottom: 8px; }
        .markdown-content p { margin-bottom: 12px; }
        .markdown-content code { background: #334155; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #fbbf24; }
        .markdown-content pre { background: #0f172a; padding: 16px; border-radius: 8px; overflow-x: auto; margin-bottom: 16px; border: 1px solid #334155; }
        .markdown-content pre code { background: transparent; padding: 0; color: #e2e8f0; }
        .result-item { padding: 10px; margin-bottom: 8px; background: #334155; border-radius: 6px; cursor: pointer; }
        .result-item:hover { background: #475569; }
        .result-item .title { font-weight: 500; margin-bottom: 4px; }
        .result-item .snippet { font-size: 12px; color: #94a3b8; }

        /* degree filter row */
        .filter-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 12px; color: #94a3b8; }
        .filter-row input[type=range] { flex: 1; }
        .filter-row span { min-width: 20px; text-align: right; }
    </style>
</head>
<body>
<div class="container">
    <aside class="sidebar">
        <div class="logo">Mimir</div>
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search knowledge base...">
            <button onclick="performSearch()">Search</button>
        </div>
        <div class="query-box">
            <textarea id="queryInput" placeholder="Ask a question..."></textarea>
            <button id="askButton" onclick="performQuery()">Ask</button>
        </div>
        <div class="controls">
            <h3>Layout</h3>
            <button class="control-btn" onclick="changeLayout('cose')">Force-directed</button>
            <button class="control-btn" onclick="changeLayout('circle')">Circle</button>
            <button class="control-btn" onclick="changeLayout('grid')">Grid</button>
            <button class="control-btn" onclick="changeLayout('dagre')">Hierarchy</button>
            <h3 style="margin-top:16px">View</h3>
            <button class="control-btn" onclick="fitGraph()">Fit to screen</button>
            <button class="control-btn" onclick="resetZoom()">Reset zoom</button>
            <button class="control-btn" onclick="toggleLabels()">Toggle labels</button>

            <h3 style="margin-top:16px">Min connections</h3>
            <div class="filter-row">
                <input type="range" id="minDegree" min="0" max="20" step="1" value="0"
                       oninput="document.getElementById('minDegreeVal').textContent=this.value">
                <span id="minDegreeVal">0</span>
                <button class="control-btn" style="width:auto;padding:4px 10px"
                        onclick="reloadWithDegree()">Apply</button>
            </div>

            <h3 style="margin-top:16px">Physics</h3>
            <label class="toggle-label">
                <input type="checkbox" id="floating-mode" onchange="toggleFloatingMode()">
                <span>Floating mode</span>
            </label>
            <div style="margin-top:8px">
                <div style="font-size:11px;color:#94a3b8;margin-bottom:5px">Repulsion strength</div>
                <div class="filter-row">
                    <input type="range" id="repulsion-slider" min="1000" max="50000" step="1000" value="10000"
                           oninput="updateRepulsionStrength()">
                    <span id="repulsion-val" style="min-width:40px;font-size:11px">10k</span>
                </div>
            </div>

            <h3 style="margin-top:16px">Relationships</h3>
            <label class="toggle-label"><input type="checkbox" id="toggle-calls" checked onchange="updateEdgeVisibility()"><span>Calls</span><span class="toggle-color" style="background:#f59e0b"></span></label>
            <label class="toggle-label"><input type="checkbox" id="toggle-imports-module" checked onchange="updateEdgeVisibility()"><span>Imports module</span><span class="toggle-color" style="background:#10b981"></span></label>
            <label class="toggle-label"><input type="checkbox" id="toggle-imports-from" checked onchange="updateEdgeVisibility()"><span>Imports from</span><span class="toggle-color" style="border:2px dashed #10b981;background:transparent"></span></label>
            <label class="toggle-label"><input type="checkbox" id="toggle-inherits-from" checked onchange="updateEdgeVisibility()"><span>Inherits from</span><span class="toggle-color" style="background:#ec4899"></span></label>
        </div>
    </aside>

    <main class="main-content">
        <div class="toolbar">
            <button onclick="reloadGraph()" class="active">Full graph</button>
            <button onclick="loadSearchResults()">Search results</button>
            <button onclick="clearSelection()">Clear selection</button>
            <a href="/metrics" style="margin-left:auto;padding:8px 16px;border:1px solid #475569;border-radius:6px;background:transparent;color:#cbd5e1;font-size:13px;text-decoration:none">Metrics dashboard</a>
        </div>
        <div id="graph-container">
            <div id="cy"></div>
            <div class="loading" id="loading">
                <div>Loading nodes...</div>
                <div class="loading-sub" id="loading-sub"></div>
            </div>
            <div class="edge-loading-badge" id="edgeBadge">Loading relationships...</div>
        </div>
        <div class="detail-panel" id="detailPanel"><h3>Node details</h3><div id="detailContent"></div></div>
        <div class="results-panel" id="resultsPanel">
            <button class="collapse-btn" onclick="toggleResultsPanel()"><span id="collapseIcon">−</span></button>
            <h3 id="resultsTitle">Results</h3>
            <div id="queryDisplay" style="font-size:12px;color:#94a3b8;margin-bottom:16px;padding:8px;background:#0f172a;border-radius:6px;display:none"></div>
            <div id="resultsContent"></div>
        </div>
    </main>
</div>

<script>
let cy = null;
let currentLayout = 'cose';
let labelsVisible = true;
let currentMinDegree = 0;

// --- Floating physics state -----------------------------------------------
let floatingMode = false;
let repulsionStrength = 10000;
let physicsAnimationId = null;
let nodeVelocities = new Map();
let spatialGrid = null;
const GRID_CELL = 200;

class SpatialGrid {
    constructor(cellSize) { this.cellSize = cellSize; this.cells = new Map(); this.nodePos = new Map(); }
    clear() { this.cells.clear(); this.nodePos.clear(); }
    key(x, y) { return `${Math.floor(x/this.cellSize)},${Math.floor(y/this.cellSize)}`; }
    insert(id, x, y, degree) {
        this.nodePos.set(id, { x, y, degree });
        const k = this.key(x, y);
        if (!this.cells.has(k)) this.cells.set(k, []);
        this.cells.get(k).push({ id, x, y, degree });
    }
    neighbors(x, y, radius) {
        const out = [], r2 = radius * radius, cr = Math.ceil(radius / this.cellSize);
        const cx = Math.floor(x / this.cellSize), cy2 = Math.floor(y / this.cellSize);
        for (let dx = -cr; dx <= cr; dx++) {
            for (let dy = -cr; dy <= cr; dy++) {
                const cell = this.cells.get(`${cx+dx},${cy2+dy}`);
                if (cell) for (const n of cell) {
                    const d2 = (x-n.x)**2 + (y-n.y)**2;
                    if (d2 < r2) out.push({ ...n, d2 });
                }
            }
        }
        return out;
    }
}

function startFloatingPhysics() {
    if (physicsAnimationId) cancelAnimationFrame(physicsAnimationId);
    spatialGrid = new SpatialGrid(GRID_CELL);
    const damping = 0.92, dt = 0.16, maxR = 400, minMove = 0.1;
    let frame = 0;

    function tick() {
        if (!floatingMode) return;
        frame++;
        const nodes = cy.nodes();
        const n = nodes.length;
        if (n > 500 && frame % 2 !== 0) { physicsAnimationId = requestAnimationFrame(tick); return; }
        if (n > 1000 && frame % 3 !== 0) { physicsAnimationId = requestAnimationFrame(tick); return; }

        spatialGrid.clear();
        nodes.forEach(nd => { const p = nd.position(); spatialGrid.insert(nd.id(), p.x, p.y, nd.degree()); });

        const cx = cy.width() / 2, cy2 = cy.height() / 2;
        const batch = new Map();

        nodes.forEach(nd => {
            const id = nd.id();
            const pos = spatialGrid.nodePos.get(id);
            if (!pos) return;
            let fx = 0, fy = 0;
            for (const nb of spatialGrid.neighbors(pos.x, pos.y, maxR)) {
                if (nb.id === id) continue;
                let dist = Math.sqrt(nb.d2);
                if (dist < 10) dist = 10;
                const combined = Math.sqrt((pos.degree + 1) * (nb.degree + 1));
                const f = (repulsionStrength * combined) / (dist * dist * dist);
                fx += (pos.x - nb.x) * f;
                fy += (pos.y - nb.y) * f;
            }
            fx += (Math.random() - 0.5) * 50;
            fy += (Math.random() - 0.5) * 50;
            fx += (cx - pos.x) * 0.0005;
            fy += (cy2 - pos.y) * 0.0005;

            let vel = nodeVelocities.get(id);
            if (!vel) { vel = { vx: 0, vy: 0 }; nodeVelocities.set(id, vel); }
            vel.vx = (vel.vx + fx * dt) * damping;
            vel.vy = (vel.vy + fy * dt) * damping;
            const mag2 = vel.vx**2 + vel.vy**2;
            if (mag2 > 2500) { const s = 50 / Math.sqrt(mag2); vel.vx *= s; vel.vy *= s; }
            if (Math.abs(vel.vx) > minMove || Math.abs(vel.vy) > minMove)
                batch.set(id, { x: pos.x + vel.vx, y: pos.y + vel.vy });
        });

        if (batch.size > 0) cy.batch(() => {
            for (const [id, pos] of batch) {
                const nd = cy.getElementById(id);
                if (nd.length) nd.position(pos);
            }
        });
        physicsAnimationId = requestAnimationFrame(tick);
    }
    tick();
}

function stopFloatingPhysics() {
    if (physicsAnimationId) { cancelAnimationFrame(physicsAnimationId); physicsAnimationId = null; }
    nodeVelocities.clear();
    if (spatialGrid) spatialGrid.clear();
}

function toggleFloatingMode() {
    floatingMode = document.getElementById('floating-mode').checked;
    floatingMode ? startFloatingPhysics() : stopFloatingPhysics();
}

function updateRepulsionStrength() {
    const v = parseInt(document.getElementById('repulsion-slider').value, 10);
    repulsionStrength = v;
    document.getElementById('repulsion-val').textContent = v >= 1000 ? Math.round(v/1000)+'k' : v;
}

// --- Cytoscape init -------------------------------------------------------
function initGraph() {
    cy = cytoscape({
        container: document.getElementById('cy'),
        style: [
            { selector: 'node', style: { 'background-color': '#3b82f6', 'label': 'data(label)', 'width': 40, 'height': 40, 'font-size': '12px', 'text-valign': 'center', 'text-halign': 'center', 'color': '#fff', 'text-outline-color': '#1e293b', 'text-outline-width': 2, 'border-width': 2, 'border-color': '#60a5fa' } },
            { selector: 'node[type="document"]', style: { 'background-color': '#10b981', 'border-color': '#34d399' } },
            { selector: 'node[type="code"]',     style: { 'background-color': '#8b5cf6', 'border-color': '#a78bfa' } },
            { selector: 'node[type="module"]',   style: { 'background-color': '#64748b', 'border-color': '#94a3b8', 'shape': 'diamond' } },
            { selector: 'node:selected',  style: { 'border-width': 4, 'border-color': '#fbbf24' } },
            { selector: 'node.highlighted', style: { 'border-width': 4, 'border-color': '#fbbf24', 'background-color': '#fbbf24', 'opacity': 1 } },
            { selector: 'node.dimmed',  style: { 'opacity': 0.2 } },
            { selector: 'edge',         style: { 'width': 2, 'line-color': '#475569', 'target-arrow-color': '#475569', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': '10px', 'color': '#94a3b8', 'text-outline-color': '#0f172a', 'text-outline-width': 2 } },
            { selector: 'edge[type="imports_module"]', style: { 'line-color': '#10b981', 'target-arrow-color': '#10b981' } },
            { selector: 'edge[type="imports_from"]',   style: { 'line-color': '#10b981', 'target-arrow-color': '#10b981', 'line-style': 'dashed' } },
            { selector: 'edge[type="calls"]',          style: { 'line-color': '#f59e0b', 'target-arrow-color': '#f59e0b', 'width': 1 } },
            { selector: 'edge[type="inherits_from"]',  style: { 'line-color': '#ec4899', 'target-arrow-color': '#ec4899', 'line-style': 'dotted' } },
            { selector: 'edge[type="has_method"]',     style: { 'line-color': '#8b5cf6', 'target-arrow-color': '#8b5cf6', 'width': 1 } },
            { selector: 'edge.highlighted', style: { 'width': 4, 'opacity': 1 } },
            { selector: 'edge.dimmed',      style: { 'opacity': 0.1 } },
        ],
    });

    cy.on('tap', 'node', function(evt) {
        highlightNodeConnections(evt.target);
        showNodeDetails(evt.target);
    });
    cy.on('tap', function(evt) {
        if (evt.target === cy) { hideDetailPanel(); cy.elements().removeClass('highlighted dimmed'); }
    });
}

// --- Two-phase graph load -------------------------------------------------
async function loadGraph(minDegree) {
    const md = minDegree !== undefined ? minDegree : currentMinDegree;
    const loadDiv = document.getElementById('loading');
    loadDiv.style.display = 'block';
    loadDiv.querySelector('div').textContent = 'Loading nodes...';
    document.getElementById('loading-sub').textContent = '';

    try {
        // Phase 1: nodes only (fast)
        const nodesRes = await fetch(`/api/graph?mode=summary&min_degree=${md}`);
        if (!nodesRes.ok) throw new Error(await nodesRes.text());
        const nodesData = await nodesRes.json();

        cy.elements().remove();
        if (nodesData.nodes.length > 0) {
            cy.add(nodesData.nodes.map(n => ({ data: n })));
            // Size nodes by degree (will be updated when edges load)
            applyLayout();
        }

        const nodeCount = nodesData.nodes.length;
        loadDiv.style.display = 'none';

        // Phase 2: edges in background
        if (nodeCount > 0) {
            const badge = document.getElementById('edgeBadge');
            badge.style.display = 'block';
            badge.textContent = 'Loading relationships...';

            try {
                const edgesRes = await fetch(`/api/graph/edges?min_degree=${md}`);
                if (edgesRes.ok) {
                    const edgesData = await edgesRes.json();
                    const nodeIds = new Set(cy.nodes().map(n => n.id()));
                    const validEdges = edgesData.edges.filter(
                        e => nodeIds.has(e.source) && nodeIds.has(e.target)
                    );
                    if (validEdges.length > 0) {
                        cy.batch(() => { cy.add(validEdges.map(e => ({ data: e }))); });
                        updateEdgeVisibility();
                        updateNodeSizes();
                    }
                    badge.textContent = `${validEdges.length.toLocaleString()} relationships loaded`;
                    setTimeout(() => { badge.style.display = 'none'; }, 2500);
                }
            } catch (edgeErr) {
                console.warn('Edge load failed:', edgeErr);
                badge.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Graph load error:', error);
        document.querySelector('#loading div').textContent = 'Error loading graph';
        document.getElementById('loading-sub').textContent = String(error);
    }
}

function reloadGraph() { loadGraph(currentMinDegree); }

function reloadWithDegree() {
    currentMinDegree = parseInt(document.getElementById('minDegree').value, 10);
    loadGraph(currentMinDegree);
}

function updateNodeSizes() {
    cy.nodes().forEach(node => {
        const deg = node.degree();
        const size = Math.min(120, 40 + deg * 8);
        node.style({ width: size, height: size });
    });
}

// --- Layout ---------------------------------------------------------------
function applyLayout() {
    const layoutOpts = {
        name: currentLayout,
        padding: 50,
        animate: true,
        animationDuration: 600,
    };
    if (currentLayout === 'cose') {
        Object.assign(layoutOpts, {
            nodeRepulsion: () => 8000,
            idealEdgeLength: () => 120,
            edgeElasticity: 0.45,
            gravity: 0.1,
            numIter: 1500,
            initialTemp: 800,
            coolingFactor: 0.95,
            minTemp: 1.0,
            tile: true,
            packComponents: true,
        });
    }
    cy.layout(layoutOpts).run();
}

function changeLayout(name) { currentLayout = name; applyLayout(); }
function fitGraph()  { cy.fit(); }
function resetZoom() { cy.reset(); cy.center(); }
function toggleLabels() {
    labelsVisible = !labelsVisible;
    cy.style().selector('node').style('label', labelsVisible ? 'data(label)' : '')
              .selector('edge').style('label', labelsVisible ? 'data(label)' : '').update();
}

function updateEdgeVisibility() {
    const show = {
        calls:          document.getElementById('toggle-calls').checked,
        imports_module: document.getElementById('toggle-imports-module').checked,
        imports_from:   document.getElementById('toggle-imports-from').checked,
        inherits_from:  document.getElementById('toggle-inherits-from').checked,
    };
    cy.edges().forEach(edge => {
        const t = edge.data('type');
        (show[t] === false) ? edge.hide() : edge.show();
    });
}

// --- Node detail panel ----------------------------------------------------
function highlightNodeConnections(node) {
    cy.elements().removeClass('highlighted dimmed');
    const out = node.outgoers('edge');
    out.addClass('highlighted');
    out.targets().addClass('highlighted');
    cy.elements().not(node).not(out).not(out.targets()).addClass('dimmed');
}

function showNodeDetails(node) {
    const data = node.data();
    const panel = document.getElementById('detailPanel');
    let html = '';
    for (const [k, v] of Object.entries(data)) {
        if (k === 'id' || k === 'label') continue;
        html += `<div class="detail-row"><label>${k}</label><span class="value">${JSON.stringify(v)}</span></div>`;
    }
    const out = node.outgoers('edge');
    if (out.length) {
        html += '<h4 style="margin-top:16px;margin-bottom:8px;color:#60a5fa;font-size:14px">Outbound</h4>';
        const byType = {};
        out.forEach(e => { const t = e.data('type')||'?'; (byType[t]=byType[t]||[]).push({id:e.target().id(),label:e.target().data('label')||e.target().id()}); });
        for (const [t, conns] of Object.entries(byType)) {
            const color = {calls:'#f59e0b',imports_module:'#10b981',imports_from:'#10b981',inherits_from:'#ec4899',has_method:'#8b5cf6'}[t]||'#94a3b8';
            html += `<div class="detail-row"><label style="color:${color}">${t.replace(/_/g,' ')} (${conns.length})</label>`;
            html += conns.map(c=>`<div style="padding:3px 0;border-bottom:1px solid #334155;cursor:pointer;font-size:13px" onclick="focusNode('${c.id}')">→ ${c.label}</div>`).join('');
            html += '</div>';
        }
    }
    document.getElementById('detailContent').innerHTML = html || '<div class="detail-row"><label>No details</label></div>';
    panel.classList.add('visible');
}

function hideDetailPanel() { document.getElementById('detailPanel').classList.remove('visible'); }

function focusNode(id) {
    const node = cy.getElementById(id);
    if (node.length) {
        cy.animate({ center: { eles: node }, zoom: 1.2 }, { duration: 300 });
        highlightNodeConnections(node);
        showNodeDetails(node);
    }
}

// --- Search / query -------------------------------------------------------
async function performSearch() {
    const q = document.getElementById('searchInput').value.trim();
    if (!q) return;
    const res = await fetch('/api/search', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query:q,top_k:10}) });
    displayResults(await res.json(), 'search', `Search: "${q}"`);
}

let isQueryLoading = false;
async function performQuery() {
    const q = document.getElementById('queryInput').value.trim();
    if (!q || isQueryLoading) return;
    isQueryLoading = true;
    const btn = document.getElementById('askButton');
    btn.disabled = true; btn.textContent = 'Generating...';
    try {
        const res = await fetch('/api/query', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({question:q}) });
        displayResults([{title:'Answer',snippet:(await res.json()).answer}], 'query', 'AI response', q);
    } finally {
        isQueryLoading = false;
        btn.disabled = false; btn.textContent = 'Ask';
    }
}

function displayResults(results, type, title, query) {
    const panel = document.getElementById('resultsPanel');
    document.getElementById('resultsTitle').textContent = title;
    const qd = document.getElementById('queryDisplay');
    if (query) { qd.textContent = `Q: ${query}`; qd.style.display = 'block'; } else { qd.style.display = 'none'; }
    let html = '';
    if (type === 'query') {
        html = `<div class="markdown-content">${marked.parse(results[0].snippet||'')}</div>`;
    } else {
        results.forEach((r,i) => {
            html += `<div class="result-item" onclick="highlightSearchResult(${i},'${(r.source||'').replace(/\\x27/g,'')}')">
                <div class="title" style="color:#60a5fa;font-size:14px">${r.title||'Result '+(i+1)}</div>
                <div class="markdown-content" style="font-size:13px">${marked.parse(r.snippet||'')}</div></div>`;
        });
    }
    document.getElementById('resultsContent').innerHTML = html;
    panel.classList.remove('collapsed');
    panel.classList.add('visible');
    document.getElementById('collapseIcon').textContent = '−';
}

function toggleResultsPanel() {
    const p = document.getElementById('resultsPanel');
    const collapsed = p.classList.toggle('collapsed');
    document.getElementById('collapseIcon').textContent = collapsed ? '→' : '−';
}

function clearSelection() { cy.$(':selected').unselect(); hideDetailPanel(); }

function highlightSearchResult(i, source) {
    if (!source) return;
    const nodes = cy.nodes().filter(n => {
        const fp = n.data('metadata')?.file_path || '';
        return fp.includes(source) || n.data('label') === source;
    });
    if (nodes.length) { cy.animate({ center:{eles:nodes[0]}, zoom:1.2 }, {duration:300}); highlightNodeConnections(nodes[0]); }
}

// --- Boot -----------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    initGraph();
    loadGraph(0);
});
document.getElementById('searchInput').addEventListener('keypress', e => { if (e.key==='Enter') performSearch(); });
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Mimir Web UI")
    parser.add_argument("--project", metavar="DIR")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if args.project:
        pp = Path(args.project).resolve()
        os.environ["PROJECT_ROOT"] = str(pp)
        os.environ["KNOWLEDGE_DIR"] = str(pp / ".knowledge" / "llamaindex")

    uvicorn.run(app, host=args.host, port=args.port)
