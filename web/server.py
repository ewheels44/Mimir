"""Mimir Web UI - FastAPI Backend"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))

from mcp_server_llamaindex import ServerConfig, KnowledgeServer

app = FastAPI(title="Mimir Web UI", version="1.0.0")


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


@app.on_event("startup")
async def startup():
    os.environ["PROJECT_ROOT"] = str(Path.cwd())
    os.environ["KNOWLEDGE_DIR"] = str(Path.cwd() / ".knowledge" / "llamaindex")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mimir Knowledge Base</title>
    <script src="https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js"></script>
    <script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            height: 100vh;
            overflow: hidden;
        }
        
        .container {
            display: flex;
            height: 100vh;
        }
        
        .sidebar {
            width: 320px;
            background: #1e293b;
            border-right: 1px solid #334155;
            display: flex;
            flex-direction: column;
            padding: 20px;
            overflow-y: auto;
        }
        
        .logo {
            font-size: 24px;
            font-weight: bold;
            color: #60a5fa;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .logo::before {
            content: "🧠";
        }
        
        .search-box {
            margin-bottom: 20px;
        }
        
        .search-box input {
            width: 100%;
            padding: 12px;
            border: 1px solid #475569;
            border-radius: 8px;
            background: #334155;
            color: #e2e8f0;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .search-box input:focus {
            border-color: #60a5fa;
        }
        
        .search-box button {
            width: 100%;
            padding: 12px;
            margin-top: 8px;
            border: none;
            border-radius: 8px;
            background: #3b82f6;
            color: white;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .search-box button:hover {
            background: #2563eb;
        }
        
        .query-box {
            margin-bottom: 20px;
        }
        
        .query-box textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid #475569;
            border-radius: 8px;
            background: #334155;
            color: #e2e8f0;
            font-size: 14px;
            outline: none;
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
        }
        
        .query-box textarea:focus {
            border-color: #60a5fa;
        }
        
        .query-box button {
            width: 100%;
            padding: 12px;
            margin-top: 8px;
            border: none;
            border-radius: 8px;
            background: #8b5cf6;
            color: white;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .query-box button:hover {
            background: #7c3aed;
        }
        
        .controls {
            margin-top: auto;
            padding-top: 20px;
            border-top: 1px solid #334155;
        }
        
        .controls h3 {
            font-size: 14px;
            color: #94a3b8;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .control-btn {
            width: 100%;
            padding: 10px;
            margin-bottom: 8px;
            border: 1px solid #475569;
            border-radius: 6px;
            background: transparent;
            color: #cbd5e1;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .control-btn:hover {
            background: #334155;
            border-color: #60a5fa;
        }
        
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            position: relative;
        }
        
        .toolbar {
            height: 50px;
            background: #1e293b;
            border-bottom: 1px solid #334155;
            display: flex;
            align-items: center;
            padding: 0 20px;
            gap: 10px;
        }
        
        .toolbar button {
            padding: 8px 16px;
            border: 1px solid #475569;
            border-radius: 6px;
            background: transparent;
            color: #cbd5e1;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .toolbar button:hover {
            background: #334155;
        }
        
        .toolbar button.active {
            background: #3b82f6;
            border-color: #3b82f6;
        }
        
        #graph-container {
            flex: 1;
            position: relative;
            background: #0f172a;
        }
        
        #cy {
            width: 100%;
            height: 100%;
        }
        
        .detail-panel {
            position: absolute;
            right: 20px;
            top: 20px;
            width: 300px;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            display: none;
            max-height: 60vh;
            overflow-y: auto;
            z-index: 1000;
        }
        
        .detail-panel.visible {
            display: block;
        }
        
        .detail-panel h3 {
            font-size: 16px;
            color: #60a5fa;
            margin-bottom: 12px;
            padding-bottom: 12px;
            border-bottom: 1px solid #334155;
        }
        
        .detail-row {
            margin-bottom: 12px;
        }
        
        .detail-row label {
            display: block;
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        
        .detail-row .value {
            display: block;
            font-size: 14px;
            color: #e2e8f0;
            word-break: break-word;
        }
        
        .results-panel {
            position: absolute;
            left: 20px;
            bottom: 20px;
            width: 400px;
            max-height: 300px;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
            display: none;
            overflow-y: auto;
        }
        
        .results-panel.visible {
            display: block;
        }
        
        .results-panel h3 {
            font-size: 14px;
            color: #60a5fa;
            margin-bottom: 12px;
        }
        
        .result-item {
            padding: 10px;
            margin-bottom: 8px;
            background: #334155;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .result-item:hover {
            background: #475569;
        }
        
        .result-item .title {
            font-weight: 500;
            margin-bottom: 4px;
        }
        
        .result-item .snippet {
            font-size: 12px;
            color: #94a3b8;
        }
        
        .loading {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 18px;
            color: #60a5fa;
        }
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
                <textarea id="queryInput" placeholder="Ask a question about your knowledge base..."></textarea>
                <button onclick="performQuery()">Ask</button>
            </div>
            
            <div class="controls">
                <h3>Layout</h3>
                <button class="control-btn" onclick="changeLayout('cose')">Force-directed</button>
                <button class="control-btn" onclick="changeLayout('circle')">Circle</button>
                <button class="control-btn" onclick="changeLayout('grid')">Grid</button>
                <button class="control-btn" onclick="changeLayout('dagre')">Hierarchy</button>
                
                <h3 style="margin-top: 16px;">View</h3>
                <button class="control-btn" onclick="fitGraph()">Fit to Screen</button>
                <button class="control-btn" onclick="resetZoom()">Reset Zoom</button>
                <button class="control-btn" onclick="toggleLabels()">Toggle Labels</button>
            </div>
        </aside>
        
        <main class="main-content">
            <div class="toolbar">
                <button onclick="loadGraph()" class="active">Full Graph</button>
                <button onclick="loadSearchResults()">Search Results</button>
                <button onclick="clearSelection()">Clear Selection</button>
            </div>
            
            <div id="graph-container">
                <div id="cy"></div>
                <div class="loading" id="loading">Loading knowledge graph...</div>
            </div>
            
            <div class="detail-panel" id="detailPanel">
                <h3>Node Details</h3>
                <div id="detailContent"></div>
            </div>
            
            <div class="results-panel" id="resultsPanel">
                <h3>Results</h3>
                <div id="resultsContent"></div>
            </div>
        </main>
    </div>

    <script>
        let cy = null;
        let currentLayout = 'cose';
        let labelsVisible = true;

        // Initialize Cytoscape
        function initGraph() {
            cy = cytoscape({
                container: document.getElementById('cy'),
                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': '#3b82f6',
                            'label': 'data(label)',
                            'width': 40,
                            'height': 40,
                            'font-size': '12px',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'color': '#fff',
                            'text-outline-color': '#1e293b',
                            'text-outline-width': 2,
                            'border-width': 2,
                            'border-color': '#60a5fa'
                        }
                    },
                    {
                        selector: 'node[type="document"]',
                        style: {
                            'background-color': '#10b981',
                            'border-color': '#34d399'
                        }
                    },
                    {
                        selector: 'node[type="code"]',
                        style: {
                            'background-color': '#8b5cf6',
                            'border-color': '#a78bfa'
                        }
                    },
                    {
                        selector: 'node[type="concept"]',
                        style: {
                            'background-color': '#f59e0b',
                            'border-color': '#fbbf24'
                        }
                    },
                    {
                        selector: 'node[type="module"]',
                        style: {
                            'background-color': '#64748b',
                            'border-color': '#94a3b8',
                            'shape': 'diamond'
                        }
                    },
                    {
                        selector: 'node:selected',
                        style: {
                            'border-width': 4,
                            'border-color': '#fbbf24'
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 2,
                            'line-color': '#475569',
                            'target-arrow-color': '#475569',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'label': 'data(label)',
                            'font-size': '10px',
                            'color': '#94a3b8',
                            'text-outline-color': '#0f172a',
                            'text-outline-width': 2
                        }
                    },
                    {
                        selector: 'edge[type="semantic"]',
                        style: {
                            'line-color': '#60a5fa',
                            'target-arrow-color': '#60a5fa',
                            'line-style': 'dashed'
                        }
                    },
                    {
                        selector: 'edge[type="imports_module"]',
                        style: {
                            'line-color': '#10b981',
                            'target-arrow-color': '#10b981',
                            'line-style': 'solid'
                        }
                    },
                    {
                        selector: 'edge[type="imports_from"]',
                        style: {
                            'line-color': '#10b981',
                            'target-arrow-color': '#10b981',
                            'line-style': 'dashed'
                        }
                    },
                    {
                        selector: 'edge[type="calls"]',
                        style: {
                            'line-color': '#f59e0b',
                            'target-arrow-color': '#f59e0b',
                            'width': 1
                        }
                    },
                    {
                        selector: 'edge[type="inherits_from"]',
                        style: {
                            'line-color': '#ec4899',
                            'target-arrow-color': '#ec4899',
                            'line-style': 'dotted'
                        }
                    },
                    {
                        selector: 'edge[type="has_method"]',
                        style: {
                            'line-color': '#8b5cf6',
                            'target-arrow-color': '#8b5cf6',
                            'width': 1
                        }
                    }
                ],
                layout: {
                    name: 'cose',
                    padding: 10,
                    animate: true,
                    animationDuration: 1000
                }
            });

            // Node click handler
            cy.on('tap', 'node', function(evt) {
                const node = evt.target;
                console.log('Node clicked:', node.id(), node.data());
                showNodeDetails(node);
            });

            // Background click handler
            cy.on('tap', function(evt) {
                if (evt.target === cy) {
                    hideDetailPanel();
                }
            });
        }

        // Load graph data from API
        async function loadGraph() {
            document.getElementById('loading').style.display = 'block';
            
            try {
                const response = await fetch('/api/graph');
                const data = await response.json();
                
                // Transform data to Cytoscape format (wrap in data property)
                const cyData = {
                    nodes: data.nodes.map(n => ({ data: n })),
                    edges: data.edges.map(e => ({ data: e }))
                };
                
                cy.elements().remove();
                cy.add(cyData);
                
                applyLayout();
                
                document.getElementById('loading').style.display = 'none';
            } catch (error) {
                console.error('Error loading graph:', error);
                document.getElementById('loading').textContent = 'Error loading graph';
            }
        }

        // Apply current layout
        function applyLayout() {
            const layout = cy.layout({
                name: currentLayout,
                padding: 10,
                animate: true,
                animationDuration: 500
            });
            layout.run();
        }

        // Change layout
        function changeLayout(layoutName) {
            currentLayout = layoutName;
            applyLayout();
        }

        // Fit graph to screen
        function fitGraph() {
            cy.fit();
        }

        // Reset zoom
        function resetZoom() {
            cy.reset();
            cy.center();
        }

        // Toggle labels
        function toggleLabels() {
            labelsVisible = !labelsVisible;
            cy.style()
                .selector('node')
                .style('label', labelsVisible ? 'data(label)' : '')
                .selector('edge')
                .style('label', labelsVisible ? 'data(label)' : '')
                .update();
        }

        // Show node details
        function showNodeDetails(node) {
            const panel = document.getElementById('detailPanel');
            const content = document.getElementById('detailContent');
            const data = node.data();
            
            console.log('Showing details for node:', node.id(), data);
            console.log('Panel element:', panel);
            console.log('Content element:', content);
            
            let html = '';
            for (const [key, value] of Object.entries(data)) {
                if (key !== 'id' && key !== 'label') {
                    html += `
                        <div class="detail-row">
                            <label>${key}</label>
                            <span class="value">${JSON.stringify(value)}</span>
                        </div>
                    `;
                }
            }
            
            if (html === '') {
                html = '<div class="detail-row"><label>No additional details</label></div>';
            }
            
            content.innerHTML = html;
            panel.classList.add('visible');
            console.log('Panel visible class added, display should be block');
        }

        // Hide detail panel
        function hideDetailPanel() {
            document.getElementById('detailPanel').classList.remove('visible');
        }

        // Perform search
        async function performSearch() {
            const query = document.getElementById('searchInput').value;
            if (!query) return;
            
            try {
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, top_k: 5 })
                });
                
                const results = await response.json();
                displayResults(results, 'search');
            } catch (error) {
                console.error('Search error:', error);
            }
        }

        // Perform query
        async function performQuery() {
            const question = document.getElementById('queryInput').value;
            if (!question) return;
            
            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });
                
                const result = await response.json();
                displayResults([{ title: 'Answer', snippet: result.answer }], 'query');
            } catch (error) {
                console.error('Query error:', error);
            }
        }

        // Display results
        function displayResults(results, type) {
            const panel = document.getElementById('resultsPanel');
            const content = document.getElementById('resultsContent');
            
            let html = '';
            results.forEach((result, index) => {
                html += `
                    <div class="result-item" onclick="highlightResult(${index})">
                        <div class="title">${result.title || 'Result ' + (index + 1)}</div>
                        <div class="snippet">${result.snippet || result}</div>
                    </div>
                `;
            });
            
            content.innerHTML = html;
            panel.classList.add('visible');
        }

        // Clear selection
        function clearSelection() {
            cy.$(':selected').unselect();
            hideDetailPanel();
        }

        // Initialize on load
        document.addEventListener('DOMContentLoaded', () => {
            initGraph();
            loadGraph();
        });

        // Enter key handlers
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') performSearch();
        });
    </script>
</body>
</html>
    """
    return html_content


@app.get("/api/graph", response_model=GraphData)
async def get_graph():
    """Get the knowledge graph data with relationships"""
    try:
        config = ServerConfig.from_env()
        server = KnowledgeServer(config)

        index = server.get_index()
        if not index:
            return GraphData(nodes=[], edges=[])

        nodes = []
        edges = []
        docstore = index.storage_context.docstore

        # Build file_path -> doc_id mapping and deduplicate on file_path
        file_path_to_id = {}
        file_path_to_node = {}
        
        for doc_id, doc in docstore.docs.items():
            metadata = doc.metadata if hasattr(doc, "metadata") else {}
            file_path = metadata.get("file_path", metadata.get("file_name", "unknown"))
            file_name = metadata.get("file_name", "unknown")
            
            # Deduplicate: if we've seen this file_path, skip
            if file_path in file_path_to_id:
                continue
            
            file_path_to_id[file_path] = doc_id
            
            node_type = "document"
            if file_name.endswith(".py"):
                node_type = "code"

            node = Node(id=doc_id, label=file_name, type=node_type, metadata=metadata)
            nodes.append(node)
            file_path_to_node[file_path] = node

        relationships_path = config.knowledge_dir.parent / "code_relationships.json"
        if relationships_path.exists():
            with open(relationships_path, "r") as f:
                rel_data = json.load(f)

            # Build comprehensive lookup for matching
            # We need to match relationship targets to indexed files
            # Relationships use paths like "src/mimir/indexing.py"
            # Indexed files have paths like "/Users/.../Mimir/src/mimir/indexing.py"
            
            # Create mapping from basename -> [file_paths]
            basename_to_paths = {}
            for fp in file_path_to_id.keys():
                basename = Path(fp).name
                if basename not in basename_to_paths:
                    basename_to_paths[basename] = []
                basename_to_paths[basename].append(fp)

            for rel in rel_data.get("relationships", []):
                source_file = rel["source"]  # e.g., "examples/run_workflow.py"
                target = rel["target"]       # e.g., "src/mimir/indexing.py" or "pathlib.Path"
                rel_type = rel["relation_type"]

                # Match source file - look for file_path that ends with source_file
                source_id = None
                for fp, did in file_path_to_id.items():
                    if fp.endswith(source_file):
                        source_id = did
                        break
                
                if not source_id:
                    continue

                # Match target file
                target_id = None
                target_node = None
                
                # Strategy 1: Direct path match
                for fp, did in file_path_to_id.items():
                    if fp.endswith(target):
                        target_id = did
                        target_node = file_path_to_node.get(fp)
                        break
                
                # Strategy 2: Target is basename
                if not target_id and target in basename_to_paths:
                    # Take the first match (could be ambiguous)
                    target_fp = basename_to_paths[target][0]
                    target_id = file_path_to_id[target_fp]
                    target_node = file_path_to_node.get(target_fp)
                
                # Strategy 3: Target is module path (e.g., "src/mimir/indexing" without .py)
                if not target_id and not target.endswith(".py"):
                    target_py = target + ".py"
                    for fp, did in file_path_to_id.items():
                        if fp.endswith(target_py):
                            target_id = did
                            target_node = file_path_to_node.get(fp)
                            break
                
                # Strategy 4: Match by basename without extension
                if not target_id:
                    target_basename = Path(target).name
                    target_stem = Path(target_basename).stem
                    for fp in file_path_to_id.keys():
                        fp_basename = Path(fp).name
                        fp_stem = Path(fp_basename).stem
                        if target_stem == fp_stem:
                            target_id = file_path_to_id[fp]
                            target_node = file_path_to_node.get(fp)
                            break

                # If no match found, create an external module node
                if not target_id:
                    target_id = f"external:{target}"
                    # Check if already exists
                    existing = next((n for n in nodes if n.id == target_id), None)
                    if not existing:
                        node = Node(
                            id=target_id,
                            label=Path(target).name if "." in target else target.split(".")[-1],
                            type="module",
                            metadata={"module_path": target, "external": True},
                        )
                        nodes.append(node)
                        target_node = node

                # Create edge
                edges.append(
                    Edge(
                        source=source_id,
                        target=target_id,
                        label=rel_type.replace("_", " "),
                        type=rel_type,
                    )
                )

        return GraphData(nodes=nodes, edges=edges)
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search")
async def search(request: SearchRequest):
    """Search the knowledge base"""
    try:
        config = ServerConfig.from_env()
        server = KnowledgeServer(config)

        results_text = server.search(request.query, request.top_k)

        results = []
        for line in results_text.split("\n"):
            if line.strip():
                results.append(
                    {
                        "title": "Result",
                        "snippet": line[:200] + "..." if len(line) > 200 else line,
                    }
                )

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query")
async def query(request: QueryRequest):
    """Query the knowledge base"""
    try:
        config = ServerConfig.from_env()
        server = KnowledgeServer(config)

        answer = server.query(request.question)

        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get knowledge base statistics"""
    try:
        config = ServerConfig.from_env()
        server = KnowledgeServer(config)

        stats = server.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
