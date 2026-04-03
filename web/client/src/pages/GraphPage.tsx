import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import cytoscape from 'cytoscape';

import { useGraphSettings } from '../hooks/useGraphSettings';
import { useGraphCache } from '../hooks/useGraphCache';
import { registerExtensions, cytoscapeStyle, layoutOptions } from '../lib/cytoscapeSetup';
import { PhysicsEngine } from '../lib/physics';
import { computeInsights } from '../lib/insights';

import Sidebar from '../components/Sidebar';
import ModuleSidebar from '../components/ModuleSidebar';
import ContextPanel from '../components/ContextPanel';
import ResultsPanel from '../components/ResultsPanel';

import {
  GraphNode,
  GraphEdge,
  InsightData,
  ResultsState,
} from '../types';

import styles from './GraphPage.module.css';

registerExtensions();

// ── Helpers ───────────────────────────────────────────────────────────────────

function updateNodeSizes(cy: cytoscape.Core) {
  cy.nodes().forEach(node => {
    const deg = node.degree();
    const size = Math.min(120, 40 + deg * 8);
    node.style({ width: size, height: size });
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function GraphPage() {
  const cyContainerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const physicsRef = useRef<PhysicsEngine | null>(null);

  const [settings, updateSettings] = useGraphSettings();
  const graphCache = useGraphCache();

  // Loading state
  const [loadingNodes, setLoadingNodes] = useState(true);
  const [loadingEdges, setLoadingEdges] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Selected node state
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedDegree, setSelectedDegree] = useState(0);
  const [selectedOutEdges, setSelectedOutEdges] = useState<{ targetId: string; targetLabel: string; type: string }[]>([]);
  const [selectedInEdges, setSelectedInEdges] = useState<{ sourceId: string; sourceLabel: string; type: string }[]>([]);

  // Panels
  const [insights, setInsights] = useState<InsightData | null>(null);
  const [results, setResults] = useState<ResultsState>({
    visible: false, title: '', type: 'search', items: [],
  });

  // ── Cytoscape init ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!cyContainerRef.current) return;

    const cy = cytoscape({
      container: cyContainerRef.current,
      style: cytoscapeStyle,
      userZoomingEnabled: true,
      userPanningEnabled: true,
    });
    cyRef.current = cy;
    physicsRef.current = new PhysicsEngine(cy);

    cy.on('tap', 'node', evt => {
      const node = evt.target as cytoscape.NodeSingular;
      handleNodeTap(node);
    });

    cy.on('tap', evt => {
      if (evt.target === cy) {
        setSelectedNode(null);
        cy.elements().removeClass('highlighted dimmed');
      }
    });

    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedNode(null);
        cy.elements().removeClass('highlighted dimmed');
      }
    };
    document.addEventListener('keydown', keyHandler);

    return () => {
      document.removeEventListener('keydown', keyHandler);
      physicsRef.current?.stop();
      cy.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Physics sync ────────────────────────────────────────────────────────────
  useEffect(() => {
    const engine = physicsRef.current;
    if (!engine) return;
    if (settings.floatingMode) {
      engine.start(settings.repulsionStrength);
    } else {
      engine.stop();
    }
  }, [settings.floatingMode, settings.repulsionStrength]);

  // ── Insights recompute when float mode opens ─────────────────────────────
  useEffect(() => {
    if (settings.floatingMode && cyRef.current) {
      setInsights(computeInsights(cyRef.current));
    }
  }, [settings.floatingMode]);

  // ── Edge visibility sync ─────────────────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const f = settings.edgeFilters;
    cy.edges().forEach(edge => {
      const t = edge.data('type') as string;
      const show =
        (t === 'calls' && f.calls) ||
        (t === 'imports_module' && f.imports_module) ||
        (t === 'imports_from' && f.imports_from) ||
        (t === 'inherits_from' && f.inherits_from) ||
        !['calls', 'imports_module', 'imports_from', 'inherits_from'].includes(t);
      show ? edge.show() : edge.hide();
    });
  }, [settings.edgeFilters]);

  // ── Labels sync ─────────────────────────────────────────────────────────
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.style()
      .selector('node')
      .style('label', settings.labelsVisible ? (ele: cytoscape.NodeSingular) => {
        const label = ele.data('label') as string;
        const meta = (ele.data('metadata') ?? {}) as { total_children?: number };
        return meta.total_children ? `${label} (${meta.total_children})` : label;
      } : '')
      .selector('edge')
      .style('label', settings.labelsVisible ? 'data(label)' : '')
      .update();
  }, [settings.labelsVisible]);

  // ── Graph load ────────────────────────────────────────────────────────────
  const loadGraph = useCallback(
    async (minDegree: number, forceRefresh = false) => {
      const cy = cyRef.current;
      if (!cy) return;

      setLoadingNodes(true);
      setLoadError(null);

      try {
        // Check server-side cache validity
        const serverChanged = await graphCache.checkServerKey();

        // Try client cache first (unless forced or server changed)
        if (!forceRefresh && !serverChanged) {
          const cached = graphCache.get(minDegree, settings.layout);
          if (cached) {
            cy.elements().remove();
            cy.add(cached.nodes.map((n: GraphNode) => ({ data: n })));
            cy.add(cached.edges.map((e: GraphEdge) => ({ data: e })));
            if (cached.viewport) {
              cy.viewport(cached.viewport);
            }
            updateNodeSizes(cy);
            applyEdgeVisibility(cy, settings.edgeFilters);
            setLoadingNodes(false);
            return;
          }
        }

        // Phase 1: nodes
        const nodesRes = await fetch(`/api/graph?mode=summary&min_degree=${minDegree}`);
        if (!nodesRes.ok) throw new Error(await nodesRes.text());
        const nodesData = await nodesRes.json();

        cy.elements().remove();
        if (nodesData.nodes.length > 0) {
          cy.add(nodesData.nodes.map((n: GraphNode) => ({ data: n })));
          cy.layout(layoutOptions(settings.layout)).run();
        }
        setLoadingNodes(false);

        if (nodesData.nodes.length === 0) return;

        // Phase 2: edges in background
        setLoadingEdges(true);
        try {
          const edgesRes = await fetch(`/api/graph/edges?min_degree=${minDegree}`);
          if (edgesRes.ok) {
            const edgesData = await edgesRes.json();
            const nodeIds = new Set(cy.nodes().map(n => n.id()));
            const valid: GraphEdge[] = edgesData.edges.filter(
              (e: GraphEdge) => nodeIds.has(e.source) && nodeIds.has(e.target)
            );
            if (valid.length > 0) {
              cy.batch(() => cy.add(valid.map(e => ({ data: e }))));
              applyEdgeVisibility(cy, settings.edgeFilters);
              updateNodeSizes(cy);
            }

            // Persist to client cache
            graphCache.set(minDegree, settings.layout, {
              nodes: nodesData.nodes,
              edges: valid,
              viewport: { zoom: cy.zoom(), pan: cy.pan() },
            });
          }
        } finally {
          setLoadingEdges(false);
        }

        // Update insights if float mode is open
        if (settings.floatingMode) setInsights(computeInsights(cy));
      } catch (err) {
        setLoadingNodes(false);
        setLoadError(String(err));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [settings.layout, settings.edgeFilters, settings.floatingMode]
  );

  // Initial load
  useEffect(() => {
    loadGraph(settings.minDegree);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Node tap ─────────────────────────────────────────────────────────────
  function handleNodeTap(node: cytoscape.NodeSingular) {
    const cy = cyRef.current!;
    cy.elements().removeClass('highlighted dimmed');
    const out = node.outgoers('edge');
    out.addClass('highlighted');
    out.targets().addClass('highlighted');
    cy.elements().not(node).not(out).not(out.targets()).addClass('dimmed');

    const nodeData = node.data() as GraphNode;
    setSelectedNode(nodeData);
    setSelectedDegree(node.degree());
    setSelectedOutEdges(
      node.outgoers('edge').map(e => ({
        targetId: e.target().id(),
        targetLabel: e.target().data('label') as string,
        type: e.data('type') as string,
      }))
    );
    setSelectedInEdges(
      node.incomers('edge').map(e => ({
        sourceId: e.source().id(),
        sourceLabel: e.source().data('label') as string,
        type: e.data('type') as string,
      }))
    );

    if (settings.floatingMode) setInsights(computeInsights(cy));
  }

  // ── Focus node (from panels) ─────────────────────────────────────────────
  const focusNode = (id: string) => {
    const cy = cyRef.current;
    if (!cy) return;
    const node = cy.getElementById(id);
    if (node.length) {
      cy.animate({ center: { eles: node }, zoom: 1.3 }, { duration: 300 });
      handleNodeTap(node);
    }
  };

  // ── Layout ────────────────────────────────────────────────────────────────
  const applyLayout = (name: string) => {
    updateSettings({ layout: name });
    cyRef.current?.layout(layoutOptions(name)).run();
  };

  // ── Search / Query ────────────────────────────────────────────────────────
  const handleSearch = async (query: string) => {
    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 10 }),
      });
      const items = await res.json();
      setResults({ visible: true, title: `Search: "${query}"`, type: 'search', items });
    } catch (err) {
      setResults({ visible: true, title: 'Error', type: 'search', items: [{ title: 'Error', snippet: String(err), source: '' }] });
    }
  };

  const handleQuery = async (question: string) => {
    setResults({ visible: true, title: 'AI response', type: 'query', items: [], query: question });
    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Server error ${res.status}: ${errorText}`);
      }
      const data = await res.json();
      if (data.detail) {
        throw new Error(data.detail);
      }
      setResults({ visible: true, title: 'AI response', type: 'query', items: [{ title: 'Answer', snippet: data.answer ?? 'No answer received', source: '' }], query: question });
    } catch (err) {
      console.error('Query error:', err);
      setResults({ visible: true, title: 'Error', type: 'query', items: [{ title: 'Error', snippet: String(err), source: '' }], query: question });
    }
  };

  const toggleResults = () => {
    setResults(r => ({ ...r, visible: !r.visible }));
  };

  const highlightSearchResult = (source: string) => {
    if (!source || !cyRef.current) return;
    const cy = cyRef.current;
    const matched = cy.nodes().filter(n => {
      const fp = (n.data('metadata') as { file_path?: string })?.file_path ?? '';
      return fp.includes(source) || n.data('label') === source;
    });
    if (matched.length) {
      cy.animate({ center: { eles: matched[0] }, zoom: 1.3 }, { duration: 300 });
      handleNodeTap(matched[0]);
    }
  };

  return (
    <div className={`${styles.root} ${settings.floatingMode ? styles.floatMode : ''}`}>
      {/* ── Sidebar ───────────────────────────────────────────────────────── */}
      <Sidebar
        settings={settings}
        onSettingsChange={updateSettings}
        onSearch={handleSearch}
        onQuery={handleQuery}
        onLayoutChange={applyLayout}
        onFit={() => cyRef.current?.fit()}
        onReset={() => { cyRef.current?.reset(); cyRef.current?.center(); }}
        onToggleLabels={() => updateSettings({ labelsVisible: !settings.labelsVisible })}
        onApplyDegree={() => loadGraph(settings.minDegree, true)}
        floating={settings.floatingMode}
      />

      {/* ── Main canvas ──────────────────────────────────────────────────── */}
      <div className={styles.main}>
        {/* Toolbar */}
        <div className={styles.toolbar}>
          <button className={styles.toolbarBtn} onClick={() => loadGraph(settings.minDegree, true)}>
            Refresh
          </button>
          <button 
            className={`${styles.toolbarBtn} ${results.visible ? styles.active : ''}`}
            onClick={toggleResults}
          >
            {results.visible ? 'Hide AI Results' : 'Show AI Results'}
          </button>
          <button className={styles.toolbarBtn} onClick={() => {
            setSelectedNode(null);
            cyRef.current?.elements().removeClass('highlighted dimmed');
          }}>
            Clear selection
          </button>
          <Link to="/metrics" className={styles.metricsLink}>
            Metrics
          </Link>
          {loadingEdges && (
            <span className={styles.edgeBadge}>Loading relationships…</span>
          )}
        </div>

        {/* Graph container */}
        <div className={styles.graphContainer}>
          <div ref={cyContainerRef} className={styles.cy} />

          {/* Loading overlay — only shown during initial node load */}
          {loadingNodes && (
            <div className={styles.loadingOverlay}>
              <div className={styles.loadingSpinner} />
              <div className={styles.loadingText}>
                {loadError ?? 'Loading nodes…'}
              </div>
            </div>
          )}
        </div>

        {/* Float mode overlays */}
        <ContextPanel
          visible={settings.floatingMode}
          insights={insights}
          selectedNode={selectedNode}
        />

        {/* Module detail sidebar */}
        <ModuleSidebar
          node={selectedNode}
          degree={selectedDegree}
          outEdges={selectedOutEdges}
          inEdges={selectedInEdges}
          onClose={() => setSelectedNode(null)}
          onFocusNode={focusNode}
        />

        {/* Results panel */}
        <ResultsPanel
          state={results}
          onClose={() => setResults(r => ({ ...r, visible: false }))}
          onHighlight={highlightSearchResult}
        />
      </div>
    </div>
  );
}

// ── Pure helpers ─────────────────────────────────────────────────────────────

function applyEdgeVisibility(
  cy: cytoscape.Core,
  filters: { calls: boolean; imports_module: boolean; imports_from: boolean; inherits_from: boolean }
) {
  cy.edges().forEach(edge => {
    const t = edge.data('type') as string;
    const show =
      (t === 'calls' && filters.calls) ||
      (t === 'imports_module' && filters.imports_module) ||
      (t === 'imports_from' && filters.imports_from) ||
      (t === 'inherits_from' && filters.inherits_from) ||
      !['calls', 'imports_module', 'imports_from', 'inherits_from'].includes(t);
    show ? edge.show() : edge.hide();
  });
}
