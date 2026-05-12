# Mimir Graph UI Enhancement Plan

## Overview

This document outlines planned enhancements to the Mimir knowledge graph visualization system, focusing on two main areas:
1. **Graph State Persistence** - Caching rendered graphs and preserving settings across navigation
2. **Float Mode Redesign** - Transforming the current physics toggle into an InfraNodus-style contextual overlay

---

## Current Architecture Analysis

### Graph Rendering System

**Location**: `web/server.py` (lines 660-1367)

The current implementation uses:
- **Backend**: FastAPI with in-memory `_graph_cache` keyed by file mtimes
- **Frontend**: Vanilla JavaScript + Cytoscape.js (seperate files and system)
- **Two-phase loading**: Nodes first (`/api/graph?mode=summary`), edges lazy-loaded (`/api/graph/edges`)
- **State management**: Global variables (`currentMinDegree`, `currentLayout`, `labelsVisible`, `floatingMode`)

### Key Components

```
Graph Page (/)          Metrics Page (/metrics)
     │                          │
     ▼                          ▼
_GRAPH_HTML (inline)      metrics.html
     │
     ├── initGraph()           Initialize Cytoscape
     ├── loadGraph()           Two-phase fetch
     ├── applyLayout()         Layout algorithms
     ├── toggleFloatingMode()  Physics simulation
     └── updateEdgeVisibility() Filter edges
```

### Current Settings (No Persistence)

| Setting | Variable | Storage |
|---------|----------|---------|
| Min connections | `currentMinDegree` | JavaScript global |
| Layout | `currentLayout` | JavaScript global |
| Labels visible | `labelsVisible` | JavaScript global |
| Floating mode | `floatingMode` | JavaScript global |
| Repulsion strength | `repulsionStrength` | JavaScript global |
| Edge filters | Checkboxes (calls, imports, inherits) | DOM state |

**Problem**: When navigating to `/metrics` and back to `/`, all settings reset to defaults.

---

## Part 1: Graph State Persistence

### Goals

1. **Initial Load Caching**: Once a graph is rendered, subsequent loads should be instant
2. **Settings Persistence**: Min connectors, layout, filters should survive tab navigation
3. **Smart Refresh**: Detect when underlying data changes and invalidate cache appropriately

### Implementation Strategy

#### Option A: SessionStorage + Render Cache (Recommended)

```javascript
// Settings persistence via sessionStorage
const GraphSettings = {
    STORAGE_KEY: 'mimir_graph_settings',
    
    save(settings) {
        sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify({
            minDegree: currentMinDegree,
            layout: currentLayout,
            labelsVisible,
            floatingMode,
            repulsionStrength,
            edgeFilters: {
                calls: document.getElementById('toggle-calls').checked,
                importsModule: document.getElementById('toggle-imports-module').checked,
                importsFrom: document.getElementById('toggle-imports-from').checked,
                inheritsFrom: document.getElementById('toggle-inherits-from').checked
            }
        }));
    },
    
    load() {
        const saved = sessionStorage.getItem(this.STORAGE_KEY);
        return saved ? JSON.parse(saved) : null;
    }
};

// Graph render cache
const GraphCache = {
    hasValidCache(cacheKey) {
        const cached = sessionStorage.getItem(`mimir_graph_${cacheKey}`);
        if (!cached) return false;
        
        const { timestamp, data } = JSON.parse(cached);
        // Cache valid for 5 minutes
        return (Date.now() - timestamp) < 5 * 60 * 1000;
    },
    
    get(cacheKey) {
        const cached = sessionStorage.getItem(`mimir_graph_${cacheKey}`);
        return cached ? JSON.parse(cached).data : null;
    },
    
    set(cacheKey, data) {
        sessionStorage.setItem(`mimir_graph_${cacheKey}`, JSON.stringify({
            timestamp: Date.now(),
            data
        }));
    }
};
```

#### Option B: Cytoscape JSON Serialization

Instead of re-fetching from server, serialize the Cytoscape graph state:

```javascript
// Save graph state
function serializeGraph() {
    return {
        elements: cy.json().elements,
        viewport: { zoom: cy.zoom(), pan: cy.pan() },
        layout: currentLayout,
        timestamp: Date.now()
    };
}

// Restore graph state
function deserializeGraph(state) {
    cy.json({ elements: state.elements });
    cy.viewport({ zoom: state.viewport.zoom, pan: state.viewport.pan });
    currentLayout = state.layout;
    updateEdgeVisibility();
    updateNodeSizes();
}
```

**Trade-offs**:
- Option A: Simpler, server-side filtering still applied
- Option B: Instant restore, but doesn't reflect server-side changes

### Recommended Approach: Hybrid

```javascript
async function loadGraph(minDegree, forceRefresh = false) {
    const settings = GraphSettings.load();
    if (settings) applySettings(settings);
    
    // Check if we have a cached render
    const cacheKey = `${currentMinDegree}_${settings?.layout || 'cose'}`;
    
    if (!forceRefresh && GraphCache.hasValidCache(cacheKey)) {
        const cached = GraphCache.get(cacheKey);
        deserializeGraph(cached);
        return;
    }
    
    // Otherwise, fetch from server (existing two-phase load)
    await fetchAndRenderGraph(minDegree);
    
    // Cache the result
    GraphCache.set(cacheKey, serializeGraph());
    GraphSettings.save();
}
```

### Backend Cache Invalidation

The backend already has `_graph_cache` keyed by file mtimes. We should expose this to the frontend:

```javascript
// On page load, check if server cache changed
async function checkCacheValidity() {
    const serverCacheKey = await fetch('/api/graph/cache-key').then(r => r.json());
    const clientCacheKey = sessionStorage.getItem('mimir_server_cache_key');
    
    if (serverCacheKey !== clientCacheKey) {
        // Server data changed, invalidate client cache
        sessionStorage.removeItem('mimir_graph_cache');
        sessionStorage.setItem('mimir_server_cache_key', serverCacheKey);
        return true; // Needs refresh
    }
    return false; // Client cache valid
}
```

---

## Part 2: Float Mode Redesign (InfraNodus-Style)

### Inspiration

The current "floating mode" is a physics simulation toggle. The redesign transforms it into a **contextual information overlay** inspired by InfraNodus:

**InfraNodus characteristics**:
- Full-screen graph visualization
- Floating overlay panels with contextual information
- Text/graph integration (showing relevant text passages alongside graph nodes)
- Ecological thinking metaphor: overview + zoom + gaps + connections
- Knowledge graph as "mind antivirus" against narrow thinking

### Proposed Design

```
┌─────────────────────────────────────────────────────────────────┐
│  Mimir Knowledge Graph                                    [≡]   │  ← Minimal header
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│   ┌───────────────────────────────────────────────────────────┐  │
│   │                                                           │  │
│   │                    GRAPH VISUALIZATION                    │  │  ← Full-screen Cytoscape
│   │                   (nodes + connections)                   │  │
│   │                                                           │  │
│   │                                                           │  │
│   │                                                           │  │
│   │                                                           │  │
│   └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────┐  ┌──────────────────────────────────────┐   │
│  │  CONTROLS      │  │  CONTEXT PANEL (Float Mode)          │   │  ← Floating overlays
│  │  ─────────     │  │  ─────────────────────────           │   │
│  │  ○ Filters     │  │                                      │   │
│  │  ○ Layout      │  │  "Ecological thinking..."            │   │
│  │  ○ Settings    │  │                                      │   │
│  │                │  │  Selected node context               │   │
│  │  [Min: 2]      │  │  Related insights                    │   │
│  │                │  │                                      │   │
│  └────────────────┘  └──────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  INSIGHTS: This cluster shows 3 related topics...         │   │  ← Bottom insight bar
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Float Mode Features

When float mode is activated:

1. **Minimalist UI**: Sidebar collapses to floating controls
2. **Context Panel**: Replaces detail panel with richer contextual information:
   - Node descriptions/excerpts from source documents
   - "Ecological thinking" insights about the discourse
   - Gap analysis (what's missing in the knowledge graph)
   - Related topics and bridging concepts
3. **Graph-as-Overlay**: Graph becomes the primary visual, UI floats above
4. **Text Integration**: Clicking a node shows relevant text excerpts

### Implementation Sketch

```css
/* Float mode styles */
.float-mode .container {
    position: relative;
}

.float-mode .sidebar {
    position: absolute;
    left: 20px;
    top: 70px;
    width: 280px;
    background: rgba(30, 41, 59, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 12px;
    border: 1px solid rgba(51, 65, 85, 0.5);
    z-index: 100;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
}

.float-mode .context-panel {
    position: absolute;
    right: 20px;
    top: 70px;
    width: 350px;
    background: rgba(30, 41, 59, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 12px;
    border: 1px solid rgba(51, 65, 85, 0.5);
    z-index: 100;
    padding: 20px;
}

.float-mode .insights-bar {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(30, 41, 59, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 8px;
    border: 1px solid rgba(51, 65, 85, 0.5);
    padding: 12px 24px;
    z-index: 100;
    max-width: 80%;
}

.float-mode #graph-container {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 1;
}
```

```javascript
function toggleFloatMode() {
    floatingMode = !floatingMode;
    document.body.classList.toggle('float-mode', floatingMode);
    
    if (floatingMode) {
        // Start physics simulation
        startFloatingPhysics();
        // Show context panel
        showContextPanel();
        // Hide traditional sidebar elements
        document.querySelector('.sidebar').classList.add('floating');
    } else {
        stopFloatingPhysics();
        hideContextPanel();
        document.querySelector('.sidebar').classList.remove('floating');
    }
    
    GraphSettings.save();
}

function showContextPanel() {
    const panel = document.getElementById('contextPanel');
    panel.innerHTML = `
        <h3>Ecological Thinking</h3>
        <p class="context-intro">
            This knowledge graph visualizes your codebase as an ecology of ideas. 
            Words are nodes, connections are relationships.
        </p>
        <div class="context-stats">
            <div class="stat">
                <span class="stat-num">${cy.nodes().length}</span>
                <span class="stat-label">concepts</span>
            </div>
            <div class="stat">
                <span class="stat-num">${cy.edges().length}</span>
                <span class="stat-label">connections</span>
            </div>
        </div>
        <div class="context-insights">
            <h4>Insights</h4>
            <p>${generateInsight()}</p>
        </div>
    `;
    panel.classList.add('visible');
}
```

### Context Panel Content

The context panel would show:

1. **Overview Stats**: Total nodes, edges, clusters
2. **Selected Node Context**: If a node is selected, show:
   - Excerpt from source document
   - Incoming/outgoing connection summary
   - "This concept bridges X and Y topics"
3. **Gap Analysis**: "No connections between [module A] and [module B]"
4. **Topic Clusters**: Auto-detected clusters with summaries
5. **Ecological Insight**: Dynamic insight based on graph structure

```javascript
function generateInsight() {
    const nodes = cy.nodes();
    const edges = cy.edges();
    
    // Find clusters using community detection
    const clusters = detectClusters();
    
    // Find bridging nodes (high betweenness)
    const bridges = findBridgingNodes();
    
    // Find gaps (disconnected components)
    const gaps = findDisconnectedComponents();
    
    return `
        This discourse contains ${clusters.length} topical clusters.
        ${bridges.length > 0 
            ? `"${bridges[0].label()}" serves as a key intermediary concept.` 
            : 'No clear bridging concepts detected.'}
        ${gaps.length > 1 
            ? `There are ${gaps.length} disconnected areas that may benefit from conceptual bridges.` 
            : 'The discourse appears well-connected.'}
    `;
}
```

---

## Implementation Phases

### Phase 1: Settings Persistence (Quick Win)

1. Add `sessionStorage` wrapper for settings
2. Save settings on every change
3. Restore settings on page load
4. Add cache-key endpoint to backend for invalidation

**Files to modify**:
- `web/server.py` (add `/api/graph/cache-key` endpoint)
- `web/server.py` `_GRAPH_HTML` JavaScript (settings persistence)

### Phase 2: Graph Render Caching

1. Implement `GraphCache` with Cytoscape JSON serialization
2. Cache invalidation based on server cache key
3. Background refresh when cache expires

### Phase 3: Float Mode Redesign

1. Create new CSS for float mode overlay UI
2. Implement context panel with insights
3. Add text excerpt integration
4. Create ecological thinking insights generator
5. Redesign controls as floating panels

### Phase 4: Advanced Features

1. **Graph Diff**: Show what changed since last visit
2. **Time Travel**: View graph at different points in time
3. **Collaborative Annotations**: Add notes to nodes
4. **Export**: Save graph state as JSON/image

---

## Technical Considerations

### Performance

- **SessionStorage limit**: ~5MB, sufficient for settings + cached graph
- **Cytoscape JSON size**: For 1000 nodes/edges, ~500KB
- **Cache strategy**: LRU eviction if storage full

### Browser Compatibility

- `sessionStorage`: All modern browsers
- `backdrop-filter`: Chrome 76+, Firefox 103+, Safari 9+
- CSS Grid/Flexbox: Universal support

### Security

- No sensitive data in client storage
- Cache keys are non-sensitive mtimes
- XSS prevention via text sanitization for excerpts

---

## UI Mockup Reference

The target UI should resemble:

![InfraNodus-style graph with contextual overlay](https://miro.medium.com/v2/resize:fit:1400/1*InCp5bzenJcxZVB0AHcv6Q.png)

**Key elements**:
- Full-bleed graph visualization
- Glassmorphism overlay panels
- Minimal chrome
- Contextual information integrated with graph
- Focus on knowledge discovery and insights

---

## Future Enhancements

### Graph Analytics

- **Centrality metrics**: Highlight most influential files/modules
- **Clustering**: Auto-detect and color-code topic clusters
- **Temporal analysis**: Show evolution over time
- **Impact analysis**: "If you change X, Y and Z are affected"

### AI Integration

- **Smart insights**: "This module is a hub with high betweenness"
- **Gap suggestions**: "Consider adding documentation for [topic]"
- **Semantic search**: "Find code related to authentication"
- **Auto-summaries**: Generate module descriptions from code

---

## Conclusion

This plan addresses the core issues:

1. **Settings Persistence**: Tab navigation won't lose user preferences
2. **Graph Caching**: Fast re-renders without waiting for data fetching
3. **Float Mode Redesign**: Transforms from a physics toggle into a rich, contextual overlay that promotes "ecological thinking" about the codebase

The implementation can be done incrementally, with Phase 1 delivering immediate value while Phase 3 creates the distinctive InfraNodus-inspired experience.

---

*Created: April 2026*
*Status: Planning phase - ready for implementation*
