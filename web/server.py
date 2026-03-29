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


# Store server configuration at module level to avoid re-detection
_server_config: Optional[ServerConfig] = None


# Store server configuration at module level to avoid re-detection
_server_config: Optional[ServerConfig] = None


@app.on_event("startup")
async def startup():
    import sys

    global _server_config

    existing_project = os.environ.get("PROJECT_ROOT")
    existing_kb = os.environ.get("KNOWLEDGE_DIR")

    if existing_project:
        print(
            f"[Startup] Using PROJECT_ROOT from env: {existing_project}",
            file=sys.stderr,
        )
    else:
        os.environ["PROJECT_ROOT"] = str(Path.cwd())
        print(
            f"[Startup] Set PROJECT_ROOT to CWD: {os.environ['PROJECT_ROOT']}",
            file=sys.stderr,
        )

    if existing_kb:
        print(f"[Startup] Using KNOWLEDGE_DIR from env: {existing_kb}", file=sys.stderr)
    else:
        project_root = Path(os.environ.get("PROJECT_ROOT", Path.cwd()))
        os.environ["KNOWLEDGE_DIR"] = str(project_root / ".knowledge" / "llamaindex")
        print(
            f"[Startup] Set KNOWLEDGE_DIR to: {os.environ['KNOWLEDGE_DIR']}",
            file=sys.stderr,
        )

    # Create server config once during startup
    _server_config = ServerConfig.from_env()
    print(
        f"[Startup] Server config initialized: project={_server_config.project_root}",
        file=sys.stderr,
    )


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
    <script src="https://unpkg.com/marked@9.1.6/marked.min.js"></script>
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
        
        .query-box button:disabled {
            background: #475569;
            cursor: not-allowed;
            opacity: 0.7;
        }
        
        .query-box button:disabled:hover {
            background: #475569;
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

        .toggle-label {
            display: flex;
            align-items: center;
            padding: 8px 0;
            cursor: pointer;
            font-size: 13px;
            color: #cbd5e1;
        }

        .toggle-label input[type="checkbox"] {
            margin-right: 10px;
            width: 16px;
            height: 16px;
            cursor: pointer;
            accent-color: #3b82f6;
        }

        .toggle-text {
            flex: 1;
        }

        .toggle-color {
            width: 12px;
            height: 12px;
            border-radius: 2px;
            margin-left: 8px;
        }

        .legend-line {
            display: inline-block;
            width: 20px;
            height: 2px;
            margin-right: 8px;
            vertical-align: middle;
        }

        .legend-line.dashed {
            height: 0;
            background: transparent;
        }

        .legend-line.dotted {
            height: 0;
            background: transparent;
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
            position: fixed;
            right: 0;
            top: 0;
            width: 450px;
            height: 100vh;
            background: #1e293b;
            border-left: 1px solid #334155;
            padding: 20px;
            box-shadow: -5px 0 30px rgba(0, 0, 0, 0.5);
            display: none;
            overflow-y: auto;
            z-index: 2000;
            transition: transform 0.3s ease;
        }
        
        .results-panel.visible {
            display: block;
        }
        
        .results-panel h3 {
            font-size: 16px;
            color: #60a5fa;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #334155;
        }
        
        .results-panel .collapse-btn {
            position: absolute;
            top: 20px;
            right: 20px;
            background: transparent;
            border: none;
            color: #94a3b8;
            font-size: 20px;
            cursor: pointer;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
            transition: all 0.2s;
            z-index: 2001;
        }
        
        .results-panel.collapsed .collapse-btn {
            left: 8px;
            right: auto;
            background: #1e293b;
            border: 1px solid #334155;
        }
        
        .results-panel .collapse-btn:hover {
            background: #334155;
            color: #e2e8f0;
        }
        
        .results-panel .collapse-btn #collapseIcon {
            display: inline-block;
            transition: transform 0.3s ease;
        }
        
        .results-panel.collapsed .collapse-btn #collapseIcon {
            transform: rotate(180deg);
        }
        
        .results-panel.collapsed {
            transform: translateX(calc(100% - 40px));
        }
        
        /* Markdown styles */
        .results-panel .markdown-content {
            color: #e2e8f0;
            line-height: 1.6;
        }
        
        .results-panel .markdown-content h1,
        .results-panel .markdown-content h2,
        .results-panel .markdown-content h3,
        .results-panel .markdown-content h4 {
            color: #60a5fa;
            margin-top: 20px;
            margin-bottom: 12px;
        }
        
        .results-panel .markdown-content h1 {
            font-size: 20px;
            border-bottom: 1px solid #334155;
            padding-bottom: 8px;
        }
        
        .results-panel .markdown-content h2 {
            font-size: 18px;
        }
        
        .results-panel .markdown-content h3 {
            font-size: 16px;
            border-bottom: none;
            padding-bottom: 0;
            margin-bottom: 8px;
        }
        
        .results-panel .markdown-content p {
            margin-bottom: 12px;
        }
        
        .results-panel .markdown-content ul,
        .results-panel .markdown-content ol {
            margin-bottom: 12px;
            padding-left: 24px;
        }
        
        .results-panel .markdown-content li {
            margin-bottom: 6px;
        }
        
        .results-panel .markdown-content code {
            background: #334155;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            color: #fbbf24;
        }
        
        .results-panel .markdown-content pre {
            background: #0f172a;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin-bottom: 16px;
            border: 1px solid #334155;
        }
        
        .results-panel .markdown-content pre code {
            background: transparent;
            padding: 0;
            color: #e2e8f0;
        }
        
        .results-panel .markdown-content blockquote {
            border-left: 3px solid #60a5fa;
            padding-left: 16px;
            margin-left: 0;
            color: #94a3b8;
        }
        
        .results-panel .markdown-content a {
            color: #60a5fa;
            text-decoration: none;
        }
        
        .results-panel .markdown-content a:hover {
            text-decoration: underline;
        }
        
        .results-panel .markdown-content table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
        }
        
        .results-panel .markdown-content th,
        .results-panel .markdown-content td {
            border: 1px solid #334155;
            padding: 8px 12px;
            text-align: left;
        }
        
        .results-panel .markdown-content th {
            background: #334155;
            color: #60a5fa;
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
                <button id="askButton" onclick="performQuery()">Ask</button>
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
                
                <h3 style="margin-top: 16px;">Physics</h3>
                <label class="toggle-label">
                    <input type="checkbox" id="floating-mode" onchange="toggleFloatingMode()">
                    <span class="toggle-text">Floating Mode</span>
                </label>
                <div style="margin-top: 10px;">
                    <label style="font-size: 11px; color: #94a3b8; display: block; margin-bottom: 5px;">Repulsion Strength</label>
                    <input type="range" id="repulsion-slider" min="1000" max="50000" value="10000" style="width: 100%;" onchange="updateRepulsionStrength()">
                </div>
                
                <h3 style="margin-top: 16px;">Relationships</h3>
                <label class="toggle-label">
                    <input type="checkbox" id="toggle-calls" checked onchange="updateEdgeVisibility()">
                    <span class="toggle-text">Calls</span>
                    <span class="toggle-color" style="background: #f59e0b;"></span>
                </label>
                <label class="toggle-label">
                    <input type="checkbox" id="toggle-imports-module" checked onchange="updateEdgeVisibility()">
                    <span class="toggle-text">Imports Module</span>
                    <span class="toggle-color" style="background: #10b981;"></span>
                </label>
                <label class="toggle-label">
                    <input type="checkbox" id="toggle-imports-from" checked onchange="updateEdgeVisibility()">
                    <span class="toggle-text">Imports From</span>
                    <span class="toggle-color" style="background: #10b981; border: 2px dashed #10b981; background: transparent;"></span>
                </label>
                <label class="toggle-label">
                    <input type="checkbox" id="toggle-inherits-from" checked onchange="updateEdgeVisibility()">
                    <span class="toggle-text">Inherits From</span>
                    <span class="toggle-color" style="background: #ec4899;"></span>
                </label>
                
                <h3 style="margin-top: 16px;">Legend</h3>
                <div style="font-size: 11px; color: #94a3b8; line-height: 1.6;">
                    <div style="margin-bottom: 8px;">
                        <span class="legend-line" style="background: #f59e0b;"></span>
                        <strong>Calls</strong> - Function/method calls
                    </div>
                    <div style="margin-bottom: 8px;">
                        <span class="legend-line" style="background: #10b981;"></span>
                        <strong>Imports Module</strong> - Direct module imports
                    </div>
                    <div style="margin-bottom: 8px;">
                        <span class="legend-line dashed" style="border-top: 2px dashed #10b981;"></span>
                        <strong>Imports From</strong> - Specific imports from module
                    </div>
                    <div style="margin-bottom: 8px;">
                        <span class="legend-line dotted" style="border-top: 3px dotted #ec4899;"></span>
                        <strong>Inherits From</strong> - Class inheritance
                    </div>
                </div>
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
                <button class="collapse-btn" onclick="toggleResultsPanel()" title="Collapse/Expand">
                    <span id="collapseIcon">−</span>
                </button>
                <h3 id="resultsTitle">Results</h3>
                <div id="queryDisplay" style="font-size: 12px; color: #94a3b8; margin-bottom: 16px; padding: 8px; background: #0f172a; border-radius: 6px; display: none;"></div>
                <div id="resultsContent"></div>
            </div>
        </main>
    </div>

    <script>
        let cy = null;
        let currentLayout = 'cose';
        let labelsVisible = true;
        let floatingMode = false;
        let repulsionStrength = 10000;
        let physicsAnimationId = null;
        let nodeVelocities = new Map();

        // Physics simulation for floating mode
        function startFloatingPhysics() {
            if (physicsAnimationId) {
                cancelAnimationFrame(physicsAnimationId);
            }
            
            const damping = 0.92;
            const timeStep = 0.16;
            
            function applyForces() {
                if (!floatingMode) return;
                
                const nodes = cy.nodes();
                const positions = new Map();
                
                // Store current positions
                nodes.forEach(node => {
                    positions.set(node.id(), node.position());
                });
                
                // Apply repulsion between all node pairs
                nodes.forEach(node1 => {
                    const pos1 = positions.get(node1.id());
                    const degree1 = node1.degree();
                    let fx = 0, fy = 0;
                    
                    nodes.forEach(node2 => {
                        if (node1.id() === node2.id()) return;
                        
                        const pos2 = positions.get(node2.id());
                        const dx = pos1.x - pos2.x;
                        const dy = pos1.y - pos2.y;
                        let dist = Math.sqrt(dx * dx + dy * dy);
                        
                        if (dist < 10) dist = 10; // Prevent division by zero
                        
                        // Repulsion force inversely proportional to distance
                        // Nodes with more connections repel more
                        const degree2 = node2.degree();
                        const combinedDegree = Math.sqrt((degree1 + 1) * (degree2 + 1));
                        const force = (repulsionStrength * combinedDegree) / (dist * dist);
                        
                        fx += (dx / dist) * force;
                        fy += (dy / dist) * force;
                    });
                    
                    // Add some gentle random drift for organic feel
                    fx += (Math.random() - 0.5) * 50;
                    fy += (Math.random() - 0.5) * 50;
                    
                    // Add slight attraction to center to prevent drifting away
                    const centerX = cy.width() / 2;
                    const centerY = cy.height() / 2;
                    fx += (centerX - pos1.x) * 0.0005;
                    fy += (centerY - pos1.y) * 0.0005;
                    
                    // Get or initialize velocity
                    let vel = nodeVelocities.get(node1.id()) || { vx: 0, vy: 0 };
                    
                    // Update velocity with force
                    vel.vx = (vel.vx + fx * timeStep) * damping;
                    vel.vy = (vel.vy + fy * timeStep) * damping;
                    
                    // Limit max velocity
                    const maxVel = 50;
                    const velMag = Math.sqrt(vel.vx * vel.vx + vel.vy * vel.vy);
                    if (velMag > maxVel) {
                        vel.vx = (vel.vx / velMag) * maxVel;
                        vel.vy = (vel.vy / velMag) * maxVel;
                    }
                    
                    nodeVelocities.set(node1.id(), vel);
                    
                    // Apply velocity to position
                    node1.position({
                        x: pos1.x + vel.vx,
                        y: pos1.y + vel.vy
                    });
                });
                
                physicsAnimationId = requestAnimationFrame(applyForces);
            }
            
            applyForces();
        }

        function stopFloatingPhysics() {
            if (physicsAnimationId) {
                cancelAnimationFrame(physicsAnimationId);
                physicsAnimationId = null;
            }
            nodeVelocities.clear();
        }

        function toggleFloatingMode() {
            floatingMode = document.getElementById('floating-mode').checked;
            if (floatingMode) {
                startFloatingPhysics();
            } else {
                stopFloatingPhysics();
            }
        }

        function updateRepulsionStrength() {
            repulsionStrength = parseInt(document.getElementById('repulsion-slider').value);
        }

        // Calculate node size based on connections
        function calculateNodeSize(node) {
            const degree = node.degree ? node.degree() : 0;
            // Base size 40, add 10 per connection, cap at 100
            return Math.min(100, 40 + (degree * 10));
        }

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
                        selector: 'node.highlighted',
                        style: {
                            'border-width': 4,
                            'border-color': '#fbbf24',
                            'background-color': '#fbbf24',
                            'opacity': 1
                        }
                    },
                    {
                        selector: 'node.dimmed',
                        style: {
                            'opacity': 0.2
                        }
                    },
                    {
                        selector: 'edge.highlighted',
                        style: {
                            'width': 4,
                            'opacity': 1,
                            'z-index': 999
                        }
                    },
                    {
                        selector: 'edge.dimmed',
                        style: {
                            'opacity': 0.1
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
                    padding: 100,
                    animate: true,
                    animationDuration: 2000,
                    // Component separation
                    componentSpacing: 200,
                    // Node repulsion (non overlapping) multiplier
                    nodeRepulsion: function(node) {
                        const degree = node.degree ? node.degree() : 1;
                        return 8000 * Math.pow(degree, 1.5);
                    },
                    // Ideal edge (non nested) length
                    idealEdgeLength: function(edge) {
                        const sourceDegree = edge.source().degree ? edge.source().degree() : 1;
                        const targetDegree = edge.target().degree ? edge.target().degree() : 1;
                        return 100 + (Math.sqrt(sourceDegree * targetDegree) * 30);
                    },
                    // Divisor to compute edge forces
                    edgeElasticity: 0.45,
                    // Nesting factor (multiplier) to compute ideal edge length for nested edges
                    nestingFactor: 0.1,
                    // Gravity force (constant)
                    gravity: 0.1,
                    // Maximum number of iterations to perform
                    numIter: 3000,
                    // Initial temperature (maximum node displacement)
                    initialTemp: 1000,
                    // Cooling factor (how temperature is reduced between consecutive iterations)
                    coolingFactor: 0.95,
                    // Minimum temperature threshold (below this layout will end)
                    minTemp: 1.0,
                    // Whether to use threading to speed up the layout
                    useMultitasking: true,
                    // Whether to tile disconnected nodes
                    tile: true,
                    // Whether to pack components without overlapping
                    packComponents: true
                }
            });

            // Node click handler
            cy.on('tap', 'node', function(evt) {
                const node = evt.target;
                console.log('Node clicked:', node.id(), node.data());
                highlightNodeConnections(node);
                showNodeDetails(node);
            });

            // Track selected node for highlighting
            let selectedNodeId = null;

            function highlightNodeConnections(node) {
                selectedNodeId = node.id();
                
                // Reset all elements
                cy.elements().removeClass('highlighted dimmed');
                
                // Get outbound connections (edges where this node is source)
                const outgoingEdges = node.outgoers('edge');
                const targetNodes = outgoingEdges.targets();
                
                // Highlight outgoing edges
                outgoingEdges.addClass('highlighted');
                
                // Highlight target nodes
                targetNodes.addClass('highlighted');
                
                // Dim everything else
                cy.elements().not(node).not(outgoingEdges).not(targetNodes).addClass('dimmed');
            }

            function clearHighlight() {
                selectedNodeId = null;
                cy.elements().removeClass('highlighted dimmed');
            }

            // Node drag handler - add extra repulsion when dragging
            cy.on('drag', 'node', function(evt) {
                const draggedNode = evt.target;
                const draggedPos = draggedNode.position();
                const draggedDegree = draggedNode.degree();
                
                // Apply immediate repulsion to nearby nodes
                cy.nodes().forEach(node => {
                    if (node.id() === draggedNode.id()) return;
                    
                    const pos = node.position();
                    const dx = pos.x - draggedPos.x;
                    const dy = pos.y - draggedPos.y;
                    const dist = Math.sqrt(dx * dx + dy * dy);
                    
                    if (dist < 300 && dist > 0) {
                        const nodeDegree = node.degree();
                        const combinedDegree = Math.sqrt((draggedDegree + 1) * (nodeDegree + 1));
                        const force = (repulsionStrength * 5 * combinedDegree) / (dist * dist);
                        
                        // Add velocity to push away from dragged node
                        let vel = nodeVelocities.get(node.id()) || { vx: 0, vy: 0 };
                        vel.vx += (dx / dist) * force * 0.5;
                        vel.vy += (dy / dist) * force * 0.5;
                        nodeVelocities.set(node.id(), vel);
                    }
                });
            });

            // Background click handler
            cy.on('tap', function(evt) {
                if (evt.target === cy) {
                    hideDetailPanel();
                    clearHighlight();
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
            let layoutOptions = {
                name: currentLayout,
                padding: 50,
                animate: true,
                animationDuration: 500
            };

            // Enhanced spacing for force-directed layout with node weight based repulsion
                    if (currentLayout === 'cose') {
                        // Calculate node degrees for sizing and spacing
                        const nodeDegrees = {};
                        cy.nodes().forEach(node => {
                            nodeDegrees[node.id()] = node.degree();
                        });
                        
                        // Set node sizes based on degree BEFORE layout
                        cy.nodes().forEach(node => {
                            const degree = nodeDegrees[node.id()];
                            // Larger nodes for more connected files
                            const size = Math.min(120, 40 + (degree * 12));
                            node.style({
                                'width': size,
                                'height': size
                            });
                        });
                        
                        layoutOptions = {
                            ...layoutOptions,
                            name: 'cose',
                            // Component separation
                            componentSpacing: 200,
                            // Node repulsion scales with degree squared
                            nodeRepulsion: function(node) {
                                const degree = nodeDegrees[node.id()] || 1;
                                return 8000 * Math.pow(degree, 1.8);
                            },
                            // Edge length scales with connectivity
                            idealEdgeLength: function(edge) {
                                const sourceDegree = nodeDegrees[edge.source().id()] || 1;
                                const targetDegree = nodeDegrees[edge.target().id()] || 1;
                                return 100 + (Math.sqrt(sourceDegree * targetDegree) * 35);
                            },
                            edgeElasticity: 0.45,
                            nestingFactor: 0.1,
                            gravity: 0.1,
                            numIter: 3000,
                            initialTemp: 1000,
                            coolingFactor: 0.95,
                            minTemp: 1.0,
                            useMultitasking: true,
                            tile: true,
                            packComponents: true
                        };
                    }

            const layout = cy.layout(layoutOptions);
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

        // Update edge visibility based on toggle checkboxes
        function updateEdgeVisibility() {
            const showCalls = document.getElementById('toggle-calls').checked;
            const showImportsModule = document.getElementById('toggle-imports-module').checked;
            const showImportsFrom = document.getElementById('toggle-imports-from').checked;
            const showInherits = document.getElementById('toggle-inherits-from').checked;

            // Show/hide edges based on their type
            cy.edges().forEach(edge => {
                const type = edge.data('type');
                let visible = true;

                if (type === 'calls' && !showCalls) visible = false;
                if (type === 'imports_module' && !showImportsModule) visible = false;
                if (type === 'imports_from' && !showImportsFrom) visible = false;
                if (type === 'inherits_from' && !showInherits) visible = false;

                if (visible) {
                    edge.show();
                } else {
                    edge.hide();
                }
            });
        }

        // Show node details
        function showNodeDetails(node) {
            const panel = document.getElementById('detailPanel');
            const content = document.getElementById('detailContent');
            const data = node.data();
            
            console.log('Showing details for node:', node.id(), data);
            
            // Get outbound connections - include both visible and hidden edges
            const outgoingEdges = node.outgoers('edge');
            
            // Debug: log all outgoing edges
            console.log('Outgoing edges for', node.id() + ':', outgoingEdges.map(e => ({type: e.data('type'), target: e.target().id()})));
            
            let html = '';
            
            // Basic node info
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
            
            // Outbound connections section
            if (outgoingEdges.length > 0) {
                html += '<h4 style="margin-top: 16px; margin-bottom: 8px; color: #60a5fa; font-size: 14px;">Outbound Connections</h4>';
                
                // Group connections by type
                const connectionsByType = {};
                outgoingEdges.forEach(edge => {
                    const type = edge.data('type') || 'unknown';
                    const target = edge.target();
                    const targetLabel = target.data('label') || target.id();
                    
                    if (!connectionsByType[type]) {
                        connectionsByType[type] = [];
                    }
                    connectionsByType[type].push({
                        target: targetLabel,
                        targetId: target.id(),
                        metadata: edge.data()
                    });
                });
                
                // Display connections by type
                for (const [type, connections] of Object.entries(connectionsByType)) {
                    const typeLabel = type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    const typeColor = getEdgeTypeColor(type);
                    
                    html += `
                        <div class="detail-row">
                            <label style="color: ${typeColor}; display: flex; align-items: center; gap: 5px;">
                                <span style="display: inline-block; width: 10px; height: 2px; background: ${typeColor};"></span>
                                ${typeLabel} (${connections.length})
                            </label>
                            <div class="value" style="margin-top: 4px;">
                                ${connections.map(conn => `
                                    <div style="padding: 4px 0; border-bottom: 1px solid #334155; cursor: pointer;" 
                                         onclick="focusNode('${conn.targetId}')">
                                        → ${conn.target}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }
            } else {
                html += '<div class="detail-row" style="margin-top: 16px;"><label>No outbound connections</label></div>';
            }
            
            if (html === '') {
                html = '<div class="detail-row"><label>No additional details</label></div>';
            }
            
            content.innerHTML = html;
            panel.classList.add('visible');
        }

        function getEdgeTypeColor(type) {
            const colors = {
                'calls': '#f59e0b',
                'imports_module': '#10b981',
                'imports_from': '#10b981',
                'inherits_from': '#ec4899',
                'has_method': '#8b5cf6'
            };
            return colors[type] || '#94a3b8';
        }

        function focusNode(nodeId) {
            const node = cy.getElementById(nodeId);
            if (node) {
                // Center on node
                cy.animate({
                    center: { eles: node },
                    zoom: 1.2
                }, { duration: 300 });
                
                // Highlight the node
                highlightNodeConnections(node);
                showNodeDetails(node);
            }
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
                    body: JSON.stringify({ query, top_k: 10 })
                });
                
                const results = await response.json();
                displayResults(results, 'search', `Search: "${query}"`);
            } catch (error) {
                console.error('Search error:', error);
                displayResults([{ title: 'Error', snippet: 'Failed to perform search. Please try again.' }], 'error', 'Error');
            }
        }

        // Store current query for display
        let currentQuery = '';
        let isQueryLoading = false;

        // Perform query
        async function performQuery() {
            const question = document.getElementById('queryInput').value;
            if (!question || isQueryLoading) return;
            
            // Store query and set loading state
            currentQuery = question;
            isQueryLoading = true;
            const askButton = document.getElementById('askButton');
            askButton.disabled = true;
            askButton.style.background = '#64748b';
            askButton.style.cursor = 'not-allowed';
            askButton.textContent = 'Generating...';
            
            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question })
                });
                
                const result = await response.json();
                displayResults([{ title: 'Answer', snippet: result.answer }], 'query', 'AI Response', question);
            } catch (error) {
                console.error('Query error:', error);
                displayResults([{ title: 'Error', snippet: 'Failed to process query. Please try again.' }], 'error', 'Error', question);
            } finally {
                // Reset loading state
                isQueryLoading = false;
                askButton.disabled = false;
                askButton.style.background = '#8b5cf6';
                askButton.style.cursor = 'pointer';
                askButton.textContent = 'Ask';
            }
        }

        // Display results
        function displayResults(results, type, title = 'Results', query = null) {
            const panel = document.getElementById('resultsPanel');
            const content = document.getElementById('resultsContent');
            const titleEl = document.getElementById('resultsTitle');
            const queryDisplay = document.getElementById('queryDisplay');
            
            titleEl.textContent = title;
            
            // Show query if provided
            if (query) {
                queryDisplay.textContent = `Q: ${query}`;
                queryDisplay.style.display = 'block';
            } else {
                queryDisplay.style.display = 'none';
            }
            
            let html = '';
            
            if (type === 'query') {
                // For query results, render the answer with markdown
                const result = results[0];
                const markdownText = result.snippet || result;
                const renderedMarkdown = marked.parse(markdownText);
                html = `
                    <div class="markdown-content">
                        ${renderedMarkdown}
                    </div>
                `;
            } else if (type === 'error') {
                // Error display
                const result = results[0];
                html = `
                    <div class="result-item" style="border-left: 3px solid #ef4444;">
                        <div class="title" style="color: #ef4444;">${result.title}</div>
                        <div class="snippet">${result.snippet}</div>
                    </div>
                `;
            } else {
                // For search results, show list with clickable items
                results.forEach((result, index) => {
                    const markdownSnippet = marked.parse(result.snippet || result);
                    html += `
                        <div class="result-item" onclick="highlightSearchResult(${index}, '${escapeHtml(result.source || '')}')" style="margin-bottom: 16px;">
                            <div class="title" style="color: #60a5fa; font-size: 14px; margin-bottom: 8px;">
                                ${result.title || 'Result ' + (index + 1)}
                            </div>
                            <div class="markdown-content" style="font-size: 13px;">
                                ${markdownSnippet}
                            </div>
                        </div>
                    `;
                });
            }
            
            content.innerHTML = html;
            
            // Ensure panel is visible and expanded when showing new results
            panel.classList.remove('collapsed');
            panel.classList.add('visible');
            
            // Reset collapse icon to show expanded state
            const icon = document.getElementById('collapseIcon');
            if (icon) {
                icon.textContent = '−';
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function hideResultsPanel() {
            const panel = document.getElementById('resultsPanel');
            panel.classList.remove('visible');
            panel.classList.remove('collapsed');
        }
        
        function toggleResultsPanel() {
            const panel = document.getElementById('resultsPanel');
            const icon = document.getElementById('collapseIcon');
            
            if (panel.classList.contains('collapsed')) {
                // Expand
                panel.classList.remove('collapsed');
                icon.textContent = '−';
            } else {
                // Collapse
                panel.classList.add('collapsed');
                icon.textContent = '→';
            }
        }

        function highlightSearchResult(index, source) {
            console.log('Highlighting result:', index, source);
            // Find and highlight the corresponding node in the graph
            if (source) {
                const nodes = cy.nodes().filter(node => {
                    const filePath = node.data('metadata')?.file_path || '';
                    return filePath.includes(source) || node.data('label') === source;
                });
                
                if (nodes.length > 0) {
                    const node = nodes[0];
                    cy.animate({
                        center: { eles: node },
                        zoom: 1.2
                    }, { duration: 300 });
                    highlightNodeConnections(node);
                }
            }
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
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        server = KnowledgeServer(_server_config)

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

        relationships_path = (
            _server_config.knowledge_dir.parent / "code_relationships.json"
        )
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
                target = rel[
                    "target"
                ]  # e.g., "src/mimir/indexing.py" or "pathlib.Path"
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
                            label=Path(target).name
                            if "." in target
                            else target.split(".")[-1],
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

        results = []
        # Parse the formatted results
        import re

        # Split by double newlines to get individual results
        entries = results_text.split("\n\n")
        for entry in entries:
            if not entry.strip():
                continue

            # Parse format: [N] filename (score: X.XXX)\ntext
            lines = entry.strip().split("\n")
            if lines:
                header = lines[0]
                content = "\n".join(lines[1:]) if len(lines) > 1 else ""

                # Extract filename from header like "[1] filename.py (score: 0.850)"
                match = re.match(r"\[\d+\]\s+(.+?)\s+\(score:", header)
                filename = match.group(1) if match else "Unknown"

                results.append(
                    {
                        "title": filename,
                        "snippet": content.strip() or header,
                        "source": filename,
                    }
                )

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query")
async def query(request: QueryRequest):
    """Query the knowledge base"""
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
    """Get knowledge base statistics"""
    try:
        global _server_config
        if _server_config is None:
            _server_config = ServerConfig.from_env()
        server = KnowledgeServer(_server_config)

        stats = server.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(
        description="Mimir Web UI - Browse your knowledge base"
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help="Path to project directory (default: current directory)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run server on (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind server to (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    # Set environment variables BEFORE uvicorn starts (so they're inherited by workers)
    if args.project:
        project_path = Path(args.project).resolve()
        os.environ["PROJECT_ROOT"] = str(project_path)
        os.environ["KNOWLEDGE_DIR"] = str(project_path / ".knowledge" / "llamaindex")
        print(f"📁 Serving project: {project_path}")
        print(f"📚 Knowledge base: {os.environ['KNOWLEDGE_DIR']}")
    else:
        # If no --project, but PROJECT_ROOT is set via env, use that
        if os.environ.get("PROJECT_ROOT"):
            print(
                f"📁 Using PROJECT_ROOT from environment: {os.environ['PROJECT_ROOT']}"
            )
            if not os.environ.get("KNOWLEDGE_DIR"):
                os.environ["KNOWLEDGE_DIR"] = str(
                    Path(os.environ["PROJECT_ROOT"]) / ".knowledge" / "llamaindex"
                )
            print(f"📚 Knowledge base: {os.environ['KNOWLEDGE_DIR']}")

    uvicorn.run(app, host=args.host, port=args.port)
